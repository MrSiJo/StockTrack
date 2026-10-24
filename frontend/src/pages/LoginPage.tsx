import { useState, type FormEvent } from 'react'
import { useAuthStore } from '../stores/authStore'
import { ErrorMessage } from '../components/ErrorMessage'
import { AuthShell, inputClass, primaryButtonClass } from './AuthForm'

export function LoginPage() {
  const login = useAuthStore((s) => s.login)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    const msg = await login(username, password)
    setBusy(false)
    if (msg) setError(msg)
  }

  return (
    <AuthShell title="Sign in">
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
            autoComplete="current-password"
            required
          />
        </label>
        {error && <ErrorMessage message={error} />}
        <button type="submit" className={primaryButtonClass} disabled={busy}>
          {busy ? 'Signing in...' : 'Sign in'}
        </button>
      </form>
    </AuthShell>
  )
}
