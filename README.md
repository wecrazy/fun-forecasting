# 📈 Fun-Forecasting v2

[![CI](https://github.com/wecrazy/fun-forecasting/actions/workflows/ci.yml/badge.svg)](https://github.com/wecrazy/fun-forecasting/actions/workflows/ci.yml)

A production-grade, full-stack multi-asset price forecasting platform.

| Layer | Technology |
|---|---|
| **Frontend** | Next.js 15 (App Router) + Tailwind CSS + Recharts |
| **Backend API** | FastAPI + Uvicorn |
| **Task Queue** | Celery + Redis (broker + result backend) |
| **ML Models** | XGBoost (Optuna) · SARIMAX · Facebook Prophet · PyTorch LSTM |
| **Feature Engineering** | Pandas + Polars (fast path) |
| **Database** | PostgreSQL (async SQLAlchemy + Alembic) |
| **Cache** | Redis (pub/sub for SSE, cache) |
| **Deployment** | Docker Compose (dev) · Kubernetes (prod) |

---

## Architecture

```
Browser
  └── Next.js (port 3000)
        │  REST + SSE
        ▼
  FastAPI (port 8000)
        │  enqueue tasks
        ▼
  Celery Workers
        │  read/write
        ├── PostgreSQL  ← jobs, predictions, assets
        └── Redis       ← broker, result backend, SSE pub/sub
```

---

## Quick Start (Docker Compose)

```bash
# 1. Copy env file
cp .env.example .env
# Edit .env: add COINGECKO_API_KEY if you have one

# 2. Start all services
docker compose up -d

# 3. Run DB migrations
docker compose exec backend alembic upgrade head

# 4. Open the app
open http://localhost:3000
# API docs:
open http://localhost:8000/docs
# Flower (Celery monitoring):
open http://localhost:5555
```

---

## Local Development (without Docker)

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Start FastAPI
uvicorn app.main:app --reload --port 8000

# Start Celery worker (separate terminal)
celery -A app.tasks.celery_app worker --loglevel=info --queues=forecasting,celery

# Run migrations
alembic upgrade head
```

### Frontend

```bash
cd frontend
npm install
npm run dev   # http://localhost:3000
```

### Prerequisites

- PostgreSQL running locally (or via Docker: `docker run -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16-alpine`)
- Redis running locally (or via Docker: `docker run -p 6379:6379 redis:7-alpine`)

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/api/v1/assets` | List all supported assets |
| `GET` | `/api/v1/assets/{id}/price` | Live price for asset |
| `POST` | `/api/v1/forecasts` | Submit new forecast job |
| `GET` | `/api/v1/forecasts` | List recent jobs |
| `GET` | `/api/v1/forecasts/{id}` | Get full result |
| `GET` | `/api/v1/jobs/{id}/status` | Job status |
| `GET` | `/api/v1/jobs/{id}/stream` | SSE progress stream |

Full interactive docs: `http://localhost:8000/docs`

---

## Supported Assets

**Cryptocurrency** (via CoinGecko)
- FUNToken (`funtoken`)
- Bitcoin (`bitcoin`)
- Ethereum (`ethereum`)
- BNB (`binancecoin`)
- Solana (`solana`)

**Indonesian Stocks** (via Yahoo Finance)
- Gojek Tokopedia (`GOTO.JK`)
- Bank Central Asia (`BBCA.JK`)
- Telkom Indonesia (`TLKM.JK`)
- Bank Rakyat Indonesia (`BBRI.JK`)
- Astra International (`ASII.JK`)

---

## Forecasting Models

### XGBoost + Optuna
Walk-forward cross-validation with Optuna hyperparameter search. Iterative multi-step forecasting on log-returns. GPU-accelerated when CUDA is available.

### SARIMAX
Seasonal ARIMA(2,0,2) with exogenous regressors (BTC/ETH returns, momentum, RSI, MACD, volume).

### Prophet
Facebook Prophet with weekly + yearly seasonality. Handles holidays and trend changepoints automatically.

### LSTM (PyTorch)
Stacked 2-layer LSTM trained on 30-day rolling windows of all engineered features. Runs on GPU when available.

### Ensemble
All models are combined via **inverse-error dynamic weighting**: models with lower CV-RMSE / residual std receive proportionally higher weights.

---

## Kubernetes Deployment

```bash
# Apply all manifests
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/postgres/
kubectl apply -f k8s/redis/
kubectl apply -f k8s/backend/
kubectl apply -f k8s/worker/
kubectl apply -f k8s/frontend/

# Check rollout
kubectl rollout status deployment/backend -n fun-forecasting
kubectl rollout status deployment/worker -n fun-forecasting
kubectl rollout status deployment/frontend -n fun-forecasting
```

> **Before deploying**: update `k8s/backend/configmap.yaml` secrets and `k8s/frontend/deployment.yaml` `NEXT_PUBLIC_API_URL` to your actual domain.

---

## Environment Variables

See [`.env.example`](.env.example) for all configurable options.

---

## Project Structure

```
fun-forecasting/
├── backend/                  # FastAPI + Celery Python app
│   ├── app/
│   │   ├── main.py           # FastAPI factory
│   │   ├── config.py         # Pydantic Settings
│   │   ├── database.py       # Async SQLAlchemy
│   │   ├── models/           # ORM models
│   │   ├── schemas/          # Pydantic schemas
│   │   ├── api/v1/           # REST endpoints
│   │   ├── services/         # Data client + Redis cache
│   │   └── tasks/
│   │       ├── celery_app.py
│   │       ├── forecast_task.py
│   │       └── pipeline/
│   │           ├── features.py        # Polars + Pandas feature eng
│   │           └── models/            # XGB · SARIMAX · Prophet · LSTM · Ensemble
│   ├── alembic/              # DB migrations
│   └── requirements.txt
│
├── frontend/                 # Next.js 15 app
│   ├── app/                  # App Router pages
│   ├── components/           # ForecastChart, MetricCards, etc.
│   └── lib/api.ts            # Typed API client + SSE hook
│
├── docker/                   # Dockerfiles + Nginx config
├── docker-compose.yml        # Local dev
├── docker-compose.prod.yml   # Production overrides
└── k8s/                      # Kubernetes manifests
```

---

## Legacy CLI

The original CLI is preserved and still works from the repo root:

```bash
pip install -r requirements.txt   # original requirements
python main.py --asset funtoken --horizon 30 --currency usd
```
