"""
pipeline/features.py — Feature engineering.

Uses Polars for fast computation, falls back to Pandas if Polars unavailable.
Migrated from root features.py with Polars optimisation path added.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import polars as pl
    _POLARS_AVAILABLE = True
except ImportError:
    _POLARS_AVAILABLE = False
    logger.info("Polars not available; using Pandas for feature engineering")

try:
    import ta  # type: ignore
    _TA_AVAILABLE = True
except ImportError:
    _TA_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_log(x: pd.Series) -> pd.Series:
    return np.log(np.clip(x.astype(float), 1e-18, None))


# ─────────────────────────────────────────────────────────────────────────────
# Polars fast path
# ─────────────────────────────────────────────────────────────────────────────

def _add_features_polars(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Polars-accelerated feature engineering (rolling stats + momentum)."""
    lf = pl.from_pandas(df_raw).lazy()

    lf = lf.with_columns([
        pl.col("price").clip(lower_bound=1e-18).log().alias("log_price"),
    ])
    lf = lf.with_columns([
        (pl.col("log_price") - pl.col("log_price").shift(1)).alias("ret1"),
    ])

    for w in (3, 7, 14, 30, 60):
        lf = lf.with_columns([
            pl.col("ret1").rolling_mean(w).alias(f"ret_mean_{w}"),
            pl.col("ret1").rolling_std(w).alias(f"ret_std_{w}"),
            (pl.col("log_price") - pl.col("log_price").shift(w)).alias(f"mom_{w}"),
        ])

    lf = lf.with_columns([
        (pl.col("volume").fill_null(0) + 1.0).clip(lower_bound=1e-18).log().alias("log_vol"),
        (pl.col("mcap").fill_null(0) + 1.0).clip(lower_bound=1e-18).log().alias("log_mcap"),
    ])
    lf = lf.with_columns([
        (pl.col("volume") / pl.col("mcap").replace(0, None)).alias("vol_mcap_ratio"),
    ])

    if "date" in df_raw.columns:
        lf = lf.with_columns([
            pl.col("date").dt.weekday().alias("dow"),
            pl.col("date").dt.day().alias("dom"),
            pl.col("date").dt.month().alias("month"),
        ])

    result = lf.collect().to_pandas()
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def add_features(
    df_raw: pd.DataFrame,
    btc_df: pd.DataFrame | None = None,
    eth_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Build feature matrix from a clean daily DataFrame (date, price, mcap, volume).

    Uses Polars fast path for rolling stats; Pandas for TA indicators and exogenous merges.
    Returns DataFrame with target column `y` = next-day log return, all NaN rows dropped.
    """
    if _POLARS_AVAILABLE:
        try:
            df = _add_features_polars(df_raw.copy())
        except Exception as exc:
            logger.warning("Polars feature path failed (%s); falling back to Pandas", exc)
            df = _pandas_base_features(df_raw.copy())
    else:
        df = _pandas_base_features(df_raw.copy())

    # ── Technical indicators (RSI, MACD, Bollinger Bands) ──────────────────
    if _TA_AVAILABLE:
        close = df["price"].astype(float)
        df["rsi_14"] = ta.momentum.RSIIndicator(close=close, window=14).rsi()
        macd_obj = ta.trend.MACD(close=close)
        df["macd"] = macd_obj.macd()
        df["macd_signal"] = macd_obj.macd_signal()
        df["macd_diff"] = macd_obj.macd_diff()
        bb = ta.volatility.BollingerBands(close=close, window=20, window_dev=2)
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_pct"] = bb.bollinger_pband()
        df["bb_width"] = bb.bollinger_wband()

    # ── Exogenous BTC / ETH ────────────────────────────────────────────────
    def _merge_exog(exog_df: pd.DataFrame, prefix: str, base: pd.DataFrame) -> pd.DataFrame:
        ex = exog_df.copy()
        ex["log_price"] = _safe_log(ex["price"])
        ex[f"{prefix}_ret1"] = ex["log_price"].diff()
        ex[f"{prefix}_ret_std_14"] = ex[f"{prefix}_ret1"].rolling(14).std()
        ex[f"{prefix}_mom_7"] = ex["log_price"] - ex["log_price"].shift(7)
        keep = ["date", f"{prefix}_ret1", f"{prefix}_ret_std_14", f"{prefix}_mom_7"]
        return base.merge(ex[keep], on="date", how="left")

    if btc_df is not None:
        df = _merge_exog(btc_df, "btc", df)
    if eth_df is not None:
        df = _merge_exog(eth_df, "eth", df)

    # ── Target: next-day log return ────────────────────────────────────────
    df["y"] = df["ret1"].shift(-1)

    df = df.dropna().reset_index(drop=True)
    return df


def _pandas_base_features(df: pd.DataFrame) -> pd.DataFrame:
    """Pure Pandas fallback for base feature engineering."""
    df["log_price"] = _safe_log(df["price"])
    df["ret1"] = df["log_price"].diff()

    for w in (3, 7, 14, 30, 60):
        df[f"ret_mean_{w}"] = df["ret1"].rolling(w).mean()
        df[f"ret_std_{w}"] = df["ret1"].rolling(w).std()
        df[f"mom_{w}"] = df["log_price"] - df["log_price"].shift(w)

    df["log_vol"] = _safe_log(df["volume"].fillna(0) + 1.0)
    df["log_mcap"] = _safe_log(df["mcap"].fillna(0) + 1.0)
    df["vol_mcap_ratio"] = (df["volume"] / df["mcap"].replace(0, np.nan)).replace(
        [np.inf, -np.inf], np.nan
    )

    if "date" in df.columns:
        df["dow"] = df["date"].dt.dayofweek
        df["dom"] = df["date"].dt.day
        df["month"] = df["date"].dt.month

    return df
