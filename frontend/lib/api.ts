/**
 * lib/api.ts — Typed API client for fun-forecasting backend.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
const API_V1 = `${API_BASE}/api/v1`

// ── Types ────────────────────────────────────────────────────────────────────

export interface AssetOut {
  id: string
  name: string
  asset_type: 'crypto' | 'stock'
  currency_native: string
}

export interface AssetListOut {
  crypto: AssetOut[]
  stocks: AssetOut[]
  total: number
}

export interface ForecastRequest {
  asset: string
  currency: 'usd' | 'idr'
  horizon_days: number
  history_days: string
  optuna_trials: number
  include_exog: boolean
}

export interface PredictionOut {
  date: string
  predicted_price: number
  predicted_price_usd: number | null
  predicted_price_idr: number | null
  predicted_return: number | null
  upper_bound: number | null
  lower_bound: number | null
  xgb_price: number | null
  sarimax_price: number | null
  prophet_price: number | null
  lstm_price: number | null
}

export interface JobStatusOut {
  job_id: string
  status: 'pending' | 'running' | 'done' | 'failed'
  asset: string
  currency: string
  horizon_days: number
  created_at: string
  completed_at: string | null
  error_message: string | null
}

export interface ForecastResultOut {
  job_id: string
  asset: string
  currency: string
  horizon_days: number
  status: string
  last_date: string | null
  last_price: number | null
  last_price_idr: number | null
  diagnostics: Record<string, unknown>
  history_tail: Array<{ date: string; price: number }>
  predictions: PredictionOut[]
  created_at: string
  completed_at: string | null
}

export interface ProgressEvent {
  job_id: string
  event: string
  message: string
  progress: number
  data?: Record<string, unknown>
}

// ── Asset endpoints ───────────────────────────────────────────────────────────

export async function listAssets(): Promise<AssetListOut> {
  const res = await fetch(`${API_V1}/assets`)
  if (!res.ok) throw new Error(`Failed to list assets: ${res.statusText}`)
  return res.json()
}

export async function getAssetPrice(assetId: string, currency = 'usd'): Promise<{ asset: string; currency: string; price: number }> {
  const res = await fetch(`${API_V1}/assets/${assetId}/price?currency=${currency}`)
  if (!res.ok) throw new Error(`Failed to get price: ${res.statusText}`)
  return res.json()
}

// ── Forecast endpoints ────────────────────────────────────────────────────────

export async function createForecast(req: ForecastRequest): Promise<JobStatusOut> {
  const res = await fetch(`${API_V1}/forecasts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) throw new Error(`Failed to create forecast: ${res.statusText}`)
  return res.json()
}

export async function getForecast(jobId: string): Promise<ForecastResultOut> {
  const res = await fetch(`${API_V1}/forecasts/${jobId}`)
  if (!res.ok) throw new Error(`Failed to get forecast: ${res.statusText}`)
  return res.json()
}

export async function listForecasts(limit = 20): Promise<JobStatusOut[]> {
  const res = await fetch(`${API_V1}/forecasts?limit=${limit}`)
  if (!res.ok) throw new Error(`Failed to list forecasts: ${res.statusText}`)
  return res.json()
}

export async function getJobStatus(jobId: string): Promise<JobStatusOut> {
  const res = await fetch(`${API_V1}/jobs/${jobId}/status`)
  if (!res.ok) throw new Error(`Failed to get job status: ${res.statusText}`)
  return res.json()
}

// ── SSE hook ──────────────────────────────────────────────────────────────────

/**
 * Subscribe to job progress events via Server-Sent Events.
 * Returns a cleanup function to close the connection.
 */
export function subscribeJobProgress(
  jobId: string,
  onEvent: (evt: ProgressEvent) => void,
  onDone?: () => void,
  onError?: (err: Event) => void,
): () => void {
  const url = `${API_V1}/jobs/${jobId}/stream`
  const es = new EventSource(url)

  es.onmessage = (e) => {
    try {
      const data: ProgressEvent = JSON.parse(e.data)
      onEvent(data)
      if (data.event === 'done' || data.event === 'error') {
        es.close()
        onDone?.()
      }
    } catch {
      // ignore parse errors
    }
  }

  es.onerror = (err) => {
    onError?.(err)
    es.close()
  }

  return () => es.close()
}

// ── Utils ─────────────────────────────────────────────────────────────────────

export function formatPrice(price: number | null | undefined, currency: string): string {
  if (price == null) return '—'
  const locale = currency === 'idr' ? 'id-ID' : 'en-US'
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: currency.toUpperCase(),
    maximumFractionDigits: currency === 'idr' ? 0 : 6,
  }).format(price)
}
