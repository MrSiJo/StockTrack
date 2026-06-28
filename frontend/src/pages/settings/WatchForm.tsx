import { useState } from 'react'
import { useSettingsStore } from '../../stores/settingsStore'
import { PhaseBadge } from '../../components/PhaseBadge'
import { BasketButton } from '../../components/BasketButton'
import type { Watch, PreviewProduct } from '../../api/types'

interface Props {
  initial?: Watch
  onClose: () => void
}

export function WatchForm({ initial, onClose }: Props) {
  const { stores, addWatch, editWatch, preview } = useSettingsStore()
  const defaultStore = stores[0]
  const [store, setStore] = useState(initial?.store ?? defaultStore?.name ?? '')
  const [kind, setKind] = useState(
    initial?.kind ?? defaultStore?.kinds?.[0] ?? 'listing',
  )
  const kindsForStore =
    stores.find((s) => s.name === store)?.kinds ?? ['listing']
  const [url, setUrl] = useState(initial?.url ?? '')
  const [label, setLabel] = useState(initial?.label ?? '')
  const [includeFilter, setIncludeFilter] = useState(
    initial?.include_filter ?? '',
  )
  const [excludeFilter, setExcludeFilter] = useState(
    initial?.exclude_filter ?? '',
  )
  const [intervalSeconds, setIntervalSeconds] = useState(
    String(initial?.interval_seconds ?? 300),
  )
  const [enabled, setEnabled] = useState(initial?.enabled ?? true)
  const [trackPriceDrops, setTrackPriceDrops] = useState(initial?.track_price_drops ?? false)

  const [previewProducts, setPreviewProducts] = useState<
    PreviewProduct[] | null
  >(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const handlePreview = async () => {
    setPreviewLoading(true)
    setPreviewError(null)
    setPreviewProducts(null)
    try {
      const products = await preview({
        store,
        url,
        kind,
        include_filter: kind === 'product' ? '' : includeFilter,
        exclude_filter: kind === 'product' ? '' : excludeFilter,
      })
      setPreviewProducts(products)
    } catch (e) {
      setPreviewError(String(e))
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setFormError(null)
    try {
      const body = {
        store,
        url,
        label,
        kind,
        include_filter: kind === 'product' ? '' : includeFilter,
        exclude_filter: kind === 'product' ? '' : excludeFilter,
        interval_seconds: Number(intervalSeconds),
        enabled,
        track_price_drops: trackPriceDrops,
      }
      if (initial) {
        await editWatch(initial.id, body)
      } else {
        await addWatch(body)
      }
      onClose()
    } catch (e) {
      setFormError(String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mb-6 rounded-lg border border-gray-200 bg-white p-4">
      <h2 className="mb-4 text-sm font-semibold text-gray-900">
        {initial ? 'Edit watch' : 'Add watch'}
      </h2>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              Store
            </label>
            <select
              value={store}
              onChange={(e) => {
                const name = e.target.value
                setStore(name)
                const ks = stores.find((s) => s.name === name)?.kinds ?? ['listing']
                if (!ks.includes(kind)) setKind(ks[0])
              }}
              className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-emerald-500"
              required
            >
              {stores.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              Kind
            </label>
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-emerald-500"
              required
            >
              {kindsForStore.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              Label (optional)
            </label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. AO Meaco Cirro"
              className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
          </div>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-gray-700">
            {kind === 'product' ? 'Product page URL' : 'Listing URL'}
          </label>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-emerald-500"
            required
          />
        </div>

        {kind !== 'product' && (
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                Include filter (substring match on brand+title)
              </label>
              <input
                type="text"
                value={includeFilter}
                onChange={(e) => setIncludeFilter(e.target.value)}
                placeholder="e.g. Meaco"
                className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                Exclude filter
              </label>
              <input
                type="text"
                value={excludeFilter}
                onChange={(e) => setExcludeFilter(e.target.value)}
                placeholder="e.g. Portable"
                className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              Poll interval (seconds)
            </label>
            <input
              type="number"
              value={intervalSeconds}
              onChange={(e) => setIntervalSeconds(e.target.value)}
              min={60}
              className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-emerald-500"
            />
          </div>
          <div className="flex items-end gap-4">
            <label className="flex cursor-pointer items-center gap-2 pb-1.5 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
              />
              Enabled
            </label>
            <label className="flex cursor-pointer items-center gap-2 pb-1.5 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={trackPriceDrops}
                onChange={(e) => setTrackPriceDrops(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
              />
              Alert on price drops
            </label>
          </div>
        </div>

        {formError && (
          <p className="text-xs text-red-600">{formError}</p>
        )}

        <div className="flex items-center gap-2 pt-1">
          <button
            type="button"
            onClick={handlePreview}
            disabled={previewLoading || !url || !store}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            {previewLoading ? 'Loading…' : 'Test / Preview'}
          </button>
          <button
            type="submit"
            disabled={saving}
            className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
          >
            {saving ? 'Saving…' : initial ? 'Save changes' : 'Add watch'}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
          >
            Cancel
          </button>
        </div>
      </form>

      {previewError && (
        <p className="mt-3 text-xs text-red-600">{previewError}</p>
      )}

      {previewProducts !== null && (
        <div className="mt-4">
          <p className="mb-2 text-xs font-medium text-gray-700">
            Preview — {previewProducts.length} product
            {previewProducts.length !== 1 ? 's' : ''} matched
          </p>
          {previewProducts.length === 0 ? (
            <p className="text-xs text-gray-500">
              No products matched with current filters.
            </p>
          ) : (
            <div className="overflow-hidden rounded border border-gray-200">
              <table className="min-w-full divide-y divide-gray-100 text-xs">
                <thead>
                  <tr className="bg-gray-50">
                    <th className="px-3 py-2 text-left font-medium text-gray-500">
                      Title
                    </th>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">
                      Phase
                    </th>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">
                      Price
                    </th>
                    <th className="px-3 py-2 text-left font-medium text-gray-500">
                      Action
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 bg-white">
                  {previewProducts.map((p) => (
                    <tr key={p.code}>
                      <td className="px-3 py-2 text-gray-900">{p.title}</td>
                      <td className="px-3 py-2">
                        <PhaseBadge availability={p.availability} />
                      </td>
                      <td className="px-3 py-2 text-gray-700">
                        {p.price != null ? `£${p.price.toFixed(0)}` : '—'}
                      </td>
                      <td className="px-3 py-2">
                        <BasketButton
                          availability={p.availability}
                          basketUrl={p.basket_url}
                          productUrl={p.url}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
