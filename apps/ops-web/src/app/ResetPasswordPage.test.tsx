import { screen, waitFor } from '@testing-library/react'
import { Route, Routes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { mockApi, renderWithProviders } from '@/test/render'
import { LoginPage } from './LoginPage'
import { ResetPasswordPage } from './ResetPasswordPage'

const TOKEN = 'tok-123'
const INVITE = { valid: true, purpose: 'invite', email: 'm***@uiowa.edu', expires_at: '2026-09-21T15:00:00Z' }
const RESET = { ...INVITE, purpose: 'reset' }
const SIGNED_OUT = { __error: { status: 401, code: 'login_required', error: 'Sign in to continue.' } }
const INVALID = { __error: { status: 404, code: 'invalid_token', error: 'This link is invalid or has expired.' } }

const STATUS = 'POST /auth/reset-password/status'
const RESET_URL = '/api/v1/auth/reset-password'

function renderAuth(route = `/auth/reset-password#token=${TOKEN}`) {
  return renderWithProviders(
    <Routes>
      <Route path="/auth/reset-password" element={<ResetPasswordPage />} />
      <Route path="/auth/login" element={<LoginPage />} />
      <Route path="/auth/forgot-password" element={<h1>Forgot password route</h1>} />
    </Routes>,
    { route, path: '/*', session: null },
  )
}

describe('ResetPasswordPage', () => {
  it('shows a skeleton while the link is checked, then the invite heading and masked email', async () => {
    mockApi({ [STATUS]: INVITE })
    renderAuth()
    expect(screen.getByRole('status', { name: 'Checking your link' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { level: 1, name: 'Set your password' })).toBeInTheDocument()
    expect(screen.getByText('m***@uiowa.edu')).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Set password' })).toBeInTheDocument()
  })

  it('uses the reset heading for an existing account', async () => {
    const { calls } = mockApi({ [STATUS]: RESET })
    renderAuth()
    expect(await screen.findByRole('heading', { level: 1, name: 'Choose a new password' })).toBeInTheDocument()
    expect(screen.getByLabelText('New password')).toBeInTheDocument()
    expect(calls[0]).toMatchObject({ method: 'POST', url: '/api/v1/auth/reset-password/status', body: { token: TOKEN } })
    expect(calls.some((call) => call.url.includes(TOKEN))).toBe(false)
  })

  it('shows the invalid-link state for an unknown or expired token, linking to a new request', async () => {
    mockApi({ [STATUS]: INVALID })
    const { user } = renderAuth()
    expect(await screen.findByRole('heading', { level: 1, name: 'This link is invalid or has expired' })).toBeInTheDocument()
    expect(screen.queryByLabelText('New password')).not.toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'Request a new link' }))
    expect(await screen.findByRole('heading', { name: 'Forgot password route' })).toBeInTheDocument()
  })

  it('ignores a token in the query string, which would reach server logs', () => {
    const { calls } = mockApi({ [STATUS]: RESET })
    renderAuth(`/auth/reset-password?token=${TOKEN}`)
    expect(screen.getByRole('heading', { level: 1, name: 'This link is invalid or has expired' })).toBeInTheDocument()
    expect(calls).toHaveLength(0)
  })

  it('treats a missing token as an invalid link without calling the API', () => {
    const { calls } = mockApi({ [STATUS]: RESET })
    renderAuth('/auth/reset-password')
    expect(screen.getByRole('heading', { level: 1, name: 'This link is invalid or has expired' })).toBeInTheDocument()
    expect(calls).toHaveLength(0)
  })

  it('offers a retry when the link cannot be checked', async () => {
    let attempts = 0
    mockApi({
      [STATUS]: () => {
        attempts += 1
        return attempts === 1 ? { __error: { status: 500, code: 'server_error', error: 'Try again later.' } } : RESET
      },
    })
    const { user } = renderAuth()
    expect(await screen.findByText('Try again later.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Choose a new password' })).toBeInTheDocument()
  })

  it('validates length and match on the client before sending', async () => {
    const { calls } = mockApi({ [STATUS]: RESET, 'POST /auth/reset-password': { reset: true } })
    const { user } = renderAuth()
    const password = await screen.findByLabelText('New password')
    await user.type(password, 'short')
    await user.type(screen.getByLabelText('Confirm password'), 'short')
    await user.click(screen.getByRole('button', { name: 'Change password' }))
    expect(await screen.findByText('Use at least 8 characters.')).toBeInTheDocument()

    await user.clear(password)
    await user.type(password, 'long-enough-1')
    await user.click(screen.getByRole('button', { name: 'Change password' }))
    expect(await screen.findByText('The passwords do not match.')).toBeInTheDocument()
    expect(calls.filter((call) => call.url === RESET_URL)).toHaveLength(0)
  })

  it('sets the password and lands on sign-in with a success notice', async () => {
    const { calls } = mockApi({ [STATUS]: INVITE, 'POST /auth/reset-password': { reset: true }, 'GET /session': SIGNED_OUT })
    const { user } = renderAuth()
    await user.type(await screen.findByLabelText('Password'), 'new-password-1')
    await user.type(screen.getByLabelText('Confirm password'), 'new-password-1')
    await user.click(screen.getByRole('button', { name: 'Set password' }))

    expect(await screen.findByText('Your password is set')).toBeInTheDocument()
    expect(screen.getByLabelText('Email or username')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Set your password' })).not.toBeInTheDocument()
    expect(calls.find((call) => call.url === RESET_URL)?.body).toEqual({ token: TOKEN, password: 'new-password-1', confirm_password: 'new-password-1' })
  })

  it('shows the changed-password notice after a reset', async () => {
    mockApi({ [STATUS]: RESET, 'POST /auth/reset-password': { reset: true }, 'GET /session': SIGNED_OUT })
    const { user } = renderAuth()
    await user.type(await screen.findByLabelText('New password'), 'new-password-1')
    await user.type(screen.getByLabelText('Confirm password'), 'new-password-1')
    await user.click(screen.getByRole('button', { name: 'Change password' }))
    expect(await screen.findByText('Your password has been changed')).toBeInTheDocument()
    expect(screen.getByText('Sign in with your new password.')).toBeInTheDocument()
  })

  it('maps server field errors onto the form', async () => {
    mockApi({
      [STATUS]: RESET,
      'POST /auth/reset-password': {
        __error: { status: 400, code: 'validation', error: 'Validation failed.', errors: { password: 'Pick a password that is harder to guess.', confirm_password: 'Passwords must match exactly.' } },
      },
    })
    const { user } = renderAuth()
    await user.type(await screen.findByLabelText('New password'), 'password1')
    await user.type(screen.getByLabelText('Confirm password'), 'password1')
    await user.click(screen.getByRole('button', { name: 'Change password' }))
    expect(await screen.findByText('Pick a password that is harder to guess.')).toBeInTheDocument()
    expect(screen.getByLabelText('New password')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('Passwords must match exactly.')).toBeInTheDocument()
    expect(screen.getByLabelText('Confirm password')).toHaveAttribute('aria-invalid', 'true')
  })

  it('switches to the invalid-link state when the token is rejected on submit', async () => {
    mockApi({ [STATUS]: RESET, 'POST /auth/reset-password': INVALID })
    const { user } = renderAuth()
    await user.type(await screen.findByLabelText('New password'), 'new-password-1')
    await user.type(screen.getByLabelText('Confirm password'), 'new-password-1')
    await user.click(screen.getByRole('button', { name: 'Change password' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'This link is invalid or has expired' })).toBeInTheDocument()
  })

  it('shows a 429 on submit as an inline alert and keeps the form', async () => {
    mockApi({
      [STATUS]: RESET,
      'POST /auth/reset-password': { __error: { status: 429, code: 'rate_limited', error: 'Too many requests.', extra: { retry_after: 30 } } },
    })
    const { user } = renderAuth()
    await user.type(await screen.findByLabelText('New password'), 'new-password-1')
    await user.type(screen.getByLabelText('Confirm password'), 'new-password-1')
    await user.click(screen.getByRole('button', { name: 'Change password' }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Too many attempts. Try again in 30 seconds.'))
    expect(screen.getByLabelText('New password')).toHaveValue('new-password-1')
  })
})
