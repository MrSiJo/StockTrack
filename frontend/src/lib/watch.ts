// Watches are labeled by the user, but the label is optional. When blank,
// fall back to a friendly store name so the dashboard never shows an empty
// group header.
const STORE_NAMES: Record<string, string> = {
  cityplumbing: 'City Plumbing',
  johnlewis: 'John Lewis',
}

export function watchDisplayName(label: string, store: string): string {
  if (label && label.trim()) return label
  if (STORE_NAMES[store]) return STORE_NAMES[store]
  return store.charAt(0).toUpperCase() + store.slice(1)
}
