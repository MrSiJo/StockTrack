import { useEffect, useState } from 'react'
import { getHistory, getPriceHistory, getStores, getRestockPatterns } from '../api/endpoints'
import type { PricePoint, Store, RestockPattern } from '../api/types'
import type { ProductHistory, Episode } from '../lib/history'
import { formatDuration, episodePhases, findRestockPattern } from '../lib/history'
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

function Sparkline({ points }: { points: PricePoint[] }) {
  if (points.length < 2) return null
  const prices = points.map((p) => p.price)
  const min = Math.min(...prices)
  const max = Math.max(...prices)
  const w = 180
  const h = 40
  const pad = 3
  const x = (i: number) => pad + (i * (w - 2 * pad)) / (points.length - 1)
  const y = (price: number) =>
    max === min ? h / 2 : pad + ((max - price) * (h - 2 * pad)) / (max - min)
  const d = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(p.price).toFixed(1)}`)
    .join(' ')
  return (
    <svg
      width={w}
      height={h}
      className="text-emerald-600"
      role="img"
      aria-label="Price trend"
    >
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  )
}

function PriceTimeline({ productId }: { productId: number }) {
  const [points, setPoints] = useState<PricePoint[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getPriceHistory(productId)
      .then(setPoints)
      .catch((e: unknown) => setError(String(e)))
  }, [productId])

  if (error) return <p className="px-4 py-2 text-xs text-red-600">{error}</p>
  if (points === null)
    return <p className="px-4 py-2 text-xs text-gray-400">Loading…</p>
  if (points.length === 0)
    return (
      <p className="px-4 py-2 text-xs text-gray-500">
        No priced events recorded for this product yet.
      </p>
    )
  return (
    <div className="space-y-2 px-4 py-3">
      <Sparkline points={points} />
      <ul className="space-y-0.5 text-xs text-gray-600">
        {points.map((p, i) => (
          <li key={i} className="tabular-nums">
            {new Date(p.ts).toLocaleDateString([], {
              day: '2-digit',
              month: 'short',
            })}{' '}
            — £{p.price.toFixed(2)}{' '}
            <span className="text-gray-400">({p.kind.replaceAll('_', ' ')})</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function RestockSummary({ pattern }: { pattern: RestockPattern | undefined }) {
  if (!pattern) return null
  if (pattern.samples >= 3) {
    return (
      <p className="text-sm text-gray-400">
        🔁 {pattern.summary}
        <span className="text-gray-600"> ({pattern.samples} restocks)</span>
      </p>
    )
  }
  return <p className="text-sm text-gray-600">🔁 Not enough restock data yet</p>
}

function ProductSection({
  entry,
  pattern,
}: {
  entry: ProductHistory
  pattern: RestockPattern | undefined
}) {
  const { product, summary, episodes } = entry
  const [showPrices, setShowPrices] = useState(false)
  const leadPart =
    summary.avg_early_lead_seconds != null
      ? ` · lead ${formatDuration(summary.avg_early_lead_seconds)}`
      : ''
  const headerText = `${product.title} · ${summary.episodes} ep${summary.episodes !== 1 ? 's' : ''} · avg ${formatDuration(summary.avg_buyable_seconds)}${leadPart}`
  const statsText =
    summary.episodes_in_window > 0
      ? `in stock ${summary.uptime_pct}% of last 7d` +
        (summary.typical_window_seconds != null
          ? ` · typical window ${formatDuration(summary.typical_window_seconds)}`
          : '')
      : 'not in stock in the last 7d'

  return (
    <div className="mb-6 overflow-hidden rounded-lg border border-gray-200 bg-white">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-100 bg-gray-50 px-4 py-2.5">
        <div>
          <span className="text-sm font-semibold text-gray-800">{headerText}</span>
          <span className="ml-2 text-xs text-gray-400">{product.store}</span>
          <p className="text-xs text-gray-500">{statsText}</p>
          <RestockSummary pattern={pattern} />
        </div>
        <button
          type="button"
          onClick={() => setShowPrices((s) => !s)}
          className="rounded border border-gray-200 px-2 py-1 text-xs text-gray-500 hover:bg-white hover:text-gray-800"
        >
          {showPrices ? 'Hide prices' : '💷 Prices'}
        </button>
      </div>
      {showPrices && (
        <div className="border-b border-gray-100">
          <PriceTimeline productId={product.id} />
        </div>
      )}
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
  const [restockPatterns, setRestockPatterns] = useState<RestockPattern[]>([])
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

  // Fetch restock patterns once; non-fatal if it errors — the summary line
  // just won't render.
  useEffect(() => {
    getRestockPatterns()
      .then(setRestockPatterns)
      .catch(() => {
        // Non-fatal: restock summary just won't show
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
          <ProductSection
            key={entry.product.id}
            entry={entry}
            pattern={findRestockPattern(restockPatterns, entry.product.store)}
          />
        ))
      )}
    </div>
  )
}
