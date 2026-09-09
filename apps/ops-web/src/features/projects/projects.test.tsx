import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { memberSession, mockApi, renderWithProviders } from '@/test/render'
import ProjectsPage from '.'

const ROUTES = ['/projects', '/projects/:projectId', '/projects/:projectId/:tab']

const ADA = { id: 1, name: 'Ada Admin', email: 'ada@uiowa.edu', avatar_url: null }
const MO = { id: 3, name: 'Mo Member', email: 'mo@uiowa.edu', avatar_url: null }

const ROVER = {
  id: 'p1',
  name: 'Crater Cruncher Rover',
  code: 'CCR',
  description: 'Lunabotics competition rover.',
  status: 'active',
  visibility: 'chapter',
  risk_level: 'high',
  lead: ADA,
  faculty_advisor: null,
  start_date: '2026-08-20',
  target_date: '2027-05-15',
  budget_amount: 5000,
  repository_url: null,
  cad_url: null,
  requirements_url: null,
  competition: 'NASA Lunabotics',
  academic_year: '2026-27',
  public_project_id: null,
  archived_at: null,
  stats: { open_work_orders: 4, overdue_work_orders: 2, completion_percent: 45, next_milestone: { id: 'm1', name: 'Critical design review', status: 'planned', due_date: '2026-11-01' }, member_count: 2 },
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-02T00:00:00Z',
}
const SHOWCASE = { ...ROVER, id: 'p2', name: 'Fall Engineering Showcase', code: 'FES', visibility: 'private', risk_level: 'low', competition: null, academic_year: '2025-26', stats: { open_work_orders: 0, overdue_work_orders: 0, completion_percent: 100, next_milestone: null, member_count: 1 } }

const MEMBERS = [
  { user: ADA, project_role: 'lead', team: null, joined_at: '2026-09-01T00:00:00Z' },
  { user: MO, project_role: 'member', team: { id: 't1', name: 'Robotic Arm' }, joined_at: '2026-09-02T00:00:00Z' },
]

const HEALTH = {
  completion_percent: 45,
  work: { total: 11, open: 4, in_progress: 3, on_hold: 1, done: 4, canceled: 1, overdue: 2, blocked: 1 },
  milestones: { total: 3, done: 1, missed: 0, upcoming: [{ id: 'm1', project_id: 'p1', name: 'Critical design review', description: null, due_date: '2026-11-01', status: 'planned', owner: ADA, weight: 2, completed_at: null }] },
  budget: { amount: 5000, used: 1250.5, remaining: 3749.5 },
  members: 2,
  teams: [{ id: 't1', name: 'Robotic Arm' }],
  activity_7d: 6,
}

const EMPTY_LIST = { items: [], next_cursor: null, total: 0 }
const USERS = {
  items: [
    { id: 'm-1', user: ADA, role: { id: 'r-1', name: 'Chapter Administrator', system_key: 'chapter_admin' }, status: 'active', teams: [] },
    { id: 'm-3', user: MO, role: { id: 'r-5', name: 'Full Member', system_key: 'full_member' }, status: 'active', teams: [] },
  ],
  next_cursor: null,
  total: 2,
}
const TEAMS = { items: [{ id: 't1', name: 'Robotic Arm', leads: [ADA], member_count: 4, project: { id: 'p1', name: ROVER.name, code: 'CCR' } }], next_cursor: null, total: 1 }

function baseHandlers(overrides: Record<string, unknown> = {}) {
  return {
    'GET /projects': { items: [ROVER, SHOWCASE], next_cursor: null, total: 2 },
    'GET /projects/:id': { project: ROVER, members: MEMBERS },
    'GET /projects/:id/health': HEALTH,
    'GET /projects/:id/activity': { items: [{ id: 'e1', event_type: 'project.updated', entity_type: 'project', entity_id: 'p1', actor: ADA, summary: 'Updated project Crater Cruncher Rover', occurred_at: '2026-09-02T00:00:00Z' }], next_cursor: null, total: 1 },
    'GET /projects/:id/milestones': { items: [], next_cursor: null, total: 0 },
    'GET /users': USERS,
    'GET /teams': TEAMS,
    'GET /assets': EMPTY_LIST,
    'GET /work-orders': EMPTY_LIST,
    ...overrides,
  }
}

afterEach(() => vi.restoreAllMocks())

describe('Projects list', () => {
  it('renders rows with code, status, completion, next milestone and overdue count', async () => {
    mockApi(baseHandlers())
    renderWithProviders(<ProjectsPage />, { route: '/projects', path: ROUTES })
    const rows = await screen.findAllByTestId('project-row')
    expect(rows).toHaveLength(2)
    const rover = rows[0]
    expect(within(rover).getByText('Crater Cruncher Rover')).toBeInTheDocument()
    expect(within(rover).getByText('CCR')).toBeInTheDocument()
    expect(within(rover).getByText('45%')).toBeInTheDocument()
    expect(within(rover).getByText(/Critical design review/)).toBeInTheDocument()
    expect(within(rover).getByText(/2 overdue/)).toBeInTheDocument()
    expect(within(rows[1]).getByRole('img', { name: 'Private project' })).toBeInTheDocument()
    expect(screen.getByText('2 projects')).toBeInTheDocument()
  })

  it('shows the empty state with a gated create action', async () => {
    mockApi(baseHandlers({ 'GET /projects': EMPTY_LIST }))
    renderWithProviders(<ProjectsPage />, { route: '/projects', path: ROUTES })
    expect(await screen.findByText('No projects yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create the first project' })).toBeInTheDocument()
  })

  it('reads filters from the URL and syncs chip changes back into the request', async () => {
    const { calls } = mockApi(baseHandlers())
    const { user } = renderWithProviders(<ProjectsPage />, { route: '/projects?view=all&filter[risk]=high', path: ROUTES })
    await screen.findAllByTestId('project-row')
    await waitFor(() => expect(calls.some((c) => c.method === 'GET' && c.url.includes('view=all') && c.url.includes('filter%5Brisk%5D=high'))).toBe(true))
    expect(screen.getByRole('button', { name: /Risk.*High risk/ })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /^Status/ }))
    await user.click(await screen.findByRole('checkbox', { name: 'Active' }))
    await waitFor(() => expect(calls.some((c) => c.url.includes('filter%5Bstatus%5D=active') && c.url.includes('filter%5Brisk%5D=high'))).toBe(true))
  })

  it('shows the no-results state with a clear action when filters hide everything', async () => {
    mockApi(baseHandlers({ 'GET /projects': EMPTY_LIST }))
    renderWithProviders(<ProjectsPage />, { route: '/projects?filter[status]=on_hold', path: ROUTES })
    expect(await screen.findByText('No projects match')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Clear search and filters' })).toBeInTheDocument()
  })

  it('shows an inline error with retry when the list fails', async () => {
    mockApi(baseHandlers({ 'GET /projects': { __error: { status: 500, code: 'server_error', error: 'Database unavailable' } } }))
    renderWithProviders(<ProjectsPage />, { route: '/projects', path: ROUTES })
    expect(await screen.findByText('Projects could not be loaded')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})

describe('Project overview', () => {
  it('renders health numbers, budget and upcoming milestones from /health', async () => {
    mockApi(baseHandlers())
    renderWithProviders(<ProjectsPage />, { route: '/projects/p1', path: ROUTES })
    expect(await screen.findByText('45% of work complete')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open: 4 work orders' })).toHaveAttribute('href', '/work-orders?filter%5Bproject%5D=p1&filter%5Bstatus%5D=open')
    expect(screen.getByRole('link', { name: 'In progress: 3 work orders' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'On hold: 1 work orders' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Overdue: 2 work orders' })).toHaveAttribute('href', '/work-orders?filter%5Bproject%5D=p1&filter%5Bdue%5D=overdue')
    expect(screen.getByRole('link', { name: 'Blocked: 1 work orders' })).toBeInTheDocument()
    expect(screen.getByText('$1,250.50')).toBeInTheDocument()
    expect(screen.getByText('$3,749.50')).toBeInTheDocument()
    expect(screen.getByText('2 members')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Robotic Arm' })).toBeInTheDocument()
    expect(screen.getByText('Updated project Crater Cruncher Rover')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Overview/ })).toHaveAttribute('aria-selected', 'true')
  })

  it('shows the not-found state for a missing project', async () => {
    mockApi(baseHandlers({ 'GET /projects/:id': { __error: { status: 404, code: 'not_found', error: 'Not found.' } } }))
    renderWithProviders(<ProjectsPage />, { route: '/projects/nope', path: ROUTES })
    expect(await screen.findByText('Project not found')).toBeInTheDocument()
  })

  it('restores the tab from the URL', async () => {
    mockApi(baseHandlers())
    renderWithProviders(<ProjectsPage />, { route: '/projects/p1/budget', path: ROUTES })
    expect(await screen.findByRole('tab', { name: 'Budget' })).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByText('Budget vs spend')).toBeInTheDocument()
  })
})

describe('Milestones', () => {
  it('posts the milestone body and shows a success toast', async () => {
    const { calls } = mockApi(
      baseHandlers({
        'POST /projects/:id/milestones': ({ body }: { body: unknown }) => ({ milestone: { id: 'm9', project_id: 'p1', status: 'planned', weight: 1, ...(body as object) } }),
      }),
    )
    const { user } = renderWithProviders(<ProjectsPage />, { route: '/projects/p1/milestones', path: ROUTES })
    await user.click(await screen.findByRole('button', { name: 'Add milestone' }))
    const dialog = await screen.findByRole('dialog', { name: 'Add milestone' })
    await user.type(within(dialog).getByLabelText(/^Name/), 'Kickoff')
    await user.type(within(dialog).getByLabelText(/Due date/), '2026-10-01')
    await user.click(within(dialog).getByRole('button', { name: 'Add milestone' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.url === '/api/v1/projects/p1/milestones')).toBeTruthy())
    const post = calls.find((c) => c.method === 'POST' && c.url === '/api/v1/projects/p1/milestones')
    expect(post?.body).toEqual({ name: 'Kickoff', description: null, due_date: '2026-10-01', owner_user_id: null, weight: 1, status: 'planned' })
    expect(await screen.findByText('Milestone added')).toBeInTheDocument()
  })

  it('marks a milestone done through PATCH and shows missed milestones in danger', async () => {
    const { calls } = mockApi(
      baseHandlers({
        'GET /projects/:id/milestones': {
          items: [
            { id: 'm1', project_id: 'p1', name: 'Late review', status: 'missed', due_date: '2026-01-01', owner: null, weight: 1 },
            { id: 'm2', project_id: 'p1', name: 'Build complete', status: 'in_progress', due_date: null, owner: MO, weight: 3 },
          ],
          next_cursor: null,
          total: 2,
        },
        'PATCH /projects/:id/milestones/:mid': ({ body }: { body: unknown }) => ({ milestone: { id: 'm2', project_id: 'p1', name: 'Build complete', status: 'done', weight: 3, ...(body as object) } }),
      }),
    )
    const { user } = renderWithProviders(<ProjectsPage />, { route: '/projects/p1/milestones', path: ROUTES })
    expect(await screen.findByText('Missed')).toBeInTheDocument()
    const buttons = screen.getAllByRole('button', { name: 'Mark done' })
    await user.click(buttons[1])
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH' && c.url === '/api/v1/projects/p1/milestones/m2')?.body).toEqual({ status: 'done' }))
    expect(await screen.findByText('Milestone marked done')).toBeInTheDocument()
  })
})

describe('Members', () => {
  it('sends the full member list to PUT /projects/:id/members', async () => {
    const { calls } = mockApi(baseHandlers({ 'PUT /projects/:id/members': { project: ROVER, members: MEMBERS } }))
    const { user } = renderWithProviders(<ProjectsPage />, { route: '/projects/p1/teams', path: ROUTES })
    await user.click(await screen.findByRole('button', { name: 'Manage members' }))
    const dialog = await screen.findByRole('dialog', { name: 'Manage members' })
    await user.selectOptions(within(dialog).getByLabelText('Role for Mo Member'), 'viewer')
    await user.selectOptions(within(dialog).getByLabelText('Team for Mo Member'), '')
    await user.click(within(dialog).getByRole('button', { name: 'Save members' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'PUT')).toBeTruthy())
    expect(calls.find((c) => c.method === 'PUT')?.body).toEqual({
      members: [
        { user_id: 1, project_role: 'lead', team_id: null },
        { user_id: 3, project_role: 'viewer', team_id: null },
      ],
    })
    expect(await screen.findByText('Members updated')).toBeInTheDocument()
  })

  it('surfaces a members-level server error inside the dialog', async () => {
    mockApi(baseHandlers({ 'PUT /projects/:id/members': { __error: { status: 400, code: 'validation', error: 'Fix fields.', errors: { members: 'The project lead must remain a member.' } } } }))
    const { user } = renderWithProviders(<ProjectsPage />, { route: '/projects/p1/teams', path: ROUTES })
    await user.click(await screen.findByRole('button', { name: 'Manage members' }))
    const dialog = await screen.findByRole('dialog', { name: 'Manage members' })
    await user.click(within(dialog).getByRole('button', { name: 'Save members' }))
    expect(await within(dialog).findByText('The project lead must remain a member.')).toBeInTheDocument()
  })
})

describe('Create and edit', () => {
  it('opens the pane from the URL, posts the body, toasts and navigates to the new project', async () => {
    const { calls } = mockApi(baseHandlers({ 'POST /projects': ({ body }: { body: unknown }) => ({ project: { ...ROVER, id: 'p3', name: (body as { name: string }).name, code: 'LR' } }) }))
    const { user } = renderWithProviders(<ProjectsPage />, { route: '/projects', path: ROUTES })
    await user.click(await screen.findByRole('button', { name: 'New Project' }))
    const pane = await screen.findByRole('dialog', { name: 'New Project' })
    await user.type(within(pane).getByLabelText(/^Name/), 'Lunar Rover')
    await user.click(within(pane).getByRole('radio', { name: 'Private' }))
    await user.type(within(pane).getByLabelText(/Academic year/), '2026-27')
    await user.click(within(pane).getByRole('button', { name: 'Create Project' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.url === '/api/v1/projects')).toBeTruthy())
    expect(calls.find((c) => c.method === 'POST')?.body).toEqual({
      name: 'Lunar Rover',
      description: null,
      status: 'active',
      visibility: 'private',
      risk_level: 'low',
      lead_user_id: null,
      faculty_advisor_user_id: null,
      start_date: null,
      target_date: null,
      budget_amount: null,
      competition: null,
      academic_year: '2026-27',
      repository_url: null,
      cad_url: null,
      requirements_url: null,
      public_project_id: null,
    })
    expect(await screen.findByText('Project created')).toBeInTheDocument()
    await waitFor(() => expect(calls.some((c) => c.method === 'GET' && c.url === '/api/v1/projects/p3')).toBe(true))
  })

  it('maps server validation errors onto the right fields and keeps the entered data', async () => {
    mockApi(baseHandlers({ 'POST /projects': { __error: { status: 400, code: 'validation', error: 'Fix fields.', errors: { code: 'That code is already used by another project.', lead_user_id: 'Choose an active member of this chapter.' } } } }))
    const { user } = renderWithProviders(<ProjectsPage />, { route: '/projects?pane=new', path: ROUTES })
    const pane = await screen.findByRole('dialog', { name: 'New Project' })
    await user.type(within(pane).getByLabelText(/^Name/), 'Duplicate')
    await user.type(within(pane).getByLabelText(/^Code/), 'CCR')
    await user.click(within(pane).getByRole('button', { name: 'Create Project' }))
    expect(await within(pane).findByText('That code is already used by another project.')).toBeInTheDocument()
    expect(within(pane).getByText('Choose an active member of this chapter.')).toBeInTheDocument()
    expect(within(pane).getByLabelText(/^Name/)).toHaveValue('Duplicate')
    expect(within(pane).getByLabelText(/^Code/)).toHaveValue('CCR')
  })

  it('validates client-side before posting', async () => {
    const { calls } = mockApi(baseHandlers())
    const { user } = renderWithProviders(<ProjectsPage />, { route: '/projects?pane=new', path: ROUTES })
    const pane = await screen.findByRole('dialog', { name: 'New Project' })
    await user.type(within(pane).getByLabelText(/Academic year/), '2026')
    await user.click(within(pane).getByRole('button', { name: 'Create Project' }))
    expect(await within(pane).findByText('Give the project a name.')).toBeInTheDocument()
    expect(within(pane).getByText('Use the form YYYY-YY, for example 2026-27.')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
  })

  it('archives from the More menu after confirming', async () => {
    const { calls } = mockApi(baseHandlers({ 'POST /projects/:id/archive': { project: { ...ROVER, status: 'archived', archived_at: '2026-09-09T00:00:00Z' } } }))
    const { user } = renderWithProviders(<ProjectsPage />, { route: '/projects/p1', path: ROUTES })
    await screen.findByText('45% of work complete')
    await user.click(screen.getByRole('button', { name: 'Project actions' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Archive project' }))
    const dialog = await screen.findByRole('dialog', { name: 'Archive this project?' })
    expect(within(dialog).getByText(/work orders, documents and history stay visible/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Archive project' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url === '/api/v1/projects/p1/archive')).toBe(true))
    expect(await screen.findByText('Project archived')).toBeInTheDocument()
  })
})

describe('Permissions', () => {
  it('hides New Project, Edit and management controls for a full member', async () => {
    mockApi(baseHandlers())
    renderWithProviders(<ProjectsPage />, { route: '/projects/p1/teams', path: ROUTES, session: memberSession() })
    await screen.findAllByTestId('project-row')
    expect(screen.queryByRole('button', { name: 'New Project' })).not.toBeInTheDocument()
    await screen.findByRole('tab', { name: /Teams/ })
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Manage members' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Project actions' })).toBeInTheDocument()
  })

  it('hides milestone management for a full member', async () => {
    mockApi(baseHandlers({ 'GET /projects/:id/milestones': { items: [{ id: 'm1', project_id: 'p1', name: 'Late review', status: 'planned', due_date: null, owner: null, weight: 1 }], next_cursor: null, total: 1 } }))
    renderWithProviders(<ProjectsPage />, { route: '/projects/p1/milestones', path: ROUTES, session: memberSession() })
    expect(await screen.findByText('Late review')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add milestone' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Mark done' })).not.toBeInTheDocument()
  })

  it('surfaces a 403 as a toast instead of failing silently', async () => {
    mockApi(baseHandlers({ 'POST /projects': { __error: { status: 403, code: 'forbidden', error: 'You do not have permission to create projects.' } } }))
    const { user } = renderWithProviders(<ProjectsPage />, { route: '/projects?pane=new', path: ROUTES })
    const pane = await screen.findByRole('dialog', { name: 'New Project' })
    await user.type(within(pane).getByLabelText(/^Name/), 'Denied')
    await user.click(within(pane).getByRole('button', { name: 'Create Project' }))
    expect(await screen.findByText('Could not save project')).toBeInTheDocument()
    expect(within(pane).getByLabelText(/^Name/)).toHaveValue('Denied')
  })
})
