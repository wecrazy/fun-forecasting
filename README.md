# FUN Forecasting (Crypto + Stocks, USD/IDR)

Forecasting project in Python for:
- **FUNToken** (primary target)
- Other crypto assets (BTC, ETH, BNB, SOL, etc.)
- Indonesian stocks (e.g. **GOTO.JK**, BBCA.JK, TLKM.JK, BBRI.JK, ASII.JK)
- Output in **USD** or **IDR**
- Export forecast reports to **CSV** or **Excel (.xlsx)**

---

## Features

- Unified market data client:
  - CoinGecko for crypto history + live price
  - CoinMarketCap fallback for live crypto price
  - Yahoo Finance (`yfinance`) for stock data
- Feature engineering:
  - Log returns, momentum, volatility windows
  - RSI, MACD, Bollinger Bands
  - Calendar effects
  - Optional BTC/ETH exogenous factors
- Forecasting model:
  - XGBoost with Optuna tuning
  - SARIMAX model
  - Ensemble output + confidence bands
- GPU-aware:
  - Auto-detects CUDA and uses XGBoost GPU mode when available

---

## System Requirements

- Python **3.10+** (recommended 3.11/3.12)
- pip
- Internet access for market data APIs

Optional for GPU acceleration:
- NVIDIA GPU + CUDA-compatible environment
- Optional `torch` install for faster CUDA detection:
  ```bash
  pip install torch
  ```

---

## Installation

```bash
cd /home/runner/work/fun-forecasting/fun-forecasting
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Environment Setup

1. Copy the env template:
   ```bash
   cp .env.example .env
   ```
2. Fill your API keys in `.env`:
   - `COINGECKO_API_KEY`
   - `COINMARKETCAP_API_KEY` (optional fallback)

> Keep `.env` private. It is git-ignored by default.

---

## Usage

### List supported assets
```bash
python main.py --list-assets
```

### Forecast FUNToken in USD (30 days), export CSV
```bash
python main.py --asset funtoken --currency usd --horizon 30 --export csv
```

### Forecast FUNToken in IDR, export Excel
```bash
python main.py --asset funtoken --currency idr --horizon 30 --export xlsx
```

### Forecast Indonesian stock (GOTO) in IDR
```bash
python main.py --asset GOTO.JK --currency idr --horizon 30 --export csv
```

### Quick aliases
- `fun` → `funtoken`
- `btc` → `bitcoin`
- `goto` → `GOTO.JK`

Example:
```bash
python main.py --asset fun --currency usd --horizon 14
```

### JSON output
```bash
python main.py --asset funtoken --currency usd --json --export none
```

---

## Export Outputs

With `--export csv`:
- `outputs/<asset>_<currency>_forecast.csv`
- `outputs/<asset>_<currency>_history.csv`
- `outputs/<asset>_<currency>_diagnostics.csv`

With `--export xlsx`:
- `outputs/<asset>_<currency>_report.xlsx`
  - Sheets: `forecast`, `history`, `diagnostics`

---

## Notes

- Currency choices are intentionally limited to **USD** and **IDR**.
- For `.JK` stocks, native price is IDR; conversion to USD uses live USD/IDR rate.
- For crypto, CoinGecko IDR pricing is supported directly.
