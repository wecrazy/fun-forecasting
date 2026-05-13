"""Application configuration loaded from environment variables."""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

COINGECKO_API_KEY: str = os.getenv("COINGECKO_API_KEY", "")
COINGECKO_BASE_URL: str = os.getenv("COINGECKO_BASE_URL", "https://api.coingecko.com/api/v3")
COINGECKO_KEY_HEADER: str = os.getenv("COINGECKO_KEY_HEADER", "x-cg-demo-api-key")

COINMARKETCAP_API_KEY: str = os.getenv("COINMARKETCAP_API_KEY", "")
COINMARKETCAP_BASE_URL: str = "https://pro-api.coinmarketcap.com/v1"

OPTUNA_TRIALS: int = int(os.getenv("OPTUNA_TRIALS", "60"))
HISTORY_DAYS: str = os.getenv("HISTORY_DAYS", "max")
INCLUDE_BTC_ETH: bool = os.getenv("INCLUDE_BTC_ETH", "1") == "1"
DEFAULT_CURRENCY: str = os.getenv("DEFAULT_CURRENCY", "usd").lower()
USE_GPU: str = os.getenv("USE_GPU", "auto").lower()

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

ALL_ASSETS: dict[str, str] = {**CRYPTO_ASSETS, **STOCK_ASSETS}
SUPPORTED_CURRENCIES: tuple[str, str] = ("usd", "idr")
FALLBACK_USD_IDR_RATE: float = 16_000.0
