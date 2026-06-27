import { getPhaseDisplay } from '../lib/phase'
import type { Availability } from '../lib/phase'

const BADGE_CLASSES: Record<'oos' | 'early' | 'public', string> = {
  oos: 'bg-gray-100 text-gray-500',
  early: 'bg-amber-100 text-amber-700 ring-1 ring-amber-300',
  public: 'bg-emerald-100 text-emerald-700 ring-1 ring-emerald-300',
}

interface Props {
  availability: Availability
}

export function PhaseBadge({ availability }: Props) {
  const { label, icon, key } = getPhaseDisplay(availability)
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${BADGE_CLASSES[key]}`}
    >
      <span aria-hidden="true">{icon}</span>
      {label}
    </span>
  )
}
