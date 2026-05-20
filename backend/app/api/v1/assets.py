"""
api/v1/assets.py — Asset catalogue endpoints.

GET /api/v1/assets        — list all supported assets
GET /api/v1/assets/{id}   — get single asset + live price
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.schemas.asset import AssetListOut, AssetOut
from app.services.data_client import get_live_price

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()


def _build_asset_out(asset_id: str, name: str, asset_type: str) -> AssetOut:
    native = "idr" if asset_id.upper().endswith(".JK") else "usd"
    return AssetOut(id=asset_id, name=name, asset_type=asset_type, currency_native=native)


@router.get("", response_model=AssetListOut)
async def list_assets() -> AssetListOut:
    """Return all supported crypto and stock assets."""
    crypto = [
        _build_asset_out(aid, name, "crypto")
        for aid, name in settings.CRYPTO_ASSETS.items()
    ]
    stocks = [
        _build_asset_out(tid, name, "stock")
        for tid, name in settings.STOCK_ASSETS.items()
    ]
    return AssetListOut(crypto=crypto, stocks=stocks, total=len(crypto) + len(stocks))


@router.get("/{asset_id}/price")
async def get_asset_price(asset_id: str, currency: str = "usd") -> dict:
    """Return live price for an asset."""
    if currency not in settings.supported_currencies:
        raise HTTPException(status_code=400, detail=f"Currency must be one of {settings.supported_currencies}")
    try:
        price = await get_live_price(asset_id, currency=currency)
    except Exception as exc:
        logger.error("Failed to fetch live price for %s: %s", asset_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"asset": asset_id, "currency": currency, "price": price}
