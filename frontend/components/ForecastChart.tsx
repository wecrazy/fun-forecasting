'use client'

import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from 'recharts'
import { useState } from 'react'
import type { PredictionOut } from '@/lib/api'

interface HistoryPoint { date: string; price: number }

interface Props {
  historyTail: HistoryPoint[]
  predictions: PredictionOut[]
  currency: string
}

type ModelKey = 'xgb_price' | 'sarimax_price' | 'prophet_price' | 'lstm_price'

const MODEL_CONFIG: { key: ModelKey; label: string; color: string }[] = [
  { key: 'xgb_price', label: 'XGBoost', color: '#f97316' },
  { key: 'sarimax_price', label: 'SARIMAX', color: '#60a5fa' },
  { key: 'prophet_price', label: 'Prophet', color: '#a78bfa' },
  { key: 'lstm_price', label: 'LSTM', color: '#34d399' },
]

export default function ForecastChart({ historyTail, predictions, currency }: Props) {
  const [visibleModels, setVisibleModels] = useState<Set<ModelKey>>(
    new Set(['xgb_price', 'sarimax_price'])
  )

  function toggleModel(key: ModelKey) {
    setVisibleModels((prev) => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })
  }

  // Combine history + forecast into one data array
  const historyData = historyTail.map((h) => ({
    date: h.date,
    history: h.price,
    ensemble: undefined as number | undefined,
    upper: undefined as number | undefined,
    lower: undefined as number | undefined,
    xgb_price: undefined as number | undefined,
    sarimax_price: undefined as number | undefined,
    prophet_price: undefined as number | undefined,
    lstm_price: undefined as number | undefined,
  }))

  const forecastData = predictions.map((p) => ({
    date: p.date,
    history: undefined as number | undefined,
    ensemble: p.predicted_price,
    upper: p.upper_bound ?? undefined,
    lower: p.lower_bound ?? undefined,
    xgb_price: p.xgb_price ?? undefined,
    sarimax_price: p.sarimax_price ?? undefined,
    prophet_price: p.prophet_price ?? undefined,
    lstm_price: p.lstm_price ?? undefined,
  }))

  const data = [...historyData, ...forecastData]
  const dividerDate = historyTail[historyTail.length - 1]?.date

  const currencySymbol = currency === 'idr' ? 'Rp' : '$'

  function formatTick(v: number): string {
    if (v >= 1_000_000) return `${currencySymbol}${(v / 1_000_000).toFixed(1)}M`
    if (v >= 1_000) return `${currencySymbol}${(v / 1_000).toFixed(0)}K`
    return `${currencySymbol}${v.toFixed(4)}`
  }

  return (
    <div className="space-y-4">
      {/* Model toggles */}
      <div className="flex flex-wrap gap-2">
        {MODEL_CONFIG.map(({ key, label, color }) => (
          <button
            key={key}
            onClick={() => toggleModel(key)}
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
              visibleModels.has(key)
                ? 'border-transparent text-white'
                : 'border-gray-700 text-gray-500 bg-transparent'
            }`}
            style={visibleModels.has(key) ? { backgroundColor: `${color}22`, borderColor: color, color } : {}}
          >
            <span
              className="h-2 w-2 rounded-full"
              style={{ backgroundColor: visibleModels.has(key) ? color : '#4b5563' }}
            />
            {label}
          </button>
        ))}
      </div>

      {/* Chart */}
      <ResponsiveContainer width="100%" height={420}>
        <ComposedChart data={data} margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 11, fill: '#6b7280' }}
            tickLine={false}
            tickFormatter={(v: string) => v.slice(5)} // MM-DD
          />
          <YAxis
            tick={{ fontSize: 11, fill: '#6b7280' }}
            tickLine={false}
            tickFormatter={formatTick}
            width={70}
          />
          <Tooltip
            contentStyle={{ backgroundColor: '#111827', border: '1px solid #374151', borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: '#9ca3af' }}
            formatter={(value: number, name: string) => [`${currencySymbol}${value?.toFixed(6)}`, name]}
          />
          <Legend wrapperStyle={{ fontSize: 12, color: '#9ca3af' }} />

          {/* Confidence band */}
          <Area
            dataKey="upper"
            stroke="none"
            fill="#3b82f6"
            fillOpacity={0.08}
            name="Upper bound"
            legendType="none"
            isAnimationActive={false}
          />
          <Area
            dataKey="lower"
            stroke="none"
            fill="#3b82f6"
            fillOpacity={0.08}
            name="Lower bound"
            legendType="none"
            isAnimationActive={false}
          />

          {/* Historical prices */}
          <Line
            dataKey="history"
            stroke="#6b7280"
            strokeWidth={1.5}
            dot={false}
            name="History"
            connectNulls={false}
          />

          {/* Ensemble forecast */}
          <Line
            dataKey="ensemble"
            stroke="#3b82f6"
            strokeWidth={2.5}
            dot={false}
            name="Ensemble"
            connectNulls={false}
            strokeDasharray="0"
          />

          {/* Per-model traces */}
          {MODEL_CONFIG.map(({ key, label, color }) =>
            visibleModels.has(key) ? (
              <Line
                key={key}
                dataKey={key}
                stroke={color}
                strokeWidth={1}
                strokeDasharray="4 2"
                dot={false}
                name={label}
                connectNulls={false}
                opacity={0.7}
              />
            ) : null
          )}

          {/* Divider between history and forecast */}
          {dividerDate && (
            <ReferenceLine
              x={dividerDate}
              stroke="#4b5563"
              strokeDasharray="4 4"
              label={{ value: 'Forecast start', fill: '#6b7280', fontSize: 10, position: 'top' }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
