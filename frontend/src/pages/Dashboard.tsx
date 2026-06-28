import { useEffect, useState } from 'react'
import { useStatusStore } from '../stores/statusStore'
import { PhaseBadge } from '../components/PhaseBadge'
import { BasketButton } from '../components/BasketButton'
import { HealthIndicator } from '../components/HealthIndicator'
import { EventFeed } from '../components/EventFeed'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { ErrorMessage } from '../components/ErrorMessage'
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

// Display-only relabel of City Plumbing's delivery-route suffix:
// the API's "carrier"/"branch" routes are shown as "delivery"/"collection".
function formatLeadTime(delivery: string): string {
  if (!delivery) return '—'
  return delivery
    .replace(/^Delivery by /, '')
    .replace(/\(carrier\)$/, '(delivery)')
    .replace(/\(branch\)$/, '(collection)')
}

// Cheapest first; products without a price sort to the end.
function byPriceAsc(a: Product, b: Product): number {
  const pa = a.current_price ?? Infinity
  const pb = b.current_price ?? Infinity
  return pa - pb
}

function ProductRow({
  product,
  showLeadTime,
}: {
  product: Product
  showLeadTime: boolean
}) {
  return (
    <tr className="hover:bg-gray-50">
      <td className="py-3 pl-4 pr-3 text-sm font-medium text-gray-900">
        {product.title}
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
        <BasketButton
          availability={product.availability}
          basketUrl={product.basket_url}
          productUrl={product.url}
        />
      </td>
    </tr>
  )
}

function WatchGroup({
  watch,
  onCheckNow,
}: {
  watch: WatchStatus
  onCheckNow: (id: number) => Promise<CheckResult | null>
}) {
  const label = watch.label || watch.store
  const [checkNote, setCheckNote] = useState<string | null>(null)
  const showLeadTime = watch.products.some((p) => p.delivery)
  const sortedProducts = [...watch.products].sort(byPriceAsc)
  const colCount = showLeadTime ? 6 : 5

  const handleCheck = async () => {
    setCheckNote(null)
    const result = await onCheckNow(watch.id)
    if (result) {
      const inStock = result.early + result.public
      const total = result.parsed
      const notifSuffix = result.notified
        ? ', notified'
        : ' (Gotify not configured)'
      setCheckNote(`Checked — ${inStock}/${total} in stock${notifSuffix}`)
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
              sortedProducts.map((p) => (
                <ProductRow key={p.id} product={p} showLeadTime={showLeadTime} />
              ))
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

  const handleCheckNow = async (id: number): Promise<CheckResult | null> => {
    const result = await checkNow(id)
    fetchAll()
    return result
  }

  // Disabled watches are hidden from the dashboard until re-enabled.
  const visibleWatches = watches.filter((w) => w.enabled)

  const hasEarlyAccess = visibleWatches.some((w) =>
    w.products.some((p) => p.availability === 'early'),
  )

  if (loading && watches.length === 0) return <LoadingSpinner />
  if (error) return <ErrorMessage message={error} />

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

      {hasEarlyAccess && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          ⚡ Early access window active — check the Add to basket links below.
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
      ) : (
        visibleWatches.map((w) => (
          <WatchGroup key={w.id} watch={w} onCheckNow={handleCheckNow} />
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
