import { create } from 'zustand'
import { ApiError, onUnauthorized } from '../api/client'
import { getMe, getSetupStatus, postLogin, postLogout, postSetup } from '../api/auth'

// In memory only. The session is an HttpOnly cookie; nothing is persisted here.
export type AuthStatus = 'loading' | 'authed' | 'login' | 'setup' | 'error'

export const COOKIE_HINT =
  'Signed in, but the browser did not keep the session cookie. Served over plain HTTP? Set COOKIE_SECURE=false.'

interface AuthState {
  status: AuthStatus
  username: string | null
  error: string | null
  bootstrap: () => Promise<void>
  /** Each returns an error message, or null on success. */
  login: (username: string, password: string) => Promise<string | null>
  setup: (username: string, password: string) => Promise<string | null>
  logout: () => Promise<void>
}

function loginMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 401) return 'Invalid username or password.'
    if (e.status === 429) return 'Too many attempts, try later.'
    return e.detail ?? `Sign in failed (${e.status}).`
  }
  return 'Could not reach the server.'
}

export const useAuthStore = create<AuthState>((set, get) => ({
  status: 'loading',
  username: null,
  error: null,

  bootstrap: async () => {
    try {
      const me = await getMe()
      set({ status: 'authed', username: me.username, error: null })
      return
    } catch (e) {
      if (!(e instanceof ApiError) || e.status !== 401) {
        set({ status: 'error', error: 'Could not reach the server.' })
        return
      }
    }
    try {
      const { setup_needed } = await getSetupStatus()
      set({ status: setup_needed ? 'setup' : 'login', username: null, error: null })
    } catch {
      set({ status: 'error', error: 'Could not reach the server.' })
    }
  },

  login: async (username, password) => {
    try {
      await postLogin(username, password)
    } catch (e) {
      return loginMessage(e)
    }
    try {
      const me = await getMe()
      set({ status: 'authed', username: me.username, error: null })
      return null
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return COOKIE_HINT
      return 'Could not reach the server.'
    }
  },

  setup: async (username, password) => {
    try {
      await postSetup(username, password)
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.status === 409) return 'Setup is already complete. Sign in instead.'
        if (e.status === 400 || e.status === 422)
          return e.detail ?? 'That password is too weak.'
        return e.detail ?? `Setup failed (${e.status}).`
      }
      return 'Could not reach the server.'
    }
    return get().login(username, password)
  },

  logout: async () => {
    try {
      await postLogout()
    } catch {
      // clear local state regardless
    } finally {
      set({ status: 'login', username: null })
    }
  },
}))

// A 401 from any ordinary request means the session is gone: route to Login.
onUnauthorized(() => {
  if (useAuthStore.getState().status === 'authed') {
    useAuthStore.setState({ status: 'login', username: null })
  }
})
