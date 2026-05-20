"""
api/v1/jobs.py — Job status and SSE progress stream.

GET /api/v1/jobs/{job_id}/status         — one-shot status
GET /api/v1/jobs/{job_id}/stream         — SSE progress stream
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.database import get_db
from app.models.forecast_job import ForecastJob
from app.schemas.forecast import JobStatusOut
from app.services.cache import subscribe_progress

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{job_id}/status", response_model=JobStatusOut)
async def get_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> JobStatusOut:
    """Return current status of a forecast job."""
    result = await db.execute(select(ForecastJob).where(ForecastJob.id == job_id))
    job: ForecastJob | None = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
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


@router.get("/{job_id}/stream")
async def stream_job_progress(job_id: str) -> EventSourceResponse:
    """
    SSE endpoint: streams progress events while the Celery task is running.
    Closes automatically when a 'done' or 'error' event is received.
    """

    async def event_generator():
        async for raw in subscribe_progress(job_id):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            yield {"event": data.get("event", "progress"), "data": raw}
            if data.get("event") in ("done", "error"):
                break
            await asyncio.sleep(0)

    return EventSourceResponse(event_generator())
