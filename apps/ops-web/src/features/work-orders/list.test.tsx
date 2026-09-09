import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { memberSession, mockApi, renderWithProviders } from '@/test/render'
import WorkOrdersPage from './index'
import { baseHandlers, makeWorkOrder, ROUTES, type HandlerInit } from './testData'

afterEach(() => vi.restoreAllMocks())

const rows = [
  makeWorkOrder({ id: 'wo-1', number: 12, title: 'Replace wheel hub bearing' }),
  makeWorkOrder({ id: 'wo-2', number: 13, title: 'Calibrate robotic arm', priority: 'medium', is_blocked: true, sub_work_orders: { total: 5, done: 2 } }),
  makeWorkOrder({ id: 'wo-3', number: 14, title: 'Order new servo drivers', priority: 'none', assignees: [], due_at: null }),
]

describe('Work Orders list', () => {
  it('renders rows with number, title, status, blocked lock and sub-work order counts, plus tab counts', async () => {
    mockApi({ ...baseHandlers(), 'GET /work-orders': { items: rows, next_cursor: null, total: 3, tabs: { todo: 3, done: 7 } } })
    renderWithProviders(<WorkOrdersPage />, { route: '/work-orders', path: ROUTES })

    const list = await screen.findByRole('list', { name: 'Work orders' })
    const items = within(list).getAllByTestId('work-order-row')
    expect(items).toHaveLength(3)
    expect(items[0]).toHaveTextContent('#12')
    expect(items[0]).toHaveTextContent('Replace wheel hub bearing')
    expect(items[0]).toHaveTextContent('Open')
    expect(items[0]).toHaveTextContent('CCR')
    expect(within(items[1]).getByRole('img', { name: 'Blocked by dependencies' })).toBeInTheDocument()
    expect(items[1]).toHaveTextContent('2/5')
    expect(items[2]).toHaveTextContent('No due date')

    expect(screen.getByRole('tab', { name: /To Do/ })).toHaveTextContent('3')
    expect(screen.getByRole('tab', { name: /Done/ })).toHaveTextContent('7')
    expect(screen.getByRole('button', { name: 'New Work Order' })).toBeInTheDocument()
  })

  it('shows the empty state with a create action only when the session may create', async () => {
    mockApi({ ...baseHandlers(), 'GET /work-orders': { items: [], next_cursor: null, total: 0, tabs: { todo: 0, done: 0 } } })
    const { unmount } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders', path: ROUTES })
    expect(await screen.findByText("You don't have any work orders")).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create the first work order' })).toBeInTheDocument()
    unmount()

    const viewer = memberSession({ permissions: { 'work_order.read_all': ['chapter'], 'project.read': ['chapter'] } })
    renderWithProviders(<WorkOrdersPage />, { route: '/work-orders', path: ROUTES, session: viewer })
    expect(await screen.findByText("You don't have any work orders")).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Create the first work order' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'New Work Order' })).not.toBeInTheDocument()
  })

  it('shows a no-results state when filters are active and clears them', async () => {
    const { calls } = mockApi({ ...baseHandlers(), 'GET /work-orders': ({ url }: HandlerInit) => ({ items: url.searchParams.get('q') ? [] : rows, next_cursor: null, total: 0, tabs: { todo: 0, done: 0 } }) })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders?q=zzz&filter[status]=open', path: ROUTES })
    expect(await screen.findByText('No work orders match')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    await screen.findByRole('list', { name: 'Work orders' })
    const last = calls.filter((c) => c.method === 'GET' && c.url.startsWith('/api/v1/work-orders?')).at(-1)!
    expect(last.url).not.toContain('q=')
    expect(last.url).not.toContain('filter%5Bstatus%5D')
  })

  it('shows an inline error with Retry when the list fails', async () => {
    let attempts = 0
    mockApi({
      ...baseHandlers(),
      'GET /work-orders': () => {
        attempts += 1
        return attempts === 1 ? { __error: { status: 500, code: 'server_error', error: 'Database unavailable' } } : { items: rows, next_cursor: null, total: 3, tabs: { todo: 3, done: 0 } }
      },
    })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders', path: ROUTES })
    expect(await screen.findByText('Work orders could not be loaded')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('list', { name: 'Work orders' })).toBeInTheDocument()
  })

  it('switches to the table view and keeps it in the URL', async () => {
    const { calls } = mockApi({ ...baseHandlers(), 'GET /work-orders': { items: rows, next_cursor: null, total: 3, tabs: { todo: 3, done: 0 } } })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders?view=table', path: ROUTES })
    const table = await screen.findByRole('table')
    expect(within(table).getByRole('columnheader', { name: /Number/ })).toBeInTheDocument()
    expect(within(table).getAllByRole('row')).toHaveLength(4)
    await user.click(within(table).getByRole('button', { name: /Due/ }))
    await waitFor(() => expect(calls.filter((c) => c.url.startsWith('/api/v1/work-orders?')).at(-1)!.url).toContain('sort=due_at'))
  })

  it('loads more rows when a next cursor is present', async () => {
    mockApi({
      ...baseHandlers(),
      'GET /work-orders': ({ url }: HandlerInit) =>
        url.searchParams.get('cursor')
          ? { items: [makeWorkOrder({ id: 'wo-9', number: 99, title: 'Second page item' })], next_cursor: null, total: 4, tabs: { todo: 4, done: 0 } }
          : { items: rows, next_cursor: 'eyJvZmZzZXQiOjUwfQ', total: 4, tabs: { todo: 4, done: 0 } },
    })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders', path: ROUTES })
    await screen.findByRole('list', { name: 'Work orders' })
    await user.click(screen.getByRole('button', { name: 'Load more' }))
    expect(await screen.findByText('Second page item')).toBeInTheDocument()
  })

  it('opens the create pane with "n" and focuses search with "/"', async () => {
    mockApi({ ...baseHandlers(), 'GET /work-orders': { items: rows, next_cursor: null, total: 3, tabs: { todo: 3, done: 0 } } })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders', path: ROUTES })
    await screen.findByRole('list', { name: 'Work orders' })
    await user.keyboard('/')
    expect(screen.getByRole('searchbox', { name: 'Search' })).toHaveFocus()
    await user.keyboard('{Escape}')
    ;(document.activeElement as HTMLElement).blur()
    await user.keyboard('n')
    expect(await screen.findByRole('dialog', { name: 'New Work Order' })).toBeInTheDocument()
  })
})
