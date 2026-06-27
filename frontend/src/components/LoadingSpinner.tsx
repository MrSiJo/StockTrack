export function LoadingSpinner() {
  return (
    <div className="flex items-center justify-center p-8">
      <div
        className="h-8 w-8 animate-spin rounded-full border-4 border-gray-200 border-t-emerald-600"
        aria-label="Loading"
        role="status"
      />
    </div>
  )
}
