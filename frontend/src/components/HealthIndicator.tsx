function formatRelative(iso: string | null): string {
  if (!iso) return 'never'
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

interface Props {
  lastOkAt: string | null
  consecutiveFailures: number
  lastError: string
  enabled: boolean
}

export function HealthIndicator({
  lastOkAt,
  consecutiveFailures,
  lastError,
  enabled,
}: Props) {
  if (!enabled) {
    return <span className="text-xs text-gray-400 italic">Disabled</span>
  }
  if (consecutiveFailures > 0) {
    return (
      <span
        className="text-xs text-amber-600 cursor-default"
        title={lastError || undefined}
      >
        ⚠ {consecutiveFailures} failed check
        {consecutiveFailures !== 1 ? 's' : ''}
      </span>
    )
  }
  return (
    <span className="text-xs text-gray-500">OK {formatRelative(lastOkAt)}</span>
  )
}
