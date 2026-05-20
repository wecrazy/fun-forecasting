"""
models/forecast_result.py — Stored per-day forecast predictions.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Date, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ForecastPrediction(Base):
    __tablename__ = "forecast_predictions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("forecast_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    date: Mapped[str] = mapped_column(String(10), nullable=False)  # ISO 8601 "YYYY-MM-DD"

    predicted_price: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_price_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_price_idr: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_return: Mapped[float | None] = mapped_column(Float, nullable=True)

    upper_bound: Mapped[float | None] = mapped_column(Float, nullable=True)
    lower_bound: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Per-model contributions
    xgb_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    sarimax_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    prophet_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    lstm_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    job: Mapped["ForecastJob"] = relationship("ForecastJob", back_populates="predictions")  # noqa: F821

    def __repr__(self) -> str:
        return f"<ForecastPrediction job_id={self.job_id} date={self.date} price={self.predicted_price}>"
