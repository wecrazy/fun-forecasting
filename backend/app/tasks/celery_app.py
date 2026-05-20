"""
tasks/celery_app.py — Celery application configuration.
"""
from __future__ import annotations

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "fun_forecasting",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.forecast_task"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,  # 24 h
    task_routes={
        "app.tasks.forecast_task.run_forecast_task": {"queue": "forecasting"},
    },
)
