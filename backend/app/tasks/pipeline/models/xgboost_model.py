"""
pipeline/models/xgboost_model.py — XGBoost + Optuna walk-forward CV.
Migrated from root forecast.py.
"""
from __future__ import annotations

import logging
from typing import Callable

import numpy as np
import optuna
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

import xgboost as xgb

logger = logging.getLogger(__name__)
optuna.logging.set_verbosity(optuna.logging.WARNING)


def _get_tree_method() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            return "gpu_hist"
    except ImportError:
        pass
    return "hist"


def _build_pipeline(cat_cols: list[str], num_cols: list[str], params: dict) -> Pipeline:
    pre = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat_cols),
            ("num", "passthrough", num_cols),
        ],
        remainder="drop",
    )
    model = xgb.XGBRegressor(
        **{k: v for k, v in params.items() if k != "n_estimators"},
        n_estimators=params.get("n_estimators", 2000),
        random_state=42,
        tree_method=_get_tree_method(),
        verbosity=0,
        eval_metric="rmse",
    )
    return Pipeline([("pre", pre), ("model", model)])


def _rmse(y_true, y_pred) -> float:
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def train_xgboost(
    df: pd.DataFrame,
    feature_cols: list[str],
    y_col: str = "y",
    trials: int = 60,
    cv_splits: int = 5,
    progress_cb: Callable[[int, int, float], None] | None = None,
) -> tuple[Pipeline, dict]:
    """
    Optuna + walk-forward CV tuning for XGBoost.

    Parameters
    ----------
    progress_cb : optional callback(trial_num, total_trials, current_best_rmse)
    """
    X = df[feature_cols].copy()
    y = df[y_col].astype(float).values

    cat_cols = [c for c in feature_cols if c in ("dow", "dom", "month")]
    num_cols = [c for c in feature_cols if c not in cat_cols]

    tscv = TimeSeriesSplit(n_splits=cv_splits)
    trial_counter = [0]

    def objective(trial: optuna.Trial) -> float:
        params = {
            "max_depth": trial.suggest_int("max_depth", 2, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.15, log=True),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "min_child_weight": trial.suggest_float("min_child_weight", 0.5, 10.0, log=True),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 1.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
            "gamma": trial.suggest_float("gamma", 0.0, 2.0),
            "n_estimators": trial.suggest_int("n_estimators", 800, 3500),
        }
        pipe = _build_pipeline(cat_cols, num_cols, params)
        rmses = []
        for train_idx, test_idx in tscv.split(X):
            pipe.fit(X.iloc[train_idx], y[train_idx])
            rmses.append(_rmse(y[test_idx], pipe.predict(X.iloc[test_idx])))

        trial_counter[0] += 1
        cv_rmse = float(np.mean(rmses))
        if progress_cb:
            progress_cb(trial_counter[0], trials, cv_rmse)
        return cv_rmse

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=trials, show_progress_bar=False)

    best = study.best_params
    pipe = _build_pipeline(cat_cols, num_cols, best)
    pipe.fit(X, y)

    resid_std = float(np.std(y - pipe.predict(X), ddof=1))
    return pipe, {"xgb_cv_rmse": float(study.best_value), "xgb_resid_std": resid_std}


def predict_xgboost(
    pipe: Pipeline,
    feature_rows: list[dict],
    feature_cols: list[str],
) -> list[float]:
    """Batch predict log-returns from a fitted XGBoost pipeline."""
    X = pd.DataFrame(feature_rows)[feature_cols]
    return list(pipe.predict(X).astype(float))
