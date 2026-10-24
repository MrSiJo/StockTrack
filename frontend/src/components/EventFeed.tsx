import type { StockEvent } from '../api/types'
import { eventTime, groupByDay } from '../lib/events'

function eventIcon(kind: string): string {
  if (kind === 'early_access') return '⚡'
  if (kind === 'public') return '🟢'
  if (kind === 'price_drop') return '💸'
  if (kind === 'new_product') return '🆕'
  if (kind === 'lead_time') return '🚚'
  if (kind === 'new_low') return '🏆'
  if (kind === 'price_rise') return '📈'
  if (kind === 'price_target') return '🎯'
  return '🔴'
}

function eventLabel(kind: string): string {
  if (kind === 'early_access') return 'early access'
  if (kind === 'public') return 'now public'
  if (kind === 'price_drop') return 'price drop'
  if (kind === 'new_product') return 'new product'
  if (kind === 'lead_time') return 'delivery changed'
  if (kind === 'new_low') return 'all-time low'
  if (kind === 'price_rise') return 'price back up'
  if (kind === 'price_target') return 'target price hit'
  return 'out of stock again'
}

function formatPrice(price: number | null): string {
  if (price == null) return ''
  return ` (£${price.toFixed(0)})`
}

interface Props {
  events: StockEvent[]
  // Day headings (the full feed); without them each old event shows its date.
  byDay?: boolean
  empty?: string
}

function EventRow({ ev, now, timeOnly }: { ev: StockEvent; now: Date; timeOnly: boolean }) {
  const time = timeOnly
    ? new Date(ev.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
    : eventTime(ev.ts, now)
  return (
    <li className="flex items-start gap-2 py-2 text-sm">
      <span className="w-24 shrink-0 tabular-nums text-gray-400">{time}</span>
      <span aria-hidden="true">{eventIcon(ev.kind)}</span>
      <span className="text-gray-700">
        {ev.store} {ev.product_title} —{' '}
        {eventLabel(ev.kind)}
        {formatPrice(ev.price)}
      </span>
    </li>
  )
}

export function EventFeed({ events, byDay = false, empty = 'No recent stock events.' }: Props) {
  const now = new Date()
  if (events.length === 0) {
    return <p className="py-4 text-sm text-gray-500">{empty}</p>
  }
  if (byDay) {
    return (
      <div>
        {groupByDay(events, now).map((day) => (
          <section key={day.label}>
            <h3 className="pt-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
              {day.label}
            </h3>
            <ul className="divide-y divide-gray-100">
              {day.events.map((ev) => (
                <EventRow key={ev.id} ev={ev} now={now} timeOnly />
              ))}
            </ul>
          </section>
        ))}
      </div>
    )
  }
  return (
    <ul className="divide-y divide-gray-100">
      {events.map((ev) => (
        <EventRow key={ev.id} ev={ev} now={now} timeOnly={false} />
      ))}
    </ul>
  )
}
