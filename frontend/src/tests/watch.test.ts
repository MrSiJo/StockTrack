import { describe, it, expect } from 'vitest'
import { watchDisplayName } from '../lib/watch'

describe('watchDisplayName', () => {
  it('uses label when present', () => {
    expect(watchDisplayName('AO — Meaco', 'ao')).toBe('AO — Meaco')
  })
  it('falls back to a titled store when label is empty', () => {
    expect(watchDisplayName('', 'cityplumbing')).toBe('City Plumbing')
    expect(watchDisplayName('  ', 'ao')).toBe('AO')
  })
  it('applies title-case to unmapped stores', () => {
    expect(watchDisplayName('', 'currys')).toBe('Currys')
  })
})
