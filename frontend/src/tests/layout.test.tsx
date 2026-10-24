// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { Layout } from '../components/Layout'
import { useAuthStore } from '../stores/authStore'

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status })
}

let logoutStatus: number

beforeEach(() => {
  document.cookie = 'stocktrack_csrf=tok; path=/'
  logoutStatus = 200
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => json(logoutStatus === 200 ? { ok: true } : { detail: 'x' }, logoutStatus)),
  )
  useAuthStore.setState({ status: 'authed', username: 'a', error: null })
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function renderLayout() {
  render(
    <MemoryRouter>
      <Layout />
    </MemoryRouter>,
  )
}

describe('Sign out', () => {
  it('shows an error and stays signed in when the server refuses', async () => {
    logoutStatus = 500
    renderLayout()
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect((await screen.findByRole('alert')).textContent).toBe('Sign out failed, try again')
    expect(useAuthStore.getState().status).toBe('authed')
  })
  it('signs out without an error on success', async () => {
    renderLayout()
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(useAuthStore.getState().status).toBe('login')
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
