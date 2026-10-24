import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { ApiError } from '../../api/client'
import {
  createToken,
  listTokens,
  revokeToken,
  type ApiToken,
  type CreatedToken,
} from '../../api/auth'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { ErrorMessage } from '../../components/ErrorMessage'

function fmt(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : 'never'
}

function stateOf(t: ApiToken): string {
  if (t.revoked_at) return 'Revoked'
  if (t.expires_at && new Date(t.expires_at).getTime() < Date.now()) return 'Expired'
  return 'Active'
}

function errText(e: unknown): string {
  if (e instanceof ApiError) return e.detail ?? e.message
  return String(e)
}

export function TokensPage() {
  const [tokens, setTokens] = useState<ApiToken[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [days, setDays] = useState('')
  const [busy, setBusy] = useState(false)
  // Component state only: never stored anywhere that persists.
  const [created, setCreated] = useState<CreatedToken | null>(null)
  const [copied, setCopied] = useState(false)
  const [confirming, setConfirming] = useState<number | null>(null)

  const load = useCallback(async () => {
    try {
      setTokens(await listTokens())
    } catch (e) {
      setError(errText(e))
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function onCreate(e: FormEvent) {
    e.preventDefault()
    const n = days.trim() === '' ? null : Number(days)
    if (n !== null && (!Number.isInteger(n) || n < 1)) {
      setError('Expiry must be a whole number of days, or empty for no expiry.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const t = await createToken(name.trim(), n)
      setCreated(t)
      setCopied(false)
      setName('')
      setDays('')
      await load()
    } catch (err) {
      setError(errText(err))
    } finally {
      setBusy(false)
    }
  }

  async function onRevoke(id: number) {
    if (confirming !== id) {
      setConfirming(id)
      return
    }
    setConfirming(null)
    try {
      await revokeToken(id)
      await load()
    } catch (err) {
      setError(errText(err))
    }
  }

  async function onCopy() {
    if (!created) return
    try {
      await navigator.clipboard.writeText(created.token)
      setCopied(true)
    } catch {
      setError('Could not copy. Select the token and copy it by hand.')
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-gray-900">API tokens</h1>
        <p className="text-sm text-gray-600">
          Read only tokens for other services. Send as <code>Authorization: Bearer ...</code>.
        </p>
      </div>

      {error && <ErrorMessage message={error} />}

      {created && (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-4" role="status">
          <p className="mb-2 text-sm font-medium text-amber-900">
            Token &quot;{created.name}&quot; created. You will not see this again.
          </p>
          <code
            data-testid="new-token"
            className="block break-all rounded bg-white p-2 font-mono text-sm text-gray-900"
          >
            {created.token}
          </code>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={onCopy}
              className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700"
            >
              {copied ? 'Copied' : 'Copy'}
            </button>
            <button
              type="button"
              onClick={() => setCreated(null)}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      <form
        onSubmit={onCreate}
        className="flex flex-wrap items-end gap-3 rounded-md border border-gray-200 bg-white p-4"
      >
        <label className="text-sm font-medium text-gray-700">
          Name
          <input
            className="mt-1 block rounded-md border border-gray-300 px-3 py-1.5 text-sm"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </label>
        <label className="text-sm font-medium text-gray-700">
          Expires in (days, optional)
          <input
            className="mt-1 block w-40 rounded-md border border-gray-300 px-3 py-1.5 text-sm"
            inputMode="numeric"
            value={days}
            onChange={(e) => setDays(e.target.value)}
          />
        </label>
        <button
          type="submit"
          disabled={busy || name.trim() === ''}
          className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          Create token
        </button>
      </form>

      {tokens === null && !error ? (
        <LoadingSpinner />
      ) : (
        tokens && (
          <div className="overflow-x-auto rounded-md border border-gray-200 bg-white">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-3 py-2">Name</th>
                  <th className="px-3 py-2">Created</th>
                  <th className="px-3 py-2">Expires</th>
                  <th className="px-3 py-2">Last used</th>
                  <th className="px-3 py-2">State</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {tokens.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-3 py-4 text-gray-500">
                      No tokens yet.
                    </td>
                  </tr>
                )}
                {tokens.map((t) => (
                  <tr key={t.id} className="border-t border-gray-100">
                    <td className="px-3 py-2 font-medium text-gray-900">{t.name}</td>
                    <td className="px-3 py-2">{fmt(t.created_at)}</td>
                    <td className="px-3 py-2">{fmt(t.expires_at)}</td>
                    <td className="px-3 py-2">{fmt(t.last_used_at)}</td>
                    <td className="px-3 py-2">{stateOf(t)}</td>
                    <td className="px-3 py-2 text-right">
                      {!t.revoked_at && (
                        <button
                          type="button"
                          onClick={() => onRevoke(t.id)}
                          onBlur={() => setConfirming(null)}
                          className={`rounded-md px-2 py-1 text-xs font-medium ${
                            confirming === t.id
                              ? 'bg-red-600 text-white hover:bg-red-700'
                              : 'border border-gray-300 text-gray-700 hover:bg-gray-50'
                          }`}
                        >
                          {confirming === t.id ? 'Confirm revoke' : 'Revoke'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  )
}
