"""
pipeline/runner.py — Orchestrates the full forecasting pipeline.

Steps:
  1. Feature engineering (Polars fast path)
  2. Train all models concurrently (ProcessPoolExecutor)
  3. Iterative multi-step forecast for each model
  4. Ensemble via dynamic inverse-error weighting
  5. Build ForecastResult with per-model traces + confidence intervals
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Callable

import numpy as np
import pandas as pd

from app.tasks.pipeline.features import add_features
from app.tasks.pipeline.models.ensemble import compute_weights, ensemble_returns
from app.tasks.pipeline.models.xgboost_model import train_xgboost
from app.tasks.pipeline.models.sarimax_model import train_sarimax, predict_sarimax
from app.tasks.pipeline.models.prophet_model import train_prophet, predict_prophet
from app.tasks.pipeline.models.pytorch_model import train_lstm, predict_lstm

logger = logging.getLogger(__name__)

MIN_REQUIRED_ROWS = 120


# ─────────────────────────────────────────────────────────────────────────────
# Per-model iterative forecasters (return log-returns)
# ─────────────────────────────────────────────────────────────────────────────

def _xgb_iterative_forecast(
    df_feat: pd.DataFrame,
    feature_cols: list[str],
    xgb_pipe,
    horizon_days: int,
) -> list[float]:
    """Iteratively predict next-day log-returns with XGBoost."""
    df = df_feat.copy()
    last_row = df.iloc[-1].copy()
    last_date = pd.to_datetime(last_row["date"])
    history_rets = df["ret1"].astype(float).values.tolist()
    history_logp = df["log_price"].astype(float).values.tolist()
    current_logp = history_logp[-1]

    rets = []

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
        ret = float(xgb_pipe.predict(X_feat)[0])
        rets.append(ret)
        history_rets.append(ret)
        current_logp = float(current_logp + ret)
        history_logp.append(current_logp)
        last_row = feat_row

    return rets


def _build_price_series(
    last_logp: float,
    log_returns: list[float],
    last_date: pd.Timestamp,
    horizon_days: int,
    resid_std: float,
    usd_idr_rate: float,
    currency: str,
) -> list[dict[str, Any]]:
    """Convert a sequence of log-returns to a list of prediction dicts."""
    current_logp = last_logp
    results = []
    for i, ret in enumerate(log_returns, start=1):
        current_logp += ret
        price = float(np.exp(current_logp))
        ci_band = resid_std * np.sqrt(i)
        upper = float(np.exp(current_logp + ci_band))
        lower = float(np.exp(current_logp - ci_band))
        date = (last_date + pd.Timedelta(days=i)).strftime("%Y-%m-%d")

        if currency.lower() == "idr":
            price_idr = price
            price_usd = price / usd_idr_rate if usd_idr_rate > 1 else None
        else:
            price_usd = price
            price_idr = price * usd_idr_rate

        results.append(
            {
                "date": date,
                "predicted_price": price,
                "predicted_price_usd": price_usd,
                "predicted_price_idr": price_idr,
                "predicted_return": ret,
                "upper_bound": upper,
                "lower_bound": lower,
            }
        )
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Main runner
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline(
    df_main: pd.DataFrame,
    coin_id: str,
    currency: str,
    horizon_days: int,
    optuna_trials: int,
    usd_idr_rate: float,
    include_exog: bool = True,
    btc_df: pd.DataFrame | None = None,
    eth_df: pd.DataFrame | None = None,
    progress_cb: Callable[[str, float, str], None] | None = None,
) -> dict[str, Any]:
    """
    Run the complete forecasting pipeline.

    progress_cb(event_name, progress_0_to_1, message)
    Returns a dict compatible with ForecastResultOut.
    """

    def _emit(event: str, pct: float, msg: str) -> None:
        if progress_cb:
            try:
                progress_cb(event, pct, msg)
            except Exception:
                pass

    _emit("started", 0.02, "Starting feature engineering…")

    # ── Feature engineering ────────────────────────────────────────────────
    btc_arg = btc_df if include_exog else None
    eth_arg = eth_df if include_exog else None
    df_feat = add_features(df_main, btc_df=btc_arg, eth_df=eth_arg)

    if len(df_feat) < MIN_REQUIRED_ROWS:
        raise ValueError(
            f"Not enough feature rows ({len(df_feat)}). Minimum required: {MIN_REQUIRED_ROWS}."
        )
    _emit("features_done", 0.10, f"Feature engineering done: {len(df_feat)} rows")

    drop_cols = {"y", "date", "price", "mcap", "volume"}
    feature_cols = [c for c in df_feat.columns if c not in drop_cols]

    diagnostics: dict[str, Any] = {"rows_used": float(len(df_feat)), "usd_idr_rate": usd_idr_rate}

    # ── XGBoost ────────────────────────────────────────────────────────────
    _emit("xgb_started", 0.12, "Training XGBoost (Optuna tuning)…")

    def _xgb_progress(trial: int, total: int, rmse: float) -> None:
        pct = 0.12 + 0.35 * trial / total
        _emit("xgb_trial", pct, f"XGBoost trial {trial}/{total} — CV-RMSE {rmse:.6f}")

    xgb_pipe, diag_xgb = train_xgboost(
        df_feat, feature_cols, trials=optuna_trials, cv_splits=5, progress_cb=_xgb_progress
    )
    diagnostics.update(diag_xgb)
    _emit("xgb_done", 0.47, f"XGBoost done. CV-RMSE={diag_xgb['xgb_cv_rmse']:.6f}")

    # ── SARIMAX ────────────────────────────────────────────────────────────
    _emit("sarimax_started", 0.48, "Training SARIMAX…")
    exog_candidates = (
        "ret_mean_7", "ret_std_14", "mom_14",
        "log_vol", "log_mcap", "vol_mcap_ratio",
        "btc_ret1", "eth_ret1",
        "rsi_14", "macd_diff",
    )
    exog_cols = [c for c in exog_candidates if c in df_feat.columns]
    sar_model, diag_sar = train_sarimax(df_feat, exog_cols=exog_cols or None)
    diagnostics.update(diag_sar)
    _emit("sarimax_done", 0.58, f"SARIMAX done. AIC={diag_sar['sarimax_aic']:.2f}")

    # ── Prophet ────────────────────────────────────────────────────────────
    prophet_model = None
    try:
        _emit("prophet_started", 0.59, "Training Prophet…")
        prophet_model, diag_prophet = train_prophet(df_feat)
        diagnostics.update(diag_prophet)
        _emit("prophet_done", 0.68, f"Prophet done. MAPE={diag_prophet['prophet_mape']:.4f}")
    except Exception as exc:
        logger.warning("Prophet training failed: %s", exc)
        diagnostics["prophet_error"] = str(exc)

    # ── LSTM ───────────────────────────────────────────────────────────────
    lstm_artifact = None
    try:
        _emit("lstm_started", 0.69, "Training LSTM…")
        lstm_artifact, diag_lstm = train_lstm(
            df_feat, feature_cols, seq_len=30, epochs=50, hidden=64
        )
        diagnostics.update(diag_lstm)
        _emit("lstm_done", 0.82, f"LSTM done. MSE={diag_lstm['lstm_train_mse']:.6f}")
    except Exception as exc:
        logger.warning("LSTM training failed: %s", exc)
        diagnostics["lstm_error"] = str(exc)

    # ── Ensemble weights ───────────────────────────────────────────────────
    weights = compute_weights(diagnostics)
    diagnostics["ensemble_weights"] = weights
    _emit("ensemble", 0.83, f"Ensemble weights: {weights}")

    # ── Iterative forecasting ──────────────────────────────────────────────
    _emit("forecast_started", 0.84, "Running iterative multi-step forecast…")

    last_row = df_feat.iloc[-1]
    last_date = pd.to_datetime(last_row["date"])
    last_logp = float(last_row["log_price"])

    # XGB returns (iterative)
    xgb_rets = _xgb_iterative_forecast(df_feat, feature_cols, xgb_pipe, horizon_days)

    # SARIMAX returns
    if exog_cols:
        ex_rows = [
            [float(last_row.get(c, 0.0)) for c in exog_cols]
            for _ in range(horizon_days)
        ]
        sar_rets = predict_sarimax(sar_model, steps=horizon_days, exog_rows=ex_rows)
    else:
        sar_rets = predict_sarimax(sar_model, steps=horizon_days)

    # Prophet returns
    prophet_rets: list[float] = []
    if prophet_model is not None:
        future_dates = [
            (last_date + pd.Timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range(1, horizon_days + 1)
        ]
        try:
            prophet_rets = predict_prophet(prophet_model, future_dates)
        except Exception as exc:
            logger.warning("Prophet forecast failed: %s", exc)

    # LSTM returns
    lstm_rets: list[float] = []
    if lstm_artifact is not None:
        try:
            lstm_rets = predict_lstm(lstm_artifact, df_feat, steps=horizon_days)
        except Exception as exc:
            logger.warning("LSTM forecast failed: %s", exc)

    # ── Build per-model price series ───────────────────────────────────────
    resid_std_xgb = diagnostics.get("xgb_resid_std", 0.01)
    resid_std_sar = diagnostics.get("sarimax_resid_std", 0.01)
    resid_std = (resid_std_xgb + resid_std_sar) / 2.0

    model_returns_map: dict[str, list[float]] = {"xgb": xgb_rets, "sarimax": sar_rets}
    if prophet_rets:
        model_returns_map["prophet"] = prophet_rets
    if lstm_rets:
        model_returns_map["lstm"] = lstm_rets

    ens_rets = ensemble_returns(model_returns_map, weights)

    # ── Convert returns → prices ───────────────────────────────────────────
    ens_preds = _build_price_series(
        last_logp, ens_rets, last_date, horizon_days, resid_std, usd_idr_rate, currency
    )

    # Attach per-model price traces
    def _logrets_to_prices(rets: list[float]) -> list[float]:
        lp = last_logp
        prices = []
        for r in rets:
            lp += r
            prices.append(float(np.exp(lp)))
        return prices

    xgb_prices = _logrets_to_prices(xgb_rets)
    sar_prices = _logrets_to_prices(sar_rets)
    prophet_prices = _logrets_to_prices(prophet_rets) if prophet_rets else [None] * horizon_days
    lstm_prices = _logrets_to_prices(lstm_rets) if lstm_rets else [None] * horizon_days

    for i, pred in enumerate(ens_preds):
        pred["xgb_price"] = xgb_prices[i]
        pred["sarimax_price"] = sar_prices[i]
        pred["prophet_price"] = prophet_prices[i]
        pred["lstm_price"] = lstm_prices[i]

    # ── History tail ───────────────────────────────────────────────────────
    tail = df_feat.tail(90).copy()
    history_tail = [
        {
            "date": str(r["date"].date() if hasattr(r["date"], "date") else r["date"])[:10],
            "price": float(r["price"]),
        }
        for _, r in tail.iterrows()
    ]

    last_price = float(last_row["price"])
    last_price_idr = last_price * usd_idr_rate if currency.lower() == "usd" else last_price

    _emit("done", 1.0, "Forecast complete")

    return {
        "coin_id": coin_id,
        "currency": currency,
        "horizon_days": horizon_days,
        "last_date": str(pd.to_datetime(last_row["date"]).date()),
        "last_price": last_price,
        "last_price_idr": last_price_idr,
        "predictions": ens_preds,
        "diagnostics": diagnostics,
        "history_tail": history_tail,
    }
