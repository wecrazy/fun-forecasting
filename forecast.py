"""
forecast.py — Forecasting engine: XGBoost (Optuna-tuned) + SARIMAX ensemble.

Features:
  • GPU auto-detection via gpu_utils
  • Walk-forward CV with Optuna hyperparameter search
  • SARIMAX on log-returns with exogenous regressors
  • Ensemble = weighted average XGB + SARIMAX
  • Confidence intervals (±1 std of training residuals)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import optuna
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_squared_error
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline

import xgboost as xgb
from statsmodels.tsa.statespace.sarimax import SARIMAX

from gpu_utils import get_xgb_tree_method

optuna.logging.set_verbosity(optuna.logging.WARNING)


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ForecastResult:
    coin_id: str
    vs_currency: str
    horizon_days: int
    last_date: str
    last_price: float
    last_price_idr: Optional[float]
    predictions: List[Dict]
    diagnostics: Dict[str, float]
    history_tail: List[Dict] = field(default_factory=list)  # last 90 days of actuals


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _rmse(y_true, y_pred) -> float:
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def _build_xgb_pipeline(cat_cols: List[str], num_cols: List[str], params: dict) -> Pipeline:
    tree_method = get_xgb_tree_method()
    pre = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat_cols),
            ("num", "passthrough", num_cols),
        ],
        remainder="drop",
    )
    model = xgb.XGBRegressor(
        **{k: v for k, v in params.items() if k != "n_estimators"},
        n_estimators=params.get("n_estimators", 2000),
        random_state=42,
        tree_method=tree_method,
        verbosity=0,
        eval_metric="rmse",
    )
    return Pipeline([("pre", pre), ("model", model)])


# ─────────────────────────────────────────────────────────────────────────────
# XGBoost Optuna tuning
# ─────────────────────────────────────────────────────────────────────────────

def tune_xgb(
    df: pd.DataFrame,
    feature_cols: List[str],
    y_col: str = "y",
    trials: int = 60,
    cv_splits: int = 5,
) -> Tuple[Pipeline, Dict[str, float]]:
    """Optuna + walk-forward CV tuning for XGBoost."""
    X = df[feature_cols].copy()
    y = df[y_col].astype(float).values

    cat_cols = [c for c in feature_cols if c in ("dow", "dom", "month")]
    num_cols = [c for c in feature_cols if c not in cat_cols]

    tscv = TimeSeriesSplit(n_splits=cv_splits)

    def objective(trial: optuna.Trial) -> float:
        params = {
            "max_depth": trial.suggest_int("max_depth", 2, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.15, log=True),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "min_child_weight": trial.suggest_float("min_child_weight", 0.5, 10.0, log=True),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 1.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
            "gamma": trial.suggest_float("gamma", 0.0, 2.0),
            "n_estimators": trial.suggest_int("n_estimators", 800, 3500),
        }
        pipe = _build_xgb_pipeline(cat_cols, num_cols, params)
        rmses = []
        for train_idx, test_idx in tscv.split(X):
            pipe.fit(X.iloc[train_idx], y[train_idx])
            rmses.append(_rmse(y[test_idx], pipe.predict(X.iloc[test_idx])))
        return float(np.mean(rmses))

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=trials, show_progress_bar=False)

    best = study.best_params
    pipe = _build_xgb_pipeline(cat_cols, num_cols, best)
    pipe.fit(X, y)

    # Residual std for confidence intervals
    resid_std = float(np.std(y - pipe.predict(X), ddof=1))

    return pipe, {"xgb_cv_rmse": float(study.best_value), "xgb_resid_std": resid_std}


# ─────────────────────────────────────────────────────────────────────────────
# SARIMAX
# ─────────────────────────────────────────────────────────────────────────────

def fit_sarimax(
    df: pd.DataFrame,
    y_col: str = "y",
    exog_cols: Optional[List[str]] = None,
) -> Tuple[object, Dict[str, float]]:
    y = df[y_col].astype(float).values
    exog = df[exog_cols].astype(float).values if exog_cols else None
    model = SARIMAX(
        y,
        exog=exog,
        order=(2, 0, 2),
        enforce_stationarity=False,
        enforce_invertibility=False,
    ).fit(disp=False)
    resid_std = float(np.std(model.resid, ddof=1))
    return model, {"sarimax_aic": float(model.aic), "sarimax_resid_std": resid_std}


# ─────────────────────────────────────────────────────────────────────────────
# Iterative forecasting
# ─────────────────────────────────────────────────────────────────────────────

def iterative_forecast(
    df_feat: pd.DataFrame,
    feature_cols: List[str],
    xgb_pipe: Pipeline,
    sarimax_model,
    exog_cols_for_sarimax: Optional[List[str]],
    horizon_days: int,
    resid_std: float,
    usd_idr_rate: float = 1.0,
    currency: str = "usd",
) -> List[Dict]:
    """
    Predict next-day returns iteratively.
    Ensemble = 0.5 × XGB + 0.5 × SARIMAX.
    Returns list of dicts with predicted price in requested currency + IDR equivalent.
    """
    df = df_feat.copy()
    last_row = df.iloc[-1].copy()
    last_date = pd.to_datetime(last_row["date"])

    history_rets = df["ret1"].astype(float).values.tolist()
    history_logp = df["log_price"].astype(float).values.tolist()
    current_logp = history_logp[-1]

    # last actual price in the requested currency
    last_price_native = float(last_row["price"])

    preds = []

    def roll_mean(arr, w):
        return float(np.mean(arr[-w:])) if len(arr) >= w else float(np.mean(arr))

    def roll_std(arr, w):
        return float(np.std(arr[-w:], ddof=1)) if len(arr) >= w else float(np.std(arr, ddof=1))

    for i in range(1, horizon_days + 1):
        next_date = last_date + pd.Timedelta(days=i)

        feat_row = last_row.copy()
        feat_row["date"] = next_date
        feat_row["dow"] = next_date.dayofweek
        feat_row["dom"] = next_date.day
        feat_row["month"] = next_date.month

        for w in (3, 7, 14, 30, 60):
            feat_row[f"ret_mean_{w}"] = roll_mean(history_rets, w)
            feat_row[f"ret_std_{w}"] = roll_std(history_rets, w)
            feat_row[f"mom_{w}"] = (
                float(current_logp - history_logp[-(w + 1)])
                if len(history_logp) > w
                else float(current_logp - history_logp[0])
            )

        X_feat = pd.DataFrame([feat_row[feature_cols].to_dict()])
        xgb_ret = float(xgb_pipe.predict(X_feat)[0])

        if exog_cols_for_sarimax:
            ex = np.array([feat_row[c] for c in exog_cols_for_sarimax], dtype=float).reshape(1, -1)
            sar_ret = float(sarimax_model.forecast(steps=1, exog=ex)[0])
        else:
            sar_ret = float(sarimax_model.forecast(steps=1)[0])

        ens_ret = 0.5 * xgb_ret + 0.5 * sar_ret
        current_logp = float(current_logp + ens_ret)
        price = float(np.exp(current_logp))

        # Confidence interval (±1 std of residuals, propagated)
        ci_band = float(resid_std * np.sqrt(i))
        upper = float(np.exp(current_logp + ci_band))
        lower = float(np.exp(current_logp - ci_band))

        # IDR price
        if currency.lower() == "idr":
            price_idr = price
            price_usd = price / usd_idr_rate if usd_idr_rate > 1 else None
        else:
            price_usd = price
            price_idr = price * usd_idr_rate

        preds.append(
            {
                "date": next_date.strftime("%Y-%m-%d"),
                "predicted_price": price,
                "predicted_price_usd": price_usd,
                "predicted_price_idr": price_idr,
                "predicted_return": ens_ret,
                "upper_bound": upper,
                "lower_bound": lower,
            }
        )

        history_rets.append(ens_ret)
        history_logp.append(current_logp)
        last_row = feat_row

    return preds


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_forecast(
    df_feat: pd.DataFrame,
    coin_id: str,
    vs_currency: str,
    horizon_days: int,
    optuna_trials: int = 60,
    usd_idr_rate: float = 1.0,
) -> ForecastResult:
    drop = {"y", "date", "price", "mcap", "volume"}
    feature_cols = [c for c in df_feat.columns if c not in drop]

    xgb_pipe, diag_xgb = tune_xgb(df_feat, feature_cols, trials=optuna_trials, cv_splits=5)

    exog_candidates = (
        "ret_mean_7", "ret_std_14", "mom_14",
        "log_vol", "log_mcap", "vol_mcap_ratio",
        "btc_ret1", "eth_ret1",
        "rsi_14", "macd_diff",
    )
    exog_cols = [c for c in exog_candidates if c in df_feat.columns]
    sar_model, diag_sar = fit_sarimax(df_feat, exog_cols=exog_cols or None)

    resid_std = (diag_xgb["xgb_resid_std"] + diag_sar["sarimax_resid_std"]) / 2.0

    preds = iterative_forecast(
        df_feat,
        feature_cols,
        xgb_pipe,
        sar_model,
        exog_cols or None,
        horizon_days,
        resid_std=resid_std,
        usd_idr_rate=usd_idr_rate,
        currency=vs_currency,
    )

    last = df_feat.iloc[-1]
    last_price = float(last["price"])
    last_price_idr = last_price * usd_idr_rate if vs_currency.lower() == "usd" else last_price

    # History tail (last 90 actual rows)
    tail = df_feat.tail(90).copy()
    history_tail = [
        {
            "date": str(r["date"].date() if hasattr(r["date"], "date") else r["date"])[:10],
            "price": float(r["price"]),
        }
        for _, r in tail.iterrows()
    ]

    return ForecastResult(
        coin_id=coin_id,
        vs_currency=vs_currency,
        horizon_days=horizon_days,
        last_date=str(pd.to_datetime(last["date"]).date()),
        last_price=last_price,
        last_price_idr=last_price_idr,
        predictions=preds,
        diagnostics={
            **diag_xgb,
            **diag_sar,
            "rows_used": float(len(df_feat)),
            "usd_idr_rate": usd_idr_rate,
        },
        history_tail=history_tail,
    )
