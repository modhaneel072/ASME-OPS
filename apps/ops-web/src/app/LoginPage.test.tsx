import { screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { mockApi, renderWithProviders } from '@/test/render'
import { LoginPage } from './LoginPage'

const SIGNED_OUT = { __error: { status: 401, code: 'login_required', error: 'Sign in to continue.' } }

describe('LoginPage', () => {
  it('links to the in-app forgot-password page and nowhere outside ASME Ops', async () => {
    mockApi({ 'GET /session': SIGNED_OUT })
    renderWithProviders(<LoginPage />, { route: '/auth/login', session: null })
    await waitFor(() => expect(screen.getByLabelText('Email or username')).toHaveFocus())
    expect(screen.getByRole('link', { name: 'Forgot password?' })).toHaveAttribute('href', '/auth/forgot-password')
    expect(screen.queryByRole('link', { name: /website/i })).not.toBeInTheDocument()
    expect(screen.getAllByRole('link')).toHaveLength(1)
    expect(screen.queryByText(/password is set|password has been changed/)).not.toBeInTheDocument()
  })

  it('does not point to the member portal when the account has no workspace membership', async () => {
    mockApi({
      'GET /session': SIGNED_OUT,
      'POST /auth/login': { user: { id: 9, name: 'No Member', email: 'no@uiowa.edu', avatar_url: null }, session: null, membership: null },
    })
    const { user } = renderWithProviders(<LoginPage />, { route: '/auth/login', session: null })
    await user.type(await screen.findByLabelText('Email or username'), 'no@uiowa.edu')
    await user.type(screen.getByLabelText('Password'), 'whatever-1')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Signed in without a workspace membership')).toBeInTheDocument()
    expect(screen.queryByText(/portal/i)).not.toBeInTheDocument()
  })
})
