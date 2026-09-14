import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { mockApi, renderWithProviders } from '@/test/render'
import { ForgotPasswordPage } from './ForgotPasswordPage'

const CONFIRMATION = "If an account exists for that email, we've sent a link to reset the password."

function renderPage() {
  return renderWithProviders(<ForgotPasswordPage />, { route: '/auth/forgot-password', session: null })
}

describe('ForgotPasswordPage', () => {
  it('sends the email and replaces the form with a neutral confirmation', async () => {
    const { calls } = mockApi({ 'POST /auth/forgot-password': { sent: true } })
    const { user } = renderPage()
    expect(screen.getByRole('heading', { level: 1, name: 'Reset your password' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to sign in' })).toHaveAttribute('href', '/auth/login')

    await user.type(screen.getByLabelText('Email'), '  mo@uiowa.edu ')
    await user.click(screen.getByRole('button', { name: 'Send reset link' }))

    expect(await screen.findByText(CONFIRMATION)).toBeInTheDocument()
    expect(calls.find((call) => call.method === 'POST')).toEqual({ method: 'POST', url: '/api/v1/auth/forgot-password', body: { email: 'mo@uiowa.edu' } })
    expect(screen.queryByLabelText('Email')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'Check your email' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to sign in' })).toHaveAttribute('href', '/auth/login')
    // The confirmation never repeats the address, so it reveals nothing about which accounts exist.
    expect(screen.queryByText(/mo@uiowa\.edu/)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Send another link' }))
    expect(screen.getByLabelText('Email')).toBeInTheDocument()
  })

  it('validates the email locally before sending', async () => {
    const { calls } = mockApi({ 'POST /auth/forgot-password': { sent: true } })
    const { user } = renderPage()
    await user.click(screen.getByRole('button', { name: 'Send reset link' }))
    expect(await screen.findByText('Enter your email address.')).toBeInTheDocument()
    await user.type(screen.getByLabelText('Email'), 'not-an-email')
    await user.click(screen.getByRole('button', { name: 'Send reset link' }))
    expect(await screen.findByText('Enter a valid email address.')).toBeInTheDocument()
    expect(calls).toHaveLength(0)
  })

  it('maps a 400 validation error onto the email field', async () => {
    mockApi({
      'POST /auth/forgot-password': { __error: { status: 400, code: 'validation', error: 'Validation failed.', errors: { email: 'Use your university email address.' } } },
    })
    const { user } = renderPage()
    await user.type(screen.getByLabelText('Email'), 'mo@example.com')
    await user.click(screen.getByRole('button', { name: 'Send reset link' }))
    expect(await screen.findByText('Use your university email address.')).toBeInTheDocument()
    expect(screen.getByLabelText('Email')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Email')).toHaveValue('mo@example.com')
    expect(screen.queryByText(CONFIRMATION)).not.toBeInTheDocument()
  })

  it('shows a 429 as an inline alert with the wait time and keeps the form', async () => {
    let attempts = 0
    mockApi({
      'POST /auth/forgot-password': () => {
        attempts += 1
        return attempts === 1 ? { __error: { status: 429, code: 'rate_limited', error: 'Too many requests.', extra: { retry_after: 120 } } } : { sent: true }
      },
    })
    const { user } = renderPage()
    await user.type(screen.getByLabelText('Email'), 'mo@uiowa.edu')
    await user.click(screen.getByRole('button', { name: 'Send reset link' }))
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Please wait before trying again')
    expect(alert).toHaveTextContent('Too many attempts. Try again in 2 minutes.')
    expect(screen.getByLabelText('Email')).toHaveValue('mo@uiowa.edu')

    await user.click(screen.getByRole('button', { name: 'Send reset link' }))
    expect(await screen.findByText(CONFIRMATION)).toBeInTheDocument()
  })
})
