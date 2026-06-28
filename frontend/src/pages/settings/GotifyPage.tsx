import { useEffect, useState } from 'react'
import { useSettingsStore } from '../../stores/settingsStore'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { ErrorMessage } from '../../components/ErrorMessage'

interface GotifyForm {
  gotify_url: string
  gotify_token: string
  gotify_priority: number
  restock_priority: number
  oos_priority: number
  gotify_send_retries: number
  default_interval_seconds: number
  failure_alert_after: number
  heartbeat_hours: number
  early_access_days: number
  ao_member: boolean
  price_drop_min_pct: number
  price_drop_min_abs: number
  price_drop_priority: number
}

const EMPTY_FORM: GotifyForm = {
  gotify_url: '',
  gotify_token: '',
  gotify_priority: 7,
  restock_priority: 8,
  oos_priority: 4,
  gotify_send_retries: 3,
  default_interval_seconds: 300,
  failure_alert_after: 6,
  heartbeat_hours: 0,
  early_access_days: 30,
  ao_member: false,
  price_drop_min_pct: 5,
  price_drop_min_abs: 5,
  price_drop_priority: 6,
}

export function GotifyPage() {
  const { settings, loading, error, fetchSettings, saveSettings, sendTest } =
    useSettingsStore()
  const [form, setForm] = useState<GotifyForm>(EMPTY_FORM)
  const [tokenDirty, setTokenDirty] = useState(false)
  const [testResult, setTestResult] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    fetchSettings()
  }, [fetchSettings])

  useEffect(() => {
    if (settings) {
      setForm({
        gotify_url: settings.gotify_url,
        gotify_token: '',
        gotify_priority: settings.gotify_priority,
        restock_priority: settings.restock_priority,
        oos_priority: settings.oos_priority,
        gotify_send_retries: settings.gotify_send_retries,
        default_interval_seconds: settings.default_interval_seconds,
        failure_alert_after: settings.failure_alert_after,
        heartbeat_hours: settings.heartbeat_hours,
        early_access_days: settings.early_access_days,
        ao_member: settings.ao_member,
        price_drop_min_pct: settings.price_drop_min_pct,
        price_drop_min_abs: settings.price_drop_min_abs,
        price_drop_priority: settings.price_drop_priority,
      })
      setTokenDirty(false)
    }
  }, [settings])

  const set = (key: keyof GotifyForm, value: string | number | boolean) =>
    setForm((f) => ({ ...f, [key]: value }))

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setSaveError(null)
    try {
      await saveSettings({
        gotify_url: form.gotify_url,
        ...(tokenDirty && form.gotify_token
          ? { gotify_token: form.gotify_token }
          : {}),
        gotify_priority: form.gotify_priority,
        restock_priority: form.restock_priority,
        oos_priority: form.oos_priority,
        gotify_send_retries: form.gotify_send_retries,
        default_interval_seconds: form.default_interval_seconds,
        failure_alert_after: form.failure_alert_after,
        heartbeat_hours: form.heartbeat_hours,
        early_access_days: form.early_access_days,
        ao_member: form.ao_member,
        price_drop_min_pct: form.price_drop_min_pct,
        price_drop_min_abs: form.price_drop_min_abs,
        price_drop_priority: form.price_drop_priority,
      })
      setTokenDirty(false)
    } catch (e) {
      setSaveError(String(e))
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const result = await sendTest()
      setTestResult(result.delivered ? '✓ Delivered' : '✗ Not delivered')
    } catch (e) {
      setTestResult(`✗ Error: ${e}`)
    } finally {
      setTesting(false)
    }
  }

  if (loading && !settings) return <LoadingSpinner />
  if (error && !settings) return <ErrorMessage message={error} />

  const inputClass =
    'w-full rounded border border-gray-300 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-emerald-500'
  const labelClass = 'mb-1 block text-xs font-medium text-gray-700'

  return (
    <div className="max-w-xl">
      <h1 className="mb-6 text-xl font-semibold text-gray-900">
        Gotify settings
      </h1>

      {saveError && <ErrorMessage message={saveError} />}

      <form onSubmit={handleSave} className="space-y-4">
        <div className="space-y-3 rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-gray-800">Connection</h2>
          <div>
            <label className={labelClass}>Gotify URL</label>
            <input
              type="url"
              value={form.gotify_url}
              onChange={(e) => set('gotify_url', e.target.value)}
              className={inputClass}
              placeholder="http://gotify.local"
            />
          </div>
          <div>
            <label className={labelClass}>
              Token
              {settings?.gotify_token_set && !tokenDirty && (
                <span className="ml-1 text-gray-400">(configured)</span>
              )}
            </label>
            <input
              type="password"
              value={form.gotify_token}
              onChange={(e) => {
                setTokenDirty(true)
                set('gotify_token', e.target.value)
              }}
              placeholder={
                settings?.gotify_token_set && !tokenDirty
                  ? '••••••• — leave blank to keep'
                  : ''
              }
              className={inputClass}
              autoComplete="new-password"
            />
          </div>
        </div>

        <div className="space-y-3 rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-gray-800">
            Notification priorities
          </h2>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className={labelClass}>Default</label>
              <input
                type="number"
                value={form.gotify_priority}
                onChange={(e) => set('gotify_priority', Number(e.target.value))}
                className={inputClass}
                min={1}
                max={10}
              />
            </div>
            <div>
              <label className={labelClass}>Restock</label>
              <input
                type="number"
                value={form.restock_priority}
                onChange={(e) =>
                  set('restock_priority', Number(e.target.value))
                }
                className={inputClass}
                min={1}
                max={10}
              />
            </div>
            <div>
              <label className={labelClass}>OOS</label>
              <input
                type="number"
                value={form.oos_priority}
                onChange={(e) => set('oos_priority', Number(e.target.value))}
                className={inputClass}
                min={1}
                max={10}
              />
            </div>
          </div>
          <div>
            <label className={labelClass}>Send retries</label>
            <input
              type="number"
              value={form.gotify_send_retries}
              onChange={(e) =>
                set('gotify_send_retries', Number(e.target.value))
              }
              className={inputClass}
              min={0}
              max={10}
            />
          </div>
        </div>

        <div className="space-y-3 rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-gray-800">
            Poll defaults
          </h2>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelClass}>Default interval (s)</label>
              <input
                type="number"
                value={form.default_interval_seconds}
                onChange={(e) =>
                  set('default_interval_seconds', Number(e.target.value))
                }
                className={inputClass}
                min={60}
              />
            </div>
            <div>
              <label className={labelClass}>Failure alert after N checks</label>
              <input
                type="number"
                value={form.failure_alert_after}
                onChange={(e) =>
                  set('failure_alert_after', Number(e.target.value))
                }
                className={inputClass}
                min={1}
              />
            </div>
            <div>
              <label className={labelClass}>Heartbeat hours (0 = off)</label>
              <input
                type="number"
                value={form.heartbeat_hours}
                onChange={(e) =>
                  set('heartbeat_hours', Number(e.target.value))
                }
                className={inputClass}
                min={0}
                step={0.5}
              />
            </div>
            <div>
              <label className={labelClass}>
                Early access days threshold
              </label>
              <input
                type="number"
                value={form.early_access_days}
                onChange={(e) =>
                  set('early_access_days', Number(e.target.value))
                }
                className={inputClass}
                min={1}
              />
            </div>
          </div>
        </div>

        <div className="space-y-3 rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-gray-800">
            Price drops & AO membership
          </h2>
          <label className="flex cursor-pointer items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={form.ao_member}
              onChange={(e) => set('ao_member', e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
            />
            I'm an AO member (track AO member price)
          </label>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className={labelClass}>Min drop %</label>
              <input type="number" min={0} value={form.price_drop_min_pct}
                onChange={(e) => set('price_drop_min_pct', Number(e.target.value))}
                className={inputClass} />
            </div>
            <div>
              <label className={labelClass}>Min drop £</label>
              <input type="number" min={0} value={form.price_drop_min_abs}
                onChange={(e) => set('price_drop_min_abs', Number(e.target.value))}
                className={inputClass} />
            </div>
            <div>
              <label className={labelClass}>Drop priority</label>
              <input type="number" min={1} max={10} value={form.price_drop_priority}
                onChange={(e) => set('price_drop_priority', Number(e.target.value))}
                className={inputClass} />
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 pt-1">
          <button
            type="submit"
            disabled={saving}
            className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Save settings'}
          </button>
          <button
            type="button"
            onClick={handleTest}
            disabled={testing}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            {testing ? 'Sending…' : 'Send test'}
          </button>
          {testResult && (
            <span
              className={`text-sm ${
                testResult.startsWith('✓')
                  ? 'text-emerald-600'
                  : 'text-red-600'
              }`}
            >
              {testResult}
            </span>
          )}
        </div>
      </form>
    </div>
  )
}
