"""
pipeline/models/pytorch_model.py — LSTM time-series model in PyTorch.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Model definition
# ─────────────────────────────────────────────────────────────────────────────

def _build_lstm(input_size: int, hidden: int = 64, num_layers: int = 2, dropout: float = 0.2):
    """Build a 2-layer stacked LSTM with a linear output head."""
    try:
        import torch
        import torch.nn as nn
    except ImportError:
        raise ImportError("pytorch (torch) is not installed.")

    class LSTMForecaster(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = nn.LSTM(
                input_size=input_size,
                hidden_size=hidden,
                num_layers=num_layers,
                batch_first=True,
                dropout=dropout if num_layers > 1 else 0.0,
            )
            self.head = nn.Linear(hidden, 1)

        def forward(self, x):
            out, _ = self.lstm(x)
            return self.head(out[:, -1, :]).squeeze(-1)

    return LSTMForecaster()


def train_lstm(
    df: pd.DataFrame,
    feature_cols: list[str],
    y_col: str = "y",
    seq_len: int = 30,
    epochs: int = 50,
    lr: float = 1e-3,
    hidden: int = 64,
    batch_size: int = 32,
) -> tuple[object, dict]:
    """
    Train a stacked LSTM on rolling windows of `seq_len` days.

    Returns (trained_model_state + config, diagnostics_dict).
    """
    try:
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset
    except ImportError:
        raise ImportError("pytorch (torch) is not installed.")

    X_arr = df[feature_cols].astype(float).values
    y_arr = df[y_col].astype(float).values

    # Normalise features with z-score per column
    x_mean = X_arr.mean(axis=0)
    x_std = X_arr.std(axis=0) + 1e-8
    X_norm = (X_arr - x_mean) / x_std

    # Build sliding-window sequences
    sequences, targets = [], []
    for i in range(seq_len, len(X_norm)):
        sequences.append(X_norm[i - seq_len: i])
        targets.append(y_arr[i])

    if not sequences:
        raise ValueError(f"Not enough data for LSTM (need > {seq_len} rows)")

    X_tensor = torch.tensor(np.stack(sequences), dtype=torch.float32)
    y_tensor = torch.tensor(np.array(targets), dtype=torch.float32)

    dataset = TensorDataset(X_tensor, y_tensor)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = _build_lstm(input_size=len(feature_cols), hidden=hidden).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    model.train()
    final_loss = 0.0
    for _ in range(epochs):
        epoch_loss = 0.0
        for xb, yb in loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            pred = model(xb)
            loss = criterion(pred, yb)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
        final_loss = epoch_loss / len(loader)

    # Compute residual std on full training set
    model.eval()
    with torch.no_grad():
        all_preds = model(X_tensor.to(device)).cpu().numpy()
    resid_std = float(np.std(y_tensor.numpy() - all_preds, ddof=1))

    # Package model state alongside normalization params for inference
    artifact = {
        "state_dict": model.state_dict(),
        "x_mean": x_mean,
        "x_std": x_std,
        "seq_len": seq_len,
        "hidden": hidden,
        "input_size": len(feature_cols),
        "feature_cols": feature_cols,
        "model": model,  # keep reference for predict_lstm in same process
    }

    return artifact, {
        "lstm_train_mse": final_loss,
        "lstm_resid_std": resid_std,
    }


def predict_lstm(
    artifact: dict,
    df_history: pd.DataFrame,
    steps: int,
) -> list[float]:
    """
    Iteratively predict `steps` future log-returns.
    Uses the last `seq_len` rows from `df_history` as the initial window.
    """
    try:
        import torch
    except ImportError:
        raise ImportError("pytorch (torch) is not installed.")

    model = artifact["model"]
    x_mean: np.ndarray = artifact["x_mean"]
    x_std: np.ndarray = artifact["x_std"]
    seq_len: int = artifact["seq_len"]
    feature_cols: list[str] = artifact["feature_cols"]

    device = next(model.parameters()).device
    X_arr = df_history[feature_cols].astype(float).values
    X_norm = (X_arr - x_mean) / x_std

    # Initialise window with last seq_len rows
    window = list(X_norm[-seq_len:])
    preds = []

    model.eval()
    with torch.no_grad():
        for _ in range(steps):
            inp = torch.tensor(np.stack(window[-seq_len:]), dtype=torch.float32).unsqueeze(0).to(device)
            ret = float(model(inp).cpu().item())
            preds.append(ret)
            # Append a zero-vector as synthetic next feature row (simplification)
            window.append(np.zeros(len(feature_cols), dtype=float))

    return preds
