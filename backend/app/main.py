"""
main.py — FastAPI application factory.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import get_settings
from app.database import Base, engine

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables on startup only for dev/test; use Alembic in production."""
    if settings.APP_ENV in {"development", "test"}:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified / created for %s.", settings.APP_ENV)
    else:
        logger.info("Skipping Base.metadata.create_all in production.")
    yield
    await engine.dispose()
    logger.info("Database engine disposed.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Fun-Forecasting API",
        version="2.0.0",
        description="Multi-asset price forecasting with XGBoost, SARIMAX, Prophet & LSTM.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "env": settings.APP_ENV}

    return app


app = create_app()
