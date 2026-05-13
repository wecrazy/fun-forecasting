"""Feature engineering for forecasting."""
from __future__ import annotations

import numpy as np
import pandas as pd

try:
    import ta  # type: ignore

    _TA_AVAILABLE = True
except Exception:  # pragma: no cover
    _TA_AVAILABLE = False


def _safe_log(x: pd.Series) -> pd.Series:
    return np.log(np.clip(x.astype(float), 1e-18, None))


def add_features(
    df_raw: pd.DataFrame,
    btc_df: pd.DataFrame | None = None,
    eth_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build model features and target from daily price frame."""
    df = df_raw.copy()

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

    df["dow"] = df["date"].dt.dayofweek
    df["dom"] = df["date"].dt.day
    df["month"] = df["date"].dt.month

    if "sector" in df.columns:
        df["sector"] = df["sector"].fillna("unknown").astype(str)
    if "market" in df.columns:
        df["market"] = df["market"].fillna("unknown").astype(str)

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

    df["y"] = df["ret1"].shift(-1)
    return df.dropna().reset_index(drop=True)
