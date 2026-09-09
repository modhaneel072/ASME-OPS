import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ADMIN_SESSION, memberSession, mockApi, renderWithProviders } from '@/test/render'
import TeamsUsersPage from '.'
import { ADA, LEE, MEMBER_ADA, MEMBER_LEE, MEMBER_MO, MO, ROLES, ROUTE_PATHS, TEAM_A, TEAM_A_DETAIL, TEAM_B, TEAM_B_DETAIL, listOf } from './testFixtures'

const TEAM_DETAILS: Record<string, unknown> = { 'team-a': TEAM_A_DETAIL, 'team-b': TEAM_B_DETAIL }

function baseHandlers() {
  return {
    'GET /teams': listOf([TEAM_A, TEAM_B]),
    'GET /teams/:id': ({ url }: { url: URL }) => {
      const id = url.pathname.split('/').pop() ?? ''
      return TEAM_DETAILS[id] ? { team: TEAM_DETAILS[id] } : { __error: { status: 404, code: 'not_found', error: 'Not found.' } }
    },
    'GET /projects': listOf([]),
    'GET /users': listOf([MEMBER_ADA, MEMBER_LEE, MEMBER_MO]),
    'GET /roles': listOf(ROLES),
  }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Teams tab', () => {
  it('renders team rows with project code, leads and member counts', async () => {
    mockApi(baseHandlers())
    renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/teams', path: ROUTE_PATHS })
    const rows = await screen.findAllByTestId('team-row')
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('Robotic Arm')
    expect(rows[0]).toHaveTextContent('CCR')
    expect(rows[0]).toHaveTextContent('2 members')
    expect(rows[0]).toHaveTextContent('Led by Lee Lead')
    expect(within(rows[0]).getByRole('img', { name: 'Lee Lead' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Teams' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText('2 teams')).toBeInTheDocument()
  })

  it('shows the empty state with a create action for managers and without one for members', async () => {
    mockApi({ ...baseHandlers(), 'GET /teams': listOf([]) })
    const first = renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/teams', path: ROUTE_PATHS })
    expect(await screen.findByText('No teams yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create the first team' })).toBeInTheDocument()
    first.unmount()

    renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/teams', path: ROUTE_PATHS, session: memberSession() })
    expect(await screen.findByText('No teams yet')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Create the first team' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'New Team' })).not.toBeInTheDocument()
  })

  it('deep-links to a team and renders its members with the Lead badge and manage controls', async () => {
    mockApi(baseHandlers())
    renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/teams/team-a', path: ROUTE_PATHS })
    const details = screen.getByRole('region', { name: 'Details' })
    expect(await within(details).findByRole('heading', { name: /Robotic Arm/ })).toBeInTheDocument()
    const members = within(details).getByRole('list', { name: 'Team members' })
    const items = within(members).getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0]).toHaveTextContent('Lee Lead')
    expect(items[0]).toHaveTextContent('Lead')
    expect(items[0]).toHaveTextContent('lee@uiowa.edu')
    expect(items[1]).toHaveTextContent('Mo Member')
    expect(within(items[1]).queryByText('Lead')).not.toBeInTheDocument()
    expect(within(details).getByRole('link', { name: 'Crater Cruncher Rover' })).toHaveAttribute('href', '/projects/proj-1')
    expect(within(details).getByRole('button', { name: 'Edit' })).toBeInTheDocument()
    expect(within(details).getByRole('button', { name: 'Manage members' })).toBeInTheDocument()
    expect(screen.getAllByTestId('team-row')[0]).toHaveAttribute('aria-current', 'true')
  })

  it('hides edit controls from a plain member', async () => {
    mockApi(baseHandlers())
    renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/teams/team-a', path: ROUTE_PATHS, session: memberSession() })
    const details = screen.getByRole('region', { name: 'Details' })
    expect(await within(details).findByRole('heading', { name: /Robotic Arm/ })).toBeInTheDocument()
    expect(within(details).queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    expect(within(details).queryByRole('button', { name: 'Manage members' })).not.toBeInTheDocument()
    expect(within(details).queryByRole('button', { name: 'More actions' })).not.toBeInTheDocument()
  })

  it('lets a team lead edit only the team they lead', async () => {
    const lead = memberSession({
      user: { ...ADMIN_SESSION.user, id: LEE.id, name: LEE.name, email: LEE.email, username: 'lee', legacy_role: 'team_leader' },
      permissions: { ...memberSession().permissions, 'team.manage': ['team'] },
      scope: { project_ids: [], team_ids: ['team-a'], lead_team_ids: ['team-a'] },
    })
    mockApi(baseHandlers())
    const own = renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/teams/team-a', path: ROUTE_PATHS, session: lead })
    let details = screen.getByRole('region', { name: 'Details' })
    expect(await within(details).findByRole('heading', { name: /Robotic Arm/ })).toBeInTheDocument()
    expect(within(details).getByRole('button', { name: 'Edit' })).toBeInTheDocument()
    own.unmount()

    renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/teams/team-b', path: ROUTE_PATHS, session: lead })
    details = screen.getByRole('region', { name: 'Details' })
    expect(await within(details).findByRole('heading', { name: /Wheels and Mobility/ })).toBeInTheDocument()
    expect(within(details).queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
  })

  it('creates a team from the pane, posts the expected body, toasts and navigates to it', async () => {
    const created = { ...TEAM_B_DETAIL, id: 'team-new', name: 'Electrical', member_count: 0 }
    TEAM_DETAILS['team-new'] = created
    const { calls } = mockApi({ ...baseHandlers(), 'POST /teams': { team: created } })
    const { user } = renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/teams', path: ROUTE_PATHS })
    await screen.findAllByTestId('team-row')

    await user.click(screen.getByRole('button', { name: 'New Team' }))
    const pane = await screen.findByRole('dialog', { name: 'New Team' })
    await user.type(within(pane).getByLabelText('Name'), 'Electrical')
    await user.click(within(pane).getByRole('button', { name: 'Create Team' }))

    await waitFor(() => expect(calls.some((call) => call.method === 'POST' && call.url === '/api/v1/teams')).toBe(true))
    const post = calls.find((call) => call.method === 'POST' && call.url === '/api/v1/teams')
    expect(post?.body).toEqual({ name: 'Electrical', description: '', parent_team_id: null, project_id: null })
    expect(await screen.findByText('Team created')).toBeInTheDocument()
    await waitFor(() => expect(calls.some((call) => call.method === 'GET' && call.url === '/api/v1/teams/team-new')).toBe(true))
    expect(screen.queryByRole('dialog', { name: 'New Team' })).not.toBeInTheDocument()
    delete TEAM_DETAILS['team-new']
  })

  it('maps server validation errors onto the right field and keeps the pane open', async () => {
    mockApi({
      ...baseHandlers(),
      'POST /teams': { __error: { status: 400, code: 'validation', error: 'Validation failed.', errors: { name: 'A team with this name already exists.' } } },
    })
    const { user } = renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/teams?pane=new', path: ROUTE_PATHS })
    const pane = await screen.findByRole('dialog', { name: 'New Team' })
    await user.type(within(pane).getByLabelText('Name'), 'Robotic Arm')
    await user.click(within(pane).getByRole('button', { name: 'Create Team' }))
    const alert = await within(pane).findByRole('alert')
    expect(alert).toHaveTextContent('A team with this name already exists.')
    expect(within(pane).getByLabelText('Name')).toHaveAttribute('aria-invalid', 'true')
    expect(within(pane).getByLabelText('Name')).toHaveValue('Robotic Arm')
    expect(screen.getByRole('dialog', { name: 'New Team' })).toBeInTheDocument()
  })

  it('replaces the membership through PUT /teams/:id/members with lead flags', async () => {
    const { calls } = mockApi({
      ...baseHandlers(),
      'PUT /teams/:id/members': ({ body }: { body: unknown }) => {
        const wanted = (body as { members: Array<{ user_id: number; is_lead: boolean }> }).members
        const people = { [ADA.id]: ADA, [LEE.id]: LEE, [MO.id]: MO }
        return { team: { ...TEAM_A_DETAIL, member_count: wanted.length, members: wanted.map((entry) => ({ user: people[entry.user_id as 1 | 2 | 3], is_lead: entry.is_lead, joined_at: null })) } }
      },
    })
    const { user } = renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/teams/team-a', path: ROUTE_PATHS })
    const details = screen.getByRole('region', { name: 'Details' })
    await user.click(await within(details).findByRole('button', { name: 'Manage members' }))
    const dialog = await screen.findByRole('dialog', { name: /Manage members/ })
    expect(within(dialog).getByRole('button', { name: 'Save members' })).toBeDisabled()
    expect(within(dialog).getByRole('checkbox', { name: /Team lead: Lee Lead/ })).toBeChecked()
    expect(within(dialog).getByRole('checkbox', { name: /Team lead: Mo Member/ })).not.toBeChecked()

    await user.type(within(dialog).getByRole('combobox'), 'Ada')
    await user.click(await screen.findByRole('option', { name: /Ada Admin/ }))
    await user.click(within(dialog).getByRole('checkbox', { name: /Team lead: Ada Admin/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Save members' }))

    await waitFor(() => expect(calls.some((call) => call.method === 'PUT')).toBe(true))
    const put = calls.find((call) => call.method === 'PUT')
    expect(put?.url).toBe('/api/v1/teams/team-a/members')
    expect(put?.body).toEqual({
      members: [
        { user_id: LEE.id, is_lead: true },
        { user_id: MO.id, is_lead: false },
        { user_id: ADA.id, is_lead: true },
      ],
    })
    expect(await screen.findByText('Members updated')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('dialog', { name: /Manage members/ })).not.toBeInTheDocument())
  })

  it('surfaces a 409 team_in_use on delete as a toast with the server message', async () => {
    const message = 'This team is still referenced by other records; reassign them or deactivate the team instead.'
    mockApi({ ...baseHandlers(), 'DELETE /teams/:id': { __error: { status: 409, code: 'team_in_use', error: message } } })
    const { user } = renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/teams/team-a', path: ROUTE_PATHS })
    const details = screen.getByRole('region', { name: 'Details' })
    await user.click(await within(details).findByRole('button', { name: 'More actions' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Delete team' }))
    const confirm = await screen.findByRole('dialog', { name: 'Delete this team?' })
    await user.click(within(confirm).getByRole('button', { name: 'Delete' }))
    expect(await screen.findByText('Could not delete team')).toBeInTheDocument()
    expect(screen.getByText(message)).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: 'Delete this team?' })).not.toBeInTheDocument()
  })

  it('shows not-found for a missing team and an error with Retry when the list fails', async () => {
    let attempts = 0
    mockApi({
      ...baseHandlers(),
      'GET /teams': () => {
        attempts += 1
        return attempts === 1 ? { __error: { status: 500, code: 'server_error', error: 'Database unavailable.' } } : listOf([TEAM_A])
      },
    })
    const { user } = renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/teams/nope', path: ROUTE_PATHS })
    expect(await screen.findByText('Teams could not be loaded')).toBeInTheDocument()
    expect(await screen.findByText('Team not found')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findAllByTestId('team-row')).toHaveLength(1)
  })
})
