import { Fragment, useEffect, useState } from 'react'
import { useSettingsStore } from '../../stores/settingsStore'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import type { SettingsUpdate } from '../../api/types'

export function StoresPage() {
  const { stores, settings, loading, fetchStores, fetchSettings, saveSettings } =
    useSettingsStore()
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [drafts, setDrafts] = useState<Record<string, string>>({})

  useEffect(() => {
    fetchStores()
    fetchSettings()
  }, [fetchStores, fetchSettings])

  if (loading && stores.length === 0) return <LoadingSpinner />

  const settingValue = (key: string): unknown =>
    settings ? (settings as unknown as Record<string, unknown>)[key] : undefined

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
                Kinds
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-gray-500">
                Status
              </th>
              <th className="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {stores.map((s) => (
              <Fragment key={s.name}>
                <tr>
                  <td className="py-3 pl-4 pr-3 text-sm font-medium text-gray-900">
                    {s.name}
                  </td>
                  <td className="px-3 py-3 text-sm text-gray-600">
                    {s.kinds.join(', ')}
                  </td>
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
                  <td className="px-3 py-3 text-right">
                    {s.settings.length > 0 && (
                      <button
                        type="button"
                        onClick={() =>
                          setExpanded((e) => ({ ...e, [s.name]: !e[s.name] }))
                        }
                        className="text-xs font-medium text-emerald-700 hover:text-emerald-600"
                      >
                        {expanded[s.name] ? '▾ Settings' : '▸ Settings'}
                      </button>
                    )}
                  </td>
                </tr>
                {s.settings.length > 0 && expanded[s.name] && (
                  <tr className="bg-gray-50">
                    <td colSpan={4} className="px-4 py-3">
                      <div className="space-y-2">
                        {s.settings.map((cfg) => (
                          <label
                            key={cfg.key}
                            className="flex cursor-pointer items-center gap-2 text-sm text-gray-700"
                          >
                            {cfg.type === 'bool' ? (
                              <input
                                type="checkbox"
                                checked={Boolean(
                                  settingValue(cfg.key) ?? cfg.default,
                                )}
                                onChange={(e) =>
                                  saveSettings({ [cfg.key]: e.target.checked } as SettingsUpdate)
                                }
                                className="h-4 w-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
                              />
                            ) : (
                              <input
                                type="number"
                                value={drafts[cfg.key] ?? String(settingValue(cfg.key) ?? cfg.default)}
                                onChange={(e) =>
                                  setDrafts((d) => ({ ...d, [cfg.key]: e.target.value }))
                                }
                                onBlur={() => {
                                  const n = Number(drafts[cfg.key])
                                  if (drafts[cfg.key] !== undefined && Number.isFinite(n))
                                    saveSettings({ [cfg.key]: n } as SettingsUpdate)
                                  setDrafts((d) => { const { [cfg.key]: _omit, ...rest } = d; return rest })
                                }}
                                className="w-24 rounded border border-gray-300 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-emerald-500"
                              />
                            )}
                            {cfg.label}
                          </label>
                        ))}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
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
