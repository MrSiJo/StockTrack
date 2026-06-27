interface Props {
  message: string
}

export function ErrorMessage({ message }: Props) {
  return (
    <div className="rounded-md bg-red-50 p-4">
      <p className="text-sm text-red-700">{message}</p>
    </div>
  )
}
