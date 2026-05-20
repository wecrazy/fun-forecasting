'use client'

import { useState } from 'react'

interface Props {
  cryptoAssets: string[]
  stockAssets: string[]
  value: string
  onChange: (value: string) => void
}

export default function AssetSelector({ cryptoAssets, stockAssets, value, onChange }: Props) {
  const [search, setSearch] = useState('')

  const filteredCrypto = cryptoAssets.filter((a) => a.toLowerCase().includes(search.toLowerCase()))
  const filteredStocks = stockAssets.filter((a) => a.toLowerCase().includes(search.toLowerCase()))

  return (
    <div className="space-y-2">
      <input
        type="text"
        placeholder="Search assets…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-blue-500 focus:outline-none"
      />
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        size={8}
        className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
      >
        <optgroup label="Cryptocurrency">
          {filteredCrypto.map((a) => (
            <option key={a} value={a} className="bg-gray-800">
              {a}
            </option>
          ))}
        </optgroup>
        <optgroup label="IDX Stocks">
          {filteredStocks.map((a) => (
            <option key={a} value={a} className="bg-gray-800">
              {a}
            </option>
          ))}
        </optgroup>
      </select>
    </div>
  )
}
