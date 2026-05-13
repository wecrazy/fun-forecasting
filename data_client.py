"""Unified data client for CoinGecko, CoinMarketCap fallback, and Yahoo Finance."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
import pandas as pd
import yfinance as yf  # type: ignore

from config import (
    COINGECKO_API_KEY,
    COINGECKO_BASE_URL,
    COINGECKO_KEY_HEADER,
    COINMARKETCAP_API_KEY,
    COINMARKETCAP_BASE_URL,
    CRYPTO_ASSETS,
    FALLBACK_USD_IDR_RATE,
    STOCK_ASSETS,
)

logger = logging.getLogger(__name__)


def _cg_headers() -> dict[str, str]:
    return {COINGECKO_KEY_HEADER: COINGECKO_API_KEY} if COINGECKO_API_KEY else {}


def _cmc_headers() -> dict[str, str]:
    return {"X-CMC_PRO_API_KEY": COINMARKETCAP_API_KEY, "Accept": "application/json"}


def build_daily_frame(market_chart_json: dict) -> pd.DataFrame:
    """Convert CoinGecko market_chart payload to clean daily DataFrame."""
    prices = pd.DataFrame(market_chart_json["prices"], columns=["ts_ms", "price"])
    mcaps = pd.DataFrame(market_chart_json.get("market_caps", []), columns=["ts_ms", "mcap"])
    vols = pd.DataFrame(market_chart_json.get("total_volumes", []), columns=["ts_ms", "volume"])

    df = prices.merge(mcaps, on="ts_ms", how="left").merge(vols, on="ts_ms", how="left")
    df["date"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True).dt.tz_convert(None)
    df = df.drop(columns=["ts_ms"]).sort_values("date")

    df["day"] = df["date"].dt.floor("D")
    df = df.groupby("day", as_index=False).last().rename(columns={"day": "date"})
    df = df[["date", "price", "mcap", "volume"]]

    df = df.set_index("date").asfreq("D")
    df[["price", "mcap", "volume"]] = df[["price", "mcap", "volume"]].ffill()
    return df.dropna().reset_index()


async def get_usd_idr_rate(timeout: float = 8.0) -> float:
    """Fetch live USD->IDR rate with fallback."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get("https://open.er-api.com/v6/latest/USD")
            resp.raise_for_status()
            data = resp.json()
            rate = data.get("rates", {}).get("IDR")
            if rate:
                return float(rate)
    except Exception as exc:
        logger.warning("Failed to fetch USD/IDR rate (%s), using fallback", exc)
    return FALLBACK_USD_IDR_RATE


async def get_crypto_data(
    coin_id: str,
    currency: str = "usd",
    days: str | int = "max",
    timeout: float = 45.0,
) -> pd.DataFrame:
    """Fetch historical crypto daily data from CoinGecko."""
    vs = currency.lower()
    url = f"{COINGECKO_BASE_URL}/coins/{coin_id}/market_chart"
    params: dict[str, Any] = {
        "vs_currency": vs,
        "days": days,
        "interval": "daily",
        "precision": "full",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, params=params, headers=_cg_headers())
        resp.raise_for_status()
    return build_daily_frame(resp.json())


async def get_live_crypto_price(
    coin_id: str,
    currency: str = "usd",
    timeout: float = 15.0,
) -> float:
    """Fetch live crypto spot price, with CoinMarketCap fallback."""
    vs = currency.lower()
    try:
        url = f"{COINGECKO_BASE_URL}/simple/price"
        params = {"ids": coin_id, "vs_currencies": vs}
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params, headers=_cg_headers())
            resp.raise_for_status()
        value = resp.json().get(coin_id, {}).get(vs)
        if value is not None:
            return float(value)
    except Exception as exc:
        logger.warning("CoinGecko live price failed (%s), trying CMC fallback", exc)

    if COINMARKETCAP_API_KEY:
        symbol_map = {
            "funtoken": "FUN",
            "bitcoin": "BTC",
            "ethereum": "ETH",
            "binancecoin": "BNB",
            "solana": "SOL",
        }
        symbol = symbol_map.get(coin_id.lower(), coin_id.upper())
        try:
            url = f"{COINMARKETCAP_BASE_URL}/cryptocurrency/quotes/latest"
            params = {"symbol": symbol, "convert": vs.upper()}
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url, params=params, headers=_cmc_headers())
                resp.raise_for_status()
            quote = resp.json()["data"][symbol]["quote"][vs.upper()]["price"]
            return float(quote)
        except Exception as exc:
            logger.error("CMC fallback failed: %s", exc)

    raise RuntimeError(f"Could not fetch live price for {coin_id} in {currency}")


def _yf_download(ticker: str, period: str) -> pd.DataFrame:
    """Download stock history and attach sector/market metadata when available."""
    t = yf.Ticker(ticker)
    hist = t.history(period=period)
    if hist.empty:
        raise ValueError(f"No data returned by yfinance for ticker {ticker!r}")

    hist = hist.reset_index()
    hist.columns = [c.lower() for c in hist.columns]
    hist = hist.rename(columns={"close": "price"})
    hist["date"] = pd.to_datetime(hist["date"]).dt.tz_localize(None)

    info = {}
    try:
        info = t.info or {}
    except Exception:
        info = {}

    hist["mcap"] = float("nan")
    hist["sector"] = str(info.get("sector", "unknown"))
    hist["market"] = str(info.get("exchange", "unknown"))

    if "volume" not in hist.columns:
        hist["volume"] = float("nan")

    return hist[["date", "price", "mcap", "volume", "sector", "market"]].copy()


async def get_stock_data(
    ticker: str,
    period: str = "5y",
    currency: str = "idr",
) -> pd.DataFrame:
    """Fetch historical stock data and convert currency when needed."""
    loop = asyncio.get_running_loop()
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
    """Fetch live-ish stock price from latest close."""
    loop = asyncio.get_running_loop()
    df = await loop.run_in_executor(None, _yf_download, ticker, "5d")
    price = float(df["price"].iloc[-1])

    is_idr_native = ticker.upper().endswith(".JK")
    if currency.lower() == "usd" and is_idr_native:
        rate = await get_usd_idr_rate()
        return price / rate
    if currency.lower() == "idr" and not is_idr_native:
        rate = await get_usd_idr_rate()
        return price * rate
    return price


def is_crypto(asset: str) -> bool:
    """Heuristic: .JK is stock, otherwise crypto."""
    return not asset.upper().endswith(".JK")


def _days_to_period(days: str | int) -> str:
    if isinstance(days, int):
        return f"{max(days, 1)}d"
    if str(days).lower() == "max":
        return "5y"
    if str(days).isdigit():
        return f"{max(int(days), 1)}d"
    return "5y"


async def get_asset_data(asset: str, currency: str = "usd", days: str | int = "max") -> pd.DataFrame:
    """Dispatch asset historical fetch to stock/crypto source."""
    if asset.upper().endswith(".JK"):
        return await get_stock_data(asset, period=_days_to_period(days), currency=currency)
    return await get_crypto_data(asset, currency=currency, days=days)


async def get_live_price(asset: str, currency: str = "usd") -> float:
    """Dispatch live price fetch to stock/crypto source."""
    if asset.upper().endswith(".JK"):
        return await get_live_stock_price(asset, currency=currency)
    return await get_live_crypto_price(asset, currency=currency)


def list_supported_assets() -> dict[str, dict[str, str]]:
    """Return predefined supported crypto and stock assets."""
    return {
        "crypto": CRYPTO_ASSETS,
        "stocks": STOCK_ASSETS,
    }
