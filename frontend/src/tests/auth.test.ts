// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status })
}

let handler: (url: string) => Response
let calls: string[]

async function load() {
  vi.resetModules()
  return import('../stores/authStore')
}

const ME = { user_id: 1, username: 'a' }

beforeEach(() => {
  document.cookie = 'stocktrack_csrf=tok; path=/'
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(`${(init?.method ?? 'GET').toUpperCase()} ${url}`)
      return handler(url)
    }),
  )
})
afterEach(() => vi.unstubAllGlobals())

describe('bootstrap', () => {
  it('me 200 -> authed', async () => {
    handler = () => json(ME)
    const { useAuthStore } = await load()
    await useAuthStore.getState().bootstrap()
    expect(useAuthStore.getState().status).toBe('authed')
    expect(useAuthStore.getState().username).toBe('a')
  })
  it('me 401 + setup_needed true -> setup', async () => {
    handler = (u) => (u === '/api/auth/me' ? json({ detail: 'x' }, 401) : json({ setup_needed: true }))
    const { useAuthStore } = await load()
    await useAuthStore.getState().bootstrap()
    expect(useAuthStore.getState().status).toBe('setup')
  })
  it('me 401 + setup_needed false -> login', async () => {
    handler = (u) => (u === '/api/auth/me' ? json({ detail: 'x' }, 401) : json({ setup_needed: false }))
    const { useAuthStore } = await load()
    await useAuthStore.getState().bootstrap()
    expect(useAuthStore.getState().status).toBe('login')
  })
})

describe('login', () => {
  it('401 gives an invalid credentials message', async () => {
    handler = () => json({ detail: 'invalid credentials' }, 401)
    const { useAuthStore } = await load()
    expect(await useAuthStore.getState().login('a', 'b')).toMatch(/invalid/i)
  })
  it('429 gives a throttle message', async () => {
    handler = () => json({ detail: 'slow' }, 429)
    const { useAuthStore } = await load()
    expect(await useAuthStore.getState().login('a', 'b')).toBe('Too many attempts, try later.')
  })
  it('200 then me 401 shows the COOKIE_SECURE hint', async () => {
    handler = (u) => (u === '/api/auth/login' ? json(ME) : json({}, 401))
    const { useAuthStore, COOKIE_HINT } = await load()
    const msg = await useAuthStore.getState().login('a', 'b')
    expect(msg).toBe(COOKIE_HINT)
    expect(msg).toContain('COOKIE_SECURE=false')
    expect(useAuthStore.getState().status).not.toBe('authed')
  })
  it('200 then me 200 is authed', async () => {
    handler = () => json(ME)
    const { useAuthStore } = await load()
    expect(await useAuthStore.getState().login('a', 'b')).toBeNull()
    expect(useAuthStore.getState().status).toBe('authed')
  })
})

describe('setup', () => {
  it('201 then logs in with the same credentials', async () => {
    handler = (u) => (u === '/api/setup' ? json(ME, 201) : json(ME))
    const { useAuthStore } = await load()
    expect(await useAuthStore.getState().setup('a', 'pw')).toBeNull()
    expect(calls).toEqual(['POST /api/setup', 'POST /api/auth/login', 'GET /api/auth/me'])
    expect(useAuthStore.getState().status).toBe('authed')
  })
  it('400 shows the server detail', async () => {
    handler = () => json({ detail: 'password too short' }, 400)
    const { useAuthStore } = await load()
    expect(await useAuthStore.getState().setup('a', 'pw')).toBe('password too short')
  })
})

describe('session loss', () => {
  it('a 401 on an ordinary call moves an authed session to login', async () => {
    handler = () => json(ME)
    const { useAuthStore } = await load()
    await useAuthStore.getState().bootstrap()
    const { api } = await import('../api/client')
    handler = () => json({ detail: 'Authentication required' }, 401)
    await expect(api.get('/watches')).rejects.toBeTruthy()
    expect(useAuthStore.getState().status).toBe('login')
  })
})

describe('logout', () => {
  async function authed() {
    handler = () => json(ME)
    const mod = await load()
    await mod.useAuthStore.getState().bootstrap()
    expect(mod.useAuthStore.getState().status).toBe('authed')
    return mod
  }

  it('200 signs out', async () => {
    const { useAuthStore } = await authed()
    handler = () => json({ ok: true })
    expect(await useAuthStore.getState().logout()).toBeNull()
    expect(useAuthStore.getState().status).toBe('login')
    expect(useAuthStore.getState().username).toBeNull()
  })
  it('401 means already signed out', async () => {
    const { useAuthStore } = await authed()
    handler = () => json({ detail: 'Authentication required' }, 401)
    expect(await useAuthStore.getState().logout()).toBeNull()
    expect(useAuthStore.getState().status).toBe('login')
  })
  it('a server error keeps the session and reports it', async () => {
    const { useAuthStore, SIGN_OUT_FAILED } = await authed()
    handler = () => json({ detail: 'boom' }, 500)
    expect(await useAuthStore.getState().logout()).toBe(SIGN_OUT_FAILED)
    expect(SIGN_OUT_FAILED).toBe('Sign out failed, try again')
    expect(useAuthStore.getState().status).toBe('authed')
    expect(useAuthStore.getState().username).toBe('a')
  })
  it('a network error keeps the session and reports it', async () => {
    const { useAuthStore, SIGN_OUT_FAILED } = await authed()
    handler = () => {
      throw new TypeError('Failed to fetch')
    }
    expect(await useAuthStore.getState().logout()).toBe(SIGN_OUT_FAILED)
    expect(useAuthStore.getState().status).toBe('authed')
  })
})
