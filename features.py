"""
features.py — Feature engineering for price forecasting.

Includes:
  • Log returns + rolling volatility / momentum (windows 3,7,14,30,60)
  • Volume / market-cap transforms
  • Calendar effects (dow, dom, month)
  • Technical indicators: RSI, MACD, Bollinger Bands (via `ta`)
  • Exogenous BTC / ETH features for crypto assets
"""
from __future__ import annotations

import numpy as np
import pandas as pd

try:
    import ta  # type: ignore

    _TA_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TA_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# Low-level helpers
# ─────────────────────────────────────────────────────────────────────────────

def _safe_log(x: pd.Series) -> pd.Series:
    return np.log(np.clip(x.astype(float), 1e-18, None))


# ─────────────────────────────────────────────────────────────────────────────
# Core feature engineering
# ─────────────────────────────────────────────────────────────────────────────

def add_features(
    df_raw: pd.DataFrame,
    btc_df: pd.DataFrame | None = None,
    eth_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Build feature matrix from a clean daily DataFrame (date, price, mcap, volume).

    Parameters
    ----------
    df_raw   : daily frame for the primary asset
    btc_df   : optional daily frame for Bitcoin (exogenous)
    eth_df   : optional daily frame for Ethereum (exogenous)

    Returns
    -------
    DataFrame with target column `y` = next-day log return, and many features.
    All NaN rows dropped.
    """
    df = df_raw.copy()

    # ── Log price & returns ──────────────────────────────────────────────────
    df["log_price"] = _safe_log(df["price"])
    df["ret1"] = df["log_price"].diff()

    # ── Rolling stats (momentum + volatility) ────────────────────────────────
    for w in (3, 7, 14, 30, 60):
        df[f"ret_mean_{w}"] = df["ret1"].rolling(w).mean()
        df[f"ret_std_{w}"] = df["ret1"].rolling(w).std()
        df[f"mom_{w}"] = df["log_price"] - df["log_price"].shift(w)

    # ── Volume / mcap features ───────────────────────────────────────────────
    df["log_vol"] = _safe_log(df["volume"].fillna(0) + 1.0)
    df["log_mcap"] = _safe_log(df["mcap"].fillna(0) + 1.0)
    df["vol_mcap_ratio"] = (df["volume"] / df["mcap"].replace(0, np.nan)).replace(
        [np.inf, -np.inf], np.nan
    )

    # ── Calendar effects ─────────────────────────────────────────────────────
    df["dow"] = df["date"].dt.dayofweek
    df["dom"] = df["date"].dt.day
    df["month"] = df["date"].dt.month

    # ── Technical indicators (RSI, MACD, Bollinger Bands) ───────────────────
    if _TA_AVAILABLE:
        close = df["price"].astype(float)
        # RSI
        df["rsi_14"] = ta.momentum.RSIIndicator(close=close, window=14).rsi()
        # MACD diff (signal line distance)
        macd_obj = ta.trend.MACD(close=close)
        df["macd"] = macd_obj.macd()
        df["macd_signal"] = macd_obj.macd_signal()
        df["macd_diff"] = macd_obj.macd_diff()
        # Bollinger Bands
        bb = ta.volatility.BollingerBands(close=close, window=20, window_dev=2)
        df["bb_upper"] = bb.bollinger_hband()
        df["bb_lower"] = bb.bollinger_lband()
        df["bb_pct"] = bb.bollinger_pband()  # % position within bands
        df["bb_width"] = bb.bollinger_wband()

    # ── Exogenous BTC / ETH ─────────────────────────────────────────────────
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

    # ── Target: next-day log return ──────────────────────────────────────────
    df["y"] = df["ret1"].shift(-1)

    # ── Final clean ─────────────────────────────────────────────────────────
    df = df.dropna().reset_index(drop=True)
    return df
