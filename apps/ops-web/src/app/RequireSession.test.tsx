import { screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { mockApi, renderWithProviders } from '@/test/render'
import { RequireSession } from './RequireSession'

describe('RequireSession', () => {
  it('explains a missing membership and offers only sign-out', async () => {
    const { calls } = mockApi({
      'GET /session': { __error: { status: 403, code: 'no_membership', error: 'You are not a member of this workspace.' } },
      'POST /auth/logout': {},
    })
    const { user } = renderWithProviders(<RequireSession />, { route: '/work-orders', session: null })
    expect(await screen.findByRole('heading', { name: 'You are signed in, but not a member of this workspace' })).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.queryByText(/portal/i)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Log out' }))
    await waitFor(() => expect(calls.some((call) => call.method === 'POST' && call.url === '/api/v1/auth/logout')).toBe(true))
  })
})
