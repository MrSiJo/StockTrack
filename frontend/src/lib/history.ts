export interface Episode {
  started_ts: string
  early_access_ts: string | null
  public_ts: string | null
  ended_ts: string | null
  ongoing: boolean
  buyable_seconds: number | null
  early_lead_seconds: number | null
  price: number | null
}

export interface ProductHistory {
  product: {
    id: number
    title: string
    store: string
    url: string
    basket_url: string
  }
  summary: {
    episodes: number
    avg_buyable_seconds: number | null
    avg_early_lead_seconds: number | null
    uptime_pct: number
    typical_window_seconds: number | null
    episodes_in_window: number
  }
  episodes: Episode[]
}

// History entries don't carry a watch_id (only `store`), so restock patterns
// are matched by store name. If multiple watches share a store, the first
// match wins.
export function findRestockPattern<T extends { store: string }>(
  patterns: T[],
  store: string,
): T | undefined {
  return patterns.find((p) => p.store === store)
}

export function formatDuration(seconds: number | null): string {
  if (seconds == null) return '—'
  if (seconds < 60) return '<1m'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ${String(minutes % 60).padStart(2, '0')}m`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ${hours % 24}h`
  const weeks = Math.floor(days / 7)
  return `${weeks}w ${days % 7}d`
}

const hhmm = (iso: string): string =>
  new Date(iso).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })

export function episodePhases(
  ep: Episode,
): Array<{ icon: string; label: string; time: string }> {
  const out: Array<{ icon: string; label: string; time: string }> = []
  if (ep.early_access_ts)
    out.push({ icon: '⚡', label: 'early access', time: hhmm(ep.early_access_ts) })
  if (ep.public_ts)
    out.push({ icon: '🟢', label: 'public', time: hhmm(ep.public_ts) })
  if (ep.ended_ts)
    out.push({ icon: '🔴', label: 'out of stock', time: hhmm(ep.ended_ts) })
  return out
}
