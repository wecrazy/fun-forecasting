"""
schemas/asset.py — Pydantic schemas for assets.
"""
from __future__ import annotations

from pydantic import BaseModel


class AssetOut(BaseModel):
    id: str
    name: str
    asset_type: str  # "crypto" | "stock"
    currency_native: str

    model_config = {"from_attributes": True}


class AssetListOut(BaseModel):
    crypto: list[AssetOut]
    stocks: list[AssetOut]
    total: int
