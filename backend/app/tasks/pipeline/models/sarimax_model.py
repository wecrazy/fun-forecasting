"""
pipeline/models/sarimax_model.py — SARIMAX wrapper.
Migrated from root forecast.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX


def train_sarimax(
    df: pd.DataFrame,
    y_col: str = "y",
    exog_cols: list[str] | None = None,
) -> tuple[object, dict]:
    """Fit a SARIMAX(2,0,2) model on log-returns."""
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


def predict_sarimax(
    model,
    steps: int,
    exog_rows: list[list[float]] | None = None,
) -> list[float]:
    """Produce `steps` one-step-ahead forecasts."""
    if exog_rows:
        ex = np.array(exog_rows, dtype=float)
        preds = model.forecast(steps=steps, exog=ex)
    else:
        preds = model.forecast(steps=steps)
    return list(float(v) for v in preds)
