import { describe, it, expect } from 'vitest'
import { formatDuration, episodePhases } from '../lib/history'

describe('formatDuration', () => {
  it('handles null, sub-minute, minutes, hours', () => {
    expect(formatDuration(null)).toBe('—')
    expect(formatDuration(30)).toBe('<1m')
    expect(formatDuration(47 * 60)).toBe('47m')
    expect(formatDuration(3900)).toBe('1h 05m')
  })
})

describe('episodePhases', () => {
  const ep = {
    started_ts: '2026-06-27T06:00:00Z',
    early_access_ts: '2026-06-27T06:00:00Z',
    public_ts: '2026-06-27T06:17:00Z',
    ended_ts: '2026-06-27T06:47:00Z',
    ongoing: false,
    buyable_seconds: 2820,
    early_lead_seconds: 1020,
    price: 629,
  }
  it('returns only phases that occurred, in order', () => {
    const phases = episodePhases(ep)
    expect(phases.map((p) => p.icon)).toEqual(['⚡', '🟢', '🔴'])
  })
  it('omits public/oos for an early-only ongoing episode', () => {
    const phases = episodePhases({ ...ep, public_ts: null, ended_ts: null, ongoing: true })
    expect(phases.map((p) => p.icon)).toEqual(['⚡'])
  })
})
