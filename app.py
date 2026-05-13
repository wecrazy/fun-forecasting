"""FastAPI application for multi-asset price forecasting."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from config import (
    ALL_ASSETS,
    DEFAULT_CURRENCY,
    HISTORY_DAYS,
    INCLUDE_BTC_ETH,
    OPTUNA_TRIALS,
    SUPPORTED_CURRENCIES,
)
from data_client import (
    get_asset_data,
    get_live_price,
    get_usd_idr_rate,
    list_supported_assets,
)
from export import export_forecast
from features import add_features
from forecast import run_forecast

app = FastAPI(title="Fun Forecasting API", version="1.0.0")


def _is_stock(asset: str) -> bool:
    return asset.upper().endswith(".JK")


def _validate_currency(currency: str) -> str:
    c = currency.lower()
    if c not in SUPPORTED_CURRENCIES:
        raise HTTPException(status_code=400, detail="currency must be 'usd' or 'idr'")
    return c


def _validate_asset(asset: str) -> str:
    if _is_stock(asset):
        return asset.upper()
    return asset.lower()


async def _to_dual_currency(price: float, asset: str, currency: str, rate: float) -> tuple[float | None, float | None]:
    if currency == "usd":
        usd = float(price)
        idr = float(price * rate)
    else:
        idr = float(price)
        usd = float(price / rate) if rate > 0 else None

    # For .JK this conversion is still valid because base data is IDR and the
    # requested currency already controls the fetched value.
    _ = asset
    return usd, idr


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/assets")
async def assets() -> dict:
    supported = list_supported_assets()
    return {
        "assets": supported,
        "all": ALL_ASSETS,
        "notes": "You can also query any CoinGecko coin id and any .JK ticker.",
    }


@app.get("/price/live")
async def live_price(
    asset: str = Query(..., description="CoinGecko coin id or stock ticker such as GOTO.JK"),
    currency: str = Query(DEFAULT_CURRENCY, description="usd or idr"),
) -> dict:
    c = _validate_currency(currency)
    a = _validate_asset(asset)

    try:
        price = await get_live_price(a, currency=c)
        rate = await get_usd_idr_rate()
        usd, idr = await _to_dual_currency(price, a, c, rate)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "asset": a,
        "requested_currency": c,
        "price": float(price),
        "price_usd": usd,
        "price_idr": idr,
        "usd_idr_rate": rate,
    }


@app.get("/predict")
async def predict(
    asset: str = Query(..., description="CoinGecko coin id or stock ticker like GOTO.JK"),
    currency: str = Query(DEFAULT_CURRENCY, description="usd or idr"),
    days: int = Query(7, ge=1, le=365),
    optuna_trials: int = Query(OPTUNA_TRIALS, ge=10, le=500),
) -> dict:
    c = _validate_currency(currency)
    a = _validate_asset(asset)

    history_window: str | int = HISTORY_DAYS if str(HISTORY_DAYS).lower() == "max" else max(days * 6, 120)

    try:
        base_df = await get_asset_data(a, currency=c, days=history_window)

        btc_df = None
        eth_df = None
        if INCLUDE_BTC_ETH and not _is_stock(a):
            if a != "bitcoin":
                btc_df = await get_asset_data("bitcoin", currency=c, days=history_window)
            if a != "ethereum":
                eth_df = await get_asset_data("ethereum", currency=c, days=history_window)

        feat_df = add_features(base_df, btc_df=btc_df, eth_df=eth_df)
        if len(feat_df) < 90:
            raise HTTPException(status_code=400, detail="not enough historical data for robust forecasting")

        rate = await get_usd_idr_rate()
        result = run_forecast(
            feat_df,
            coin_id=a,
            vs_currency=c,
            horizon_days=days,
            optuna_trials=optuna_trials,
            usd_idr_rate=rate,
        )
        return {
            "asset": result.coin_id,
            "currency": result.vs_currency,
            "horizon_days": result.horizon_days,
            "last_date": result.last_date,
            "last_price": result.last_price,
            "last_price_idr": result.last_price_idr,
            "diagnostics": result.diagnostics,
            "predictions": result.predictions,
            "history_tail": result.history_tail,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/export")
async def export(
    asset: str = Query(..., description="CoinGecko coin id or .JK stock ticker"),
    currency: str = Query(DEFAULT_CURRENCY, description="usd or idr"),
    days: int = Query(7, ge=1, le=365),
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
    optuna_trials: int = Query(OPTUNA_TRIALS, ge=10, le=500),
):
    c = _validate_currency(currency)
    a = _validate_asset(asset)

    prediction = await predict(asset=a, currency=c, days=days, optuna_trials=optuna_trials)

    from forecast import ForecastResult

    result = ForecastResult(
        coin_id=prediction["asset"],
        vs_currency=prediction["currency"],
        horizon_days=prediction["horizon_days"],
        last_date=prediction["last_date"],
        last_price=float(prediction["last_price"]),
        last_price_idr=float(prediction["last_price_idr"]) if prediction["last_price_idr"] is not None else None,
        predictions=prediction["predictions"],
        diagnostics=prediction["diagnostics"],
        history_tail=prediction.get("history_tail", []),
    )

    out_path = export_forecast(result, fmt=format)
    media_type = "text/csv" if format == "csv" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return FileResponse(
        path=Path(out_path),
        filename=Path(out_path).name,
        media_type=media_type,
    )
