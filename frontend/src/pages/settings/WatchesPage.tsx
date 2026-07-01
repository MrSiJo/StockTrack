import { useEffect, useState } from 'react'
import { useSettingsStore } from '../../stores/settingsStore'
import { WatchForm } from './WatchForm'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { ErrorMessage } from '../../components/ErrorMessage'
import type { Watch } from '../../api/types'

function formatInterval(secs: number): string {
  if (secs < 60) return `${secs}s`
  if (secs < 3600) return `${Math.round(secs / 60)}m`
  return `${(secs / 3600).toFixed(1)}h`
}

export function WatchesPage() {
  const { watches, loading, error, fetchWatches, fetchStores, editWatch, removeWatch } =
    useSettingsStore()
  const [showAddForm, setShowAddForm] = useState(false)
  const [editTarget, setEditTarget] = useState<Watch | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null)

  useEffect(() => {
    fetchWatches()
    fetchStores()
  }, [fetchWatches, fetchStores])

  // editWatch already surfaces failures via the store error banner
  const handleToggle = (w: Watch) =>
    editWatch(w.id, { enabled: !w.enabled }).catch(() => {})
  const handleDelete = async (id: number) => {
    await removeWatch(id)
    setConfirmDelete(null)
  }

  if (loading && watches.length === 0) return <LoadingSpinner />

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">Watches</h1>
        <button
          onClick={() => { setShowAddForm(true); setEditTarget(null) }}
          className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-emerald-500"
        >
          + Add watch
        </button>
      </div>

      {error && <ErrorMessage message={error} />}

      {(showAddForm || editTarget) && (
        <WatchForm
          initial={editTarget ?? undefined}
          onClose={() => { setShowAddForm(false); setEditTarget(null) }}
        />
      )}

      {watches.length === 0 && !showAddForm ? (
        <p className="text-sm text-gray-500">No watches yet.</p>
      ) : (
        <ul className="divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white">
          {watches.map((w) => (
            <li
              key={w.id}
              className={`flex items-center gap-4 px-4 py-3 ${!w.enabled ? 'opacity-60' : ''}`}
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-gray-900">
                  {w.label || w.store}
                </p>
                <p className="truncate text-xs text-gray-500">{w.url}</p>
                <p className="text-xs text-gray-400">
                  {w.store} · every {formatInterval(w.interval_seconds)}
                  {w.include_filter && ` · incl: ${w.include_filter}`}
                  {w.exclude_filter && ` · excl: ${w.exclude_filter}`}
                </p>
              </div>

              <label className="flex cursor-pointer items-center gap-1.5 text-xs text-gray-600">
                <input
                  type="checkbox"
                  checked={w.enabled}
                  onChange={() => handleToggle(w)}
                  className="h-4 w-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
                />
                {w.enabled ? 'Enabled' : 'Disabled'}
              </label>

              <button
                onClick={() => { setEditTarget(w); setShowAddForm(false) }}
                className="rounded border border-gray-200 px-2 py-1 text-xs text-gray-500 hover:text-gray-900"
              >
                Edit
              </button>

              {confirmDelete === w.id ? (
                <span className="flex gap-1">
                  <button
                    onClick={() => handleDelete(w.id)}
                    className="rounded border border-red-200 px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                  >
                    Confirm
                  </button>
                  <button
                    onClick={() => setConfirmDelete(null)}
                    className="rounded border border-gray-200 px-2 py-1 text-xs text-gray-500"
                  >
                    Cancel
                  </button>
                </span>
              ) : (
                <button
                  onClick={() => setConfirmDelete(w.id)}
                  className="rounded border border-gray-200 px-2 py-1 text-xs text-red-500 hover:text-red-700"
                >
                  Delete
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
