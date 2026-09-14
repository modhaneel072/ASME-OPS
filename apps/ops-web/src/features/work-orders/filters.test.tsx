import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mockApi, renderWithProviders } from '@/test/render'
import WorkOrdersPage from './index'
import { baseHandlers, makeWorkOrder, ROUTES, type HandlerInit } from './testData'

afterEach(() => vi.restoreAllMocks())

const listHandler = { items: [makeWorkOrder()], next_cursor: null, total: 1, tabs: { todo: 1, done: 0 } }

function lastListUrl(calls: Array<{ method: string; url: string }>) {
  return calls.filter((c) => c.method === 'GET' && c.url.startsWith('/api/v1/work-orders?')).at(-1)!.url
}

describe('Work Orders filters, sort and saved filters', () => {
  it('writes filter chips into URL params and sends them as filter[...]', async () => {
    const { calls } = mockApi({ ...baseHandlers(), 'GET /work-orders': listHandler })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders', path: ROUTES })
    await screen.findByRole('list', { name: 'Work orders' })

    await user.click(screen.getByRole('button', { name: 'Status' }))
    await user.click(await screen.findByRole('checkbox', { name: 'Open' }))
    await waitFor(() => expect(lastListUrl(calls)).toContain('filter%5Bstatus%5D=open'))
    await user.click(screen.getByRole('checkbox', { name: 'In progress' }))
    await waitFor(() => expect(lastListUrl(calls)).toContain('filter%5Bstatus%5D=open%2Cin_progress'))
    await user.keyboard('{Escape}')

    await user.click(screen.getByRole('button', { name: 'Assigned To' }))
    await user.click(await screen.findByRole('checkbox', { name: 'Me' }))
    await waitFor(() => expect(lastListUrl(calls)).toContain('filter%5Bassignee%5D=me'))
    await user.keyboard('{Escape}')

    await user.click(screen.getByRole('button', { name: 'Due Date' }))
    await user.click(await screen.findByRole('radio', { name: 'Overdue' }))
    await waitFor(() => expect(lastListUrl(calls)).toContain('filter%5Bdue%5D=overdue'))
  })

  it('reveals hidden chips through Add Filter and restores chips from a deep link', async () => {
    mockApi({ ...baseHandlers(), 'GET /work-orders': listHandler })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders?filter[project]=proj-1&filter[vendor]=v-1', path: ROUTES })
    await screen.findByRole('list', { name: 'Work orders' })
    // An active chip is a trigger button plus its own "clear" button beside it.
    expect(await screen.findByRole('button', { name: 'Clear Project filter' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Project/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Clear Vendor filter' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Created by/ })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Add Filter' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Created by' }))
    expect(screen.getByRole('button', { name: /^Created by/ })).toBeInTheDocument()
  })

  it('changes sort and tab through the URL', async () => {
    const { calls } = mockApi({ ...baseHandlers(), 'GET /work-orders': listHandler })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders', path: ROUTES })
    await screen.findByRole('list', { name: 'Work orders' })
    expect(lastListUrl(calls)).toContain('sort=-updated_at')
    expect(lastListUrl(calls)).toContain('tab=todo')

    await user.click(screen.getByRole('button', { name: /^Sort:/ }))
    await user.click(await screen.findByRole('menuitem', { name: 'Priority: Highest First' }))
    await waitFor(() => expect(lastListUrl(calls)).toContain('sort=-priority'))

    await user.click(screen.getByRole('tab', { name: /Done/ }))
    await waitFor(() => expect(lastListUrl(calls)).toContain('tab=done'))
  })

  it('searches by text and by #number', async () => {
    const { calls } = mockApi({ ...baseHandlers(), 'GET /work-orders': listHandler })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders', path: ROUTES })
    await screen.findByRole('list', { name: 'Work orders' })
    await user.type(screen.getByRole('searchbox', { name: 'Search' }), '#12')
    await waitFor(() => expect(lastListUrl(calls)).toContain('q=%2312'))
  })

  it('applies a saved filter, replacing the URL params', async () => {
    const { calls } = mockApi({
      ...baseHandlers(),
      'GET /work-orders': listHandler,
      'GET /saved-filters': {
        personal: [{ id: 'sf-1', entity_type: 'work_order', name: 'Overdue for me', visibility: 'private', team: null, owner: null, filter: { due: 'overdue', assignee: 'me' }, sort: 'due_at', view_type: 'panel', is_default: true }],
        shared: [{ id: 'sf-2', entity_type: 'work_order', name: 'Rover work', visibility: 'chapter', team: null, owner: null, filter: { project: 'proj-1' }, sort: null, view_type: null, is_default: false }],
      },
    })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders?filter[status]=open', path: ROUTES })
    await screen.findByRole('list', { name: 'Work orders' })
    await user.click(screen.getByRole('button', { name: 'My Filters' }))
    const panel = await screen.findByRole('dialog', { name: 'My Filters' })
    expect(within(panel).getByText('Rover work')).toBeInTheDocument()
    expect(within(panel).getByRole('img', { name: 'Default filter' })).toBeInTheDocument()
    await user.click(within(panel).getByText('Overdue for me').closest('button')!)
    await waitFor(() => {
      const url = lastListUrl(calls)
      expect(url).toContain('filter%5Bdue%5D=overdue')
      expect(url).toContain('filter%5Bassignee%5D=me')
      expect(url).toContain('sort=due_at')
      expect(url).not.toContain('filter%5Bstatus%5D')
    })
  })

  it('saves the current filters as a new saved filter', async () => {
    const { calls } = mockApi({ ...baseHandlers(), 'GET /work-orders': listHandler, 'POST /saved-filters': ({ body }: HandlerInit) => ({ saved_filter: { id: 'sf-9', entity_type: 'work_order', ...(body as object), team: null, owner: null, is_default: false } }) })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders?filter[status]=open&sort=due_at&q=hub', path: ROUTES })
    await screen.findByRole('list', { name: 'Work orders' })
    await user.click(screen.getByRole('button', { name: 'My Filters' }))
    await user.click(await screen.findByRole('button', { name: 'Save current filters' }))
    const dialog = await screen.findByRole('dialog', { name: 'Save current filters' })
    await user.type(within(dialog).getByLabelText('Name'), 'Open soonest')
    await user.click(within(dialog).getByRole('button', { name: 'Save filter' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url === '/api/v1/saved-filters')).toBe(true))
    const post = calls.find((c) => c.method === 'POST' && c.url === '/api/v1/saved-filters')!
    expect(post.body).toEqual({ entity_type: 'work_order', name: 'Open soonest', visibility: 'private', team_id: null, filter: { status: 'open', q: 'hub' }, sort: 'due_at', view_type: 'panel' })
    expect(await screen.findByText('Filter saved')).toBeInTheDocument()
  })

  it('sets a saved filter as default from its row menu', async () => {
    const { calls } = mockApi({
      ...baseHandlers(),
      'GET /work-orders': listHandler,
      'GET /saved-filters': { personal: [{ id: 'sf-1', entity_type: 'work_order', name: 'Mine', visibility: 'private', team: null, owner: null, filter: {}, sort: null, view_type: null, is_default: false }], shared: [] },
      'PATCH /saved-filters/:id': ({ body }: HandlerInit) => ({ saved_filter: { id: 'sf-1', entity_type: 'work_order', name: 'Mine', visibility: 'private', team: null, owner: null, filter: {}, sort: null, view_type: null, ...(body as object) } }),
    })
    const { user } = renderWithProviders(<WorkOrdersPage />, { route: '/work-orders', path: ROUTES })
    await screen.findByRole('list', { name: 'Work orders' })
    await user.click(screen.getByRole('button', { name: 'My Filters' }))
    await user.click(await screen.findByRole('button', { name: 'Actions for Mine' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Set as default' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH' && c.url === '/api/v1/saved-filters/sf-1')?.body).toEqual({ is_default: true }))
  })
})
