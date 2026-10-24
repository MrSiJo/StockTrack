import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import { LoadingSpinner } from './components/LoadingSpinner'
import { ErrorMessage } from './components/ErrorMessage'
import { Dashboard } from './pages/Dashboard'
import { HistoryPage } from './pages/HistoryPage'
import { LoginPage } from './pages/LoginPage'
import { SetupPage } from './pages/SetupPage'
import { WatchesPage } from './pages/settings/WatchesPage'
import { GotifyPage } from './pages/settings/GotifyPage'
import { StoresPage } from './pages/settings/StoresPage'
import { TokensPage } from './pages/settings/TokensPage'
import { useAuthStore } from './stores/authStore'

export function App() {
  const status = useAuthStore((s) => s.status)
  const error = useAuthStore((s) => s.error)
  const bootstrap = useAuthStore((s) => s.bootstrap)

  useEffect(() => {
    void bootstrap()
  }, [bootstrap])

  // Never render the dashboard (and so never poll /api) until the session is known.
  if (status === 'loading') return <LoadingSpinner />
  if (status === 'error') {
    return (
      <div className="p-6">
        <ErrorMessage message={error ?? 'Could not reach the server.'} />
      </div>
    )
  }

  return (
    <BrowserRouter>
      <Routes>
        {status === 'authed' ? (
          <>
            <Route path="/" element={<Layout />}>
              <Route index element={<Dashboard />} />
              <Route path="history" element={<HistoryPage />} />
              <Route path="settings/watches" element={<WatchesPage />} />
              <Route path="settings/gotify" element={<GotifyPage />} />
              <Route path="settings/stores" element={<StoresPage />} />
              <Route path="settings/tokens" element={<TokensPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </>
        ) : (
          <>
            <Route
              path="/setup"
              element={status === 'setup' ? <SetupPage /> : <Navigate to="/login" replace />}
            />
            <Route
              path="/login"
              element={status === 'setup' ? <Navigate to="/setup" replace /> : <LoginPage />}
            />
            <Route
              path="*"
              element={<Navigate to={status === 'setup' ? '/setup' : '/login'} replace />}
            />
          </>
        )}
      </Routes>
    </BrowserRouter>
  )
}
