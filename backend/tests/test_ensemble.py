"""
tests/test_ensemble.py — Unit tests for ensemble weighting.
"""
import pytest

from app.tasks.pipeline.models.ensemble import compute_weights, ensemble_returns


def test_compute_weights_basic():
    diag = {"xgb_cv_rmse": 0.1, "sarimax_resid_std": 0.2}
    w = compute_weights(diag)
    assert set(w.keys()) == {"xgb", "sarimax"}
    assert abs(sum(w.values()) - 1.0) < 1e-6
    # lower error → higher weight
    assert w["xgb"] > w["sarimax"]


def test_compute_weights_no_valid_raises():
    with pytest.raises(ValueError):
        compute_weights({})


def test_ensemble_returns_weighted():
    model_returns = {"xgb": [0.1, 0.2, 0.3], "sarimax": [0.3, 0.2, 0.1]}
    weights = {"xgb": 0.6, "sarimax": 0.4}
    result = ensemble_returns(model_returns, weights)
    assert len(result) == 3
    # first value: 0.6*0.1 + 0.4*0.3 = 0.18
    assert abs(result[0] - 0.18) < 1e-6


def test_ensemble_returns_length_mismatch():
    with pytest.raises(ValueError):
        ensemble_returns({"xgb": [0.1, 0.2], "sarimax": [0.1]}, {"xgb": 0.5, "sarimax": 0.5})
