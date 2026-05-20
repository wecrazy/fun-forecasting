"""
services/data_client.py — Unified async data client (migrated from root data_client.py).

Supports:
  • CoinGecko (crypto OHLCV + live price)
  • CoinMarketCap (fallback live price for crypto)
  • Yahoo Finance / yfinance (Indonesian stocks + any ticker)
  • USD→IDR exchange rate (open.er-api.com, fallback constant)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
import pandas as pd
import yfinance as yf  # type: ignore

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_USD_IDR_RATE_CACHE: float | None = None
_USD_IDR_RATE_LOCK = asyncio.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cg_headers() -> dict[str, str]:
    if settings.COINGECKO_API_KEY:
        return {settings.COINGECKO_KEY_HEADER: settings.COINGECKO_API_KEY}
    return {}


def _cmc_headers() -> dict[str, str]:
    return {"X-CMC_PRO_API_KEY": settings.COINMARKETCAP_API_KEY, "Accept": "application/json"}


def build_daily_frame(market_chart_json: dict) -> pd.DataFrame:
    """Convert CoinGecko market_chart JSON → clean daily DataFrame."""
    prices = pd.DataFrame(market_chart_json["prices"], columns=["ts_ms", "price"])
    mcaps = pd.DataFrame(market_chart_json.get("market_caps", []), columns=["ts_ms", "mcap"])
    vols = pd.DataFrame(market_chart_json.get("total_volumes", []), columns=["ts_ms", "volume"])

    df = prices.merge(mcaps, on="ts_ms", how="left").merge(vols, on="ts_ms", how="left")
    df["date"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True).dt.tz_convert(None)
    df = df.drop(columns=["ts_ms"]).sort_values("date")

    df["day"] = df["date"].dt.floor("D")
    df = (
        df.groupby("day", as_index=False)
        .last()
        .rename(columns={"day": "date"})
        .drop(columns=["date_y"], errors="ignore")
    )
    df = df[["date", "price", "mcap", "volume"]]
    df = df.set_index("date").asfreq("D")
    df[["price", "mcap", "volume"]] = df[["price", "mcap", "volume"]].ffill()
    df = df.dropna().reset_index()
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Exchange-rate
# ─────────────────────────────────────────────────────────────────────────────

async def get_usd_idr_rate(timeout: float = 8.0) -> float:
    """Fetch live USD→IDR rate; falls back to settings.FALLBACK_USD_IDR_RATE."""
    global _USD_IDR_RATE_CACHE

    async with _USD_IDR_RATE_LOCK:
        if _USD_IDR_RATE_CACHE is not None:
            return _USD_IDR_RATE_CACHE

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.get("https://open.er-api.com/v6/latest/USD")
                r.raise_for_status()
                data = r.json()
                rate = data["rates"].get("IDR")
                if rate:
                    _USD_IDR_RATE_CACHE = float(rate)
                    return _USD_IDR_RATE_CACHE
        except Exception as exc:
            logger.warning(
                "USD/IDR rate fetch failed (%s); using fallback %s",
                exc,
                settings.FALLBACK_USD_IDR_RATE,
            )
        return settings.FALLBACK_USD_IDR_RATE


# ─────────────────────────────────────────────────────────────────────────────
# Crypto — CoinGecko
# ─────────────────────────────────────────────────────────────────────────────

async def get_crypto_data(
    coin_id: str,
    currency: str = "usd",
    days: str = "max",
    timeout: float = 45.0,
) -> pd.DataFrame:
    """Fetch historical OHLCV for a crypto coin via CoinGecko."""
    vs = currency.lower()
    url = f"{settings.COINGECKO_BASE_URL}/coins/{coin_id}/market_chart"
    params: dict[str, Any] = {
        "vs_currency": vs,
        "days": days,
        "interval": "daily",
        "precision": "full",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url, params=params, headers=_cg_headers())
        r.raise_for_status()
    return build_daily_frame(r.json())


async def get_live_crypto_price(
    coin_id: str,
    currency: str = "usd",
    timeout: float = 15.0,
) -> float:
    """Return live spot price via CoinGecko simple/price, fallback to CMC."""
    vs = currency.lower()
    try:
        url = f"{settings.COINGECKO_BASE_URL}/simple/price"
        params = {"ids": coin_id, "vs_currencies": vs}
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url, params=params, headers=_cg_headers())
            r.raise_for_status()
        data = r.json()
        price = data.get(coin_id, {}).get(vs)
        if price is not None:
            return float(price)
    except Exception as exc:
        logger.warning("CoinGecko live price failed (%s); trying CMC...", exc)

    if settings.COINMARKETCAP_API_KEY:
        try:
            symbol_map = {
                "funtoken": "FUN",
                "bitcoin": "BTC",
                "ethereum": "ETH",
                "binancecoin": "BNB",
                "solana": "SOL",
            }
            symbol = symbol_map.get(coin_id.lower(), coin_id.upper())
            url = f"{settings.COINMARKETCAP_BASE_URL}/cryptocurrency/quotes/latest"
            params_cmc = {"symbol": symbol, "convert": vs.upper()}
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.get(url, params=params_cmc, headers=_cmc_headers())
                r.raise_for_status()
            data = r.json()
            price = data["data"][symbol]["quote"][vs.upper()]["price"]
            if price is not None:
                return float(price)
        except Exception as exc2:
            logger.error("CMC fallback also failed: %s", exc2)

    raise RuntimeError(f"Could not fetch live price for {coin_id} in {currency}")


# ─────────────────────────────────────────────────────────────────────────────
# Stocks — Yahoo Finance
# ─────────────────────────────────────────────────────────────────────────────

def _yf_download(ticker: str, period: str) -> pd.DataFrame:
    """Synchronous yfinance download (run in executor)."""
    t = yf.Ticker(ticker)
    hist = t.history(period=period)
    if hist.empty:
        raise ValueError(f"No data returned by yfinance for ticker {ticker!r}")
    hist = hist.reset_index()
    hist.columns = [c.lower() for c in hist.columns]
    hist = hist.rename(columns={"date": "date", "close": "price", "volume": "volume"})
    hist["date"] = pd.to_datetime(hist["date"]).dt.tz_localize(None)
    hist["mcap"] = float("nan")
    return hist[["date", "price", "mcap", "volume"]].copy()


async def get_stock_data(
    ticker: str,
    period: str = "5y",
    currency: str = "idr",
) -> pd.DataFrame:
    """Fetch historical daily close for an IDX stock via yfinance."""
    loop = asyncio.get_event_loop()
    df = await loop.run_in_executor(None, _yf_download, ticker, period)

    is_idr_native = ticker.upper().endswith(".JK")

    if currency.lower() == "usd" and is_idr_native:
        rate = await get_usd_idr_rate()
        df["price"] = df["price"] / rate
    elif currency.lower() == "idr" and not is_idr_native:
        rate = await get_usd_idr_rate()
        df["price"] = df["price"] * rate

    return df


async def get_live_stock_price(ticker: str, currency: str = "idr") -> float:
    """Return latest close price for a stock ticker."""
    loop = asyncio.get_event_loop()
    df = await loop.run_in_executor(None, _yf_download, ticker, "5d")
    price = float(df["price"].iloc[-1])

    is_idr_native = ticker.upper().endswith(".JK")
    if currency.lower() == "usd" and is_idr_native:
        rate = await get_usd_idr_rate()
        price = price / rate
    elif currency.lower() == "idr" and not is_idr_native:
        rate = await get_usd_idr_rate()
        price = price * rate

    return price


# ─────────────────────────────────────────────────────────────────────────────
# Unified dispatcher
# ─────────────────────────────────────────────────────────────────────────────

def is_crypto(asset: str) -> bool:
    return asset.lower() in settings.CRYPTO_ASSETS or not asset.upper().endswith(".JK")


async def get_asset_data(asset: str, currency: str = "usd", days: str = "max") -> pd.DataFrame:
    """Route to crypto or stock fetcher based on asset id."""
    if asset.upper() in {k.upper() for k in settings.STOCK_ASSETS}:
        period = "5y" if days == "max" else f"{days}d"
        return await get_stock_data(asset, period=period, currency=currency)
    return await get_crypto_data(asset, currency=currency, days=days)


async def get_live_price(asset: str, currency: str = "usd") -> float:
    """Route to crypto or stock live price fetcher."""
    if asset.upper() in {k.upper() for k in settings.STOCK_ASSETS}:
        return await get_live_stock_price(asset, currency=currency)
    return await get_live_crypto_price(asset, currency=currency)
