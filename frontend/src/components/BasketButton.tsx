import { productLinkFor } from '../lib/phase'
import type { Availability } from '../lib/phase'

interface Props {
  availability: Availability
  basketUrl: string
  productUrl: string
}

export function BasketButton({ availability, basketUrl, productUrl }: Props) {
  const link = productLinkFor(availability, productUrl, basketUrl)
  if (!link) return null

  if (link.kind === 'basket') {
    return (
      <a
        href={link.href}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1.5 rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white shadow-sm hover:bg-emerald-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600"
      >
        {link.label}
      </a>
    )
  }

  if (link.kind === 'product') {
    return (
      <a
        href={link.href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-sm text-blue-600 hover:text-blue-500 hover:underline"
      >
        {link.label}
      </a>
    )
  }

  // link.kind === 'muted'
  return (
    <a
      href={link.href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-xs text-gray-400 hover:text-gray-200 underline"
    >
      {link.label}
    </a>
  )
}
