import { screen, waitFor, within } from '@testing-library/react'
import { useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { memberSession, mockApi, renderWithProviders } from '@/test/render'
import NotificationsPage from './index'

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname + location.search}</output>
}

const NOW = Date.now()
const minutesAgo = (minutes: number) => new Date(NOW - minutes * 60_000).toISOString()

const ITEMS = [
  {
    id: 'n-1',
    type: 'work_order.assigned',
    title: 'Assigned #12 Replace rover wheel bearing',
    body: 'Lee Lead assigned you. Due Friday.',
    entity_type: 'work_order',
    entity_id: 'wo-1',
    read_at: null,
    created_at: minutesAgo(5),
    href: '/app/work-orders/wo-1',
  },
  {
    id: 'n-2',
    type: 'project.added',
    title: 'Added to Crater Cruncher Rover',
    body: null,
    entity_type: 'project',
    entity_id: 'p-1',
    read_at: minutesAgo(30),
    created_at: minutesAgo(60),
    href: '/app/projects/p-1',
  },
  {
    id: 'n-3',
    type: 'system',
    title: 'Welcome to ASME Ops',
    body: 'Finish setting up your chapter profile.',
    entity_type: null,
    entity_id: null,
    read_at: null,
    created_at: minutesAgo(120),
    href: null,
  },
]

function listPayload(items = ITEMS, extra: Record<string, unknown> = {}) {
  return { items, notifications: items, next_cursor: null, total: items.length, unread_count: items.filter((i) => !i.read_at).length, ...extra }
}

describe('NotificationsPage', () => {
  it('renders rows with unread emphasis, type labels and relative times', async () => {
    mockApi({ 'GET /notifications': listPayload() })
    renderWithProviders(<NotificationsPage />, { route: '/notifications' })

    const rows = await screen.findAllByTestId('notification-row')
    expect(rows).toHaveLength(3)
    expect(rows[0]).toHaveAttribute('data-unread', 'true')
    expect(rows[1]).not.toHaveAttribute('data-unread')
    expect(within(rows[0]).getByText('Work order')).toBeInTheDocument()
    expect(within(rows[1]).getByText('Project')).toBeInTheDocument()
    expect(within(rows[2]).getByText('System')).toBeInTheDocument()
    expect(within(rows[0]).getByText('5 minutes ago')).toBeInTheDocument()
    expect(screen.getByText('2 unread')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mark all as read' })).toBeEnabled()
  })

  it('shows the caught-up empty state and disables mark-all when nothing is unread', async () => {
    mockApi({ 'GET /notifications': listPayload([]) })
    renderWithProviders(<NotificationsPage />, { route: '/notifications' })
    expect(await screen.findByText("You're all caught up")).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mark all as read' })).toBeDisabled()
  })

  it('marks a row read and navigates to its record', async () => {
    const { calls } = mockApi({
      'GET /notifications': listPayload(),
      'POST /notifications/read': { updated: 1 },
    })
    const { user } = renderWithProviders(
      <>
        <NotificationsPage />
        <LocationProbe />
      </>,
      { route: '/notifications' },
    )
    const row = await screen.findByRole('button', { name: /Assigned #12/ })
    await user.click(row)
    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.url === '/api/v1/notifications/read')?.body).toEqual({ ids: ['n-1'] }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/work-orders/wo-1'))
  })

  it('does not post again for a notification that is already read and stays put without a link', async () => {
    const { calls } = mockApi({
      'GET /notifications': listPayload(),
      'POST /notifications/read': { updated: 1 },
    })
    const { user } = renderWithProviders(
      <>
        <NotificationsPage />
        <LocationProbe />
      </>,
      { route: '/notifications' },
    )
    await user.click(await screen.findByRole('button', { name: /Added to Crater Cruncher Rover/ }))
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0)
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/projects/p-1'))

    await user.click(screen.getByRole('button', { name: /Welcome to ASME Ops/ }))
    await waitFor(() => expect(calls.filter((c) => c.method === 'POST')).toHaveLength(1))
    expect(screen.getByTestId('location')).toHaveTextContent('/projects/p-1')
  })

  it('marks everything read with {all: true} and confirms with a toast', async () => {
    const { calls } = mockApi({
      'GET /notifications': listPayload(),
      'POST /notifications/read': { updated: 2 },
    })
    const { user } = renderWithProviders(<NotificationsPage />, { route: '/notifications' })
    await user.click(await screen.findByRole('button', { name: 'Mark all as read' }))
    await waitFor(() => expect(calls.find((c) => c.method === 'POST')?.body).toEqual({ all: true }))
    expect(await screen.findByText('Marked 2 notifications as read')).toBeInTheDocument()
  })

  it('surfaces a failed mark-all as a toast instead of failing silently', async () => {
    mockApi({
      'GET /notifications': listPayload(),
      'POST /notifications/read': { __error: { status: 403, code: 'forbidden', error: 'You do not have permission to do that.' } },
    })
    const { user } = renderWithProviders(<NotificationsPage />, { route: '/notifications' })
    await user.click(await screen.findByRole('button', { name: 'Mark all as read' }))
    expect(await screen.findByText('Could not mark notifications as read')).toBeInTheDocument()
    expect(screen.getByText('You do not have permission to do that.')).toBeInTheDocument()
  })

  it('keeps the Unread filter in the URL and sends it to the API', async () => {
    const { calls } = mockApi({
      'GET /notifications': ({ url }: { url: URL }) => (url.searchParams.get('unread') === '1' ? listPayload(ITEMS.filter((i) => !i.read_at), { total: 2 }) : listPayload()),
    })
    const { user } = renderWithProviders(
      <>
        <NotificationsPage />
        <LocationProbe />
      </>,
      { route: '/notifications?unread=1' },
    )
    expect(await screen.findAllByTestId('notification-row')).toHaveLength(2)
    expect(calls[0].url).toContain('unread=1')
    expect(screen.getByRole('radio', { name: /Unread/ })).toHaveAttribute('aria-checked', 'true')

    await user.click(screen.getByRole('radio', { name: 'All' }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/notifications'))
    expect(await screen.findAllByTestId('notification-row')).toHaveLength(3)
  })

  it('offers a way out of an empty Unread view', async () => {
    mockApi({ 'GET /notifications': ({ url }: { url: URL }) => (url.searchParams.get('unread') === '1' ? listPayload([], { unread_count: 0 }) : listPayload()) })
    const { user } = renderWithProviders(<NotificationsPage />, { route: '/notifications?unread=1' })
    expect(await screen.findByText('No unread notifications right now.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Show all notifications' }))
    expect(await screen.findAllByTestId('notification-row')).toHaveLength(3)
  })

  it('loads more pages with the cursor', async () => {
    const page2 = [{ ...ITEMS[2], id: 'n-9', title: 'Older notice' }]
    const { calls } = mockApi({
      'GET /notifications': ({ url }: { url: URL }) => (url.searchParams.get('cursor') === 'c2' ? listPayload(page2, { total: 4 }) : listPayload(ITEMS, { next_cursor: 'c2', total: 4 })),
    })
    const { user } = renderWithProviders(<NotificationsPage />, { route: '/notifications' })
    await screen.findAllByTestId('notification-row')
    expect(screen.getByText('Showing 3 of 4')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Load more' }))
    expect(await screen.findByText('Older notice')).toBeInTheDocument()
    expect(calls.some((c) => c.url.includes('cursor=c2'))).toBe(true)
    expect(screen.queryByRole('button', { name: 'Load more' })).not.toBeInTheDocument()
  })

  it('shows an inline error with retry when the list fails', async () => {
    let attempts = 0
    mockApi({
      'GET /notifications': () => {
        attempts += 1
        return attempts === 1 ? { __error: { status: 500, code: 'server_error', error: 'Database unavailable.' } } : listPayload()
      },
    })
    const { user } = renderWithProviders(<NotificationsPage />, { route: '/notifications' })
    expect(await screen.findByText('Notifications could not be loaded')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findAllByTestId('notification-row')).toHaveLength(3)
  })

  it('works for an ordinary member and hides everything from a role without notification.read', async () => {
    mockApi({ 'GET /notifications': listPayload() })
    const { unmount } = renderWithProviders(<NotificationsPage />, { route: '/notifications', session: memberSession() })
    expect(await screen.findAllByTestId('notification-row')).toHaveLength(3)
    unmount()

    const { calls } = mockApi({ 'GET /notifications': listPayload() })
    renderWithProviders(<NotificationsPage />, { route: '/notifications', session: memberSession({ permissions: { 'report.view': ['chapter'] } }) })
    expect(screen.getByText('Notifications are not available for your role')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Mark all as read' })).not.toBeInTheDocument()
    expect(calls).toHaveLength(0)
  })
})
