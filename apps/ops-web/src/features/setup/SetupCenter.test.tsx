import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextSetupTask, summarizeSetupPhase, type SetupProgress, type SetupTask } from '@/api/contracts/setup'
import { ADMIN_SESSION, createTestQueryClient, memberSession, mockApi, renderWithProviders } from '@/test/render'
import SetupPage from './index'
import { appPath } from './paths'

/* Fixtures -------------------------------------------------------------------- */

function task(overrides: Partial<SetupTask> & Pick<SetupTask, 'key' | 'title' | 'href'>): SetupTask {
  return {
    description: `${overrides.title} description.`,
    estimated_minutes: 5,
    status: 'incomplete',
    stage: null,
    count: null,
    optional: false,
    ...overrides,
  }
}

function freshProgress(): SetupProgress {
  return {
    phases: [
      {
        key: 'foundation',
        title: 'Build the Foundation',
        description: 'Describe the chapter, where work happens, what you own and who does it.',
        tasks: [
          task({ key: 'chapter_profile', title: 'Complete the chapter profile', href: '/app/settings/chapter' }),
          task({ key: 'locations', title: 'Add your first location', href: '/app/locations', count: 0 }),
          task({ key: 'assets', title: 'Register your assets', href: '/app/assets', count: 2, estimated_minutes: 15 }),
          task({ key: 'teams_users', title: 'Set up teams and members', href: '/app/teams-users', count: 3, estimated_minutes: 10 }),
          task({ key: 'officer_guide', title: 'Read the officer guide', href: '/app/setup', optional: true, estimated_minutes: 10 }),
        ],
      },
      {
        key: 'project_work',
        title: 'Organize Project Work',
        description: 'Create a project, label work with categories and prepare parts and procedures.',
        tasks: [
          task({ key: 'first_project', title: 'Create your first project', href: '/app/projects', count: 0 }),
          task({ key: 'categories', title: 'Review categories', href: '/app/categories', status: 'complete', count: 14 }),
          task({ key: 'parts', title: 'Stock your parts inventory', href: '/app/parts', status: 'unavailable', stage: 4, estimated_minutes: 15 }),
          task({ key: 'procedure', title: 'Write a procedure', href: '/app/procedures', status: 'unavailable', stage: 5, estimated_minutes: 20 }),
        ],
      },
      {
        key: 'standardize',
        title: 'Standardize Operations',
        description: 'Automate recurring work, open a request portal and build dashboards.',
        tasks: [
          task({ key: 'maintenance_plan', title: 'Create a maintenance plan', href: '/app/maintenance-plans', status: 'unavailable', stage: 5 }),
          task({ key: 'request_portal', title: 'Open the request portal', href: '/app/requests', status: 'unavailable', stage: 3 }),
          task({ key: 'automation', title: 'Add an automation', href: '/app/automations', status: 'unavailable', stage: 6 }),
          task({ key: 'dashboard', title: 'Build a dashboard', href: '/app/dashboards', status: 'unavailable', stage: 7 }),
        ],
      },
    ],
    progress: { completed: 1, available: 6, percent: 17 },
    banner_dismissed: false,
    completed_at: null,
  }
}

/** Every live task done (the optional guide included); nothing left but "Mark setup complete". */
function finishedProgress(): SetupProgress {
  const progress = freshProgress()
  for (const phase of progress.phases) {
    for (const item of phase.tasks) if (item.status === 'incomplete') item.status = 'complete'
  }
  progress.progress = { completed: 6, available: 6, percent: 100 }
  return progress
}

function taskCard(key: string): HTMLElement {
  const card = document.querySelector<HTMLElement>(`[data-testid="setup-task"][data-task-key="${key}"]`)
  if (!card) throw new Error(`No task card for ${key}`)
  return card
}

afterEach(() => vi.restoreAllMocks())

/* Helpers --------------------------------------------------------------------- */

describe('setup helpers', () => {
  it('strips the router basename from API hrefs', () => {
    expect(appPath('/app/locations')).toBe('/locations')
    expect(appPath('/app/settings/chapter')).toBe('/settings/chapter')
    expect(appPath('/app')).toBe('/')
    expect(appPath('/api/v1/docs')).toBe('/api/v1/docs')
  })

  it('suggests the first incomplete required task, then optional ones, never unavailable ones', () => {
    expect(nextSetupTask(freshProgress())?.key).toBe('chapter_profile')
    const onlyGuideLeft = freshProgress()
    for (const phase of onlyGuideLeft.phases) for (const item of phase.tasks) if (item.status === 'incomplete' && !item.optional) item.status = 'complete'
    expect(nextSetupTask(onlyGuideLeft)?.key).toBe('officer_guide')
    expect(nextSetupTask(finishedProgress())).toBeNull()
  })

  it('summarises a phase without counting optional or unavailable tasks', () => {
    const [foundation, projectWork, standardize] = freshProgress().phases
    expect(summarizeSetupPhase(foundation)).toEqual({ available: 4, completed: 0, deferred: false })
    expect(summarizeSetupPhase(projectWork)).toEqual({ available: 2, completed: 1, deferred: false })
    expect(summarizeSetupPhase(standardize)).toEqual({ available: 0, completed: 0, deferred: true })
  })
})

/* Page ------------------------------------------------------------------------ */

describe('SetupPage', () => {
  it('renders the welcome heading, phases, tasks and their statuses from the payload', async () => {
    mockApi({ 'GET /setup': freshProgress() })
    renderWithProviders(<SetupPage />, { route: '/setup' })

    expect(screen.getByRole('heading', { level: 1, name: 'Welcome to ASME Ops Setup Center' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { level: 2, name: 'Build the Foundation' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Organize Project Work' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2, name: 'Standardize Operations' })).toBeInTheDocument()
    expect(screen.getAllByTestId('setup-task')).toHaveLength(13)

    // Incomplete: outline indicator + "Set up" link to the task's screen (basename stripped).
    const assets = taskCard('assets')
    expect(within(assets).getByRole('img', { name: 'Not done yet' })).toBeInTheDocument()
    expect(within(assets).getByRole('link', { name: 'Set up Register your assets' })).toHaveAttribute('href', '/assets')
    expect(within(assets).getByText('~15 min')).toBeInTheDocument()
    expect(within(assets).getByText('2 assets registered')).toBeInTheDocument()
    expect(within(taskCard('teams_users')).getByText('3 active members')).toBeInTheDocument()
    expect(within(taskCard('locations')).getByText('0 locations added')).toBeInTheDocument()

    // Complete: "Done" and a subtle "Review" link.
    const categories = taskCard('categories')
    expect(within(categories).getByText('Done')).toBeInTheDocument()
    expect(within(categories).getByRole('link', { name: 'Review Review categories' })).toHaveAttribute('href', '/categories')
    expect(within(categories).queryByRole('link', { name: /Set up/ })).not.toBeInTheDocument()
    expect(within(categories).getByText('14 categories')).toBeInTheDocument()

    // Unavailable: lock + stage badge, no control at all.
    const parts = taskCard('parts')
    expect(within(parts).getByRole('img', { name: 'Not available yet' })).toBeInTheDocument()
    expect(within(parts).getByText('Stage 4')).toBeInTheDocument()
    expect(within(parts).queryByRole('link')).not.toBeInTheDocument()
    expect(within(parts).queryByRole('button')).not.toBeInTheDocument()

    // Optional guide opens in place rather than linking back to this page.
    const guide = taskCard('officer_guide')
    expect(within(guide).getByText('Optional')).toBeInTheDocument()
    expect(within(guide).getByRole('button', { name: 'Read guide' })).toBeInTheDocument()
    expect(within(guide).queryByRole('link')).not.toBeInTheDocument()

    // Phase summaries.
    expect(screen.getByText('0 of 4 done')).toBeInTheDocument()
    expect(screen.getByText('1 of 2 done')).toBeInTheDocument()
    expect(screen.getByText('Later stages')).toBeInTheDocument()

    // Progress panel and the highlighted next task.
    expect(screen.getByRole('progressbar', { name: 'Setup progress' })).toHaveAttribute('aria-valuenow', '17')
    expect(screen.getByText('1 of 6 tasks done')).toBeInTheDocument()
    const next = screen.getByRole('region', { name: 'Up next' })
    expect(within(next).getByRole('heading', { level: 3, name: 'Complete the chapter profile' })).toBeInTheDocument()
    expect(within(next).getByRole('link', { name: 'Set up Complete the chapter profile' })).toHaveAttribute('href', '/settings/chapter')
  })

  it('disables "Mark setup complete" with a hint until every required task is done', async () => {
    mockApi({ 'GET /setup': freshProgress() })
    renderWithProviders(<SetupPage />, { route: '/setup' })
    const button = await screen.findByRole('button', { name: 'Mark setup complete' })
    expect(button).toBeDisabled()
    expect(button).toHaveAccessibleDescription(/Finish the remaining 5 required tasks/)
    expect(screen.getByRole('button', { name: 'Mark officer guide read' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Hide setup banner' })).toBeInTheDocument()
  })

  it('hides chapter-level actions for members who cannot manage setup', async () => {
    mockApi({ 'GET /setup': freshProgress() })
    const { user } = renderWithProviders(<SetupPage />, { route: '/setup', session: memberSession() })
    await screen.findByRole('heading', { level: 2, name: 'Build the Foundation' })

    expect(screen.queryByRole('button', { name: 'Mark setup complete' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Mark officer guide read' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /setup banner/ })).not.toBeInTheDocument()
    // Members still see progress and can navigate to each task's screen.
    expect(screen.getByText('1 of 6 tasks done')).toBeInTheDocument()
    expect(within(taskCard('assets')).getByRole('link', { name: /Set up/ })).toBeInTheDocument()

    // The guide is readable, but only setup managers can mark it read.
    await user.click(within(taskCard('officer_guide')).getByRole('button', { name: 'Read guide' }))
    const dialog = await screen.findByRole('dialog', { name: 'Officer guide' })
    expect(within(dialog).getByRole('heading', { name: 'Roles' })).toBeInTheDocument()
    expect(within(dialog).queryByRole('button', { name: 'Mark as read' })).not.toBeInTheDocument()
  })

  it('marks setup complete after confirmation, refetches progress and invalidates the session', async () => {
    const state = { completed_at: null as string | null }
    const { calls } = mockApi({
      'GET /setup': () => ({ ...finishedProgress(), completed_at: state.completed_at }),
      'POST /setup/complete': () => {
        state.completed_at = '2026-09-09T12:00:00Z'
        return { ...finishedProgress(), completed_at: state.completed_at }
      },
    })
    const queryClient = createTestQueryClient()
    queryClient.setQueryData(['session'], ADMIN_SESSION)
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const { user } = renderWithProviders(<SetupPage />, { route: '/setup', queryClient })

    const button = await screen.findByRole('button', { name: 'Mark setup complete' })
    expect(button).toBeEnabled()
    expect(screen.getByText('Every available task is done')).toBeInTheDocument()
    await user.click(button)

    const dialog = await screen.findByRole('dialog', { name: 'Mark setup complete?' })
    await user.click(within(dialog).getByRole('button', { name: 'Mark complete' }))

    expect(await screen.findByText('Setup marked complete')).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'POST').map((c) => c.url)).toEqual(['/api/v1/setup/complete'])
    await waitFor(() => expect(calls.filter((c) => c.method === 'GET' && c.url === '/api/v1/setup').length).toBeGreaterThanOrEqual(2))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['setup'] })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['session'] })

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Mark setup complete' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /setup banner/ })).not.toBeInTheDocument()
    expect(screen.getByText(/Setup completed/)).toBeInTheDocument()
  })

  it('surfaces a server 403 on completion as an error toast and keeps the page usable', async () => {
    mockApi({
      'GET /setup': finishedProgress(),
      'POST /setup/complete': { __error: { status: 403, code: 'forbidden', error: 'You do not have permission to do that.' } },
    })
    const { user } = renderWithProviders(<SetupPage />, { route: '/setup' })
    await user.click(await screen.findByRole('button', { name: 'Mark setup complete' }))
    await user.click(within(await screen.findByRole('dialog')).getByRole('button', { name: 'Mark complete' }))

    expect(await screen.findByText('Could not mark setup complete')).toBeInTheDocument()
    expect(screen.getByText('You do not have permission to do that.')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mark setup complete' })).toBeEnabled()
  })

  it('hides and restores the setup banner for the current user', async () => {
    const state = { dismissed: false }
    const { calls } = mockApi({
      'GET /setup': () => ({ ...freshProgress(), banner_dismissed: state.dismissed }),
      'POST /setup/dismiss-banner': () => {
        state.dismissed = true
        return { ...freshProgress(), banner_dismissed: true }
      },
      'POST /setup/reopen-banner': () => {
        state.dismissed = false
        return { ...freshProgress(), banner_dismissed: false }
      },
    })
    const { user } = renderWithProviders(<SetupPage />, { route: '/setup' })

    await user.click(await screen.findByRole('button', { name: 'Hide setup banner' }))
    expect(await screen.findByText('Setup banner hidden')).toBeInTheDocument()
    const show = await screen.findByRole('button', { name: 'Show setup banner' })

    await user.click(show)
    expect(await screen.findByText('Setup banner restored')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Hide setup banner' })).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'POST').map((c) => c.url)).toEqual(['/api/v1/setup/dismiss-banner', '/api/v1/setup/reopen-banner'])
  })

  it('marks the officer guide read from the panel and hides the button once recorded', async () => {
    const state = { read: false }
    const withGuide = () => {
      const progress = freshProgress()
      const guide = progress.phases[0].tasks.find((t) => t.key === 'officer_guide')
      if (guide && state.read) guide.status = 'complete'
      return progress
    }
    const { calls } = mockApi({
      'GET /setup': withGuide,
      'POST /setup/mark-guide-read': () => {
        state.read = true
        return withGuide()
      },
    })
    const { user } = renderWithProviders(<SetupPage />, { route: '/setup' })

    await user.click(await screen.findByRole('button', { name: 'Mark officer guide read' }))
    expect(await screen.findByText('Officer guide marked as read')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST' && c.url === '/api/v1/setup/mark-guide-read')).toBe(true)
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Mark officer guide read' })).not.toBeInTheDocument())
    const guide = taskCard('officer_guide')
    expect(within(guide).getByText('Done')).toBeInTheDocument()
    expect(within(guide).getByRole('button', { name: 'Review Read the officer guide' })).toBeInTheDocument()
  })

  it('opens the officer guide and lets a setup manager mark it read from the dialog', async () => {
    const state = { read: false }
    mockApi({
      'GET /setup': () => {
        const progress = freshProgress()
        const guide = progress.phases[0].tasks.find((t) => t.key === 'officer_guide')
        if (guide && state.read) guide.status = 'complete'
        return progress
      },
      'POST /setup/mark-guide-read': () => {
        state.read = true
        const progress = freshProgress()
        progress.phases[0].tasks[4].status = 'complete'
        return progress
      },
    })
    const { user } = renderWithProviders(<SetupPage />, { route: '/setup' })
    await screen.findByRole('heading', { level: 2, name: 'Build the Foundation' })

    await user.click(within(taskCard('officer_guide')).getByRole('button', { name: 'Read guide' }))
    const dialog = await screen.findByRole('dialog', { name: 'Officer guide' })
    expect(within(dialog).getByRole('heading', { name: 'Roles' })).toBeInTheDocument()
    expect(within(dialog).getByRole('heading', { name: 'Work orders' })).toBeInTheDocument()
    expect(within(dialog).getByRole('heading', { name: 'Reporting' })).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Mark as read' }))
    expect(await screen.findByText('Officer guide marked as read')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Officer guide' })).not.toBeInTheDocument())
    expect(within(taskCard('officer_guide')).getByText('Done')).toBeInTheDocument()
  })

  it('closes the officer guide with Escape', async () => {
    mockApi({ 'GET /setup': freshProgress() })
    const { user } = renderWithProviders(<SetupPage />, { route: '/setup' })
    await screen.findByRole('heading', { level: 2, name: 'Build the Foundation' })
    await user.click(within(taskCard('officer_guide')).getByRole('button', { name: 'Read guide' }))
    await screen.findByRole('dialog', { name: 'Officer guide' })
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows a loading skeleton, then an inline error with a working Retry', async () => {
    let attempts = 0
    mockApi({
      'GET /setup': () => {
        attempts += 1
        return attempts === 1 ? { __error: { status: 500, code: 'server_error', error: 'Database unavailable.' } } : freshProgress()
      },
    })
    const { user } = renderWithProviders(<SetupPage />, { route: '/setup' })
    expect(screen.getByLabelText('Loading setup progress')).toBeInTheDocument()

    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('Setup progress could not be loaded')).toBeInTheDocument()
    expect(within(alert).getByText('Database unavailable.')).toBeInTheDocument()

    await user.click(within(alert).getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('heading', { level: 2, name: 'Build the Foundation' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
