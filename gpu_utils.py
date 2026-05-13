"""
gpu_utils.py — GPU detection helpers for XGBoost acceleration.
"""
from __future__ import annotations

from config import USE_GPU


def is_gpu_available() -> bool:
    """
    Return True when a CUDA-capable GPU is found AND USE_GPU is not "false".
    Falls back gracefully; never raises.
    """
    if USE_GPU == "false":
        return False

    # 1. Try PyTorch CUDA detection (lightweight check)
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            return True
    except ImportError:
        pass

    # 2. Try a tiny XGBoost GPU fit as a last-resort check
    try:
        import xgboost as xgb
        import numpy as np

        dtrain = xgb.DMatrix(np.zeros((10, 2)), label=np.zeros(10))
        xgb.train({"tree_method": "gpu_hist", "verbosity": 0}, dtrain, num_boost_round=1)
        return True
    except Exception:
        pass

    return False


def get_xgb_tree_method(gpu_available: bool | None = None) -> str:
    """
    Return the best XGBoost tree_method string.
    Uses 'gpu_hist' when GPU available; otherwise 'hist'.
    """
    available = is_gpu_available() if gpu_available is None else gpu_available
    if USE_GPU == "true" or (USE_GPU == "auto" and available):
        return "gpu_hist"
    return "hist"
