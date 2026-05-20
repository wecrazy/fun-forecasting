import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Fun Forecasting',
  description: 'Multi-asset price forecasting with XGBoost, SARIMAX, Prophet & LSTM',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-950 text-gray-100 antialiased">
        <header className="border-b border-gray-800 bg-gray-900">
          <nav className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3">
            <a href="/" className="text-xl font-bold tracking-tight text-blue-400">
              📈 Fun Forecasting
            </a>
            <a href="/forecast" className="text-sm text-gray-400 hover:text-white transition-colors">
              New Forecast
            </a>
            <a href="/assets" className="text-sm text-gray-400 hover:text-white transition-colors">
              Assets
            </a>
          </nav>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-8">{children}</main>
        <footer className="border-t border-gray-800 py-6 text-center text-xs text-gray-600">
          Fun Forecasting v2.0 — XGBoost · SARIMAX · Prophet · LSTM
        </footer>
      </body>
    </html>
  )
}
