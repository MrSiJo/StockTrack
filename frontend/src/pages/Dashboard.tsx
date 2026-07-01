import { useEffect, useState } from 'react'
import { useStatusStore } from '../stores/statusStore'
import { PhaseBadge } from '../components/PhaseBadge'
import { BasketButton } from '../components/BasketButton'
import { HealthIndicator } from '../components/HealthIndicator'
import { EventFeed } from '../components/EventFeed'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { ErrorMessage } from '../components/ErrorMessage'
import { muteProduct, unmuteProduct } from '../api/endpoints'
import type { WatchStatus, Product, CheckResult } from '../api/types'

function formatPrice(price: number | null): string {
  if (price == null) return '—'
  return `£${price.toFixed(0)}`
}

function formatRelative(iso: string | null): string {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

// Backend stores "Delivery by <date>" or "Collection by <date>"; show the
// date with the channel as a compact suffix, e.g. "Tue 30 Jun (delivery)".
function formatLeadTime(delivery: string): string {
  if (!delivery) return '—'
  const m = delivery.match(/^(Delivery|Collection) by (.+)$/)
  if (!m) return delivery
  return `${m[2]} (${m[1].toLowerCase()})`
}

// Cheapest first; products without a price sort to the end.
function byPriceAsc(a: Product, b: Product): number {
  const pa = a.current_price ?? Infinity
  const pb = b.current_price ?? Infinity
  return pa - pb
}

// In stock = any non-oos phase (covers "public" and early-access "early").
function isInStock(p: Product): boolean {
  return p.availability !== 'oos'
}

// Sub-group divider row inside a watch's product table (in stock / out of stock).
function SubHeader({ label, count, colSpan }: {
  label: string
  count: number
  colSpan: number
}) {
  return (
    <tr className="bg-gray-50">
      <td
        colSpan={colSpan}
        className="px-4 py-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500"
      >
        {label} · {count}
      </td>
    </tr>
  )
}

function isMuted(p: Product): boolean {
  return p.muted_until != null && new Date(p.muted_until) > new Date()
}

function isAtLowestPrice(p: Product): boolean {
  return (
    p.current_price != null &&
    p.lowest_price != null &&
    p.current_price <= p.lowest_price
  )
}

const MUTE_CHOICES = [
  { label: 'Mute 1h', hours: 1 },
  { label: 'Mute 24h', hours: 24 },
  { label: 'Mute 7d', hours: 168 },
]

function MuteMenu({
  product,
  onChanged,
}: {
  product: Product
  onChanged: () => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [muteError, setMuteError] = useState<string | null>(null)
  const muted = isMuted(product)

  const apply = async (hours: number | null) => {
    setBusy(true)
    setMuteError(null)
    try {
      if (hours == null) await unmuteProduct(product.id)
      else await muteProduct(product.id, hours)
      setOpen(false)
      await onChanged()
    } catch (e) {
      setMuteError(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <span className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        title={
          muted
            ? `Muted until ${new Date(product.muted_until!).toLocaleString()}`
            : 'Mute alerts for this product'
        }
        className={`rounded border px-1.5 py-1 text-xs ${
          muted
            ? 'border-amber-300 bg-amber-50 text-amber-700'
            : 'border-gray-200 text-gray-400 hover:text-gray-700'
        }`}
      >
        🔕
      </button>
      {open && (
        <span className="absolute right-0 z-10 mt-1 flex w-28 flex-col rounded-md border border-gray-200 bg-white py-1 shadow-lg">
          {MUTE_CHOICES.map((c) => (
            <button
              key={c.hours}
              type="button"
              disabled={busy}
              onClick={() => apply(c.hours)}
              className="px-3 py-1 text-left text-xs text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              {c.label}
            </button>
          ))}
          {muted && (
            <button
              type="button"
              disabled={busy}
              onClick={() => apply(null)}
              className="border-t border-gray-100 px-3 py-1 text-left text-xs text-amber-700 hover:bg-gray-50 disabled:opacity-50"
            >
              Unmute
            </button>
          )}
          {muteError && (
            <span className="px-3 py-1 text-xs text-red-600">{muteError}</span>
          )}
        </span>
      )}
    </span>
  )
}

function ProductRow({
  product,
  showLeadTime,
  onChanged,
}: {
  product: Product
  showLeadTime: boolean
  onChanged: () => Promise<void>
}) {
  return (
    <tr className="hover:bg-gray-50">
      <td className="py-3 pl-4 pr-3 text-sm font-medium text-gray-900">
        {product.title}
        {isAtLowestPrice(product) && (
          <span className="ml-1.5" title="Lowest price seen">
            🏆
          </span>
        )}
        {isMuted(product) && (
          <span
            className="ml-1.5 opacity-60"
            title={`Muted until ${new Date(product.muted_until!).toLocaleString()}`}
          >
            🔕
          </span>
        )}
      </td>
      <td className="py-3 px-3">
        <PhaseBadge availability={product.availability} />
      </td>
      <td className="py-3 px-3 tabular-nums text-sm text-gray-700">
        {formatPrice(product.current_price)}
      </td>
      {showLeadTime && (
        <td className="py-3 px-3 text-sm text-gray-600">
          {formatLeadTime(product.delivery)}
        </td>
      )}
      <td className="py-3 px-3 tabular-nums text-sm text-gray-500">
        {formatRelative(product.last_checked)}
      </td>
      <td className="py-3 pl-3 pr-4">
        <span className="flex items-center gap-1.5">
          <BasketButton
            availability={product.availability}
            basketUrl={product.basket_url}
            productUrl={product.url}
          />
          <MuteMenu product={product} onChanged={onChanged} />
        </span>
      </td>
    </tr>
  )
}

function WatchGroup({
  watch,
  onCheckNow,
  onChanged,
}: {
  watch: WatchStatus
  onCheckNow: (id: number) => Promise<CheckResult>
  onChanged: () => Promise<void>
}) {
  const label = watch.label || watch.store
  const [checkNote, setCheckNote] = useState<string | null>(null)
  const showLeadTime = watch.products.some((p) => p.delivery)
  const sortedProducts = [...watch.products].sort(byPriceAsc)
  const inStockProducts = sortedProducts.filter(isInStock)
  const oosProducts = sortedProducts.filter((p) => !isInStock(p))
  const colCount = showLeadTime ? 6 : 5

  const handleCheck = async () => {
    setCheckNote(null)
    try {
      const result = await onCheckNow(watch.id)
      const inStock = result.early + result.public
      const total = result.parsed
      const notifSuffix = result.notified
        ? ', notified'
        : ' (Gotify not configured)'
      setCheckNote(`Checked — ${inStock}/${total} in stock${notifSuffix}`)
    } catch (e) {
      setCheckNote(`Check failed — ${String(e)}`)
    }
  }

  return (
    <div className={`mb-6 ${!watch.enabled ? 'opacity-60' : ''}`}>
      <div className="flex items-center justify-between rounded-t-lg border border-b-0 border-gray-200 bg-gray-50 px-4 py-2">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-gray-800">{label}</span>
          <HealthIndicator
            lastOkAt={watch.last_ok_at}
            consecutiveFailures={watch.consecutive_failures}
            lastError={watch.last_error}
            enabled={watch.enabled}
          />
          {checkNote && (
            <span className="text-xs text-gray-500 italic">{checkNote}</span>
          )}
        </div>
        <button
          onClick={handleCheck}
          className="rounded border border-gray-200 px-2 py-1 text-xs text-gray-500 transition-colors hover:bg-white hover:text-gray-800"
        >
          Check now
        </button>
      </div>
      <div className="overflow-hidden rounded-b-lg border border-gray-200">
        <table className="min-w-full divide-y divide-gray-100">
          <thead>
            <tr className="bg-white">
              <th className="py-2 pl-4 pr-3 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
                Product
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
                Phase
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
                Price
              </th>
              {showLeadTime && (
                <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
                  Lead time
                </th>
              )}
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
                Checked
              </th>
              <th className="py-2 pl-3 pr-4 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
                Action
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {sortedProducts.length === 0 ? (
              <tr>
                <td
                  colSpan={colCount}
                  className="px-4 py-4 text-center text-sm text-gray-400"
                >
                  No products tracked yet — run a check or add filters.
                </td>
              </tr>
            ) : (
              <>
                {inStockProducts.length > 0 && (
                  <>
                    <SubHeader
                      label="In stock"
                      count={inStockProducts.length}
                      colSpan={colCount}
                    />
                    {inStockProducts.map((p) => (
                      <ProductRow
                        key={p.id}
                        product={p}
                        showLeadTime={showLeadTime}
                        onChanged={onChanged}
                      />
                    ))}
                  </>
                )}
                {oosProducts.length > 0 && (
                  <>
                    <SubHeader
                      label="Out of stock"
                      count={oosProducts.length}
                      colSpan={colCount}
                    />
                    {oosProducts.map((p) => (
                      <ProductRow
                        key={p.id}
                        product={p}
                        showLeadTime={showLeadTime}
                        onChanged={onChanged}
                      />
                    ))}
                  </>
                )}
              </>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function Dashboard() {
  const { watches, events, loading, error, fetchAll, checkNow } =
    useStatusStore()

  useEffect(() => {
    fetchAll()
  }, [fetchAll])

  // checkNow throws on failure; fetchAll only runs after a successful check so
  // a failed one can't clear still-valid data or its own error state.
  const handleCheckNow = async (id: number): Promise<CheckResult> => {
    const result = await checkNow(id)
    await fetchAll()
    return result
  }

  const [query, setQuery] = useState('')
  const [inStockOnly, setInStockOnly] = useState(false)

  // Disabled watches are hidden from the dashboard until re-enabled.
  const visibleWatches = watches.filter((w) => w.enabled)

  const hasEarlyAccess = visibleWatches.some((w) =>
    w.products.some((p) => p.availability === 'early'),
  )

  // Client-side filtering: search on brand/title/code + in-stock-only toggle.
  // Groups with no matching products are hidden while a filter is active.
  const q = query.trim().toLowerCase()
  const filterActive = q !== '' || inStockOnly
  const filteredWatches = visibleWatches
    .map((w) => ({
      ...w,
      products: w.products.filter(
        (p) =>
          (!q ||
            `${p.brand} ${p.title} ${p.code}`.toLowerCase().includes(q)) &&
          (!inStockOnly || isInStock(p)),
      ),
    }))
    .filter((w) => !filterActive || w.products.length > 0)

  if (loading && watches.length === 0) return <LoadingSpinner />
  // Full-page error only when there's no data to show; once loaded, a failed
  // refresh renders inline above the still-valid dashboard (as WatchesPage does).
  if (error && watches.length === 0) return <ErrorMessage message={error} />

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">Dashboard</h1>
        <button
          onClick={() => fetchAll()}
          className="flex items-center gap-1.5 rounded-md bg-white px-3 py-1.5 text-sm font-medium text-gray-700 shadow-sm ring-1 ring-inset ring-gray-300 hover:bg-gray-50"
        >
          ↻ Refresh
        </button>
      </div>

      {error && (
        <div className="mb-4">
          <ErrorMessage message={error} />
        </div>
      )}

      {hasEarlyAccess && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          ⚡ Early access window active — check the Add to basket links below.
        </div>
      )}

      {visibleWatches.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search products…"
            className="w-64 rounded-md border border-gray-300 px-3 py-1.5 text-sm shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
          />
          <label className="flex cursor-pointer items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={inStockOnly}
              onChange={(e) => setInStockOnly(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
            />
            In stock only
          </label>
        </div>
      )}

      {watches.length === 0 ? (
        <div className="py-12 text-center text-gray-500">
          <p className="text-base">No watches configured.</p>
          <p className="mt-1 text-sm">
            <a
              href="/settings/watches"
              className="text-blue-600 hover:underline"
            >
              Add a watch
            </a>{' '}
            to start tracking.
          </p>
        </div>
      ) : visibleWatches.length === 0 ? (
        <div className="py-12 text-center text-gray-500">
          <p className="text-base">All watches are disabled.</p>
          <p className="mt-1 text-sm">
            Enable one on the{' '}
            <a href="/settings/watches" className="text-blue-600 hover:underline">
              Watches
            </a>{' '}
            page to see it here.
          </p>
        </div>
      ) : filteredWatches.length === 0 ? (
        <div className="py-12 text-center text-gray-500">
          <p className="text-base">No products match the current filter.</p>
        </div>
      ) : (
        filteredWatches.map((w) => (
          <WatchGroup
            key={w.id}
            watch={w}
            onCheckNow={handleCheckNow}
            onChanged={fetchAll}
          />
        ))
      )}

      <div className="mt-8">
        <h2 className="mb-3 text-base font-semibold text-gray-900">
          Recent events
        </h2>
        <div className="rounded-lg border border-gray-200 bg-white px-4">
          <EventFeed events={events} />
        </div>
      </div>
    </div>
  )
}
