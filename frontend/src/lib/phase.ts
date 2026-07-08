export type Availability = 'oos' | 'early' | 'public' | string

export interface PhaseDisplay {
  label: string
  icon: string
  /** Tailwind-class key for callers that need to apply their own styles */
  key: 'oos' | 'early' | 'public'
}

export function getPhaseDisplay(availability: Availability): PhaseDisplay {
  if (availability === 'early') {
    return { label: 'Early access', icon: '⚡', key: 'early' }
  }
  if (availability === 'public') {
    return { label: 'In stock', icon: '🟢', key: 'public' }
  }
  return { label: 'OOS', icon: '🔴', key: 'oos' }
}

/**
 * Returns true only when the product is in the early-access phase AND the
 * store has exposed a basket deep-link. This is the single source-of-truth
 * for the "Add to basket" decision — never inline this check.
 */
export function shouldShowBasketButton(
  availability: Availability,
  basketUrl: string,
): boolean {
  return availability === 'early' && Boolean(basketUrl)
}

export type ProductLink = { href: string; label: string; kind: 'basket' | 'product' | 'muted' }

export function productLinkFor(
  availability: string,
  url: string,
  basketUrl: string,
): ProductLink | null {
  if (availability === 'early' && basketUrl)
    return { href: basketUrl, label: '🛒 Add to basket ↗', kind: 'basket' }
  if (availability === 'public' && url)
    return { href: url, label: 'Open product page ↗', kind: 'product' }
  if (url) return { href: url, label: 'View product page ↗', kind: 'muted' }
  return null
}
