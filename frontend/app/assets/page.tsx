import { listAssets, getAssetPrice } from '@/lib/api'
import Link from 'next/link'

export const revalidate = 60

export default async function AssetsPage() {
  const assets = await listAssets().catch(() => ({ crypto: [], stocks: [], total: 0 }))

  const allAssets = [...assets.crypto, ...assets.stocks]

  // Fetch live prices in parallel (best-effort)
  const prices = await Promise.allSettled(
    allAssets.map((a) => getAssetPrice(a.id, a.currency_native))
  )

  const priceMap: Record<string, number | null> = {}
  allAssets.forEach((a, i) => {
    const result = prices[i]
    priceMap[a.id] = result.status === 'fulfilled' ? result.value.price : null
  })

  function formatP(price: number | null, currency: string): string {
    if (price == null) return '—'
    const locale = currency === 'idr' ? 'id-ID' : 'en-US'
    return new Intl.NumberFormat(locale, {
      style: 'currency',
      currency: currency.toUpperCase(),
      maximumFractionDigits: currency === 'idr' ? 0 : 6,
    }).format(price)
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold text-white">Supported Assets</h1>
        <p className="text-gray-400 mt-1">{assets.total} assets available for forecasting.</p>
      </div>

      {/* Crypto */}
      <section>
        <h2 className="text-xl font-semibold text-white mb-4">Cryptocurrency</h2>
        <div className="overflow-hidden rounded-xl border border-gray-800">
          <table className="w-full text-sm">
            <thead className="bg-gray-900 text-gray-500 uppercase text-xs tracking-wider">
              <tr>
                <th className="px-4 py-3 text-left">ID</th>
                <th className="px-4 py-3 text-left">Name</th>
                <th className="px-4 py-3 text-right">Live Price (USD)</th>
                <th className="px-4 py-3 text-left"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800 bg-gray-950">
              {assets.crypto.map((a) => (
                <tr key={a.id} className="hover:bg-gray-900 transition-colors">
                  <td className="px-4 py-3 font-mono font-medium text-blue-400">{a.id}</td>
                  <td className="px-4 py-3 text-white">{a.name}</td>
                  <td className="px-4 py-3 text-right text-green-400 font-mono">
                    {formatP(priceMap[a.id], 'usd')}
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/forecast?asset=${a.id}`}
                      className="text-xs text-blue-400 hover:text-blue-300"
                    >
                      Forecast →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Stocks */}
      <section>
        <h2 className="text-xl font-semibold text-white mb-4">IDX Stocks</h2>
        <div className="overflow-hidden rounded-xl border border-gray-800">
          <table className="w-full text-sm">
            <thead className="bg-gray-900 text-gray-500 uppercase text-xs tracking-wider">
              <tr>
                <th className="px-4 py-3 text-left">Ticker</th>
                <th className="px-4 py-3 text-left">Company</th>
                <th className="px-4 py-3 text-right">Live Price (IDR)</th>
                <th className="px-4 py-3 text-left"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800 bg-gray-950">
              {assets.stocks.map((a) => (
                <tr key={a.id} className="hover:bg-gray-900 transition-colors">
                  <td className="px-4 py-3 font-mono font-medium text-purple-400">{a.id}</td>
                  <td className="px-4 py-3 text-white">{a.name}</td>
                  <td className="px-4 py-3 text-right text-green-400 font-mono">
                    {formatP(priceMap[a.id], 'idr')}
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/forecast?asset=${a.id}`}
                      className="text-xs text-blue-400 hover:text-blue-300"
                    >
                      Forecast →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
