"""
main.py — CLI runner for multi-asset forecasting (crypto + stocks).
"""
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

import pandas as pd

from config import (
    ALL_ASSETS,
    CRYPTO_ASSETS,
    DEFAULT_ASSET,
    DEFAULT_CURRENCY,
    HISTORY_DAYS,
    INCLUDE_BTC_ETH,
    OPTUNA_TRIALS,
    STOCK_ASSETS,
    SUPPORTED_CURRENCIES,
)
from data_client import get_asset_data, get_usd_idr_rate
from features import add_features
from forecast import ForecastResult, run_forecast
from gpu_utils import get_xgb_tree_method, is_gpu_available

ASSET_ALIASES: dict[str, str] = {
    "fun": "funtoken",
    "btc": "bitcoin",
    "eth": "ethereum",
    "bnb": "binancecoin",
    "sol": "solana",
    "goto": "GOTO.JK",
    "bbca": "BBCA.JK",
    "tlkm": "TLKM.JK",
    "bbri": "BBRI.JK",
    "asii": "ASII.JK",
}
# Minimum rows after feature engineering:
# - longest lookback window is 60 days
# - 5-fold walk-forward CV and SARIMAX need enough post-NaN observations
# 120 keeps training/validation splits stable.
MIN_REQUIRED_ROWS = 120
MIN_HORIZON_DAYS = 1


def _resolve_asset(user_asset: str) -> str:
    raw = user_asset.strip()
    lower = raw.lower()
    if lower in ASSET_ALIASES:
        return ASSET_ALIASES[lower]

    for key in ALL_ASSETS:
        if key.lower() == lower:
            return key
    raise ValueError(f"Unsupported asset {user_asset!r}. Use --list-assets to view valid values.")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Forecast crypto and stock prices in USD or IDR, with CSV/XLSX export."
    )
    p.add_argument("--asset", default=DEFAULT_ASSET, help="Asset id/ticker, e.g. funtoken, bitcoin, GOTO.JK")
    p.add_argument("--currency", default=DEFAULT_CURRENCY, choices=list(SUPPORTED_CURRENCIES))
    p.add_argument("--horizon", type=int, default=30, help="Forecast horizon in days")
    p.add_argument(
        "--days",
        default=HISTORY_DAYS,
        help="History window; 'max' or number of days (string value)",
    )
    p.add_argument("--trials", type=int, default=OPTUNA_TRIALS, help="Optuna trials for XGBoost tuning")
    p.add_argument("--output-dir", default="outputs", help="Directory for exported files")
    p.add_argument("--export", choices=["none", "csv", "xlsx"], default="csv")
    p.add_argument("--json", action="store_true", help="Print full JSON result")
    p.add_argument("--list-assets", action="store_true", help="List supported assets and exit")
    p.add_argument(
        "--include-exog",
        dest="include_exog",
        action="store_true",
        default=INCLUDE_BTC_ETH,
        help="Include BTC/ETH exogenous features for crypto assets",
    )
    p.add_argument("--no-include-exog", dest="include_exog", action="store_false")
    return p


def _normalize_days(days: str) -> str:
    value = str(days).strip().lower()
    if value == "max":
        return "max"
    if value.isdigit() and int(value) > 0:
        return str(int(value))
    raise ValueError("--days must be 'max' or a positive integer (e.g. 365)")


def _print_assets() -> None:
    print("\nCrypto assets:")
    for aid, name in CRYPTO_ASSETS.items():
        print(f"  - {aid:12s} : {name}")
    print("\nStocks:")
    for ticker, name in STOCK_ASSETS.items():
        print(f"  - {ticker:12s} : {name}")
    print("")


async def _prepare_features(asset: str, currency: str, days: str, include_exog: bool) -> pd.DataFrame:
    main_df = await get_asset_data(asset, currency=currency, days=days)

    crypto_assets_lower = {k.lower() for k in CRYPTO_ASSETS}
    if asset.lower() in crypto_assets_lower and include_exog:
        btc_task = get_asset_data("bitcoin", currency=currency, days=days)
        eth_task = get_asset_data("ethereum", currency=currency, days=days)
        btc_df, eth_df = await asyncio.gather(btc_task, eth_task)
        return add_features(main_df, btc_df=btc_df, eth_df=eth_df)

    return add_features(main_df)


def _export_result(result: ForecastResult, export_mode: str, output_dir: str) -> list[str]:
    if export_mode == "none":
        return []

    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    prefix = f"{result.coin_id}_{result.vs_currency}"
    forecast_df = pd.DataFrame(result.predictions)
    history_df = pd.DataFrame(result.history_tail)
    diagnostics_df = pd.DataFrame([result.diagnostics])

    paths: list[str] = []
    if export_mode == "csv":
        forecast_path = out_dir / f"{prefix}_forecast.csv"
        history_path = out_dir / f"{prefix}_history.csv"
        diagnostics_path = out_dir / f"{prefix}_diagnostics.csv"
        forecast_df.to_csv(forecast_path, index=False)
        history_df.to_csv(history_path, index=False)
        diagnostics_df.to_csv(diagnostics_path, index=False)
        paths.extend([str(forecast_path), str(history_path), str(diagnostics_path)])
    else:
        xlsx_path = out_dir / f"{prefix}_report.xlsx"
        with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
            forecast_df.to_excel(writer, sheet_name="forecast", index=False)
            history_df.to_excel(writer, sheet_name="history", index=False)
            diagnostics_df.to_excel(writer, sheet_name="diagnostics", index=False)
        paths.append(str(xlsx_path))
    return paths


def _short_summary(result: ForecastResult, export_paths: list[str]) -> str:
    first = result.predictions[0]
    last = result.predictions[-1]
    summary = {
        "asset": result.coin_id,
        "currency": result.vs_currency,
        "horizon_days": result.horizon_days,
        "last_actual_date": result.last_date,
        "last_actual_price": result.last_price,
        "next_day_prediction": first["predicted_price"],
        "last_day_prediction": last["predicted_price"],
        "xgb_cv_rmse": result.diagnostics.get("xgb_cv_rmse"),
        "sarimax_aic": result.diagnostics.get("sarimax_aic"),
        "exports": export_paths,
    }
    return json.dumps(summary, indent=2)


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    asset = _resolve_asset(args.asset)
    days = _normalize_days(args.days)
    if args.horizon < MIN_HORIZON_DAYS:
        raise ValueError(f"--horizon must be >= {MIN_HORIZON_DAYS}")

    feat_df = await _prepare_features(
        asset=asset,
        currency=args.currency,
        days=days,
        include_exog=bool(args.include_exog),
    )
    if len(feat_df) < MIN_REQUIRED_ROWS:
        raise ValueError(
            f"Not enough feature rows ({len(feat_df)}). Minimum required is {MIN_REQUIRED_ROWS}."
        )

    usd_idr_rate = await get_usd_idr_rate()
    result = run_forecast(
        df_feat=feat_df,
        coin_id=asset,
        vs_currency=args.currency,
        horizon_days=args.horizon,
        optuna_trials=args.trials,
        usd_idr_rate=usd_idr_rate,
    )

    export_paths = _export_result(result, export_mode=args.export, output_dir=args.output_dir)
    gpu_available = is_gpu_available()
    gpu_tree_method = get_xgb_tree_method(gpu_available=gpu_available)
    payload = {
        **asdict(result),
        "export_paths": export_paths,
        "gpu_tree_method": gpu_tree_method,
        "gpu_available": gpu_available,
    }
    return payload


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if args.list_assets:
        _print_assets()
        return

    result_dict = asyncio.run(_run(args))
    if args.json:
        print(json.dumps(result_dict, indent=2))
        return

    result_field_names = {f.name for f in fields(ForecastResult)}
    result = ForecastResult(**{k: v for k, v in result_dict.items() if k in result_field_names})
    export_paths = result_dict.get("export_paths", [])
    print(_short_summary(result, export_paths))


if __name__ == "__main__":
    main()
