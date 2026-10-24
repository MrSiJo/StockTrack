import { api } from './client'

export interface AuthUser {
  user_id: number
  username: string
}

export interface ApiToken {
  id: number
  name: string
  created_at: string | null
  expires_at: string | null
  last_used_at: string | null
  revoked_at: string | null
}

export interface CreatedToken extends ApiToken {
  token: string
}

const probe = { authProbe: true }

export const getMe = () => api.get<AuthUser>('/auth/me', probe)
export const getSetupStatus = () => api.get<{ setup_needed: boolean }>('/setup', probe)
export const postSetup = (username: string, password: string) =>
  api.post<AuthUser>('/setup', { username, password }, probe)
export const postLogin = (username: string, password: string) =>
  api.post<AuthUser>('/auth/login', { username, password }, probe)
export const postLogout = () => api.post<{ ok: boolean }>('/auth/logout', undefined, probe)

export const listTokens = () => api.get<ApiToken[]>('/tokens')
export const createToken = (name: string, expiresInDays: number | null) =>
  api.post<CreatedToken>('/tokens', { name, expires_in_days: expiresInDays })
export const revokeToken = (id: number) => api.post<ApiToken>(`/tokens/${id}/revoke`)
