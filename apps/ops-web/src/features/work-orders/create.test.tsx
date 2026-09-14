import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mockApi, renderWithProviders } from '@/test/render'
import WorkOrdersPage from './index'
import { baseHandlers, makeDetail, makeWorkOrder, ROUTES, type HandlerInit } from './testData'

afterEach(() => vi.restoreAllMocks())

const listHandler = { items: [makeWorkOrder()], next_cursor: null, total: 1, tabs: { todo: 1, done: 0 } }

describe('Work Order create and edit panes', () => {
  it('posts the expected body (estimated_minutes from hours + minutes), creates sub-work orders and navigates to the detail', async () => {
    const created = makeDetail({ id: 'wo-101', number: 101, title: 'Rebuild soldering station' })
    const { calls } = mockApi({
      ...baseHandlers(),
      'GET /work-orders': listHandler,
      'POST /work-orders': { work_order: created },
      'POST /work-orders/:id/sub-work-orders': ({ body }: HandlerInit) => ({ work_order: makeDetail({ id: 'wo-102', number: 102, title: (body as { title: string }).title, parent_id: 'wo-101' }) }),
      'GET /work-orders/:id': { work_order: created },
    })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders/new?project=proj-1', path: ROUTES })
    const pane = await screen.findByRole('dialog', { name: 'New Work Order' })

    await user.type(within(pane).getByLabelText('Title'), 'Rebuild soldering station')
    await user.type(within(pane).getByLabelText('Estimated hours'), '1')
    await user.type(within(pane).getByLabelText('Estimated minutes'), '30')
    await user.click(within(pane).getByRole('radio', { name: 'Medium' }))
    await user.selectOptions(within(pane).getByLabelText('Work type'), 'preventive')
    await user.type(within(pane).getByLabelText('Budget code'), 'SHOP-26')
    await user.click(within(pane).getByRole('button', { name: 'Add sub-work order' }))
    await user.type(within(pane).getByLabelText('Sub-work order 1 title'), 'Replace tips')
    await user.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url === '/api/v1/work-orders')).toBe(true))
    const post = calls.find((c) => c.method === 'POST' && c.url === '/api/v1/work-orders')!
    expect(post.body).toMatchObject({
      title: 'Rebuild soldering station',
      description: null,
      priority: 'medium',
      work_type: 'preventive',
      project_id: 'proj-1',
      estimated_minutes: 90,
      budget_code: 'SHOP-26',
      assignee_user_ids: [],
      watcher_user_ids: [],
      category_ids: [],
    })
    expect(post.body).not.toHaveProperty('draft')

    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.url === '/api/v1/work-orders/wo-101/sub-work-orders')?.body).toEqual({ title: 'Replace tips' }))
    expect(await screen.findByText('#101 created')).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Rebuild soldering station' })).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: 'New Work Order' })).not.toBeInTheDocument()
  })

  it('sends draft: true from "Save as draft"', async () => {
    const created = makeDetail({ id: 'wo-103', number: 103, status: 'draft' })
    const { calls } = mockApi({ ...baseHandlers(), 'GET /work-orders': listHandler, 'POST /work-orders': { work_order: created }, 'GET /work-orders/:id': { work_order: created } })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders/new', path: ROUTES })
    const pane = await screen.findByRole('dialog', { name: 'New Work Order' })
    await user.type(within(pane).getByLabelText('Title'), 'Draft idea')
    await user.click(screen.getByRole('button', { name: 'Save as draft' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.url === '/api/v1/work-orders')?.body).toMatchObject({ title: 'Draft idea', draft: true }))
  })

  it('maps server validation errors to the right fields and keeps the entered data', async () => {
    const { calls } = mockApi({
      ...baseHandlers(),
      'GET /work-orders': listHandler,
      'POST /work-orders': { __error: { status: 400, code: 'validation', error: 'Validation failed.', errors: { title: 'Keep the title under 240 characters.', due_at: 'Due date must be on or after the start date.', priority: 'Critical priority requires a safety officer or lead.' } } },
    })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders/new', path: ROUTES })
    const pane = await screen.findByRole('dialog', { name: 'New Work Order' })
    await user.type(within(pane).getByLabelText('Title'), 'Something')
    await user.click(screen.getByRole('button', { name: 'Create' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true))
    expect(await screen.findByText('Keep the title under 240 characters.')).toBeInTheDocument()
    expect(screen.getByText('Due date must be on or after the start date.')).toBeInTheDocument()
    expect(screen.getByText('Critical priority requires a safety officer or lead.')).toBeInTheDocument()
    expect(within(pane).getByLabelText('Title')).toHaveValue('Something')
    expect(screen.getByRole('dialog', { name: 'New Work Order' })).toBeInTheDocument()
  })

  it('validates the title client-side before posting', async () => {
    const { calls } = mockApi({ ...baseHandlers(), 'GET /work-orders': listHandler })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders/new', path: ROUTES })
    await screen.findByRole('dialog', { name: 'New Work Order' })
    await user.click(screen.getByRole('button', { name: 'Create' }))
    expect(await screen.findByText('Give the work order a title.')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
  })

  it('offers Critical only when the session may cancel or Safety is selected', async () => {
    mockApi({ ...baseHandlers(), 'GET /work-orders': listHandler })
    const { user, unmount } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders/new', path: ROUTES })
    let pane = await screen.findByRole('dialog', { name: 'New Work Order' })
    expect(within(pane).getByRole('radio', { name: 'Critical' })).toBeInTheDocument()
    unmount()

    const { memberSession } = await import('@/test/render')
    renderWithProviders(<WorkOrdersPage />, { route: '/work-orders/new?category=cat-1', path: ROUTES, session: memberSession() })
    pane = await screen.findByRole('dialog', { name: 'New Work Order' })
    await waitFor(() => expect(within(pane).getByRole('radiogroup', { name: 'Priority' })).toBeInTheDocument())
    expect(within(pane).queryByRole('radio', { name: 'Critical' })).not.toBeInTheDocument()
    // Selecting the Safety category unlocks it.
    const categories = within(pane).getByLabelText('Categories')
    await user.click(categories)
    await user.type(categories, 'Safe')
    await user.click(within(await screen.findByRole('listbox')).getByRole('option', { name: /Safety/ }))
    expect(await within(pane).findByRole('radio', { name: 'Critical' })).toBeInTheDocument()
  })

  it('edits an existing work order with PATCH and publishes a draft', async () => {
    const draft = makeDetail({ id: 'wo-5', number: 5, status: 'draft', title: 'Draft plan', estimated_minutes: 125 })
    const { calls } = mockApi({
      ...baseHandlers(),
      'GET /work-orders': listHandler,
      'GET /work-orders/:id': { work_order: draft },
      'PATCH /work-orders/:id': ({ body }: HandlerInit) => ({ work_order: { ...draft, ...(body as object), status: (body as { status?: string }).status ?? draft.status } }),
    })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders/wo-5/edit', path: ROUTES })
    const pane = await screen.findByRole('dialog', { name: 'Edit #5' })
    expect(within(pane).getByLabelText('Title')).toHaveValue('Draft plan')
    expect(within(pane).getByLabelText('Estimated hours')).toHaveValue('2')
    expect(within(pane).getByLabelText('Estimated minutes')).toHaveValue('5')
    await user.click(screen.getByRole('button', { name: 'Publish' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH' && c.url === '/api/v1/work-orders/wo-5')?.body).toMatchObject({ title: 'Draft plan', status: 'open', estimated_minutes: 125 }))
    expect(await screen.findByText('#5 published')).toBeInTheDocument()
  })
})
