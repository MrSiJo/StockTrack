import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { Dashboard } from './pages/Dashboard'
import { HistoryPage } from './pages/HistoryPage'
import { WatchesPage } from './pages/settings/WatchesPage'
import { GotifyPage } from './pages/settings/GotifyPage'
import { StoresPage } from './pages/settings/StoresPage'

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="settings/watches" element={<WatchesPage />} />
          <Route path="settings/gotify" element={<GotifyPage />} />
          <Route path="settings/stores" element={<StoresPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
