// Offer watches: one listing, many sellers, several variants (plugin API 2).
// Variant labels are free text from the plugin; they are grouped in the order
// they first appear and never parsed.
import type { Product } from '../api/types'

export const DEFAULT_PER_VARIANT = 5

export interface VariantGroup {
  variant: string
  products: Product[]
}

export function hasVariants(products: Product[]): boolean {
  return products.some((p) => !!p.variant)
}

// What a new customer pays, else the quoted price: always a known figure when
// the seller quotes one, so unknown discounts never jump the queue.
function startPrice(p: Product): number {
  return p.price_new_customer ?? p.current_price ?? Infinity
}

function byStartPrice(a: Product, b: Product): number {
  const pa = startPrice(a)
  const pb = startPrice(b)
  if (pa !== pb) return pa - pb
  return (a.seller ?? '').localeCompare(b.seller ?? '')
}

// Variants in first seen order, each group cheapest to start with first.
export function groupByVariant(products: Product[]): VariantGroup[] {
  const groups = new Map<string, Product[]>()
  for (const p of products) {
    const v = p.variant ?? ''
    if (!groups.has(v)) groups.set(v, [])
    groups.get(v)!.push(p)
  }
  return [...groups.entries()].map(([variant, ps]) => ({
    variant,
    products: [...ps].sort(byStartPrice),
  }))
}

export function variantsOf(products: Product[]): string[] {
  return groupByVariant(products).map((g) => g.variant)
}

// The chips the viewer picked; an empty selection means every variant.
export function selectVariants(
  groups: VariantGroup[],
  selected: string[],
): VariantGroup[] {
  if (selected.length === 0) return groups
  const want = new Set(selected)
  return groups.filter((g) => want.has(g.variant))
}

export function toggleVariant(selected: string[], variant: string): string[] {
  return selected.includes(variant)
    ? selected.filter((v) => v !== variant)
    : [...selected, variant]
}

// Per viewer conveniences, kept in the browser. Storage can be missing or
// throw (private windows, blocked site data), so every access is guarded and
// the page works the same without it.
export interface OfferViewPrefs {
  variants: string[]
  collapsed: boolean
}

const PREFS_KEY = (watchId: number) => `stocktrack.offers.${watchId}`

export function loadPrefs(watchId: number): OfferViewPrefs {
  const fallback = { variants: [], collapsed: false }
  try {
    const raw = window.localStorage.getItem(PREFS_KEY(watchId))
    if (!raw) return fallback
    const data = JSON.parse(raw)
    return {
      variants: Array.isArray(data.variants)
        ? data.variants.filter((v: unknown) => typeof v === 'string')
        : [],
      collapsed: data.collapsed === true,
    }
  } catch {
    return fallback
  }
}

export function savePrefs(watchId: number, prefs: OfferViewPrefs): void {
  try {
    window.localStorage.setItem(PREFS_KEY(watchId), JSON.stringify(prefs))
  } catch {
    // not fatal: the choice just isn't remembered
  }
}
