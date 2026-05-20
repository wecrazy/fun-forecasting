"""
pipeline/models/ensemble.py — Dynamic weighted ensemble of all models.

Weights are computed by inverse CV-RMSE / residual std so better models
contribute more to the ensemble prediction.
"""
from __future__ import annotations

import numpy as np


def compute_weights(diagnostics: dict[str, float]) -> dict[str, float]:
    """
    Compute normalised ensemble weights from diagnostic metrics.

    Lower error → higher weight. Models missing from diagnostics are skipped.
    """
    # Map model name → error metric (lower = better)
    error_map = {
        "xgb": diagnostics.get("xgb_cv_rmse") or diagnostics.get("xgb_resid_std"),
        "sarimax": diagnostics.get("sarimax_resid_std"),
        "prophet": diagnostics.get("prophet_resid_std"),
        "lstm": diagnostics.get("lstm_resid_std"),
    }

    # Keep only models with valid (positive) errors
    valid = {k: v for k, v in error_map.items() if v and v > 0}
    if not valid:
        raise ValueError("No valid model diagnostics available for ensemble weighting")

    # Inverse-error weighting
    inv = {k: 1.0 / v for k, v in valid.items()}
    total = sum(inv.values())
    weights = {k: v / total for k, v in inv.items()}
    return weights


def ensemble_returns(
    model_returns: dict[str, list[float]],
    weights: dict[str, float],
) -> list[float]:
    """
    Combine per-model return sequences into a single ensemble sequence.

    model_returns : {"xgb": [...], "sarimax": [...], ...}
    weights       : normalised weights from compute_weights()
    """
    # Ensure all sequences have the same length
    lengths = {len(v) for v in model_returns.values()}
    if len(lengths) > 1:
        raise ValueError(f"Model return sequences have different lengths: {lengths}")
    n = lengths.pop()

    result = np.zeros(n, dtype=float)
    total_weight = 0.0
    for name, rets in model_returns.items():
        w = weights.get(name, 0.0)
        if w > 0:
            result += w * np.array(rets, dtype=float)
            total_weight += w

    if total_weight > 0:
        result /= total_weight  # re-normalise in case some models were absent

    return list(float(v) for v in result)
