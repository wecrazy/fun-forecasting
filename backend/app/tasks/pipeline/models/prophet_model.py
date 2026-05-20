"""
pipeline/models/prophet_model.py — Facebook Prophet wrapper.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def train_prophet(
    df: pd.DataFrame,
    date_col: str = "date",
    y_col: str = "y",
) -> tuple[object, dict]:
    """
    Fit a Prophet model on log-returns.

    Returns (model, diagnostics_dict).
    """
    try:
        from prophet import Prophet  # type: ignore
    except ImportError:
        raise ImportError(
            "prophet is not installed. Add 'prophet>=1.1.5' to requirements.txt."
        )

    train = pd.DataFrame(
        {"ds": pd.to_datetime(df[date_col]), "y": df[y_col].astype(float)}
    )

    model = Prophet(
        daily_seasonality=False,
        weekly_seasonality=True,
        yearly_seasonality=True,
        interval_width=0.95,
        changepoint_prior_scale=0.05,
    )
    model.fit(train)

    # In-sample diagnostics
    forecast = model.predict(train[["ds"]])
    resid = train["y"].values - forecast["yhat"].values
    mape = float(np.mean(np.abs(resid / (np.abs(train["y"].values) + 1e-8))))
    resid_std = float(np.std(resid, ddof=1))

    return model, {
        "prophet_mape": mape,
        "prophet_resid_std": resid_std,
    }


def predict_prophet(
    model,
    future_dates: list[str],
) -> list[float]:
    """Predict log-returns for a list of ISO date strings."""
    future_df = pd.DataFrame({"ds": pd.to_datetime(future_dates)})
    forecast = model.predict(future_df)
    return list(float(v) for v in forecast["yhat"].values)
