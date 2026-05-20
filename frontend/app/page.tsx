import { listForecasts, listAssets, formatPrice } from '@/lib/api'
import Link from 'next/link'

export const revalidate = 30

export default async function DashboardPage() {
  const [assetsData, recentJobs] = await Promise.all([
    listAssets().catch(() => ({ crypto: [], stocks: [], total: 0 })),
    listForecasts(5).catch(() => []),
  ])

  const statusColor: Record<string, string> = {
    done: 'text-green-400 bg-green-400/10',
    running: 'text-yellow-400 bg-yellow-400/10',
    pending: 'text-blue-400 bg-blue-400/10',
    failed: 'text-red-400 bg-red-400/10',
  }

  return (
    <div className="space-y-10">
      {/* Hero */}
      <section className="text-center py-10">
        <h1 className="text-4xl font-extrabold tracking-tight text-white mb-3">
          Multi-Asset Price Forecasting
        </h1>
        <p className="text-gray-400 text-lg max-w-2xl mx-auto">
          Ensemble of XGBoost, SARIMAX, Prophet &amp; LSTM — powered by FastAPI + Celery.
        </p>
        <div className="mt-6 flex justify-center gap-4">
          <Link
            href="/forecast"
            className="rounded-lg bg-blue-600 px-6 py-3 font-semibold text-white hover:bg-blue-700 transition-colors"
          >
            New Forecast →
          </Link>
          <Link
            href="/assets"
            className="rounded-lg border border-gray-700 px-6 py-3 font-semibold text-gray-300 hover:bg-gray-800 transition-colors"
          >
            Browse Assets
          </Link>
        </div>
      </section>

      {/* Summary cards */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Crypto Assets', value: assetsData.crypto.length, icon: '₿' },
          { label: 'Stock Assets', value: assetsData.stocks.length, icon: '📊' },
          { label: 'Total Assets', value: assetsData.total, icon: '🌐' },
          { label: 'Recent Jobs', value: recentJobs.length, icon: '⚡' },
        ].map((card) => (
          <div key={card.label} className="rounded-xl border border-gray-800 bg-gray-900 p-5">
            <div className="text-2xl mb-1">{card.icon}</div>
            <div className="text-3xl font-bold text-white">{card.value}</div>
            <div className="text-sm text-gray-500 mt-1">{card.label}</div>
          </div>
        ))}
      </section>

      {/* Recent forecast jobs */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-white">Recent Forecasts</h2>
          <Link href="/forecast" className="text-sm text-blue-400 hover:text-blue-300">
            + New
          </Link>
        </div>
        {recentJobs.length === 0 ? (
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-10 text-center text-gray-500">
            No forecasts yet. <Link href="/forecast" className="text-blue-400">Create one →</Link>
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-gray-800">
            <table className="w-full text-sm">
              <thead className="bg-gray-900 text-gray-500 uppercase text-xs tracking-wider">
                <tr>
                  <th className="px-4 py-3 text-left">Asset</th>
                  <th className="px-4 py-3 text-left">Currency</th>
                  <th className="px-4 py-3 text-left">Horizon</th>
                  <th className="px-4 py-3 text-left">Status</th>
                  <th className="px-4 py-3 text-left">Created</th>
                  <th className="px-4 py-3 text-left"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800 bg-gray-950">
                {recentJobs.map((job) => (
                  <tr key={job.job_id} className="hover:bg-gray-900 transition-colors">
                    <td className="px-4 py-3 font-medium text-white">{job.asset}</td>
                    <td className="px-4 py-3 text-gray-400 uppercase">{job.currency}</td>
                    <td className="px-4 py-3 text-gray-400">{job.horizon_days}d</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor[job.status] || ''}`}>
                        {job.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">
                      {new Date(job.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3">
                      <Link
                        href={`/forecast/${job.job_id}`}
                        className="text-blue-400 hover:text-blue-300 text-xs"
                      >
                        View →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Models overview */}
      <section>
        <h2 className="text-xl font-semibold text-white mb-4">Forecasting Models</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { name: 'XGBoost', desc: 'Optuna-tuned gradient boosting with walk-forward CV', color: 'border-orange-500/40 bg-orange-500/5' },
            { name: 'SARIMAX', desc: 'Seasonal ARIMA with exogenous regressors (BTC/ETH)', color: 'border-blue-500/40 bg-blue-500/5' },
            { name: 'Prophet', desc: 'Facebook Prophet with weekly/yearly seasonality', color: 'border-purple-500/40 bg-purple-500/5' },
            { name: 'LSTM', desc: 'Stacked LSTM for sequence-to-sequence forecasting', color: 'border-green-500/40 bg-green-500/5' },
          ].map((m) => (
            <div key={m.name} className={`rounded-xl border p-4 ${m.color}`}>
              <div className="font-semibold text-white mb-1">{m.name}</div>
              <div className="text-xs text-gray-400">{m.desc}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
