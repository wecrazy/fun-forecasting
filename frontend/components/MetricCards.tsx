import type { ForecastResultOut, PredictionOut } from '@/lib/api'
import { formatPrice } from '@/lib/api'

interface Props {
  result: ForecastResultOut
  nextDay: PredictionOut | undefined
  lastDay: PredictionOut | undefined
}

export default function MetricCards({ result, nextDay, lastDay }: Props) {
  const diag = result.diagnostics

  const cards = [
    {
      label: 'Last Actual Price',
      value: formatPrice(result.last_price, result.currency),
      sub: result.last_date ?? '—',
      color: 'border-gray-700',
    },
    {
      label: 'Next Day Forecast',
      value: formatPrice(nextDay?.predicted_price, result.currency),
      sub: nextDay?.date ?? '—',
      color: 'border-blue-500/40',
    },
    {
      label: `${result.horizon_days}d Forecast`,
      value: formatPrice(lastDay?.predicted_price, result.currency),
      sub: lastDay?.date ?? '—',
      color: 'border-purple-500/40',
    },
    {
      label: 'XGBoost CV-RMSE',
      value: typeof diag.xgb_cv_rmse === 'number' ? diag.xgb_cv_rmse.toFixed(6) : '—',
      sub: 'log-return scale',
      color: 'border-orange-500/40',
    },
    {
      label: 'SARIMAX AIC',
      value: typeof diag.sarimax_aic === 'number' ? diag.sarimax_aic.toFixed(2) : '—',
      sub: 'lower is better',
      color: 'border-blue-500/40',
    },
    {
      label: 'Prophet MAPE',
      value: typeof diag.prophet_mape === 'number' ? `${(diag.prophet_mape as number * 100).toFixed(2)}%` : '—',
      sub: 'mean abs % error',
      color: 'border-purple-500/40',
    },
  ]

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      {cards.map((c) => (
        <div key={c.label} className={`rounded-xl border bg-gray-900 p-4 ${c.color}`}>
          <div className="text-xs text-gray-500 truncate mb-1">{c.label}</div>
          <div className="text-lg font-bold text-white truncate">{c.value}</div>
          <div className="text-xs text-gray-600 mt-0.5 truncate">{c.sub}</div>
        </div>
      ))}
    </div>
  )
}
