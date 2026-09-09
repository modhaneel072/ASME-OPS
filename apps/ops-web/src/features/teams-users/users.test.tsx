import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { memberSession, mockApi, renderWithProviders } from '@/test/render'
import TeamsUsersPage from '.'
import { INVITE_LINK_WARNING } from './InviteDialog'
import { SELF_HINT } from './UsersTab'
import { MEMBER_ADA, MEMBER_LEE, MEMBER_MO, ROLES, ROLE_LEAD, ROUTE_PATHS, TEAM_A, TEAM_B, listOf } from './testFixtures'

const MEMBERS: Record<string, unknown> = { '1': MEMBER_ADA, '2': MEMBER_LEE, '3': MEMBER_MO }

function baseHandlers() {
  return {
    'GET /users': listOf([MEMBER_ADA, MEMBER_LEE, MEMBER_MO]),
    'GET /users/:id': ({ url }: { url: URL }) => {
      const id = url.pathname.split('/').pop() ?? ''
      return MEMBERS[id] ? { member: MEMBERS[id] } : { __error: { status: 404, code: 'not_found', error: 'Not found.' } }
    },
    'GET /roles': listOf(ROLES),
    'GET /teams': listOf([TEAM_A, TEAM_B]),
  }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Users tab', () => {
  it('renders member rows with role, status and team chips, and filters through the URL', async () => {
    const { calls } = mockApi(baseHandlers())
    const { user } = renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/users', path: ROUTE_PATHS })
    const rows = await screen.findAllByTestId('member-row')
    expect(rows).toHaveLength(3)
    expect(rows[1]).toHaveTextContent('Lee Lead')
    expect(rows[1]).toHaveTextContent('lee@uiowa.edu')
    expect(rows[1]).toHaveTextContent('Team Lead')
    expect(rows[1]).toHaveTextContent('Robotic Arm')
    expect(rows[2]).toHaveTextContent('Invited')
    expect(rows[0]).toHaveTextContent('You')

    await user.click(screen.getByRole('button', { name: /^Role/ }))
    await user.click(await screen.findByRole('checkbox', { name: 'Team Lead' }))
    await waitFor(() => expect(calls.some((call) => call.method === 'GET' && decodeURIComponent(call.url).includes('/users?') && decodeURIComponent(call.url).includes('filter[role]=team_lead'))).toBe(true))
    expect(screen.getByRole('button', { name: /^Role/ })).toHaveTextContent('Team Lead')
  })

  it('restores filters from a deep link and offers to clear them when nothing matches', async () => {
    const { calls } = mockApi({ ...baseHandlers(), 'GET /users': listOf([]) })
    const { user } = renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/users?filter[team]=team-a&filter[status]=invited', path: ROUTE_PATHS })
    expect(await screen.findByText('No members match')).toBeInTheDocument()
    const request = calls.find((call) => call.url.startsWith('/api/v1/users?'))
    expect(decodeURIComponent(request?.url ?? '')).toContain('filter[team]=team-a')
    expect(decodeURIComponent(request?.url ?? '')).toContain('filter[status]=invited')
    expect(screen.getByRole('button', { name: /^Status/ })).toHaveTextContent('Invited')
    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    await waitFor(() => expect(screen.getByRole('button', { name: /^Status/ })).not.toHaveTextContent('Invited'))
  })

  it('shows no invite or access controls to a plain member', async () => {
    mockApi(baseHandlers())
    renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/users/2', path: ROUTE_PATHS, session: memberSession() })
    const details = screen.getByRole('region', { name: 'Details' })
    expect(await within(details).findByRole('heading', { name: /Lee Lead/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Invite member' })).not.toBeInTheDocument()
    expect(within(details).queryByText('Role & access')).not.toBeInTheDocument()
    expect(within(details).queryByRole('form', { name: 'Role and access' })).not.toBeInTheDocument()
    expect(within(details).getByRole('link', { name: 'Robotic Arm' })).toHaveAttribute('href', '/teams-users/teams/team-a')
  })

  it('invites a member, shows the one-time link with a copy button, then navigates to them', async () => {
    const invited = { id: 'm-42', user: { id: 42, name: 'New Person', email: 'new.person@uiowa.edu', avatar_url: null }, role: ROLE_LEAD, status: 'invited', title: null, teams: [], joined_at: '2026-09-09T00:00:00Z', last_login_at: null }
    MEMBERS['42'] = invited
    const inviteUrl = 'http://localhost/reset-password/tok-123'
    const { calls } = mockApi({ ...baseHandlers(), 'POST /users/invite': { member: invited, invite_url: inviteUrl } })
    const { user } = renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/users', path: ROUTE_PATHS })
    await screen.findAllByTestId('member-row')

    await user.click(screen.getByRole('button', { name: 'Invite member' }))
    const dialog = await screen.findByRole('dialog', { name: 'Invite a member' })
    await user.type(within(dialog).getByLabelText('Email'), 'New.Person@UIowa.edu')
    await user.type(within(dialog).getByLabelText('Name'), 'New Person')
    await user.selectOptions(within(dialog).getByLabelText('Role'), 'team_lead')
    await user.click(within(dialog).getByRole('button', { name: 'Create invitation' }))

    await waitFor(() => expect(calls.some((call) => call.method === 'POST' && call.url === '/api/v1/users/invite')).toBe(true))
    const post = calls.find((call) => call.method === 'POST' && call.url === '/api/v1/users/invite')
    expect(post?.body).toEqual({ email: 'new.person@uiowa.edu', name: 'New Person', role_key: 'team_lead' })

    const ready = await screen.findByRole('dialog', { name: 'Invitation ready' })
    expect(within(ready).getByLabelText('Invite link')).toHaveValue(inviteUrl)
    expect(within(ready).getByText(INVITE_LINK_WARNING)).toBeInTheDocument()
    expect(within(ready).queryByLabelText('Email')).not.toBeInTheDocument()
    await user.click(within(ready).getByRole('button', { name: 'Copy link' }))
    expect(await within(ready).findByRole('button', { name: 'Copied' })).toBeInTheDocument()
    await expect(navigator.clipboard.readText()).resolves.toBe(inviteUrl)

    await user.click(within(ready).getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(calls.some((call) => call.method === 'GET' && call.url === '/api/v1/users/42')).toBe(true))
    delete MEMBERS['42']
  })

  it('puts a 409 already_member on the email field and keeps the form', async () => {
    const message = 'That person is already an active member of this chapter.'
    mockApi({ ...baseHandlers(), 'POST /users/invite': { __error: { status: 409, code: 'already_member', error: message } } })
    const { user } = renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/users?pane=invite', path: ROUTE_PATHS })
    const dialog = await screen.findByRole('dialog', { name: 'Invite a member' })
    await user.type(within(dialog).getByLabelText('Email'), 'lee@uiowa.edu')
    await user.type(within(dialog).getByLabelText('Name'), 'Lee Again')
    await user.click(within(dialog).getByRole('button', { name: 'Create invitation' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent(message)
    expect(within(dialog).getByLabelText('Email')).toHaveAttribute('aria-invalid', 'true')
    expect(within(dialog).getByLabelText('Email')).toHaveValue('lee@uiowa.edu')
  })

  it('opens the invite dialog with the n shortcut only for managers', async () => {
    mockApi(baseHandlers())
    const { user, unmount } = renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/users', path: ROUTE_PATHS })
    await screen.findAllByTestId('member-row')
    await user.keyboard('n')
    expect(await screen.findByRole('dialog', { name: 'Invite a member' })).toBeInTheDocument()
    unmount()

    renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/users', path: ROUTE_PATHS, session: memberSession() })
    await screen.findAllByTestId('member-row')
    await user.keyboard('n')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('saves role and title changes through PATCH /users/:id with only the changed keys', async () => {
    const { calls } = mockApi({
      ...baseHandlers(),
      'PATCH /users/:id': ({ body }: { body: unknown }) => ({ member: { ...MEMBER_LEE, ...(body as object), role: ROLES[0] } }),
    })
    const { user } = renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/users/2', path: ROUTE_PATHS })
    const form = await screen.findByRole('form', { name: 'Role and access' })
    const save = within(form).getByRole('button', { name: 'Save changes' })
    expect(save).toBeDisabled()
    await user.type(within(form).getByLabelText('Title'), 'Rover lead')
    await user.selectOptions(within(form).getByLabelText('Role'), 'r-1')
    expect(save).toBeEnabled()
    await user.click(save)

    await waitFor(() => expect(calls.some((call) => call.method === 'PATCH')).toBe(true))
    const patch = calls.find((call) => call.method === 'PATCH')
    expect(patch?.url).toBe('/api/v1/users/2')
    expect(patch?.body).toEqual({ role_id: 'r-1', title: 'Rover lead' })
    expect(await screen.findByText('Member updated')).toBeInTheDocument()
  })

  it('shows a 409 last_admin conflict inline and keeps the entered values', async () => {
    const message = 'At least one active Chapter Administrator must remain.'
    mockApi({ ...baseHandlers(), 'PATCH /users/:id': { __error: { status: 409, code: 'last_admin', error: message } } })
    const { user } = renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/users/2', path: ROUTE_PATHS })
    const form = await screen.findByRole('form', { name: 'Role and access' })
    await user.click(within(form).getByRole('radio', { name: 'Suspended' }))
    await user.click(within(form).getByRole('button', { name: 'Save changes' }))
    const alert = await within(form).findByRole('alert')
    expect(alert).toHaveTextContent(message)
    expect(within(form).getByRole('radio', { name: 'Suspended' })).toHaveAttribute('aria-checked', 'true')
  })

  it('disables role and status for the session user with the explanatory hint', async () => {
    mockApi(baseHandlers())
    renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/users/1', path: ROUTE_PATHS })
    const form = await screen.findByRole('form', { name: 'Role and access' })
    expect(within(form).getByLabelText('Role')).toBeDisabled()
    expect(within(form).queryByRole('radiogroup', { name: 'Status' })).not.toBeInTheDocument()
    expect(within(form).getByText(new RegExp(SELF_HINT))).toBeInTheDocument()
    expect(within(form).getByLabelText('Title')).toBeEnabled()
    const details = screen.getByRole('region', { name: 'Details' })
    expect(within(details).getByText('Username')).toBeInTheDocument()
    expect(within(details).getByText('ada')).toBeInTheDocument()
  })
})
