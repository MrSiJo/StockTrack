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
  }
  episodes: Episode[]
}

export function formatDuration(seconds: number | null): string {
  if (seconds == null) return '—'
  if (seconds < 60) return '<1m'
  const m = Math.round(seconds / 60)
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  const rem = m % 60
  return `${h}h ${String(rem).padStart(2, '0')}m`
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
