import { describe, it, expect } from 'vitest'
import { getPhaseDisplay, shouldShowBasketButton, productLinkFor } from '../lib/phase'

describe('getPhaseDisplay', () => {
  it('maps oos to OOS with red icon', () => {
    const d = getPhaseDisplay('oos')
    expect(d.label).toBe('OOS')
    expect(d.icon).toBe('🔴')
  })

  it('maps early to Early access with lightning icon', () => {
    const d = getPhaseDisplay('early')
    expect(d.label).toBe('Early access')
    expect(d.icon).toBe('⚡')
  })

  it('maps public to In stock with green icon', () => {
    const d = getPhaseDisplay('public')
    expect(d.label).toBe('In stock')
    expect(d.icon).toBe('🟢')
  })

  it('treats empty string as OOS', () => {
    const d = getPhaseDisplay('')
    expect(d.label).toBe('OOS')
  })
})

describe('shouldShowBasketButton', () => {
  it('returns true when early and basket_url is set', () => {
    expect(
      shouldShowBasketButton(
        'early',
        'https://ao.com/Build_Shopping_Basket.aspx?items=ABC123:1',
      ),
    ).toBe(true)
  })

  it('returns false when early but basket_url is empty', () => {
    expect(shouldShowBasketButton('early', '')).toBe(false)
  })

  it('returns false when public even with basket_url', () => {
    expect(
      shouldShowBasketButton(
        'public',
        'https://ao.com/Build_Shopping_Basket.aspx?items=ABC123:1',
      ),
    ).toBe(false)
  })

  it('returns false when oos', () => {
    expect(
      shouldShowBasketButton(
        'oos',
        'https://ao.com/Build_Shopping_Basket.aspx?items=ABC123:1',
      ),
    ).toBe(false)
  })

  it('returns false when availability is blank string', () => {
    expect(shouldShowBasketButton('', 'https://ao.com/basket')).toBe(false)
  })
})

describe('productLinkFor', () => {
  it('early -> basket', () => {
    expect(productLinkFor('early', 'u', 'b')).toEqual(
      { href: 'b', label: '🛒 Add to basket ↗', kind: 'basket' })
  })
  it('public -> product url', () => {
    expect(productLinkFor('public', 'u', '')).toEqual(
      { href: 'u', label: 'Open product page ↗', kind: 'product' })
  })
  it('oos still links to product url (muted)', () => {
    expect(productLinkFor('oos', 'u', '')).toEqual(
      { href: 'u', label: 'View product page ↗', kind: 'muted' })
  })
  it('no url -> null', () => {
    expect(productLinkFor('oos', '', '')).toBeNull()
  })
})
