import { useEffect, useState } from 'react'
import { getHistory, getStores } from '../api/endpoints'
import type { Store } from '../api/types'
import type { ProductHistory, Episode } from '../lib/history'
import { formatDuration, episodePhases } from '../lib/history'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { ErrorMessage } from '../components/ErrorMessage'

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString([], { day: '2-digit', month: 'short' })
}

function EpisodeTimeline({ ep }: { ep: Episode }) {
  const phases = episodePhases(ep)
  if (phases.length === 0) return null
  return (
    <span className="text-xs text-gray-500">
      {phases.map((p, i) => (
        <span key={p.icon}>
          {i > 0 && <span className="mx-1 text-gray-300">→</span>}
          <span>
            {p.icon}
            {p.time}
          </span>
        </span>
      ))}
    </span>
  )
}

function EpisodeRow({
  ep,
  basketUrl,
}: {
  ep: Episode
  basketUrl: string
}) {
  if (ep.ongoing) {
    const isEarlyOnly = Boolean(ep.early_access_ts) && !ep.public_ts
    return (
      <div className="flex flex-wrap items-center gap-3 rounded-md border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm">
        <span className="font-medium text-emerald-800">
          🟢 in stock now — {formatDuration(ep.buyable_seconds)} so far
        </span>
        {isEarlyOnly && basketUrl && (
          <a
            href={basketUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 rounded-md bg-amber-500 px-3 py-1 text-xs font-semibold text-white hover:bg-amber-600"
          >
            🛒 Add to basket
          </a>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-wrap items-center gap-3 px-4 py-2 text-sm text-gray-700">
      <span className="font-medium tabular-nums">
        {shortDate(ep.started_ts)} · {formatDuration(ep.buyable_seconds)}
      </span>
      {ep.price != null && (
        <span className="text-gray-400">£{ep.price.toFixed(0)}</span>
      )}
      <EpisodeTimeline ep={ep} />
    </div>
  )
}

function ProductSection({ entry }: { entry: ProductHistory }) {
  const { product, summary, episodes } = entry
  const leadPart =
    summary.avg_early_lead_seconds != null
      ? ` · lead ${formatDuration(summary.avg_early_lead_seconds)}`
      : ''
  const headerText = `${product.title} · ${summary.episodes} ep${summary.episodes !== 1 ? 's' : ''} · avg ${formatDuration(summary.avg_buyable_seconds)}${leadPart}`

  return (
    <div className="mb-6 overflow-hidden rounded-lg border border-gray-200 bg-white">
      <div className="border-b border-gray-100 bg-gray-50 px-4 py-2.5">
        <span className="text-sm font-semibold text-gray-800">{headerText}</span>
        <span className="ml-2 text-xs text-gray-400">{product.store}</span>
      </div>
      <div className="divide-y divide-gray-50">
        {episodes.map((ep, i) => (
          <EpisodeRow key={i} ep={ep} basketUrl={product.basket_url} />
        ))}
      </div>
    </div>
  )
}

export function HistoryPage() {
  const [history, setHistory] = useState<ProductHistory[]>([])
  const [stores, setStores] = useState<Store[]>([])
  const [selectedStore, setSelectedStore] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Fetch stores once for the filter dropdown
  useEffect(() => {
    getStores()
      .then(setStores)
      .catch(() => {
        // Non-fatal: dropdown just won't populate
      })
  }, [])

  // Fetch history whenever the store filter changes
  useEffect(() => {
    setLoading(true)
    setError(null)
    getHistory(selectedStore || undefined)
      .then((data) => {
        setHistory(data)
        setLoading(false)
      })
      .catch((e: unknown) => {
        setError(String(e))
        setLoading(false)
      })
  }, [selectedStore])

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">History</h1>
        <div className="flex items-center gap-2">
          <label
            htmlFor="store-filter"
            className="text-sm font-medium text-gray-600"
          >
            Store
          </label>
          <select
            id="store-filter"
            value={selectedStore}
            onChange={(e) => setSelectedStore(e.target.value)}
            className="rounded-md border border-gray-300 bg-white py-1.5 pl-3 pr-8 text-sm text-gray-700 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="">All</option>
            {stores.map((s) => (
              <option key={s.name} value={s.name}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading ? (
        <LoadingSpinner />
      ) : error ? (
        <ErrorMessage message={error} />
      ) : history.length === 0 ? (
        <div className="py-12 text-center text-gray-500">
          <p className="text-base">No stock episodes recorded yet — they'll appear here as StockTrack catches restocks.</p>
        </div>
      ) : (
        history.map((entry) => (
          <ProductSection key={entry.product.id} entry={entry} />
        ))
      )}
    </div>
  )
}
