import { useState } from 'react'
import type { Product } from '../api/types'
import {
  DEFAULT_PER_VARIANT,
  filterByRating,
  groupByVariant,
  ratingSteps,
  selectVariants,
  toggleVariant,
} from '../lib/offers'

const UNKNOWN_TIP = "The seller's discounts could not be read: check at checkout"

function OfferPrice({ price }: { price: number | null | undefined }) {
  if (price == null) return <span title={UNKNOWN_TIP}>?</span>
  return <>£{price.toFixed(2)}</>
}

const TH =
  'px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500'
const COLS = 5

// A watch whose products have variants: one block per variant, cheapest
// first, the first few shown until the viewer asks for the rest. Variant
// chips pick which blocks show; none picked means all of them.
export function OfferTable({
  products,
  selected,
  onSelect,
  minRating = null,
  onMinRating,
}: {
  products: Product[]
  selected: string[]
  onSelect: (variants: string[]) => void
  minRating?: number | null
  onMinRating?: (min: number | null) => void
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const steps = ratingSteps(products)
  // A remembered floor no longer on offer (ratings changed) falls back to all.
  const floor = minRating != null && steps.includes(minRating) ? minRating : null
  // The first chip shows everything: name it by the lowest rating when every
  // seller has one, else "All".
  const rated = products.map((p) => p.seller_rating).filter((r): r is number => r != null)
  const lowest = rated.length ? Math.floor(Math.min(...rated) * 10 + 1e-6) / 10 : 0
  const allLabel = rated.length === products.length && rated.length
    ? `${lowest.toFixed(1)}+` : 'All'
  const groups = groupByVariant(filterByRating(products, floor))
  const shown = selectVariants(groups, selected)

  const toggleExpanded = (variant: string) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(variant)) next.delete(variant)
      else next.add(variant)
      return next
    })

  return (
    <div className="overflow-x-auto rounded-b-lg border border-gray-200 bg-white">
      <div
        className="flex flex-wrap items-center gap-1.5 border-b border-gray-100 px-4 py-2"
        role="group"
        aria-label="Variants"
      >
        <button
          type="button"
          onClick={() => onSelect([])}
          aria-pressed={selected.length === 0}
          className={chipClass(selected.length === 0)}
        >
          All
        </button>
        {groups.map((g) => (
          <button
            key={g.variant}
            type="button"
            onClick={() => onSelect(toggleVariant(selected, g.variant))}
            aria-pressed={selected.includes(g.variant)}
            className={chipClass(selected.includes(g.variant))}
          >
            {g.variant || 'Other'}
          </button>
        ))}
        {onMinRating && steps.some((r) => r > lowest + 1e-6) && (
          <span className="ml-auto flex items-center gap-1.5" role="group" aria-label="Seller rating">
            <span className="text-xs text-gray-500">Rating</span>
            {[null, ...steps.filter((r) => r > lowest + 1e-6)].map((r) => {
              const active = floor === r
              return (
                <button
                  key={r ?? 'all'}
                  type="button"
                  onClick={() => onMinRating(r)}
                  aria-pressed={active}
                  className={chipClass(active)}
                >
                  {r == null ? allLabel : `${r.toFixed(1)}+`}
                </button>
              )
            })}
          </span>
        )}
      </div>
      <table className="min-w-full divide-y divide-gray-100">
        <thead>
          <tr className="bg-white">
            <th className={`${TH} pl-4`}>Seller</th>
            <th className={TH}>Rating</th>
            <th className={TH} title="What a new customer pays, best first order discount taken off">
              New
            </th>
            <th className={TH} title="What a returning customer pays, best returning discount taken off">
              Returning
            </th>
            <th className={`${TH} text-gray-400`} title="The seller's price before any discount">
              List
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {shown.length === 0 && (
            <tr>
              <td colSpan={COLS} className="px-4 py-4 text-center text-sm text-gray-400">
                Nothing matches.
              </td>
            </tr>
          )}
          {shown.map((g) => {
            const all = expanded.has(g.variant)
            const rows = all ? g.products : g.products.slice(0, DEFAULT_PER_VARIANT)
            const hidden = g.products.length - rows.length
            return (
              <VariantBlock
                key={g.variant}
                variant={g.variant}
                rows={rows}
                total={g.products.length}
                hidden={hidden}
                expanded={all}
                onToggle={() => toggleExpanded(g.variant)}
              />
            )
          })}
        </tbody>
      </table>
      <p className="px-4 py-2 text-xs text-gray-400">
        Sorted by the new customer price. ? means it depends on discounts that could not be read; check at checkout.
      </p>
    </div>
  )
}

function chipClass(active: boolean): string {
  return `rounded-full border px-2.5 py-0.5 text-xs ${
    active
      ? 'border-gray-800 bg-gray-800 text-white'
      : 'border-gray-200 text-gray-600 hover:border-gray-400'
  }`
}

function VariantBlock({
  variant,
  rows,
  total,
  hidden,
  expanded,
  onToggle,
}: {
  variant: string
  rows: Product[]
  total: number
  hidden: number
  expanded: boolean
  onToggle: () => void
}) {
  return (
    <>
      <tr className="bg-gray-50">
        <td
          colSpan={COLS}
          className="px-4 py-1.5 text-xs font-semibold uppercase tracking-wide text-gray-500"
        >
          {variant || 'Other'} · {total}
        </td>
      </tr>
      {rows.map((p) => (
        <tr key={p.id} className="hover:bg-gray-50">
          <td className="py-2 pl-4 pr-3 text-sm font-medium text-gray-900">
            {p.url ? (
              <a href={p.url} target="_blank" rel="noopener noreferrer" className="hover:underline">
                {p.seller || p.title}
              </a>
            ) : (
              p.seller || p.title
            )}
          </td>
          <td className="px-3 py-2 tabular-nums text-sm text-gray-600">
            {p.seller_rating != null ? p.seller_rating.toFixed(1) : '—'}
          </td>
          <td className="px-3 py-2 tabular-nums text-sm text-gray-900">
            <OfferPrice price={p.price_new_customer} />
          </td>
          <td className="px-3 py-2 tabular-nums text-sm text-gray-700">
            <OfferPrice price={p.price_returning_customer} />
          </td>
          <td className="px-3 py-2 tabular-nums text-sm text-gray-400">
            <OfferPrice price={p.list_price === undefined ? p.current_price : p.list_price} />
          </td>
        </tr>
      ))}
      {(hidden > 0 || expanded) && total > DEFAULT_PER_VARIANT && (
        <tr>
          <td colSpan={COLS} className="px-4 py-1.5">
            <button
              type="button"
              onClick={onToggle}
              className="text-xs text-gray-500 hover:text-gray-800 hover:underline"
            >
              {expanded ? `Show cheapest ${DEFAULT_PER_VARIANT}` : `Show all ${total}`}
            </button>
          </td>
        </tr>
      )}
    </>
  )
}
