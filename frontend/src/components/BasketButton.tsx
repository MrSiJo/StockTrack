import { shouldShowBasketButton } from '../lib/phase'
import type { Availability } from '../lib/phase'

interface Props {
  availability: Availability
  basketUrl: string
  productUrl: string
}

export function BasketButton({ availability, basketUrl, productUrl }: Props) {
  if (shouldShowBasketButton(availability, basketUrl)) {
    return (
      <a
        href={basketUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1.5 rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white shadow-sm hover:bg-emerald-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600"
      >
        🛒 Add to basket ↗
      </a>
    )
  }
  if (availability === 'public' && productUrl) {
    return (
      <a
        href={productUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="text-sm text-blue-600 hover:text-blue-500 hover:underline"
      >
        Open product page ↗
      </a>
    )
  }
  return null
}
