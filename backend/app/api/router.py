"""
api/router.py — Mounts all v1 sub-routers.
"""
from fastapi import APIRouter

from app.api.v1 import assets, forecasts, jobs

api_router = APIRouter()

api_router.include_router(assets.router, prefix="/assets", tags=["assets"])
api_router.include_router(forecasts.router, prefix="/forecasts", tags=["forecasts"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
