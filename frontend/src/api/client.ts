const BASE = '/api'
const CSRF_COOKIE = 'stocktrack_csrf'
const MUTATING = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

export class ApiError extends Error {
  status: number
  /** The server's `detail` string when the body was JSON with one, else null. */
  detail: string | null
  constructor(status: number, message: string, detail: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export interface RequestOpts {
  /** Login, setup and the session probe: their 401 is an answer, not an expired session. */
  authProbe?: boolean
}

/** Called on a 401 from any request that is not an auth probe: the session has gone.
 * The auth store registers it (the store imports this module, so a callback avoids a cycle). */
let unauthorized: (() => void) | null = null
export function onUnauthorized(cb: (() => void) | null) {
  unauthorized = cb
}

export function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null
  const prefix = `${name}=`
  for (const part of document.cookie ? document.cookie.split('; ') : []) {
    if (part.startsWith(prefix)) return decodeURIComponent(part.slice(prefix.length))
  }
  return null
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  opts: RequestOpts = {},
): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> | undefined),
  }
  if (MUTATING.has(method)) {
    let csrf = readCookie(CSRF_COOKIE)
    if (!csrf) {
      // The server sets the CSRF cookie on any safe response; make one cheap GET.
      await fetch(`${BASE}/setup`, { credentials: 'include' }).catch(() => undefined)
      csrf = readCookie(CSRF_COOKIE)
    }
    if (csrf) headers['X-CSRF-Token'] = csrf
  }
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    method,
    headers,
    credentials: 'include',
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    let detail: string | null = null
    try {
      const parsed = JSON.parse(text) as { detail?: unknown }
      if (typeof parsed.detail === 'string') detail = parsed.detail
    } catch {
      // not JSON
    }
    if (res.status === 401 && !opts.authProbe) unauthorized?.()
    throw new ApiError(res.status, text, detail)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  get: <T>(path: string, opts?: RequestOpts) => request<T>(path, {}, opts),
  post: <T>(path: string, body?: unknown, opts?: RequestOpts) =>
    request<T>(
      path,
      {
        method: 'POST',
        body: body !== undefined ? JSON.stringify(body) : undefined,
      },
      opts,
    ),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  delete: <T = void>(path: string) => request<T>(path, { method: 'DELETE' }),
}
