"""
tests/test_features.py — Unit tests for pipeline feature engineering.
"""
import numpy as np
import pandas as pd
import pytest

from app.tasks.pipeline.features import add_features


def _make_df(n: int = 200) -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    rng = np.random.default_rng(42)
    prices = np.cumprod(1 + rng.normal(0, 0.02, n)) * 100
    return pd.DataFrame({
        "date": dates,
        "price": prices,
        "mcap": prices * 1e6,
        "volume": rng.uniform(1e4, 1e6, n),
    })


def test_add_features_shape():
    df = _make_df(200)
    feat = add_features(df)
    # y column must exist, NaN rows dropped
    assert "y" in feat.columns
    assert feat.isna().sum().sum() == 0
    assert len(feat) < len(df)  # NaN rows removed


def test_add_features_required_cols():
    df = _make_df(200)
    feat = add_features(df)
    for col in ("log_price", "ret1", "ret_mean_7", "ret_std_7", "mom_14", "dow", "dom", "month"):
        assert col in feat.columns, f"Missing column: {col}"


def test_add_features_with_exog():
    df = _make_df(200)
    btc = _make_df(200)
    eth = _make_df(200)
    feat = add_features(df, btc_df=btc, eth_df=eth)
    assert "btc_ret1" in feat.columns
    assert "eth_ret1" in feat.columns
