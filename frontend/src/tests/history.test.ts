import { describe, it, expect } from 'vitest'
import { formatDuration, episodePhases, findRestockPattern } from '../lib/history'

describe('formatDuration', () => {
  it('handles null, sub-minute, minutes, hours', () => {
    expect(formatDuration(null)).toBe('—')
    expect(formatDuration(30)).toBe('<1m')
    expect(formatDuration(47 * 60)).toBe('47m')
    expect(formatDuration(3900)).toBe('1h 05m')
  })
})

describe('formatDuration ladder', () => {
  it('formats across the ladder', () => {
    expect(formatDuration(30)).toBe('<1m')
    expect(formatDuration(90)).toBe('1m')
    expect(formatDuration(3690)).toBe('1h 01m')
    expect(formatDuration(24 * 3600)).toBe('1d 0h')
    expect(formatDuration((6 * 24 + 23) * 3600)).toBe('6d 23h')
    expect(formatDuration(7 * 24 * 3600)).toBe('1w 0d')
    expect(formatDuration((2 * 7 + 3) * 24 * 3600)).toBe('2w 3d')
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

describe('findRestockPattern', () => {
  const patterns = [
    { store: 'ao', summary: 'Usually restocks around 06:00' },
    { store: 'currys', summary: 'No clear pattern yet' },
  ]
  it('returns the pattern matching the given store', () => {
    expect(findRestockPattern(patterns, 'currys')?.summary).toBe('No clear pattern yet')
  })
  it('returns undefined when no pattern matches the store', () => {
    expect(findRestockPattern(patterns, 'unknown-store')).toBeUndefined()
  })
})
