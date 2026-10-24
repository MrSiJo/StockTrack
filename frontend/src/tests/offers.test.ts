import { describe, it, expect, afterEach, vi } from 'vitest'
import type { Product } from '../api/types'
import {
  groupByVariant,
  hasVariants,
  loadPrefs,
  savePrefs,
  selectVariants,
  toggleVariant,
  variantsOf,
} from '../lib/offers'

let nextId = 1
function offer(seller: string, variant: string, price: number | null): Product {
  return {
    id: nextId++, store: 'fake', code: `${seller}:${variant}`,
    title: `${seller} ${variant}`, url: '', brand: seller, availability: 'public',
    basket_url: '', delivery: '', current_in_stock: true, current_price: price,
    lowest_price: price, muted_until: null, available_since: null,
    last_checked: null, variant, seller, seller_rating: 4.8,
    price_new_customer: null, price_returning_customer: null,
  }
}

const mattresses = [
  offer('Sleepco', 'Double', 320),
  offer('Sleepco', 'King', 420),
  offer('Bedworks', 'Double', 300),
  offer('Dozey', 'Double', null),
  offer('Bedworks', 'King', 400),
]

describe('offer grouping', () => {
  it('detects variant watches', () => {
    expect(hasVariants(mattresses)).toBe(true)
    expect(hasVariants([{ ...mattresses[0], variant: '' }])).toBe(false)
  })
  it('groups in first seen order, cheapest first, unpriced last', () => {
    const groups = groupByVariant(mattresses)
    expect(groups.map((g) => g.variant)).toEqual(['Double', 'King'])
    expect(groups[0].products.map((p) => p.seller)).toEqual(['Bedworks', 'Sleepco', 'Dozey'])
    expect(variantsOf(mattresses)).toEqual(['Double', 'King'])
  })
  it('an empty selection shows every variant', () => {
    const groups = groupByVariant(mattresses)
    expect(selectVariants(groups, []).length).toBe(2)
    expect(selectVariants(groups, ['King']).map((g) => g.variant)).toEqual(['King'])
  })
  it('toggles a chip on and off', () => {
    expect(toggleVariant([], 'King')).toEqual(['King'])
    expect(toggleVariant(['King', 'Double'], 'King')).toEqual(['Double'])
  })
})

describe('view prefs', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('round trips through storage', () => {
    const store = new Map<string, string>()
    vi.stubGlobal('window', {
      localStorage: {
        getItem: (k: string) => store.get(k) ?? null,
        setItem: (k: string, v: string) => void store.set(k, v),
      },
    })
    savePrefs(4, { variants: ['King'], collapsed: true })
    expect(loadPrefs(4)).toEqual({ variants: ['King'], collapsed: true })
    expect(loadPrefs(5)).toEqual({ variants: [], collapsed: false })
  })
  it('works when storage throws', () => {
    vi.stubGlobal('window', {
      localStorage: {
        getItem: () => { throw new Error('blocked') },
        setItem: () => { throw new Error('blocked') },
      },
    })
    expect(() => savePrefs(4, { variants: [], collapsed: false })).not.toThrow()
    expect(loadPrefs(4)).toEqual({ variants: [], collapsed: false })
  })
})
