import type { StockEvent } from '../api/types'

function eventIcon(kind: string): string {
  if (kind === 'early_access') return '⚡'
  if (kind === 'public') return '🟢'
  if (kind === 'price_drop') return '💸'
  if (kind === 'new_product') return '🆕'
  if (kind === 'lead_time') return '🚚'
  return '🔴'
}

function eventLabel(kind: string): string {
  if (kind === 'early_access') return 'early access'
  if (kind === 'public') return 'now public'
  if (kind === 'price_drop') return 'price drop'
  if (kind === 'new_product') return 'new product'
  if (kind === 'lead_time') return 'delivery changed'
  return 'out of stock again'
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function formatPrice(price: number | null): string {
  if (price == null) return ''
  return ` (£${price.toFixed(0)})`
}

interface Props {
  events: StockEvent[]
}

export function EventFeed({ events }: Props) {
  if (events.length === 0) {
    return (
      <p className="py-4 text-sm text-gray-500">No recent stock events.</p>
    )
  }
  return (
    <ul className="divide-y divide-gray-100">
      {events.map((ev) => (
        <li key={ev.id} className="flex items-start gap-2 py-2 text-sm">
          <span className="w-10 shrink-0 tabular-nums text-gray-400">
            {formatTime(ev.ts)}
          </span>
          <span aria-hidden="true">{eventIcon(ev.kind)}</span>
          <span className="text-gray-700">
            {ev.store} {ev.product_title} —{' '}
            {eventLabel(ev.kind)}
            {formatPrice(ev.price)}
          </span>
        </li>
      ))}
    </ul>
  )
}
