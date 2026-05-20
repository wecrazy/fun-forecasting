"""
models/forecast_job.py — ForecastJob ORM model.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ForecastJob(Base):
    __tablename__ = "forecast_jobs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    asset: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="usd")
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    history_days: Mapped[str] = mapped_column(String(16), nullable=False, default="max")
    optuna_trials: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    include_exog: Mapped[bool] = mapped_column(default=True)

    # Status: pending | running | done | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    last_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_price_idr: Mapped[float | None] = mapped_column(Float, nullable=True)
    diagnostics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    history_tail: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    celery_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    predictions: Mapped[list["ForecastPrediction"]] = relationship(  # noqa: F821
        "ForecastPrediction", back_populates="job", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ForecastJob id={self.id} asset={self.asset} status={self.status}>"
