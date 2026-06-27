import { NavLink, Outlet } from 'react-router-dom'

interface NavItemProps {
  to: string
  label: string
  end?: boolean
}

function NavItem({ to, label, end }: NavItemProps) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
          isActive
            ? 'bg-gray-100 text-gray-900'
            : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
        }`
      }
    >
      {label}
    </NavLink>
  )
}

export function Layout() {
  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex h-14 items-center gap-6">
            <span className="text-base font-semibold tracking-tight text-gray-900">
              StockTrack
            </span>
            <nav className="flex items-center gap-1">
              <NavItem to="/" label="Dashboard" end />
              <NavItem to="/settings/watches" label="Watches" />
              <NavItem to="/settings/gotify" label="Gotify" />
              <NavItem to="/settings/stores" label="Stores" />
            </nav>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <Outlet />
      </main>
    </div>
  )
}
