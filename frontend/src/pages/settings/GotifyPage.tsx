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
  price_drop_min_pct: number
  price_drop_min_abs: number
  price_drop_priority: number
  lead_time_priority: number
  lead_time_min_change_days: number
  new_product_priority: number
  alert_group_threshold: number
  price_drop_in_stock_only: boolean
  digest_cadence: string
  digest_hour: number
  digest_priority: number
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
  price_drop_min_pct: 5,
  price_drop_min_abs: 5,
  price_drop_priority: 6,
  lead_time_priority: 5,
  lead_time_min_change_days: 7,
  new_product_priority: 8,
  alert_group_threshold: 3,
  price_drop_in_stock_only: true,
  digest_cadence: 'off',
  digest_hour: 8,
  digest_priority: 4,
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
        price_drop_min_pct: settings.price_drop_min_pct,
        price_drop_min_abs: settings.price_drop_min_abs,
        price_drop_priority: settings.price_drop_priority,
        lead_time_priority: settings.lead_time_priority,
        lead_time_min_change_days: settings.lead_time_min_change_days,
        new_product_priority: settings.new_product_priority,
        alert_group_threshold: settings.alert_group_threshold,
        price_drop_in_stock_only: settings.price_drop_in_stock_only,
        digest_cadence: settings.digest_cadence,
        digest_hour: settings.digest_hour,
        digest_priority: settings.digest_priority,
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
        price_drop_min_pct: form.price_drop_min_pct,
        price_drop_min_abs: form.price_drop_min_abs,
        price_drop_priority: form.price_drop_priority,
        lead_time_priority: form.lead_time_priority,
        lead_time_min_change_days: form.lead_time_min_change_days,
        new_product_priority: form.new_product_priority,
        alert_group_threshold: form.alert_group_threshold,
        price_drop_in_stock_only: form.price_drop_in_stock_only,
        digest_cadence: form.digest_cadence,
        digest_hour: form.digest_hour,
        digest_priority: form.digest_priority,
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
            <div>
              <label className={labelClass}>New product</label>
              <input
                type="number"
                value={form.new_product_priority}
                onChange={(e) =>
                  set('new_product_priority', Number(e.target.value))
                }
                className={inputClass}
                min={1}
                max={10}
              />
            </div>
            <div>
              <label className={labelClass}>Lead time</label>
              <input
                type="number"
                value={form.lead_time_priority}
                onChange={(e) =>
                  set('lead_time_priority', Number(e.target.value))
                }
                className={inputClass}
                min={1}
                max={10}
              />
            </div>
            <div>
              <label className={labelClass}>Group alerts at ≥ (0 = off)</label>
              <input
                type="number"
                value={form.alert_group_threshold}
                onChange={(e) =>
                  set('alert_group_threshold', Number(e.target.value))
                }
                className={inputClass}
                min={0}
                max={50}
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
            <div>
              <label className={labelClass}>
                Lead-time alert min swing (days, 0 = any change)
              </label>
              <input
                type="number"
                value={form.lead_time_min_change_days}
                onChange={(e) =>
                  set('lead_time_min_change_days', Number(e.target.value))
                }
                className={inputClass}
                min={0}
              />
            </div>
          </div>
          <p className="text-xs text-gray-500">
            Delivery dates that naturally slide day-to-day (e.g. rolling
            next-day estimates) won't alert unless the date swings by at least
            this many days. Delivery ↔ collection switches always alert.
          </p>
        </div>

        <div className="space-y-3 rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-gray-800">
            Price drops
          </h2>
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
          <label className="flex cursor-pointer items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={form.price_drop_in_stock_only}
              onChange={(e) => set('price_drop_in_stock_only', e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
            />
            Only alert on price changes while in stock
          </label>
        </div>

        <div className="space-y-3 rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-gray-800">Digest</h2>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className={labelClass}>Cadence</label>
              <select
                value={form.digest_cadence}
                onChange={(e) => set('digest_cadence', e.target.value)}
                className={inputClass}
              >
                <option value="off">Off</option>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly (Mondays)</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Send after hour</label>
              <input type="number" min={0} max={23} value={form.digest_hour}
                onChange={(e) => set('digest_hour', Number(e.target.value))}
                className={inputClass} />
            </div>
            <div>
              <label className={labelClass}>Priority</label>
              <input type="number" min={1} max={10} value={form.digest_priority}
                onChange={(e) => set('digest_priority', Number(e.target.value))}
                className={inputClass} />
            </div>
          </div>
          <p className="text-xs text-gray-500">
            One roll-up push per day (or week) with what's in stock and what
            changed — checked every 15 minutes against the server timezone.
          </p>
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
