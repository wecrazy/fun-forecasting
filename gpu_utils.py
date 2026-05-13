"""GPU detection helpers."""
from __future__ import annotations

from config import USE_GPU


def is_gpu_available() -> bool:
    """Return True if CUDA GPU is available and GPU usage is not disabled."""
    if USE_GPU == "false":
        return False

    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            return True
    except Exception:
        pass

    try:
        import numpy as np
        import xgboost as xgb

        dtrain = xgb.DMatrix(np.zeros((8, 2)), label=np.zeros(8))
        xgb.train({"tree_method": "gpu_hist", "verbosity": 0}, dtrain, num_boost_round=1)
        return True
    except Exception:
        return False


def get_xgb_tree_method() -> str:
    """Return XGBoost tree_method based on USE_GPU policy and availability."""
    if USE_GPU == "true":
        return "gpu_hist"
    if USE_GPU == "auto" and is_gpu_available():
        return "gpu_hist"
    return "hist"
