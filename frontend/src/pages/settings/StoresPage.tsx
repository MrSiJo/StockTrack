import { useEffect } from 'react'
import { useSettingsStore } from '../../stores/settingsStore'
import { LoadingSpinner } from '../../components/LoadingSpinner'

export function StoresPage() {
  const { stores, loading, fetchStores } = useSettingsStore()

  useEffect(() => {
    fetchStores()
  }, [fetchStores])

  if (loading && stores.length === 0) return <LoadingSpinner />

  return (
    <div>
      <h1 className="mb-6 text-xl font-semibold text-gray-900">Stores</h1>
      <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
        <table className="min-w-full divide-y divide-gray-100">
          <thead>
            <tr className="bg-gray-50">
              <th className="py-2 pl-4 pr-3 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
                Name
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
                Kind
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
                Status
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {stores.map((s) => (
              <tr key={s.name}>
                <td className="py-3 pl-4 pr-3 text-sm font-medium text-gray-900">
                  {s.name}
                </td>
                <td className="px-3 py-3 text-sm text-gray-600">{s.kind}</td>
                <td className="px-3 py-3">
                  {s.supported ? (
                    <span className="inline-flex items-center rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-700">
                      Supported
                    </span>
                  ) : (
                    <span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-500">
                      Plugin required
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-4 text-xs text-gray-500">
        New <em>listing</em> stores always require a code plugin in{' '}
        <code className="rounded bg-gray-100 px-1 py-0.5">
          backend/stocktrack/sites/
        </code>
        .
      </p>
    </div>
  )
}
