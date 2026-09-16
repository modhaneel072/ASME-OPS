import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { OperationsReport } from '@/api/contracts/reports'
import type { Session } from '@/api/contracts/session'
import { ADMIN_SESSION, memberSession, mockApi, renderWithProviders, type MockHandler } from '@/test/render'
import ReportingPage from '.'

/* Fixtures -------------------------------------------------------------------- */

const REPORT: OperationsReport = {
  range: { key: 'custom', start: '2026-08-03', end: '2026-08-16', timezone: 'America/Chicago' },
  created_vs_completed: [
    { week_start: '2026-08-03', created: 3, completed: 1 },
    { week_start: '2026-08-10', created: 3, completed: 2 },
  ],
  by_work_type: [
    { work_type: 'reactive', count: 2 },
    { work_type: 'preventive', count: 1 },
    { work_type: 'project', count: 1 },
    { work_type: 'event', count: 1 },
    { work_type: 'inspection', count: 1 },
    { work_type: 'safety', count: 0 },
    { work_type: 'procurement', count: 0 },
    { work_type: 'documentation', count: 1 },
  ],
  repeating_vs_non: { repeating: 1, non_repeating: 6 },
  status_distribution: [
    { status: 'draft', count: 0 },
    { status: 'open', count: 1 },
    { status: 'in_progress', count: 1 },
    { status: 'on_hold', count: 1 },
    { status: 'done', count: 3 },
    { status: 'canceled', count: 1 },
    { status: 'skipped', count: 0 },
  ],
  priority_distribution: [
    { priority: 'none', count: 1 },
    { priority: 'low', count: 2 },
    { priority: 'medium', count: 2 },
    { priority: 'high', count: 1 },
    { priority: 'critical', count: 1 },
  ],
  on_time_completion_rate: 0.5,
  overdue_open: 2,
  avg_completion_hours: 132,
  workload_by_team: [
    { team: { id: 't1', name: 'Robotic Arm' }, open: 2, in_progress: 0 },
    { team: { id: 't2', name: 'Wheels and Mobility' }, open: 0, in_progress: 1 },
    { team: null, open: 1, in_progress: 0 },
  ],
  workload_by_user: [
    { user: { id: 3, name: 'Mo Member', email: 'mo@uiowa.edu', avatar_url: null }, open: 1, in_progress: 1 },
    { user: { id: 2, name: 'Lee Lead', email: 'lee@uiowa.edu', avatar_url: null }, open: 0, in_progress: 1 },
  ],
  hours_logged: 2,
  parts_cost: 25.5,
  other_cost: 14.25,
  totals: { created: 6, completed: 3, open: 4 },
}

function emptyReport(): OperationsReport {
  return {
    ...REPORT,
    created_vs_completed: REPORT.created_vs_completed.map((week) => ({ ...week, created: 0, completed: 0 })),
    by_work_type: REPORT.by_work_type.map((row) => ({ ...row, count: 0 })),
    repeating_vs_non: { repeating: 0, non_repeating: 0 },
    status_distribution: REPORT.status_distribution.map((row) => ({ ...row, count: 0 })),
    priority_distribution: REPORT.priority_distribution.map((row) => ({ ...row, count: 0 })),
    on_time_completion_rate: null,
    overdue_open: 0,
    avg_completion_hours: null,
    workload_by_team: [],
    workload_by_user: [],
    hours_logged: 0,
    parts_cost: 0,
    other_cost: 0,
    totals: { created: 0, completed: 0, open: 0 },
  }
}

const PROJECTS = { items: [{ id: 'p1', name: 'Crater Cruncher Rover', code: 'CCR', status: 'active', visibility: 'chapter' }], next_cursor: null, total: 1 }
const TEAMS = {
  items: [
    { id: 't1', name: 'Robotic Arm' },
    { id: 't2', name: 'Wheels and Mobility' },
  ],
  next_cursor: null,
  total: 2,
}

function mockReport(handler: MockHandler = REPORT) {
  return mockApi({ 'GET /reports/operations': handler, 'GET /projects': PROJECTS, 'GET /teams': TEAMS })
}

/* Helpers --------------------------------------------------------------------- */

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{JSON.stringify({ pathname: location.pathname, params: Object.fromEntries(new URLSearchParams(location.search)) })}</output>
}

function currentUrl() {
  return JSON.parse(screen.getByTestId('location').textContent ?? '{}') as { pathname: string; params: Record<string, string> }
}

function reportRequests(calls: Array<{ url: string }>) {
  return calls.filter((call) => call.url.startsWith('/api/v1/reports/operations')).map((call) => new URL(call.url, 'http://test.local').searchParams)
}

function renderReporting(route: string, session: Session = ADMIN_SESSION) {
  return renderWithProviders(
    <>
      <ReportingPage />
      <LocationProbe />
    </>,
    { route, path: ['/reporting/:report', '/reporting/dashboards/:dashboardId'], session },
  )
}

const HEADLINE = '6 created · 3 completed'

function region(name: string) {
  return screen.getByRole('region', { name })
}

/** A BarRows row: label element → its <li>; the value is the trailing text. */
function expectBarRow(container: HTMLElement, labelText: string, value: number) {
  const label = within(container).getByText(labelText)
  const row = label.closest('li')
  expect(row).not.toBeNull()
  expect(row).toHaveTextContent(new RegExp(`${value}$`))
}

afterEach(() => {
  vi.restoreAllMocks()
})

/* Tests ----------------------------------------------------------------------- */

describe('Operations dashboard', () => {
  it('renders every metric from the operations payload', async () => {
    mockReport()
    const { user } = renderReporting('/reporting/operations?range=custom&start=2026-08-03&end=2026-08-16')
    expect(await screen.findByRole('heading', { name: 'Operations' })).toBeInTheDocument()
    expect(screen.getByText('Work-order throughput, timeliness and workload')).toBeInTheDocument()
    expect(await screen.findByText(HEADLINE)).toBeInTheDocument()

    // Resolved window and totals
    const summary = screen.getByRole('list', { name: 'Report summary' })
    expect(summary).toHaveTextContent('Aug 3 – Aug 16, 2026')
    expect(summary).toHaveTextContent('America/Chicago')
    expect(summary).toHaveTextContent('6 created')
    expect(summary).toHaveTextContent('3 completed')
    expect(summary).toHaveTextContent('4 open now')
    expect(screen.getByRole('button', { name: /Aug 3 – Aug 16, 2026/ })).toBeInTheDocument()

    // Created vs completed: weekly numbers are in the table alternative
    const created = region('Created vs Completed')
    expect(created).toHaveTextContent('Most new work started the week of Aug 3 (3 work orders)')
    await user.click(within(created).getByRole('button', { name: 'Show as table' }))
    const weekRows = within(within(created).getByRole('table')).getAllByRole('row').slice(1)
    expect(weekRows.map((row) => within(row).getAllByRole('cell').map((cell) => cell.textContent))).toEqual([
      ['Aug 3', '3', '1'],
      ['Aug 10', '3', '2'],
    ])

    // Work orders by type: every type including zeros
    const byType = region('Work orders by type')
    expect(within(byType).getByText('7')).toBeInTheDocument()
    expectBarRow(byType, 'Reactive', 2)
    expectBarRow(byType, 'Preventive', 1)
    expectBarRow(byType, 'Project', 1)
    expectBarRow(byType, 'Event', 1)
    expectBarRow(byType, 'Inspection', 1)
    expectBarRow(byType, 'Safety', 0)
    expectBarRow(byType, 'Procurement', 0)
    expectBarRow(byType, 'Documentation', 1)
    expect(byType).toHaveTextContent('Most common: Reactive (2).')

    // Repeating vs non-repeating
    const repeating = region('Repeating vs non-repeating')
    expect(repeating).toHaveTextContent('1 repeating')
    expect(within(repeating).getByText('6')).toBeInTheDocument()
    expect(repeating).toHaveTextContent('14.3% repeating')
    expect(repeating).toHaveTextContent('85.7% non-repeating')

    // Status distribution: legend entries are drill-down links
    const status = region('Status distribution')
    expect(within(status).getByRole('link', { name: 'Done 3' })).toHaveAttribute('href', '/work-orders?filter[status]=done&tab=all')
    expect(within(status).getByRole('link', { name: 'Open 1' })).toHaveAttribute('href', '/work-orders?filter[status]=open&tab=all')
    expect(within(status).getByRole('link', { name: 'In progress 1' })).toBeInTheDocument()
    expect(within(status).getByRole('link', { name: 'On hold 1' })).toBeInTheDocument()
    expect(within(status).getByRole('link', { name: 'Canceled 1' })).toBeInTheDocument()
    expect(within(status).getByRole('link', { name: 'Draft 0' })).toBeInTheDocument()
    expect(within(status).getByRole('link', { name: 'Skipped 0' })).toBeInTheDocument()

    // Priority distribution with badge labels
    const priority = region('Priority distribution')
    expect(priority).toHaveTextContent('2 high or critical')
    expect(within(priority).getByLabelText('Priority None').closest('li')).toHaveTextContent(/1$/)
    expect(within(priority).getByLabelText('Priority Low').closest('li')).toHaveTextContent(/2$/)
    expect(within(priority).getByLabelText('Priority Medium').closest('li')).toHaveTextContent(/2$/)
    expect(within(priority).getByLabelText('Priority High').closest('li')).toHaveTextContent(/1$/)
    expect(within(priority).getByLabelText('Priority Critical').closest('li')).toHaveTextContent(/1$/)

    // Value cards
    expect(within(region('On-time completion')).getByText('50%')).toBeInTheDocument()
    const overdue = region('Overdue open')
    expect(within(overdue).getByText('2')).toBeInTheDocument()
    expect(within(overdue).getByRole('link', { name: /View overdue work orders/ })).toHaveAttribute('href', '/work-orders?filter[due]=overdue')
    expect(within(region('Average completion time')).getByText('132.0 h')).toBeInTheDocument()

    // Workload by team: names link to the filtered work-order list
    const teams = region('Workload by team')
    expect(within(teams).getByRole('link', { name: 'Robotic Arm' })).toHaveAttribute('href', '/work-orders?filter[team]=t1')
    expect(within(teams).getByRole('link', { name: 'Wheels and Mobility' })).toHaveAttribute('href', '/work-orders?filter[team]=t2')
    expect(teams).toHaveTextContent('2 open · 0 in progress')
    expect(teams).toHaveTextContent('0 open · 1 in progress')
    expect(teams).toHaveTextContent('No team')
    expect(within(teams).getByText('4')).toBeInTheDocument()

    // Workload by user table
    const users = region('Workload by user')
    const rows = within(users).getAllByRole('row').slice(1)
    expect(within(rows[0]).getByText('Mo Member')).toBeInTheDocument()
    expect(within(rows[1]).getByText('Lee Lead')).toBeInTheDocument()
    // numeric cells only: the name cell also carries a decorative avatar
    expect(rows.map((row) => within(row).getAllByRole('cell').slice(1).map((cell) => cell.textContent))).toEqual([
      ['1', '1', '2'],
      ['0', '1', '1'],
    ])

    // Time and cost tiles
    expect(within(region('Hours logged')).getByText('2.0 h')).toBeInTheDocument()
    expect(within(region('Parts cost')).getByText('$25.50')).toBeInTheDocument()
    expect(within(region('Other cost')).getByText('$14.25')).toBeInTheDocument()
  })

  it('shows the loading skeleton before the report arrives', async () => {
    mockReport(() => new Promise((resolve) => setTimeout(() => resolve(REPORT), 30)))
    renderReporting('/reporting/operations')
    expect(screen.getByRole('status', { name: 'Loading report' })).toBeInTheDocument()
    expect(await screen.findByText(HEADLINE)).toBeInTheDocument()
    expect(screen.queryByRole('status', { name: 'Loading report' })).not.toBeInTheDocument()
  })

  it('writes the selected range to the URL and requests it from the API', async () => {
    const { calls } = mockReport()
    const { user } = renderReporting('/reporting/operations')
    await screen.findByText(HEADLINE)
    expect(reportRequests(calls)[0].get('range')).toBe('30d')
    expect(screen.getByRole('radio', { name: '30 days' })).toHaveAttribute('aria-checked', 'true')

    await user.click(screen.getByRole('radio', { name: '7 days' }))
    expect(currentUrl().params).toEqual({ range: '7d' })
    expect(screen.getByRole('radio', { name: '7 days' })).toHaveAttribute('aria-checked', 'true')
    await waitFor(() => expect(reportRequests(calls).at(-1)?.get('range')).toBe('7d'))

    await user.click(screen.getByRole('radio', { name: 'Semester' }))
    expect(currentUrl().params).toEqual({ range: 'semester' })
    await waitFor(() => expect(reportRequests(calls).at(-1)?.get('range')).toBe('semester'))
  })

  it('validates a custom range before applying it', async () => {
    const { calls } = mockReport()
    const { user } = renderReporting('/reporting/operations')
    await screen.findByText(HEADLINE)

    await user.click(screen.getByRole('radio', { name: 'Custom' }))
    const dialog = await screen.findByRole('dialog', { name: 'Custom date range' })
    expect(screen.getByRole('radio', { name: 'Custom' })).toHaveAttribute('aria-checked', 'true')
    const startInput = within(dialog).getByLabelText('Start')
    const endInput = within(dialog).getByLabelText('End')
    expect(startInput).toHaveFocus()

    // end before start
    fireEvent.change(startInput, { target: { value: '2026-08-16' } })
    fireEvent.change(endInput, { target: { value: '2026-08-03' } })
    await user.click(within(dialog).getByRole('button', { name: 'Apply' }))
    expect(await within(dialog).findByText('End must be on or after start.')).toBeInTheDocument()
    expect(currentUrl().params.range).toBeUndefined()
    expect(reportRequests(calls).some((request) => request.get('range') === 'custom')).toBe(false)

    // longer than the API allows
    fireEvent.change(startInput, { target: { value: '2025-01-01' } })
    fireEvent.change(endInput, { target: { value: '2026-01-02' } })
    await user.click(within(dialog).getByRole('button', { name: 'Apply' }))
    expect(await within(dialog).findByText('Custom ranges may cover at most 366 days.')).toBeInTheDocument()

    // valid
    fireEvent.change(startInput, { target: { value: '2026-08-16' } })
    fireEvent.change(endInput, { target: { value: '2026-08-20' } })
    await user.click(within(dialog).getByRole('button', { name: 'Apply' }))
    await waitFor(() => expect(currentUrl().params).toEqual({ range: 'custom', start: '2026-08-16', end: '2026-08-20' }))
    expect(screen.queryByRole('dialog', { name: 'Custom date range' })).not.toBeInTheDocument()
    await waitFor(() => {
      const last = reportRequests(calls).at(-1)
      expect(last?.get('range')).toBe('custom')
      expect(last?.get('start')).toBe('2026-08-16')
      expect(last?.get('end')).toBe('2026-08-20')
    })
    expect(screen.getByRole('button', { name: /Aug 16 – Aug 20, 2026/ })).toBeInTheDocument()
  })

  it('does not request a custom range until both dates are present', async () => {
    const { calls } = mockReport()
    const { user } = renderReporting('/reporting/operations?range=custom')
    expect(await screen.findByText('Choose a custom date range')).toBeInTheDocument()
    expect(reportRequests(calls)).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Choose dates' }))
    expect(await screen.findByRole('dialog', { name: 'Custom date range' })).toBeInTheDocument()
  })

  it('restores filters from the URL and writes chip changes back', async () => {
    const { calls } = mockReport()
    const { user } = renderReporting('/reporting/operations?range=semester&filter[team]=t1')
    await screen.findByText(HEADLINE)
    expect(screen.getByRole('radio', { name: 'Semester' })).toHaveAttribute('aria-checked', 'true')
    const first = reportRequests(calls)[0]
    expect(first.get('range')).toBe('semester')
    expect(first.get('filter[team]')).toBe('t1')
    expect(first.get('filter[project]')).toBeNull()
    expect(await screen.findByRole('button', { name: /Team.*Robotic Arm/ })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /^Project/ }))
    await user.click(await screen.findByRole('radio', { name: 'Crater Cruncher Rover' }))
    expect(currentUrl().params).toEqual({ range: 'semester', 'filter[team]': 't1', 'filter[project]': 'p1' })
    await waitFor(() => expect(reportRequests(calls).at(-1)?.get('filter[project]')).toBe('p1'))

    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(currentUrl().params).toEqual({ range: 'semester' })
    await waitFor(() => {
      const last = reportRequests(calls).at(-1)
      expect(last?.get('filter[project]')).toBeNull()
      expect(last?.get('filter[team]')).toBeNull()
    })
  })

  it('shows the empty state with a create action when nothing happened in the range', async () => {
    mockReport(emptyReport())
    renderReporting('/reporting/operations')
    expect(await screen.findByText('No work in this range')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'New Work Order' })).toHaveAttribute('href', '/work-orders/new')
    expect(screen.queryByRole('region', { name: 'Created vs Completed' })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Hours logged' })).not.toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Report summary' })).toHaveTextContent('0 open now')
  })

  it('hides the create action from members without work_order.create', async () => {
    mockReport(emptyReport())
    const permissions = { ...memberSession().permissions }
    delete permissions['work_order.create']
    renderReporting('/reporting/operations', memberSession({ permissions }))
    expect(await screen.findByText('No work in this range')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'New Work Order' })).not.toBeInTheDocument()
  })

  it('offers to clear filters from the empty state when filters are active', async () => {
    mockReport(emptyReport())
    const { user } = renderReporting('/reporting/operations?filter[project]=p1')
    const empty = (await screen.findByText('No work in this range')).closest('[role="status"]') as HTMLElement
    expect(within(empty).queryByRole('link', { name: 'New Work Order' })).not.toBeInTheDocument()
    await user.click(within(empty).getByRole('button', { name: 'Clear filters' }))
    expect(currentUrl().params).toEqual({})
  })

  it('still shows time and cost tiles when only those are non-zero', async () => {
    mockReport({ ...emptyReport(), hours_logged: 1.5 })
    renderReporting('/reporting/operations')
    expect(await screen.findByText('No work in this range')).toBeInTheDocument()
    expect(within(region('Hours logged')).getByText('1.5 h')).toBeInTheDocument()
  })

  it('does not request the report or render its controls without report.view', async () => {
    const { calls } = mockReport()
    renderReporting('/reporting/operations', memberSession({ permissions: { 'project.read': ['chapter'] } }))
    expect(await screen.findByText('Reports are not available for your role')).toBeInTheDocument()
    expect(screen.queryByRole('radiogroup', { name: 'Date range' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Project/ })).not.toBeInTheDocument()
    expect(reportRequests(calls)).toHaveLength(0)
  })

  it('renders for a full member who holds report.view', async () => {
    mockReport()
    renderReporting('/reporting/operations', memberSession())
    expect(await screen.findByText(HEADLINE)).toBeInTheDocument()
  })

  it('shows an inline error with retry when the request fails', async () => {
    let attempts = 0
    mockReport(() => (attempts++ === 0 ? { __error: { status: 500, code: 'server_error', error: 'Database unavailable' } } : REPORT))
    const { user } = renderReporting('/reporting/operations')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The report could not be loaded')
    expect(alert).toHaveTextContent('Database unavailable')
    await user.click(within(alert).getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText(HEADLINE)).toBeInTheDocument()
  })

  it('surfaces a 403 as a toast and an inline error', async () => {
    mockReport({ __error: { status: 403, code: 'forbidden', error: 'Missing report.view' } })
    renderReporting('/reporting/operations')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('You do not have permission to view this report')
    expect(await screen.findByText('You do not have permission to view reports')).toBeInTheDocument()
  })

  it('maps server date errors onto the custom range form', async () => {
    mockReport(({ url }: { url: URL }) => (url.searchParams.get('range') === 'custom' ? { __error: { status: 400, code: 'validation', error: 'Validation failed', errors: { end: 'End must be on or after start.' } } } : REPORT))
    const { user } = renderReporting('/reporting/operations?range=custom&start=2026-08-16&end=2026-08-03')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('The report request was not valid')
    expect(alert).toHaveTextContent('End must be on or after start.')
    await user.click(within(alert).getByRole('button', { name: 'Change dates' }))
    const dialog = await screen.findByRole('dialog', { name: 'Custom date range' })
    expect(within(dialog).getByLabelText('Start')).toHaveValue('2026-08-16')
    expect(within(dialog).getByLabelText('End')).toHaveValue('2026-08-03')
    expect(await within(dialog).findByText('End must be on or after start.')).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    await user.click(screen.getByRole('button', { name: 'Reset to 30 days' }))
    expect(currentUrl().params).toEqual({})
    expect(await screen.findByText(HEADLINE)).toBeInTheDocument()
  })

  it('explains an unknown project or team filter', async () => {
    mockReport({ __error: { status: 404, code: 'not_found', error: 'Project not found' } })
    const { user } = renderReporting('/reporting/operations?filter[project]=gone')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('That project or team could not be found')
    await user.click(within(alert).getByRole('button', { name: 'Clear filters' }))
    expect(currentUrl().params).toEqual({})
  })
})

describe('Planned reports', () => {
  it.each([
    ['/reporting/project-health', 'Project Health'],
    ['/reporting/asset-health', 'Asset Health'],
    ['/reporting/details', 'Reporting Details'],
    ['/reporting/activity', 'Recent Activity'],
    ['/reporting/exports', 'Export Data'],
    ['/reporting/dashboards', 'Dashboards'],
    ['/reporting/builder', 'Report Builder'],
    ['/reporting/dashboards/abc-123', 'Dashboards'],
  ])('%s renders the ComingSoon page for %s', (route, title) => {
    mockReport()
    renderReporting(route)
    expect(screen.getByRole('heading', { name: title })).toBeInTheDocument()
    expect(screen.getByText(`${title} is coming soon`)).toBeInTheDocument()
    expect(screen.queryByRole('radiogroup', { name: 'Date range' })).not.toBeInTheDocument()
  })

  it('derives a title for an unknown report key', () => {
    mockReport()
    renderReporting('/reporting/something-else')
    expect(screen.getByText('Something Else is coming soon')).toBeInTheDocument()
  })
})
