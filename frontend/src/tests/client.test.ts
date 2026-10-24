// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, onUnauthorized } from '../api/client'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status })
}

function clearCookies() {
  for (const c of document.cookie.split('; ')) {
    const name = c.split('=')[0]
    if (name) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`
  }
}

beforeEach(() => {
  clearCookies()
  document.cookie = 'stocktrack_csrf=abc123; path=/'
})
afterEach(() => {
  vi.unstubAllGlobals()
  onUnauthorized(null)
})

function stub(fn: (url: string, init?: RequestInit) => Promise<Response>) {
  const m = vi.fn((url: string, init?: RequestInit) => fn(url, init))
  vi.stubGlobal('fetch', m)
  return m
}

function headersOf(call: unknown[]) {
  return (call[1] as RequestInit).headers as Record<string, string>
}

describe('client', () => {
  it('sends credentials and no CSRF header on GET', async () => {
    const f = stub(async () => json({ ok: 1 }))
    await api.get('/x')
    expect((f.mock.calls[0][1] as RequestInit).credentials).toBe('include')
    expect(headersOf(f.mock.calls[0])['X-CSRF-Token']).toBeUndefined()
  })

  it.each([
    ['post', () => api.post('/x', { a: 1 })],
    ['put', () => api.put('/x', { a: 1 })],
    ['delete', () => api.delete('/x')],
  ])('echoes the CSRF cookie on %s', async (_n, call) => {
    const f = stub(async () => json({}))
    await call()
    expect(headersOf(f.mock.calls[0])['X-CSRF-Token']).toBe('abc123')
  })

  it('primes the cookie with a GET when it is absent', async () => {
    clearCookies()
    const f = stub(async (url) => {
      if (url === '/api/setup') document.cookie = 'stocktrack_csrf=fresh; path=/'
      return json({})
    })
    await api.post('/x', {})
    expect(f.mock.calls[0][0]).toBe('/api/setup')
    expect(headersOf(f.mock.calls[1])['X-CSRF-Token']).toBe('fresh')
  })

  it('fires the 401 hook, but not for auth probes', async () => {
    stub(async () => json({ detail: 'Authentication required' }, 401))
    const hook = vi.fn()
    onUnauthorized(hook)
    await expect(api.get('/x')).rejects.toBeInstanceOf(ApiError)
    expect(hook).toHaveBeenCalledTimes(1)
    await expect(api.get('/x', { authProbe: true })).rejects.toMatchObject({
      status: 401,
      detail: 'Authentication required',
    })
    expect(hook).toHaveBeenCalledTimes(1)
  })
})
