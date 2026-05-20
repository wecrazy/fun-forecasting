import { getForecast, formatPrice } from '@/lib/api'
import ForecastChart from '@/components/ForecastChart'
import MetricCards from '@/components/MetricCards'
import JobStatusBadge from '@/components/JobStatusBadge'
import JobPoller from '@/components/JobPoller'
import Link from 'next/link'

interface Props {
  params: { jobId: string }
}

export default async function ForecastResultPage({ params }: Props) {
  const { jobId } = params
  let result = null
  let fetchError: string | null = null

  try {
    result = await getForecast(jobId)
  } catch (err: unknown) {
    fetchError = err instanceof Error ? err.message : 'Failed to load forecast'
  }

  if (fetchError || !result) {
    return (
      <div className="text-center py-20 space-y-4">
        <div className="text-5xl">⚠️</div>
        <h1 className="text-2xl font-bold text-white">Forecast Not Found</h1>
        <p className="text-gray-400">{fetchError}</p>
        <Link href="/" className="text-blue-400 hover:text-blue-300">← Back to Dashboard</Link>
      </div>
    )
  }

  if (result.status === 'pending' || result.status === 'running') {
    return (
      <div className="text-center py-20 space-y-4">
        {/* Client-side SSE poller — refreshes the page when the job completes */}
        <JobPoller jobId={jobId} status={result.status} />
        <div className="text-5xl animate-spin">⏳</div>
        <h1 className="text-2xl font-bold text-white">Forecast In Progress</h1>
        <p className="text-gray-400">
          Job {jobId} is currently <span className="font-medium text-yellow-400">{result.status}</span>.
          This page will update automatically when the forecast completes.
        </p>
        <Link href="/" className="text-sm text-gray-500 hover:text-gray-400">
          ← Back to Dashboard
        </Link>
      </div>
    )
  }

  if (result.status === 'failed') {
    return (
      <div className="text-center py-20 space-y-4">
        <div className="text-5xl">❌</div>
        <h1 className="text-2xl font-bold text-white">Forecast Failed</h1>
        <p className="text-gray-400">{result.diagnostics?.error as string ?? 'Unknown error'}</p>
        <Link href="/forecast" className="text-blue-400 hover:text-blue-300">Try Again →</Link>
      </div>
    )
  }

  const nextDay = result.predictions[0]
  const lastDay = result.predictions[result.predictions.length - 1]

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-3xl font-bold text-white uppercase">{result.asset}</h1>
            <JobStatusBadge status={result.status} />
          </div>
          <p className="text-gray-400">
            {result.horizon_days}-day forecast · Currency: <span className="uppercase font-medium text-white">{result.currency}</span>
          </p>
          {result.last_date && (
            <p className="text-sm text-gray-500 mt-1">
              Last actual: {result.last_date} @ {formatPrice(result.last_price, result.currency)}
            </p>
          )}
        </div>
        <div className="flex gap-3">
          <Link
            href="/forecast"
            className="rounded-lg border border-gray-700 px-4 py-2 text-sm font-medium text-gray-300 hover:bg-gray-800 transition-colors"
          >
            + New Forecast
          </Link>
          <Link
            href="/"
            className="rounded-lg border border-gray-700 px-4 py-2 text-sm font-medium text-gray-300 hover:bg-gray-800 transition-colors"
          >
            ← Dashboard
          </Link>
        </div>
      </div>

      {/* Metric cards */}
      <MetricCards
        result={result}
        nextDay={nextDay}
        lastDay={lastDay}
      />

      {/* Chart */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-6">
        <h2 className="text-lg font-semibold text-white mb-4">Price Forecast</h2>
        <ForecastChart
          historyTail={result.history_tail}
          predictions={result.predictions}
          currency={result.currency}
        />
      </div>

      {/* Diagnostics accordion */}
      <details className="rounded-xl border border-gray-800 bg-gray-900">
        <summary className="cursor-pointer px-6 py-4 text-sm font-medium text-gray-300 hover:text-white">
          🔬 Model Diagnostics
        </summary>
        <div className="px-6 pb-6">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4">
            {Object.entries(result.diagnostics)
              .filter(([, v]) => typeof v === 'number')
              .map(([k, v]) => (
                <div key={k} className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2">
                  <div className="text-xs text-gray-500 truncate">{k}</div>
                  <div className="text-sm font-mono text-white">{(v as number).toPrecision(6)}</div>
                </div>
              ))}
          </div>
          <pre className="text-xs text-gray-500 overflow-auto max-h-40 font-mono">
            {JSON.stringify(result.diagnostics, null, 2)}
          </pre>
        </div>
      </details>
    </div>
  )
}
