# FUN Forecasting (Crypto + Stocks, USD/IDR)

[![CI](https://github.com/wecrazy/fun-forecasting/actions/workflows/ci.yml/badge.svg)](https://github.com/wecrazy/fun-forecasting/actions/workflows/ci.yml)

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

- Python **3.10+**
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
cd /path/to/fun-forecasting
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

## CI/CD

### Continuous Integration (CI)

Runs automatically on every push and pull request:
1. Sets up Python 3.11
2. Installs `requirements.txt`
3. Runs a smoke test: `python main.py --list-assets`

### Continuous Deployment (CD)

Triggered by:
- **Manual run** via *Actions → CD → Run workflow* (choose asset, currency, horizon, export)
- **Automatic** on every push to `main` after CI passes

The CD job:
1. Installs dependencies
2. Builds a temporary `.env` inside the runner from GitHub Secrets (never committed)
3. Runs the forecast and uploads results as a GitHub Actions artifact (30-day retention)

### Required GitHub Secrets

Set these in **Settings → Secrets and variables → Actions**:

| Secret | Required | Description |
|---|---|---|
| `COINGECKO_API_KEY` | Yes | CoinGecko API key |
| `COINMARKETCAP_API_KEY` | No | CoinMarketCap API key (fallback) |
| `OPTUNA_TRIALS` | No | Override Optuna trial count (default: 60) |
| `USE_GPU` | No | `auto` / `true` / `false` (default: auto) |

> **Never** commit a real `.env` file. The `.github/workflows/cd.yml` generates one at
> runtime inside the runner from the secrets above.

### GitHub Environment (optional)

To add deployment protection rules (e.g. require a manual approval before CD runs):
1. Go to **Settings → Environments → New environment**
2. Name it `production`
3. Add required reviewers or branch restrictions as needed

### Extending the Deploy Step

At the bottom of `.github/workflows/cd.yml` there is a commented-out block showing how
to add a real deploy step (Render, Railway, VPS, etc.). Add your target there.

---

## Notes

- Currency choices are intentionally limited to **USD** and **IDR**.
- For `.JK` stocks, native price is IDR; conversion to USD uses live USD/IDR rate.
- For crypto, CoinGecko IDR pricing is supported directly.
- If live FX retrieval fails, the system falls back to a default USD/IDR rate from config.
