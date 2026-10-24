import { describe, it, expect } from 'vitest'
import type { StockEvent } from '../api/types'
import { eventTime, groupByDay, recentEvents } from '../lib/events'

const NOW = new Date(2026, 9, 24, 18, 0) // local time, 24 Oct 2026 18:00

let nextId = 1
function ev(at: Date): StockEvent {
  return {
    id: nextId++, ts: at.toISOString(), kind: 'public', price: null,
    available_seconds: null, product_title: 'Thing', store: 'fake', url: '',
    basket_url: '',
  }
}

describe('recent events', () => {
  it('keeps the last 24 hours only, newest first', () => {
    const old = ev(new Date(2026, 8, 29, 16, 30))
    const a = ev(new Date(2026, 9, 24, 9, 0))
    const b = ev(new Date(2026, 9, 23, 19, 0))
    expect(recentEvents([old, b, a], NOW).map((e) => e.id)).toEqual([a.id, b.id])
  })
  it('caps the count', () => {
    const many = Array.from({ length: 9 }, (_, i) => ev(new Date(2026, 9, 24, 10, i)))
    expect(recentEvents(many, NOW)).toHaveLength(5)
  })
})

describe('event time', () => {
  it('shows only the time today and the date otherwise', () => {
    expect(eventTime(new Date(2026, 9, 24, 9, 5).toISOString(), NOW)).toBe('09:05')
    const old = eventTime(new Date(2026, 8, 29, 16, 30).toISOString(), NOW)
    expect(old).toContain('16:30')
    expect(old).toMatch(/29/)
  })
})

describe('day groups', () => {
  it('groups newest first with Today and Yesterday labels', () => {
    const days = groupByDay([
      ev(new Date(2026, 9, 23, 8, 0)),
      ev(new Date(2026, 9, 24, 9, 0)),
      ev(new Date(2026, 9, 24, 7, 0)),
      ev(new Date(2026, 8, 29, 16, 30)),
    ], NOW)
    expect(days.map((d) => d.label.startsWith('Today') || d.label.startsWith('Yesterday')
      ? d.label : 'older')).toEqual(['Today', 'Yesterday', 'older'])
    expect(days[0].events).toHaveLength(2)
  })
})
