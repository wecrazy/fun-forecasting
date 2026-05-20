"""
schemas/forecast.py — Pydantic request/response schemas for forecasts and jobs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Request ───────────────────────────────────────────────────────────────────

class ForecastRequest(BaseModel):
    asset: str = Field(default="funtoken", description="Asset id or ticker, e.g. funtoken, bitcoin, GOTO.JK")
    currency: str = Field(default="usd", pattern="^(usd|idr)$")
    horizon_days: int = Field(default=30, ge=1, le=365)
    history_days: str = Field(default="max", description="'max' or positive integer string")
    optuna_trials: int = Field(default=60, ge=1, le=500)
    include_exog: bool = Field(default=True, description="Include BTC/ETH exogenous features")


# ── Prediction row ────────────────────────────────────────────────────────────

class PredictionOut(BaseModel):
    date: str
    predicted_price: float
    predicted_price_usd: float | None = None
    predicted_price_idr: float | None = None
    predicted_return: float | None = None
    upper_bound: float | None = None
    lower_bound: float | None = None
    xgb_price: float | None = None
    sarimax_price: float | None = None
    prophet_price: float | None = None
    lstm_price: float | None = None

    model_config = {"from_attributes": True}


# ── Job status ────────────────────────────────────────────────────────────────

class JobStatusOut(BaseModel):
    job_id: str
    status: str  # pending | running | done | failed
    asset: str
    currency: str
    horizon_days: int
    created_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None

    model_config = {"from_attributes": True}


# ── Full forecast result ──────────────────────────────────────────────────────

class ForecastResultOut(BaseModel):
    job_id: str
    asset: str
    currency: str
    horizon_days: int
    status: str
    last_date: str | None = None
    last_price: float | None = None
    last_price_idr: float | None = None
    diagnostics: dict[str, Any] = {}
    history_tail: list[dict[str, Any]] = []
    predictions: list[PredictionOut] = []
    created_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── SSE progress event ────────────────────────────────────────────────────────

class ProgressEvent(BaseModel):
    job_id: str
    event: str  # e.g. "data_fetched", "features_done", "xgb_trial", "done", "error"
    message: str
    progress: float = 0.0  # 0.0–1.0
    data: dict[str, Any] = {}
