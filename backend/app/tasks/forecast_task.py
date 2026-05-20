"""
tasks/forecast_task.py — Celery task that runs the full forecasting pipeline.

Flow:
  1. Update ForecastJob.status = "running"
  2. Fetch data via data_client
  3. Run pipeline (feature engineering + model training + forecasting)
  4. Persist predictions to DB
  5. Update ForecastJob.status = "done"

Progress events are published to Redis pub/sub so the SSE endpoint can stream them.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from celery import Task
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Sync SQLAlchemy engine for Celery worker (no asyncio) ──────────────────
if "+asyncpg" in settings.DATABASE_URL:
    _sync_db_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2", 1)
elif "+psycopg2" in settings.DATABASE_URL:
    _sync_db_url = settings.DATABASE_URL
else:
    raise ValueError(
        "DATABASE_URL must use postgresql+asyncpg or postgresql+psycopg2 for Celery worker sync engine"
    )
_engine = None
_SessionLocal = None


def _get_sync_session() -> Session:
    global _engine, _SessionLocal
    if _engine is None:
        from sqlalchemy import create_engine as _ce
        _engine = _ce(_sync_db_url, pool_pre_ping=True)
        _SessionLocal = sessionmaker(bind=_engine)
    return _SessionLocal()


# ── Redis pub/sub helper (sync) ────────────────────────────────────────────

def _publish_sync(job_id: str, event: dict) -> None:
    """Publish a progress event to Redis synchronously."""
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        r.publish(f"job:{job_id}:progress", json.dumps(event))
    except Exception as exc:
        logger.debug("Progress publish failed: %s", exc)


def _emit(job_id: str, event: str, progress: float, message: str, **extra) -> None:
    _publish_sync(job_id, {"job_id": job_id, "event": event, "progress": progress, "message": message, **extra})


# ─────────────────────────────────────────────────────────────────────────────
# Celery task
# ─────────────────────────────────────────────────────────────────────────────

@celery_app.task(bind=True, name="app.tasks.forecast_task.run_forecast_task", max_retries=2, default_retry_delay=30)
def run_forecast_task(self: Task, job_id: str) -> dict:
    """Execute the full forecasting pipeline for a given ForecastJob ID."""
    from app.models.forecast_job import ForecastJob
    from app.models.forecast_result import ForecastPrediction
    from app.services.data_client import get_asset_data, get_usd_idr_rate
    from app.tasks.pipeline.runner import run_pipeline

    session = _get_sync_session()
    try:
        # ── Fetch job parameters ────────────────────────────────────────────
        job: ForecastJob | None = session.get(ForecastJob, job_id)
        if job is None:
            raise ValueError(f"ForecastJob {job_id!r} not found")

        # ── Mark as running ─────────────────────────────────────────────────
        job.status = "running"
        session.commit()
        _emit(job_id, "started", 0.01, "Job started")

        # ── Fetch market data ───────────────────────────────────────────────
        _emit(job_id, "data_fetching", 0.05, f"Fetching data for {job.asset}…")

        async def _fetch_all():
            main_df = await get_asset_data(job.asset, currency=job.currency, days=job.history_days)
            btc_df = eth_df = None
            crypto_assets_lower = {k.lower() for k in settings.CRYPTO_ASSETS}
            if job.asset.lower() in crypto_assets_lower and job.include_exog:
                btc_df, eth_df = await asyncio.gather(
                    get_asset_data("bitcoin", currency=job.currency, days=job.history_days),
                    get_asset_data("ethereum", currency=job.currency, days=job.history_days),
                )
            rate = await get_usd_idr_rate()
            return main_df, btc_df, eth_df, rate

        main_df, btc_df, eth_df, usd_idr_rate = asyncio.run(_fetch_all())
        _emit(job_id, "data_fetched", 0.09, "Market data fetched")

        # ── Progress callback ───────────────────────────────────────────────
        def progress_cb(event: str, pct: float, msg: str) -> None:
            _emit(job_id, event, pct, msg)

        # ── Run pipeline ────────────────────────────────────────────────────
        result = run_pipeline(
            df_main=main_df,
            coin_id=job.asset,
            currency=job.currency,
            horizon_days=job.horizon_days,
            optuna_trials=job.optuna_trials,
            usd_idr_rate=usd_idr_rate,
            include_exog=job.include_exog,
            btc_df=btc_df,
            eth_df=eth_df,
            progress_cb=progress_cb,
        )

        # ── Persist predictions ─────────────────────────────────────────────
        _emit(job_id, "saving", 0.97, "Saving predictions to database…")
        for pred in result["predictions"]:
            session.add(
                ForecastPrediction(
                    job_id=job_id,
                    date=pred["date"],
                    predicted_price=pred["predicted_price"],
                    predicted_price_usd=pred.get("predicted_price_usd"),
                    predicted_price_idr=pred.get("predicted_price_idr"),
                    predicted_return=pred.get("predicted_return"),
                    upper_bound=pred.get("upper_bound"),
                    lower_bound=pred.get("lower_bound"),
                    xgb_price=pred.get("xgb_price"),
                    sarimax_price=pred.get("sarimax_price"),
                    prophet_price=pred.get("prophet_price"),
                    lstm_price=pred.get("lstm_price"),
                )
            )

        # Store diagnostics / history_tail as JSON in extra columns
        # (persisted via task result for now; can be moved to a separate table)
        job.last_date = result.get("last_date")
        job.last_price = result.get("last_price")
        job.last_price_idr = result.get("last_price_idr")
        job.diagnostics = result.get("diagnostics") or {}
        job.history_tail = result.get("history_tail") or []
        job.status = "done"
        job.completed_at = datetime.now(timezone.utc)
        session.commit()

        _emit(job_id, "done", 1.0, "Forecast complete", diagnostics=result["diagnostics"])
        return {"job_id": job_id, "status": "done"}

    except Exception as exc:
        logger.exception("Forecast task %s failed: %s", job_id, exc)
        try:
            job = session.get(ForecastJob, job_id)
            if job:
                job.status = "failed"
                job.error_message = str(exc)
                session.commit()
        except Exception:
            pass
        _emit(job_id, "error", 0.0, f"Error: {exc}")
        raise self.retry(exc=exc) if self.request.retries < self.max_retries else exc
    finally:
        session.close()
