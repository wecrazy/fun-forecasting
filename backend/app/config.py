"""
config.py — Centralised settings via Pydantic BaseSettings.
All values can be overridden via environment variables or a .env file.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── Application ───────────────────────────────────────────────────────────
    APP_ENV: Literal["development", "production", "test"] = "development"
    SECRET_KEY: str = "change-me-in-production"
    ALLOWED_ORIGINS: list[str] = Field(default=["http://localhost:3000", "http://127.0.0.1:3000"])

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/fun_forecasting"

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ── CoinGecko ─────────────────────────────────────────────────────────────
    COINGECKO_API_KEY: str = ""
    COINGECKO_BASE_URL: str = "https://api.coingecko.com/api/v3"
    COINGECKO_KEY_HEADER: str = "x-cg-demo-api-key"

    # ── CoinMarketCap (optional fallback) ─────────────────────────────────────
    COINMARKETCAP_API_KEY: str = ""
    COINMARKETCAP_BASE_URL: str = "https://pro-api.coinmarketcap.com/v1"

    # ── Forecasting knobs ─────────────────────────────────────────────────────
    OPTUNA_TRIALS: int = 60
    HISTORY_DAYS: str = "max"
    INCLUDE_BTC_ETH: bool = True
    DEFAULT_CURRENCY: str = "usd"
    DEFAULT_ASSET: str = "funtoken"
    FALLBACK_USD_IDR_RATE: float = 16_300.0

    # ── GPU ───────────────────────────────────────────────────────────────────
    USE_GPU: Literal["auto", "true", "false"] = "auto"

    # ── Supported assets (static, kept here for reference) ───────────────────
    CRYPTO_ASSETS: dict[str, str] = {
        "funtoken": "FUNToken",
        "bitcoin": "Bitcoin",
        "ethereum": "Ethereum",
        "binancecoin": "BNB",
        "solana": "Solana",
    }

    STOCK_ASSETS: dict[str, str] = {
        "GOTO.JK": "Gojek Tokopedia",
        "BBCA.JK": "Bank Central Asia",
        "TLKM.JK": "Telkom Indonesia",
        "BBRI.JK": "Bank Rakyat Indonesia",
        "ASII.JK": "Astra International",
    }

    @property
    def all_assets(self) -> dict[str, str]:
        return {**self.CRYPTO_ASSETS, **self.STOCK_ASSETS}

    @property
    def supported_currencies(self) -> tuple[str, ...]:
        return ("usd", "idr")


@lru_cache
def get_settings() -> Settings:
    return Settings()
