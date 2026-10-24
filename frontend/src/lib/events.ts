// Event feed helpers: what counts as recent on the dashboard, and day
// grouping for the full feed on the History page.
import type { StockEvent } from '../api/types'

export const RECENT_HOURS = 24
export const RECENT_MAX = 5

// Events newer than `hours` ago, newest first, at most `max`.
export function recentEvents(
  events: StockEvent[],
  now: Date,
  hours = RECENT_HOURS,
  max = RECENT_MAX,
): StockEvent[] {
  const since = now.getTime() - hours * 3600 * 1000
  return events
    .filter((e) => new Date(e.ts).getTime() >= since)
    .sort((a, b) => b.ts.localeCompare(a.ts))
    .slice(0, max)
}

function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  )
}

export function dayLabel(d: Date, now: Date): string {
  if (sameDay(d, now)) return 'Today'
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  if (sameDay(d, yesterday)) return 'Yesterday'
  return d.toLocaleDateString([], {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    ...(d.getFullYear() !== now.getFullYear() ? { year: 'numeric' } : {}),
  })
}

// "16:30" for today, "29 Sep 16:30" otherwise, so an old event never reads
// as a current one.
export function eventTime(iso: string, now: Date): string {
  const d = new Date(iso)
  const time = d.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
  if (sameDay(d, now)) return time
  const date = d.toLocaleDateString([], {
    day: 'numeric',
    month: 'short',
    ...(d.getFullYear() !== now.getFullYear() ? { year: 'numeric' } : {}),
  })
  return `${date} ${time}`
}

export interface EventDay {
  label: string
  events: StockEvent[]
}

// Newest first, one group per local day.
export function groupByDay(events: StockEvent[], now: Date): EventDay[] {
  const days: EventDay[] = []
  for (const e of [...events].sort((a, b) => b.ts.localeCompare(a.ts))) {
    const label = dayLabel(new Date(e.ts), now)
    const last = days[days.length - 1]
    if (last && last.label === label) last.events.push(e)
    else days.push({ label, events: [e] })
  }
  return days
}
