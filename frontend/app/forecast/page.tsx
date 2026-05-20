'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { createForecast, type ForecastRequest, subscribeJobProgress, type ProgressEvent } from '@/lib/api'

const CRYPTO_ASSETS = ['funtoken', 'bitcoin', 'ethereum', 'binancecoin', 'solana']
const STOCK_ASSETS = ['GOTO.JK', 'BBCA.JK', 'TLKM.JK', 'BBRI.JK', 'ASII.JK']

export default function ForecastPage() {
  const router = useRouter()
  const [form, setForm] = useState<ForecastRequest>({
    asset: 'funtoken',
    currency: 'usd',
    horizon_days: 30,
    history_days: 'max',
    optuna_trials: 30,
    include_exog: true,
  })
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState<ProgressEvent | null>(null)
  const [error, setError] = useState<string | null>(null)

  function handleChange(key: keyof ForecastRequest, value: unknown) {
    setForm((f) => ({ ...f, [key]: value }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setProgress(null)

    try {
      const job = await createForecast(form)
      // Start listening to SSE progress
      const cleanup = subscribeJobProgress(
        job.job_id,
        (evt) => setProgress(evt),
        () => {
          cleanup()
          router.push(`/forecast/${job.job_id}`)
        },
        () => {
          setError('Connection lost. Redirecting…')
          setTimeout(() => router.push(`/forecast/${job.job_id}`), 1500)
        },
      )
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unknown error')
      setLoading(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">New Forecast</h1>
        <p className="text-gray-400 mt-1">Configure parameters and submit a forecasting job.</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6 rounded-xl border border-gray-800 bg-gray-900 p-6">
        {/* Asset selector */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">Asset</label>
          <select
            value={form.asset}
            onChange={(e) => handleChange('asset', e.target.value)}
            className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
          >
            <optgroup label="Cryptocurrency">
              {CRYPTO_ASSETS.map((a) => <option key={a} value={a}>{a}</option>)}
            </optgroup>
            <optgroup label="IDX Stocks">
              {STOCK_ASSETS.map((a) => <option key={a} value={a}>{a}</option>)}
            </optgroup>
          </select>
        </div>

        {/* Currency */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">Currency</label>
          <div className="flex gap-3">
            {(['usd', 'idr'] as const).map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => handleChange('currency', c)}
                className={`flex-1 rounded-lg border py-2 text-sm font-medium uppercase transition-colors ${
                  form.currency === c
                    ? 'border-blue-500 bg-blue-600 text-white'
                    : 'border-gray-700 bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {c}
              </button>
            ))}
          </div>
        </div>

        {/* Horizon */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Forecast Horizon: <span className="text-blue-400">{form.horizon_days} days</span>
          </label>
          <input
            type="range" min={1} max={365} step={1}
            value={form.horizon_days}
            onChange={(e) => handleChange('horizon_days', parseInt(e.target.value))}
            className="w-full accent-blue-500"
          />
          <div className="flex justify-between text-xs text-gray-600 mt-1">
            <span>1d</span><span>365d</span>
          </div>
        </div>

        {/* History */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">History Window</label>
          <select
            value={form.history_days}
            onChange={(e) => handleChange('history_days', e.target.value)}
            className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
          >
            <option value="max">Max (all available)</option>
            <option value="365">1 Year</option>
            <option value="730">2 Years</option>
            <option value="1825">5 Years</option>
          </select>
        </div>

        {/* Optuna trials */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Optuna Trials (XGBoost): <span className="text-blue-400">{form.optuna_trials}</span>
          </label>
          <input
            type="range" min={5} max={200} step={5}
            value={form.optuna_trials}
            onChange={(e) => handleChange('optuna_trials', parseInt(e.target.value))}
            className="w-full accent-blue-500"
          />
          <div className="flex justify-between text-xs text-gray-600 mt-1">
            <span>5 (fast)</span><span>200 (best)</span>
          </div>
        </div>

        {/* Include exog */}
        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            id="exog"
            checked={form.include_exog}
            onChange={(e) => handleChange('include_exog', e.target.checked)}
            className="h-4 w-4 accent-blue-500"
          />
          <label htmlFor="exog" className="text-sm text-gray-300">
            Include BTC/ETH as exogenous features (for crypto assets)
          </label>
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-lg bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        )}

        {/* Progress */}
        {loading && progress && (
          <div className="rounded-lg border border-blue-500/30 bg-blue-500/5 px-4 py-3 space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-blue-300">{progress.message}</span>
              <span className="text-gray-500">{Math.round(progress.progress * 100)}%</span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-gray-700">
              <div
                className="h-1.5 rounded-full bg-blue-500 transition-all duration-300"
                style={{ width: `${progress.progress * 100}%` }}
              />
            </div>
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-blue-600 py-3 font-semibold text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? '⏳ Running forecast…' : '🚀 Run Forecast'}
        </button>
      </form>
    </div>
  )
}
