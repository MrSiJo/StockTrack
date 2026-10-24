import { useState, type FormEvent } from 'react'
import { useAuthStore } from '../stores/authStore'
import { ErrorMessage } from '../components/ErrorMessage'
import { AuthShell, inputClass, primaryButtonClass } from './AuthForm'

export function SetupPage() {
  const setup = useAuthStore((s) => s.setup)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (password !== confirm) {
      setError('Passwords do not match.')
      return
    }
    setBusy(true)
    setError(null)
    const msg = await setup(username, password)
    setBusy(false)
    if (msg) setError(msg)
  }

  return (
    <AuthShell title="First run setup">
      <p className="mb-4 text-sm text-gray-600">Create the account you will sign in with.</p>
      <form onSubmit={onSubmit} className="space-y-4">
        <label className="block text-sm font-medium text-gray-700">
          Username
          <input
            className={inputClass}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
        </label>
        <label className="block text-sm font-medium text-gray-700">
          Password
          <input
            className={inputClass}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            required
          />
        </label>
        <label className="block text-sm font-medium text-gray-700">
          Confirm password
          <input
            className={inputClass}
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
            required
          />
        </label>
        {error && <ErrorMessage message={error} />}
        <button type="submit" className={primaryButtonClass} disabled={busy}>
          {busy ? 'Creating...' : 'Create account'}
        </button>
      </form>
    </AuthShell>
  )
}
