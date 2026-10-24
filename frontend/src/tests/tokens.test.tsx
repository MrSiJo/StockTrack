// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TokensPage } from '../pages/settings/TokensPage'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status })
}

const meta = {
  id: 1,
  name: 'reader',
  created_at: '2026-10-24T10:00:00Z',
  expires_at: null,
  last_used_at: null,
  revoked_at: null,
}

let list: unknown[]
let calls: Array<[string, string, string | undefined]>

beforeEach(() => {
  document.cookie = 'stocktrack_csrf=tok; path=/'
  list = [meta]
  calls = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const m = (init?.method ?? 'GET').toUpperCase()
      calls.push([m, url, init?.body as string | undefined])
      if (m === 'GET') return json(list)
      if (url === '/api/tokens') {
        list = [...list, { ...meta, id: 2, name: 'fresh' }]
        return json({ ...meta, id: 2, name: 'fresh', token: 'st_secretvalue' }, 201)
      }
      list = [{ ...meta, revoked_at: '2026-10-24T11:00:00Z' }]
      return json(list[0])
    }),
  )
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('TokensPage', () => {
  it('shows a created token once and dismiss clears it', async () => {
    const user = userEvent.setup()
    render(<TokensPage />)
    await screen.findByText('reader')
    await user.type(screen.getByLabelText('Name'), 'fresh')
    await user.type(screen.getByLabelText(/Expires in/), '30')
    await user.click(screen.getByRole('button', { name: 'Create token' }))
    expect((await screen.findByTestId('new-token')).textContent).toBe('st_secretvalue')
    expect(screen.getByText(/will not see this again/)).toBeTruthy()
    const post = calls.find((c) => c[0] === 'POST')!
    expect(JSON.parse(post[2]!)).toEqual({ name: 'fresh', expires_in_days: 30 })
    await user.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(screen.queryByTestId('new-token')).toBeNull()
    expect(document.body.textContent).not.toContain('st_secretvalue')
    expect(JSON.stringify(Object.entries(localStorage))).not.toContain('st_secret')
  })

  it('revoke needs two clicks', async () => {
    const user = userEvent.setup()
    render(<TokensPage />)
    await user.click(await screen.findByRole('button', { name: 'Revoke' }))
    expect(calls.some((c) => c[1].includes('revoke'))).toBe(false)
    await user.click(screen.getByRole('button', { name: 'Confirm revoke' }))
    await waitFor(() => expect(calls.some((c) => c[1] === '/api/tokens/1/revoke')).toBe(true))
    await screen.findByText('Revoked')
  })
})
