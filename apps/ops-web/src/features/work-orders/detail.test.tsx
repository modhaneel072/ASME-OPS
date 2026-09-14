import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { memberSession, mockApi, renderWithProviders } from '@/test/render'
import WorkOrdersPage from './index'
import { ADA, baseHandlers, makeDetail, makeWorkOrder, MO, ROUTES, type HandlerInit } from './testData'

afterEach(() => vi.restoreAllMocks())

const listHandler = { items: [makeWorkOrder()], next_cursor: null, total: 1, tabs: { todo: 1, done: 0 } }

describe('Work Order detail', () => {
  it('lets an assigned member start but hides Assign, Cancel and Edit on someone else\'s work order', async () => {
    const wo = makeDetail({ assignees: [MO], created_by: ADA, status: 'open' })
    mockApi({ ...baseHandlers(), 'GET /work-orders': listHandler, 'GET /work-orders/:id': { work_order: wo } })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders/wo-1', path: ROUTES, session: memberSession() })
    await screen.findByRole('heading', { name: 'Replace wheel hub bearing' })
    expect(screen.getByRole('button', { name: 'Start' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Edit assignees' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit watchers' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add dependency' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'More actions' }))
    expect(await screen.findByRole('menuitem', { name: 'Watch' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Cancel work order' })).not.toBeInTheDocument()
  })

  it('hides Start from a member who is not assigned', async () => {
    const wo = makeDetail({ assignees: [ADA], created_by: ADA, status: 'open' })
    mockApi({ ...baseHandlers(), 'GET /work-orders': listHandler, 'GET /work-orders/:id': { work_order: wo } })
    renderWithProviders(<WorkOrdersPage />, { route: '/work-orders/wo-1', path: ROUTES, session: memberSession() })
    await screen.findByRole('heading', { name: 'Replace wheel hub bearing' })
    expect(screen.queryByRole('button', { name: 'Start' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Complete' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Log time' })).not.toBeInTheDocument()
  })

  it('shows the admin the status-dependent actions and surfaces a 409 as a toast', async () => {
    const wo = makeDetail({ status: 'open' })
    mockApi({
      ...baseHandlers(),
      'GET /work-orders': listHandler,
      'GET /work-orders/:id': { work_order: wo },
      'POST /work-orders/:id/start': { __error: { status: 409, code: 'invalid_transition', error: 'Cannot start a work order that is done.' } },
    })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders/wo-1', path: ROUTES })
    await screen.findByRole('heading', { name: 'Replace wheel hub bearing' })
    expect(screen.getByRole('button', { name: 'Complete' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit assignees' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Start' }))
    expect(await screen.findByText('Cannot start a work order that is done.')).toBeInTheDocument()
  })

  it('shows the blocked alert with blocking numbers and disables Start', async () => {
    const wo = makeDetail({ is_blocked: true, dependencies: { blocked_by: [{ id: 'dep-1', dependency_type: 'finish_to_start', work_order: { id: 'wo-7', number: 7, title: 'Machine the bracket', status: 'in_progress' } }], blocking: [] } })
    mockApi({ ...baseHandlers(), 'GET /work-orders': listHandler, 'GET /work-orders/:id': { work_order: wo } })
    renderWithProviders(<WorkOrdersPage />, { route: '/work-orders/wo-1', path: ROUTES })
    await screen.findByRole('heading', { name: 'Replace wheel hub bearing' })
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Blocked by dependencies')
    expect(within(alert).getByRole('link', { name: '#7' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start' })).toBeDisabled()
  })

  it('completes through the dialog with note and time entry prefilled for the session user', async () => {
    const wo = makeDetail({ status: 'in_progress', asset: null })
    const done = { ...wo, status: 'done', completed_at: '2026-09-09T10:00:00Z' }
    const { calls } = mockApi({
      ...baseHandlers(),
      'GET /work-orders': listHandler,
      'GET /work-orders/:id': { work_order: wo },
      'POST /work-orders/:id/complete': { work_order: done, follow_up: null },
    })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders/wo-1', path: ROUTES })
    await screen.findByRole('heading', { name: 'Replace wheel hub bearing' })
    await user.click(screen.getByRole('button', { name: 'Complete' }))
    const dialog = await screen.findByRole('dialog', { name: 'Complete #12' })
    await user.type(within(dialog).getByLabelText('Completion note'), 'Bearing replaced and tested.')
    expect(await within(dialog).findByText('Ada Admin')).toBeInTheDocument()
    await user.type(within(dialog).getByLabelText('Time entry 1 minutes'), '45')
    await user.click(within(dialog).getByRole('button', { name: 'Add cost' }))
    await user.type(within(dialog).getByLabelText('Cost 1 amount'), '12.5')
    await user.type(within(dialog).getByLabelText('Cost 1 description'), 'Bearing')
    expect(within(dialog).queryByText(/Asset status/)).not.toBeInTheDocument()
    await user.click(within(dialog).getByRole('checkbox', { name: /Create a follow-up work order/ }))
    await user.type(within(dialog).getByLabelText('Follow-up title'), 'Inspect other hubs')
    await user.click(within(dialog).getByRole('button', { name: 'Mark as done' }))

    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url === '/api/v1/work-orders/wo-1/complete')).toBe(true))
    const post = calls.find((c) => c.method === 'POST' && c.url === '/api/v1/work-orders/wo-1/complete')!
    expect(post.body).toEqual({
      note: 'Bearing replaced and tested.',
      time_entries: [{ user_id: 1, minutes: 45, note: null }],
      cost_entries: [{ type: 'parts', amount: 12.5, vendor_id: null, description: 'Bearing' }],
      follow_up: { title: 'Inspect other hubs', priority: 'high', work_type: 'reactive', due_at: null },
    })
    expect(await screen.findByText('#12 completed')).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: 'Complete #12' })).not.toBeInTheDocument()
  })

  it('shows nested completion errors next to the right rows', async () => {
    const wo = makeDetail({ status: 'open' })
    mockApi({
      ...baseHandlers(),
      'GET /work-orders': listHandler,
      'GET /work-orders/:id': { work_order: wo },
      'POST /work-orders/:id/complete': { __error: { status: 400, code: 'validation', error: 'Validation failed.', errors: { 'time_entries[0].minutes': 'Must be at least 1.' } } },
    })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders/wo-1', path: ROUTES })
    await screen.findByRole('heading', { name: 'Replace wheel hub bearing' })
    await user.click(screen.getByRole('button', { name: 'Complete' }))
    const dialog = await screen.findByRole('dialog', { name: 'Complete #12' })
    await user.type(within(dialog).getByLabelText('Time entry 1 minutes'), '0')
    await user.click(within(dialog).getByRole('button', { name: 'Mark as done' }))
    expect(await within(dialog).findByText('Must be at least 1.')).toBeInTheDocument()
  })

  it('requires a reason to cancel and posts it', async () => {
    const wo = makeDetail({ status: 'open' })
    const { calls } = mockApi({ ...baseHandlers(), 'GET /work-orders': listHandler, 'GET /work-orders/:id': { work_order: wo }, 'POST /work-orders/:id/cancel': { work_order: { ...wo, status: 'canceled' } } })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders/wo-1', path: ROUTES })
    await screen.findByRole('heading', { name: 'Replace wheel hub bearing' })
    await user.click(screen.getByRole('button', { name: 'More actions' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Cancel work order' }))
    const dialog = await screen.findByRole('dialog', { name: 'Cancel #12?' })
    await user.click(within(dialog).getByRole('button', { name: 'Cancel work order' }))
    expect(await within(dialog).findByText('A reason is required to cancel a work order.')).toBeInTheDocument()
    expect(calls.some((c) => c.url.endsWith('/cancel'))).toBe(false)
    await user.type(within(dialog).getByLabelText('Reason'), 'Superseded by #20')
    await user.click(within(dialog).getByRole('button', { name: 'Cancel work order' }))
    await waitFor(() => expect(calls.find((c) => c.url.endsWith('/cancel'))?.body).toEqual({ note: 'Superseded by #20' }))
    expect(await screen.findByText('#12 canceled')).toBeInTheDocument()
  })

  it('shows a not-found state for an unknown id', async () => {
    mockApi({ ...baseHandlers(), 'GET /work-orders': listHandler, 'GET /work-orders/:id': { __error: { status: 404, code: 'not_found', error: 'Not found.' } } })
    renderWithProviders(<WorkOrdersPage />, { route: '/work-orders/nope', path: ROUTES })
    expect(await screen.findByText('Work order not found')).toBeInTheDocument()
  })

  it('posts a comment and lists activity', async () => {
    const wo = makeDetail({ status: 'in_progress', status_history: [{ id: 'h-1', from_status: null, to_status: 'open', changed_by: ADA, note: null, changed_at: '2026-09-01T12:00:00Z' }, { id: 'h-2', from_status: 'open', to_status: 'in_progress', changed_by: ADA, note: null, changed_at: '2026-09-02T12:00:00Z' }] })
    const { calls } = mockApi({
      ...baseHandlers(),
      'GET /work-orders': listHandler,
      'GET /work-orders/:id': { work_order: wo },
      'GET /work-orders/:id/comments': { items: [{ id: 'c-1', entity_type: 'work_order', entity_id: 'wo-1', author: ADA, body: 'Ping @[Lee Lead](user:2)', parent_comment_id: null, edited_at: null, created_at: '2026-09-02T13:00:00Z', deleted: false, mentions: [] }], next_cursor: null, total: 1 },
      'POST /work-orders/:id/comments': ({ body }: HandlerInit) => ({ comment: { id: 'c-2', entity_type: 'work_order', entity_id: 'wo-1', author: ADA, body: (body as { body: string }).body, parent_comment_id: null, edited_at: null, created_at: '2026-09-02T14:00:00Z', deleted: false, mentions: [] } }),
    })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders/wo-1', path: ROUTES })
    await screen.findByRole('heading', { name: 'Replace wheel hub bearing' })
    expect(await screen.findByText('@Lee Lead')).toBeInTheDocument()
    expect(screen.getByText('Opened')).toBeInTheDocument()
    expect(screen.getByText('Started')).toBeInTheDocument()
    await user.type(screen.getByRole('textbox', { name: 'Comment' }), 'On it')
    await user.click(screen.getByRole('button', { name: 'Comment' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.url === '/api/v1/work-orders/wo-1/comments')?.body).toEqual({ body: 'On it' }))
  })
})
