import type { ReactNode } from 'react'

export function AuthShell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <h1 className="mb-4 text-lg font-semibold tracking-tight text-gray-900">
          StockTrack
          <span className="ml-2 text-sm font-normal text-gray-500">{title}</span>
        </h1>
        {children}
      </div>
    </div>
  )
}

export const inputClass =
  'mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-emerald-600 focus:outline-none focus:ring-1 focus:ring-emerald-600'
export const primaryButtonClass =
  'w-full rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50'
