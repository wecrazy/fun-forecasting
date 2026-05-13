"""Forecasting engine: XGBoost + SARIMAX ensemble."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import optuna
import pandas as pd
import xgboost as xgb
from sklearn.compose import ColumnTransformer
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from statsmodels.tsa.statespace.sarimax import SARIMAX

from gpu_utils import get_xgb_tree_method

optuna.logging.set_verbosity(optuna.logging.WARNING)


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
    history_tail: List[Dict] = field(default_factory=list)


def _rmse(y_true, y_pred) -> float:
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def _build_xgb_pipeline(cat_cols: List[str], num_cols: List[str], params: dict, tree_method: str) -> Pipeline:
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


def _fit_with_gpu_fallback(pipe: Pipeline, X: pd.DataFrame, y: np.ndarray) -> Pipeline:
    try:
        pipe.fit(X, y)
        return pipe
    except Exception:
        model = pipe.named_steps["model"]
        if getattr(model, "tree_method", None) == "gpu_hist":
            params = model.get_xgb_params()
            params["tree_method"] = "hist"
            params["n_estimators"] = model.n_estimators

            pre = pipe.named_steps["pre"]
            cpu_model = xgb.XGBRegressor(
                **params,
                random_state=42,
                verbosity=0,
                eval_metric="rmse",
            )
            cpu_pipe = Pipeline([("pre", pre), ("model", cpu_model)])
            cpu_pipe.fit(X, y)
            return cpu_pipe
        raise


def tune_xgb(
    df: pd.DataFrame,
    feature_cols: List[str],
    y_col: str = "y",
    trials: int = 60,
    cv_splits: int = 5,
) -> Tuple[Pipeline, Dict[str, float]]:
    """Tune XGBoost with Optuna and walk-forward CV."""
    X = df[feature_cols].copy()
    y = df[y_col].astype(float).values

    cat_cols = [c for c in feature_cols if str(X[c].dtype) in ("object", "category")]
    cat_cols.extend([c for c in ("dow", "dom", "month") if c in feature_cols and c not in cat_cols])
    num_cols = [c for c in feature_cols if c not in cat_cols]

    tree_method = get_xgb_tree_method()
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
        pipe = _build_xgb_pipeline(cat_cols, num_cols, params, tree_method)
        rmses = []
        for train_idx, test_idx in tscv.split(X):
            fitted = _fit_with_gpu_fallback(pipe, X.iloc[train_idx], y[train_idx])
            rmses.append(_rmse(y[test_idx], fitted.predict(X.iloc[test_idx])))
        return float(np.mean(rmses))

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=trials, show_progress_bar=False)

    best_pipe = _build_xgb_pipeline(cat_cols, num_cols, study.best_params, tree_method)
    best_pipe = _fit_with_gpu_fallback(best_pipe, X, y)
    resid_std = float(np.std(y - best_pipe.predict(X), ddof=1))

    return best_pipe, {"xgb_cv_rmse": float(study.best_value), "xgb_resid_std": resid_std}


def fit_sarimax(
    df: pd.DataFrame,
    y_col: str = "y",
    exog_cols: Optional[List[str]] = None,
) -> Tuple[object, Dict[str, float]]:
    """Fit SARIMAX model."""
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
    """Generate iterative multi-day forecasts."""
    df = df_feat.copy()
    last_row = df.iloc[-1].copy()
    last_date = pd.to_datetime(last_row["date"])

    history_rets = df["ret1"].astype(float).values.tolist()
    history_logp = df["log_price"].astype(float).values.tolist()
    current_logp = history_logp[-1]

    preds: List[Dict] = []

    def roll_mean(arr, w):
        return float(np.mean(arr[-w:])) if len(arr) >= w else float(np.mean(arr))

    def roll_std(arr, w):
        window = arr[-w:] if len(arr) >= w else arr
        return float(np.std(window, ddof=1)) if len(window) > 1 else 0.0

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
                float(current_logp - history_logp[-(w + 1)]) if len(history_logp) > w else float(current_logp - history_logp[0])
            )

        x_input = pd.DataFrame([feat_row[feature_cols].to_dict()])
        xgb_ret = float(xgb_pipe.predict(x_input)[0])

        if exog_cols_for_sarimax:
            ex = np.array([feat_row[c] for c in exog_cols_for_sarimax], dtype=float).reshape(1, -1)
            sar_ret = float(sarimax_model.forecast(steps=1, exog=ex)[0])
        else:
            sar_ret = float(sarimax_model.forecast(steps=1)[0])

        ens_ret = 0.5 * xgb_ret + 0.5 * sar_ret
        current_logp = float(current_logp + ens_ret)
        price = float(np.exp(current_logp))

        ci_band = float(resid_std * np.sqrt(i))
        upper = float(np.exp(current_logp + ci_band))
        lower = float(np.exp(current_logp - ci_band))

        if currency.lower() == "idr":
            price_idr = price
            price_usd = price / usd_idr_rate if usd_idr_rate > 0 else None
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


def run_forecast(
    df_feat: pd.DataFrame,
    coin_id: str,
    vs_currency: str,
    horizon_days: int,
    optuna_trials: int = 60,
    usd_idr_rate: float = 1.0,
) -> ForecastResult:
    """Train ensemble and return forecast payload."""
    drop_cols = {"y", "date", "price", "mcap", "volume"}
    feature_cols = [c for c in df_feat.columns if c not in drop_cols]

    xgb_pipe, diag_xgb = tune_xgb(df_feat, feature_cols, trials=optuna_trials, cv_splits=5)

    exog_candidates = (
        "ret_mean_7",
        "ret_std_14",
        "mom_14",
        "log_vol",
        "log_mcap",
        "vol_mcap_ratio",
        "btc_ret1",
        "eth_ret1",
        "rsi_14",
        "macd_diff",
    )
    exog_cols = [c for c in exog_candidates if c in df_feat.columns]
    sar_model, diag_sar = fit_sarimax(df_feat, exog_cols=exog_cols or None)

    resid_std = (diag_xgb["xgb_resid_std"] + diag_sar["sarimax_resid_std"]) / 2.0

    predictions = iterative_forecast(
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

    last_row = df_feat.iloc[-1]
    last_price = float(last_row["price"])
    last_price_idr = last_price if vs_currency.lower() == "idr" else last_price * usd_idr_rate

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
        last_date=str(pd.to_datetime(last_row["date"]).date()),
        last_price=last_price,
        last_price_idr=last_price_idr,
        predictions=predictions,
        diagnostics={
            **diag_xgb,
            **diag_sar,
            "rows_used": float(len(df_feat)),
            "usd_idr_rate": float(usd_idr_rate),
        },
        history_tail=history_tail,
    )
