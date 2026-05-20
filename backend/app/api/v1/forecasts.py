"""
api/v1/forecasts.py — Forecast job CRUD endpoints.

POST /api/v1/forecasts              — submit new forecast job
GET  /api/v1/forecasts/{job_id}     — retrieve full result
GET  /api/v1/forecasts              — list recent jobs
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.forecast_job import ForecastJob
from app.models.forecast_result import ForecastPrediction
from app.schemas.forecast import (
    ForecastRequest,
    ForecastResultOut,
    JobStatusOut,
    PredictionOut,
)

router = APIRouter()


def _job_to_status(job: ForecastJob) -> JobStatusOut:
    return JobStatusOut(
        job_id=job.id,
        status=job.status,
        asset=job.asset,
        currency=job.currency,
        horizon_days=job.horizon_days,
        created_at=job.created_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
    )


@router.post("", response_model=JobStatusOut, status_code=202)
async def create_forecast(
    req: ForecastRequest,
    db: AsyncSession = Depends(get_db),
) -> JobStatusOut:
    """Submit a new forecast job. Returns immediately with job_id; processing is async."""
    from app.tasks.forecast_task import run_forecast_task  # avoid circular import

    job = ForecastJob(
        id=str(uuid.uuid4()),
        asset=req.asset,
        currency=req.currency,
        horizon_days=req.horizon_days,
        history_days=req.history_days,
        optuna_trials=req.optuna_trials,
        include_exog=req.include_exog,
        status="pending",
    )
    db.add(job)
    await db.flush()

    # Enqueue Celery task
    task = run_forecast_task.apply_async(
        args=[job.id],
        task_id=str(uuid.uuid4()),
    )
    job.celery_task_id = task.id
    await db.commit()
    await db.refresh(job)
    return _job_to_status(job)


@router.get("", response_model=list[JobStatusOut])
async def list_forecasts(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
) -> list[JobStatusOut]:
    """List recent forecast jobs, newest first."""
    result = await db.execute(
        select(ForecastJob).order_by(ForecastJob.created_at.desc()).limit(limit)
    )
    jobs = result.scalars().all()
    return [_job_to_status(j) for j in jobs]


@router.get("/{job_id}", response_model=ForecastResultOut)
async def get_forecast(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> ForecastResultOut:
    """Retrieve a completed forecast result including all predictions."""
    result = await db.execute(
        select(ForecastJob)
        .where(ForecastJob.id == job_id)
        .options(selectinload(ForecastJob.predictions))
    )
    job: ForecastJob | None = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")

    preds = [
        PredictionOut(
            date=p.date,
            predicted_price=p.predicted_price,
            predicted_price_usd=p.predicted_price_usd,
            predicted_price_idr=p.predicted_price_idr,
            predicted_return=p.predicted_return,
            upper_bound=p.upper_bound,
            lower_bound=p.lower_bound,
            xgb_price=p.xgb_price,
            sarimax_price=p.sarimax_price,
            prophet_price=p.prophet_price,
            lstm_price=p.lstm_price,
        )
        for p in sorted(job.predictions, key=lambda x: x.date)
    ]

    # diagnostics and history_tail are stored as extra attributes on the job
    diagnostics = getattr(job, "_diagnostics", {})
    history_tail = getattr(job, "_history_tail", [])

    return ForecastResultOut(
        job_id=job.id,
        asset=job.asset,
        currency=job.currency,
        horizon_days=job.horizon_days,
        status=job.status,
        diagnostics=diagnostics,
        history_tail=history_tail,
        predictions=preds,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )
