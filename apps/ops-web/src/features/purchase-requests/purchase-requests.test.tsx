import { screen, waitFor, within } from '@testing-library/react'
import { useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Session } from '@/api/contracts/session'
import { ADMIN_SESSION, memberSession, mockApi, renderWithProviders } from '@/test/render'
import PurchaseRequestsPage from '.'

const PATHS = ['/purchase-requests', '/purchase-requests/:purchaseRequestId']

/* Fixtures --------------------------------------------------------------------- */

const ADA = { id: 1, name: 'Ada Admin', email: 'ada@uiowa.edu', avatar_url: null }
const MO = { id: 3, name: 'Mo Member', email: 'mo@uiowa.edu', avatar_url: null }
const PROJECT = { id: 'proj-1', name: 'Crater Cruncher Rover', code: 'CCR', visibility: 'chapter' as const }
const VENDOR = { id: 'v-1', name: 'McMaster-Carr' }

function location(id: string, name: string, isDefault = false) {
  return {
    id,
    name,
    description: null,
    parent_id: null,
    building: null,
    room: null,
    is_default: isDefault,
    path: [name],
    asset_count: 0,
    open_work_order_count: 0,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
  }
}

const LAB = location('loc-1', 'Robotics Lab')
const STOCKROOM = location('loc-2', 'Stockroom', true)

const BEARING_PART = {
  id: 'part-1',
  name: 'Bearing 608ZZ',
  sku: 'BRG-608',
  unit: 'each',
  description: 'Sealed skate bearing',
  manufacturer_part_number: '608ZZ-SKF',
  unit_cost: 3.25,
  default_location: { id: LAB.id, name: LAB.name },
  preferred_vendor: VENDOR,
}
const FILAMENT_PART = { id: 'part-2', name: 'PLA filament 1kg', sku: 'FIL-PLA', unit: 'spool', manufacturer_part_number: null, unit_cost: 21.5, default_location: null, preferred_vendor: null }

const PART_ITEM = {
  id: 'item-1',
  part: { id: BEARING_PART.id, name: BEARING_PART.name, sku: BEARING_PART.sku, unit: 'each' },
  description: 'Bearing 608ZZ',
  vendor_part_number: '60355K54',
  url: 'https://www.mcmaster.com/60355K54',
  quantity: 20,
  unit_price: 3.25,
  line_total: 65,
  received_quantity: 5,
  receive_location: { id: LAB.id, name: LAB.name },
}

const FREE_TEXT_ITEM = {
  id: 'item-2',
  part: null,
  description: 'Shipping crate',
  vendor_part_number: null,
  url: null,
  quantity: 1,
  unit_price: 35,
  line_total: 35,
  received_quantity: 0,
  receive_location: null,
}

function request(overrides: Record<string, unknown> = {}) {
  return {
    id: 'pr-1',
    number: 12,
    display_number: 'PR-12',
    title: 'Rover drivetrain bearings',
    status: 'draft',
    requester: ADA,
    project: PROJECT,
    vendor: VENDOR,
    needed_by: '2026-09-30',
    purpose: 'Rebuild the gearbox before the design review.',
    budget_code: 'CCR-FY26',
    shipping_amount: 12.5,
    tax_amount: 4.25,
    estimated_total: 116.75,
    approved_total: null,
    item_count: 2,
    order_reference: null,
    submitted_at: null,
    approved_at: null,
    ordered_at: null,
    received_at: null,
    created_at: '2026-09-10T10:00:00Z',
    updated_at: '2026-09-14T12:00:00Z',
    is_overdue: false,
    ...overrides,
  }
}

const OVERDUE = request({
  id: 'pr-2',
  number: 9,
  display_number: 'PR-9',
  title: 'Weld gas cylinder swap',
  status: 'treasurer_review',
  requester: MO,
  project: null,
  vendor: null,
  needed_by: '2026-08-01',
  estimated_total: 240,
  is_overdue: true,
})

const SUBMIT_EVENT = {
  id: 'ev-1',
  action: 'submit',
  from_status: 'draft',
  to_status: 'treasurer_review',
  step: 'treasurer',
  comment: 'Bearings are seized, we cannot run the rover.',
  actor: ADA,
  created_at: '2026-09-12T09:00:00Z',
}

function detail(overrides: Record<string, unknown> = {}) {
  return {
    ...request(),
    items: [PART_ITEM, FREE_TEXT_ITEM],
    events: [SUBMIT_EVENT],
    decline_reason: null,
    attachment_count: 0,
    available_actions: [] as string[],
    ...overrides,
  }
}

const TABS = { mine: 2, review: 1, open: 3, closed: 4, all: 7 }

function list(items: unknown[], extra: Record<string, unknown> = {}) {
  return { items, next_cursor: null, total: items.length, tabs: TABS, ...extra }
}

function handlers(extra: Record<string, unknown> = {}) {
  return {
    'GET /projects': { items: [{ ...PROJECT, status: 'active' }], next_cursor: null, total: 1 },
    'GET /vendors': { items: [{ ...VENDOR, is_active: true, created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z' }], next_cursor: null, total: 1 },
    'GET /locations': { items: [LAB, STOCKROOM], next_cursor: null, total: 2 },
    'GET /parts': { items: [BEARING_PART, FILAMENT_PART], next_cursor: null, total: 2 },
    'GET /teams': { items: [{ id: 'team-1', name: 'Drivetrain', leads: [], member_count: 3 }], next_cursor: null, total: 1 },
    ...extra,
  }
}

/* Sessions --------------------------------------------------------------------- */

function withPermissions(session: Session, keys: string[]): Session {
  return { ...session, permissions: { ...session.permissions, ...Object.fromEntries(keys.map((key) => [key, ['chapter']])) } }
}

/** Chapter admin who may also raise requests: sees New, Edit and the settings dialog. */
const ADMIN = withPermissions(ADMIN_SESSION, ['purchase.submit', 'purchase.review'])
/** A member who may raise requests but not review them or manage chapter settings. */
const SUBMITTER = withPermissions(memberSession(), ['purchase.submit'])
/** A member with neither. */
const READER = memberSession()

function LocationProbe() {
  const location_ = useLocation()
  return <output data-testid="location">{`${location_.pathname}${location_.search}`}</output>
}

function listCall(calls: Array<{ method: string; url: string }>) {
  return calls.filter((call) => call.method === 'GET' && call.url.startsWith('/api/v1/purchase-requests?')).at(-1)
}

function param(url: string, key: string) {
  return new URL(url, 'http://test.local').searchParams.get(key)
}

afterEach(() => {
  vi.restoreAllMocks()
})

/* List ------------------------------------------------------------------------- */

describe('Purchase requests list', () => {
  it('renders each request with its number, status, people, total and needed-by', async () => {
    mockApi(handlers({ 'GET /purchase-requests': list([request(), OVERDUE]) }))
    renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests', path: PATHS, session: ADMIN })

    const rows = await screen.findAllByTestId('purchase-request-row')
    expect(rows).toHaveLength(2)

    const first = within(rows[0])
    expect(first.getByText('PR-12')).toBeInTheDocument()
    expect(first.getByText('Rover drivetrain bearings')).toBeInTheDocument()
    expect(first.getByText('Draft')).toBeInTheDocument()
    expect(first.getByText('Ada Admin')).toBeInTheDocument()
    expect(first.getByText('Crater Cruncher Rover')).toBeInTheDocument()
    expect(first.getByText('McMaster-Carr')).toBeInTheDocument()
    expect(first.getByText('$116.75')).toBeInTheDocument()
    expect(first.getByText('Sep 30, 2026')).toBeInTheDocument()
    expect(first.queryByText('(overdue)')).not.toBeInTheDocument()

    const second = within(rows[1])
    expect(second.getByText('Treasurer review')).toBeInTheDocument()
    expect(second.getByText('(overdue)')).toBeInTheDocument()
    expect(second.getByText('Aug 1, 2026')).toBeInTheDocument()
  })

  it('shows the tab counts from the payload and asks for the tab the user picks', async () => {
    const { calls } = mockApi(handlers({ 'GET /purchase-requests': list([request()]) }))
    const { user } = renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests', path: PATHS, session: ADMIN })

    await screen.findAllByTestId('purchase-request-row')
    const tablist = screen.getByRole('tablist', { name: 'Purchase request tabs' })
    expect(within(tablist).getByRole('tab', { name: /Mine/ })).toHaveTextContent('2')
    expect(within(tablist).getByRole('tab', { name: /Needs review/ })).toHaveTextContent('1')
    expect(within(tablist).getByRole('tab', { name: /Open/ })).toHaveTextContent('3')
    expect(within(tablist).getByRole('tab', { name: /Closed/ })).toHaveTextContent('4')
    expect(within(tablist).getByRole('tab', { name: /Mine/ })).toHaveAttribute('aria-selected', 'true')
    expect(param(listCall(calls)!.url, 'tab')).toBe('mine')

    await user.click(within(tablist).getByRole('tab', { name: /Needs review/ }))
    await waitFor(() => expect(param(listCall(calls)!.url, 'tab')).toBe('review'))
  })

  it('passes the URL search, filters and sort through to the API', async () => {
    const { calls } = mockApi(handlers({ 'GET /purchase-requests': list([request()]) }))
    renderWithProviders(<PurchaseRequestsPage />, {
      route: '/purchase-requests?tab=open&q=bearing&sort=needed_by&filter[status]=draft,submitted&filter[project]=proj-1&filter[vendor]=v-1',
      path: PATHS,
      session: ADMIN,
    })

    await screen.findAllByTestId('purchase-request-row')
    const url = listCall(calls)!.url
    expect(param(url, 'tab')).toBe('open')
    expect(param(url, 'q')).toBe('bearing')
    expect(param(url, 'sort')).toBe('needed_by')
    expect(param(url, 'filter[status]')).toBe('draft,submitted')
    expect(param(url, 'filter[project]')).toBe('proj-1')
    expect(param(url, 'filter[vendor]')).toBe('v-1')
    expect(screen.getByRole('button', { name: /Status.*Draft/ })).toBeInTheDocument()
  })

  it('offers the tab empty state with a create action, and a clear action when filters are on', async () => {
    mockApi(handlers({ 'GET /purchase-requests': list([]) }))
    const { unmount } = renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests', path: PATHS, session: ADMIN })
    expect(await screen.findByText('You have not asked for anything yet')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'New purchase request' }).length).toBeGreaterThan(0)
    unmount()

    renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests?filter[status]=declined', path: PATHS, session: ADMIN })
    expect(await screen.findByText('No purchase requests match')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Clear search and filters' })).toBeInTheDocument()
  })

  it('shows an inline error with a retry that reloads the list', async () => {
    let attempts = 0
    mockApi(
      handlers({
        'GET /purchase-requests': () => {
          attempts += 1
          return attempts === 1 ? { __error: { status: 500, code: 'server_error', error: 'Database unavailable' } } : list([request()])
        },
      }),
    )
    const { user } = renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests', path: PATHS, session: ADMIN })

    expect(await screen.findByText('Purchase requests could not be loaded')).toBeInTheDocument()
    expect(screen.getByText('Database unavailable')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findAllByTestId('purchase-request-row')).toHaveLength(1)
  })

  it('hides creation and settings from a member who holds neither permission', async () => {
    mockApi(handlers({ 'GET /purchase-requests': list([request()]) }))
    const { user } = renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests', path: PATHS, session: READER })

    await screen.findAllByTestId('purchase-request-row')
    expect(screen.queryByRole('button', { name: 'New purchase request' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Purchasing settings' })).not.toBeInTheDocument()

    await user.keyboard('n')
    expect(screen.queryByRole('dialog', { name: 'New purchase request' })).not.toBeInTheDocument()
  })

  it('opens the create sheet with "n" for someone who may submit requests', async () => {
    mockApi(handlers({ 'GET /purchase-requests': list([request()]) }))
    const { user } = renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests', path: PATHS, session: SUBMITTER })

    await screen.findAllByTestId('purchase-request-row')
    await user.keyboard('n')
    expect(await screen.findByRole('dialog', { name: 'New purchase request' })).toBeInTheDocument()
  })
})

/* Detail ------------------------------------------------------------------------ */

describe('Purchase request detail', () => {
  it('renders the header, totals, line items and the approval timeline', async () => {
    mockApi(handlers({ 'GET /purchase-requests': list([request()]), 'GET /purchase-requests/:id': { purchase_request: detail({ status: 'treasurer_review' }) } }))
    renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests/pr-1', path: PATHS, session: ADMIN })

    const heading = await screen.findByRole('heading', { level: 2, name: /Rover drivetrain bearings/ })
    expect(within(heading).getByText('Treasurer review')).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Details' })).getByText('PR-12')).toBeInTheDocument()

    const table = screen.getByRole('table', { name: /Line items on PR-12/ })
    const rows = within(table).getAllByRole('row')
    const bearing = within(rows[1])
    expect(bearing.getByText('Bearing 608ZZ')).toBeInTheDocument()
    expect(bearing.getByText('BRG-608 · 60355K54')).toBeInTheDocument()
    expect(bearing.getByRole('link', { name: /Product link/ })).toHaveAttribute('href', 'https://www.mcmaster.com/60355K54')
    expect(bearing.getByText('20 each')).toBeInTheDocument()
    expect(bearing.getByText('$3.25')).toBeInTheDocument()
    expect(bearing.getByText('$65.00')).toBeInTheDocument()
    expect(bearing.getByText('Robotics Lab')).toBeInTheDocument()
    expect(within(rows[2]).getByText('Shipping crate')).toBeInTheDocument()
    expect(within(rows[2]).getByText('Default')).toBeInTheDocument()

    const foot = within(table).getAllByRole('row').slice(-4)
    expect(within(foot[0]).getByText('$100.00')).toBeInTheDocument()
    expect(within(foot[1]).getByText('$12.50')).toBeInTheDocument()
    expect(within(foot[2]).getByText('$4.25')).toBeInTheDocument()
    expect(within(foot[3]).getByText('$116.75')).toBeInTheDocument()

    expect(screen.getByText('Submitted for approval · Treasurer')).toBeInTheDocument()
    expect(screen.getByText('Bearings are seized, we cannot run the rover.')).toBeInTheDocument()
    expect(screen.getByText('CCR-FY26')).toBeInTheDocument()
  })

  it('shows the decline reason when a request was declined', async () => {
    mockApi(
      handlers({
        'GET /purchase-requests': list([request()]),
        'GET /purchase-requests/:id': { purchase_request: detail({ status: 'declined', decline_reason: 'Out of budget this semester.', available_actions: ['reopen'] }) },
      }),
    )
    renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests/pr-1', path: PATHS, session: ADMIN })

    expect(await screen.findByText('Out of budget this semester.')).toBeInTheDocument()
  })

  it('answers a request the caller cannot read with a not-found state', async () => {
    mockApi(handlers({ 'GET /purchase-requests': list([]), 'GET /purchase-requests/:id': { __error: { status: 404, code: 'not_found', error: 'Not found' } } }))
    renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests/pr-nope', path: PATHS, session: ADMIN })

    expect(await screen.findByText('Purchase request not found')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back to purchase requests' })).toBeInTheDocument()
  })

  it('renders only the actions the server allows, and none at all when there are none', async () => {
    mockApi(
      handlers({
        'GET /purchase-requests': list([request()]),
        'GET /purchase-requests/:id': { purchase_request: detail({ status: 'received', received_at: '2026-09-15T12:00:00Z', available_actions: [] }) },
      }),
    )
    renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests/pr-1', path: PATHS, session: ADMIN })

    await screen.findByRole('heading', { level: 2, name: /Rover drivetrain bearings/ })
    expect(screen.queryByRole('group', { name: 'Purchase request actions' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit request' })).not.toBeInTheDocument()
  })

  it('offers exactly the available actions on a draft the caller owns', async () => {
    mockApi(
      handlers({
        'GET /purchase-requests': list([request()]),
        'GET /purchase-requests/:id': { purchase_request: detail({ available_actions: ['submit', 'cancel'] }) },
      }),
    )
    renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests/pr-1', path: PATHS, session: ADMIN })

    const bar = await screen.findByRole('group', { name: 'Purchase request actions' })
    expect(within(bar).getByRole('button', { name: 'Edit request' })).toBeInTheDocument()
    expect(within(bar).getByRole('button', { name: 'Submit for approval' })).toBeInTheDocument()
    expect(within(bar).getByRole('button', { name: 'Cancel request' })).toBeInTheDocument()
    expect(within(bar).queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    expect(within(bar).queryByRole('button', { name: 'Receive items' })).not.toBeInTheDocument()
  })

  it('hides Edit request on a draft the caller neither raised nor reviews', async () => {
    mockApi(
      handlers({
        'GET /purchase-requests': list([request()]),
        'GET /purchase-requests/:id': { purchase_request: detail({ requester: ADA, available_actions: [] }) },
      }),
    )
    // SUBMITTER is Mo, who did not raise PR-12 and holds no purchase.review
    renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests/pr-1', path: PATHS, session: SUBMITTER })

    await screen.findByRole('heading', { level: 2, name: /Rover drivetrain bearings/ })
    expect(screen.queryByRole('button', { name: 'Edit request' })).not.toBeInTheDocument()
  })
})

/* Workflow actions --------------------------------------------------------------- */

describe('Purchase request actions', () => {
  function actionHandlers(available: string[], extra: Record<string, unknown> = {}, overrides: Record<string, unknown> = {}) {
    return handlers({
      'GET /purchase-requests': list([request()]),
      'GET /purchase-requests/:id': { purchase_request: detail({ available_actions: available, ...overrides }) },
      ...extra,
    })
  }

  it('submits a draft straight away', async () => {
    const { calls } = mockApi(
      actionHandlers(['submit', 'cancel'], {
        'POST /purchase-requests/:id/submit': { purchase_request: detail({ status: 'treasurer_review', available_actions: [] }) },
      }),
    )
    const { user } = renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests/pr-1', path: PATHS, session: ADMIN })

    await user.click(await screen.findByRole('button', { name: 'Submit for approval' }))
    await waitFor(() => expect(calls.some((call) => call.url === '/api/v1/purchase-requests/pr-1/submit')).toBe(true))
    expect(await screen.findByText('PR-12 submitted')).toBeInTheDocument()
  })

  it('approves with an optional approved total and comment', async () => {
    const { calls } = mockApi(
      actionHandlers(
        ['approve', 'decline', 'request_changes'],
        { 'POST /purchase-requests/:id/approve': { purchase_request: detail({ status: 'approved', available_actions: ['order'] }) } },
        { status: 'treasurer_review' },
      ),
    )
    const { user } = renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests/pr-1', path: PATHS, session: ADMIN })

    await user.click(await screen.findByRole('button', { name: 'Approve' }))
    const dialog = await screen.findByRole('dialog', { name: 'Approve PR-12?' })
    expect(within(dialog).getByText(/Estimated total \$116\.75/)).toBeInTheDocument()
    await user.type(within(dialog).getByLabelText('Approved total'), '110.00')
    await user.type(within(dialog).getByLabelText('Comment'), 'Buy the sealed ones.')
    await user.click(within(dialog).getByRole('button', { name: 'Approve' }))

    await waitFor(() => expect(calls.some((call) => call.url === '/api/v1/purchase-requests/pr-1/approve')).toBe(true))
    expect(calls.find((call) => call.url === '/api/v1/purchase-requests/pr-1/approve')!.body).toEqual({ comment: 'Buy the sealed ones.', approved_total: 110 })
    expect(await screen.findByText('PR-12 approved')).toBeInTheDocument()
  })

  it('refuses to decline without a reason and posts it once given', async () => {
    const { calls } = mockApi(
      actionHandlers(
        ['approve', 'decline'],
        { 'POST /purchase-requests/:id/decline': { purchase_request: detail({ status: 'declined', decline_reason: 'No budget left.', available_actions: ['reopen'] }) } },
        { status: 'treasurer_review' },
      ),
    )
    const { user } = renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests/pr-1', path: PATHS, session: ADMIN })

    await user.click(await screen.findByRole('button', { name: 'Decline' }))
    const dialog = await screen.findByRole('dialog', { name: 'Decline PR-12?' })
    await user.click(within(dialog).getByRole('button', { name: 'Decline' }))
    expect(await within(dialog).findByText('A comment is required.')).toBeInTheDocument()
    expect(calls.some((call) => call.method === 'POST')).toBe(false)

    await user.type(within(dialog).getByLabelText('Reason'), 'No budget left.')
    await user.click(within(dialog).getByRole('button', { name: 'Decline' }))
    await waitFor(() => expect(calls.some((call) => call.url === '/api/v1/purchase-requests/pr-1/decline')).toBe(true))
    expect(calls.find((call) => call.method === 'POST')!.body).toEqual({ comment: 'No budget left.' })
  })

  it('requests changes through the hyphenated route with a required comment', async () => {
    const { calls } = mockApi(
      actionHandlers(
        ['approve', 'request_changes'],
        { 'POST /purchase-requests/:id/request-changes': { purchase_request: detail({ status: 'draft', available_actions: ['submit'] }) } },
        { status: 'treasurer_review' },
      ),
    )
    const { user } = renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests/pr-1', path: PATHS, session: ADMIN })

    await user.click(await screen.findByRole('button', { name: 'Request changes' }))
    const dialog = await screen.findByRole('dialog', { name: 'Request changes on PR-12?' })
    await user.type(within(dialog).getByLabelText('What needs to change?'), 'Split the bearings onto their own request.')
    await user.click(within(dialog).getByRole('button', { name: 'Request changes' }))

    await waitFor(() => expect(calls.some((call) => call.url === '/api/v1/purchase-requests/pr-1/request-changes')).toBe(true))
    expect(calls.find((call) => call.method === 'POST')!.body).toEqual({ comment: 'Split the bearings onto their own request.' })
    expect(await screen.findByText('Changes requested on PR-12')).toBeInTheDocument()
  })

  it('records an order reference when marking a request as ordered', async () => {
    const { calls } = mockApi(
      actionHandlers(
        ['order', 'cancel'],
        { 'POST /purchase-requests/:id/order': { purchase_request: detail({ status: 'ordered', order_reference: 'PO-2291', available_actions: ['receive'] }) } },
        { status: 'approved', approved_total: 110 },
      ),
    )
    const { user } = renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests/pr-1', path: PATHS, session: ADMIN })

    await user.click(await screen.findByRole('button', { name: 'Mark as ordered' }))
    const dialog = await screen.findByRole('dialog', { name: 'Mark PR-12 as ordered' })
    await user.type(within(dialog).getByLabelText('Order reference'), 'PO-2291')
    await user.type(within(dialog).getByLabelText('Approved total'), '112.40')
    await user.click(within(dialog).getByRole('button', { name: 'Mark as ordered' }))

    await waitFor(() => expect(calls.some((call) => call.url === '/api/v1/purchase-requests/pr-1/order')).toBe(true))
    expect(calls.find((call) => call.method === 'POST')!.body).toEqual({ order_reference: 'PO-2291', approved_total: 112.4 })
    expect(await screen.findByText('PR-12 marked as ordered')).toBeInTheDocument()
  })

  it('receives each line with its outstanding quantity and location', async () => {
    const { calls } = mockApi(
      actionHandlers(
        ['receive', 'cancel'],
        { 'POST /purchase-requests/:id/receive': { purchase_request: detail({ status: 'received', available_actions: [] }) } },
        { status: 'ordered' },
      ),
    )
    const { user } = renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests/pr-1', path: PATHS, session: ADMIN })

    await user.click(await screen.findByRole('button', { name: 'Receive items' }))
    const dialog = await screen.findByRole('dialog', { name: 'Receive items on PR-12' })
    expect(within(dialog).getByText('15 each outstanding')).toBeInTheDocument()
    expect(within(dialog).getByText('1 outstanding')).toBeInTheDocument()
    expect(within(dialog).getByLabelText('Quantity received for Bearing 608ZZ')).toHaveValue('15')
    // a free-text line moves no stock, so its location picker is disabled
    expect(within(dialog).getByRole('combobox', { name: 'Location for Shipping crate' })).toBeDisabled()

    const quantity = within(dialog).getByLabelText('Quantity received for Bearing 608ZZ')
    await user.clear(quantity)
    await user.type(quantity, '99')
    await user.click(within(dialog).getByRole('button', { name: 'Record receipt' }))
    expect(await within(dialog).findByText('At most 15 outstanding on this line.')).toBeInTheDocument()
    expect(calls.some((call) => call.method === 'POST')).toBe(false)

    await user.clear(quantity)
    await user.type(quantity, '10')
    // the line already carries its part's receive location, so the picker shows that name
    await user.click(within(dialog).getByText('Robotics Lab'))
    await user.click(await screen.findByRole('option', { name: 'Stockroom' }))
    await user.type(within(dialog).getByLabelText('Note'), 'Two boxes, one back-ordered.')
    await user.click(within(dialog).getByRole('button', { name: 'Record receipt' }))

    await waitFor(() => expect(calls.some((call) => call.url === '/api/v1/purchase-requests/pr-1/receive')).toBe(true))
    expect(calls.find((call) => call.method === 'POST')!.body).toEqual({
      lines: [
        { item_id: 'item-1', quantity: 10, location_id: 'loc-2' },
        { item_id: 'item-2', quantity: 1 },
      ],
      note: 'Two boxes, one back-ordered.',
    })
    expect(await screen.findByText('Receipt recorded on PR-12')).toBeInTheDocument()
  })

  it('maps a per-line receive error from the server onto that line', async () => {
    mockApi(
      actionHandlers(
        ['receive'],
        {
          'POST /purchase-requests/:id/receive': {
            __error: { status: 400, code: 'validation', error: 'Please fix the highlighted fields.', errors: { 'lines[0].quantity': 'Only 15 of this line is still outstanding.' } },
          },
        },
        { status: 'partially_received' },
      ),
    )
    const { user } = renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests/pr-1', path: PATHS, session: ADMIN })

    await user.click(await screen.findByRole('button', { name: 'Receive items' }))
    const dialog = await screen.findByRole('dialog', { name: 'Receive items on PR-12' })
    await user.click(within(dialog).getByRole('button', { name: 'Record receipt' }))
    expect(await within(dialog).findByText('Only 15 of this line is still outstanding.')).toBeInTheDocument()
  })

  it('cancels with a comment and reopens a canceled request in one click', async () => {
    // the detail is re-read after every action, so the fixture moves with the workflow
    let current = detail({ available_actions: ['cancel'] })
    const { calls } = mockApi(
      handlers({
        'GET /purchase-requests': list([request()]),
        'GET /purchase-requests/:id': () => ({ purchase_request: current }),
        'POST /purchase-requests/:id/cancel': () => {
          current = detail({ status: 'canceled', available_actions: ['reopen'] })
          return { purchase_request: current }
        },
        'POST /purchase-requests/:id/reopen': () => {
          current = detail({ status: 'draft', available_actions: ['submit'] })
          return { purchase_request: current }
        },
      }),
    )
    const { user } = renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests/pr-1', path: PATHS, session: ADMIN })

    await user.click(await screen.findByRole('button', { name: 'Cancel request' }))
    const dialog = await screen.findByRole('dialog', { name: 'Cancel PR-12?' })
    await user.type(within(dialog).getByLabelText('Comment'), 'Found spares in the stockroom.')
    await user.click(within(dialog).getByRole('button', { name: 'Cancel request' }))

    await waitFor(() => expect(calls.some((call) => call.url === '/api/v1/purchase-requests/pr-1/cancel')).toBe(true))
    expect(calls.find((call) => call.method === 'POST')!.body).toEqual({ comment: 'Found spares in the stockroom.' })
    expect(await screen.findByText('PR-12 canceled')).toBeInTheDocument()

    await user.click(await screen.findByRole('button', { name: 'Reopen as draft' }))
    await waitFor(() => expect(calls.some((call) => call.url === '/api/v1/purchase-requests/pr-1/reopen')).toBe(true))
    expect(await screen.findByText('PR-12 reopened as a draft')).toBeInTheDocument()
  })

  it('surfaces a conflict from the server as a toast and keeps the dialog open', async () => {
    mockApi(
      actionHandlers(
        ['approve'],
        { 'POST /purchase-requests/:id/approve': { __error: { status: 409, code: 'self_approval', error: 'You cannot approve your own request.' } } },
        { status: 'treasurer_review' },
      ),
    )
    const { user } = renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests/pr-1', path: PATHS, session: ADMIN })

    await user.click(await screen.findByRole('button', { name: 'Approve' }))
    const dialog = await screen.findByRole('dialog', { name: 'Approve PR-12?' })
    await user.click(within(dialog).getByRole('button', { name: 'Approve' }))

    expect(await screen.findByText('Could not approve this request')).toBeInTheDocument()
    expect(screen.getAllByText('You cannot approve your own request.').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByRole('dialog', { name: 'Approve PR-12?' })).toBeInTheDocument()
  })
})

/* New and edit ------------------------------------------------------------------- */

describe('New purchase request', () => {
  it('fills a line from the part picker, keeps totals live and posts the payload', async () => {
    const created = detail({ id: 'pr-new', number: 13, display_number: 'PR-13', title: 'Rover drivetrain bearings', items: [], available_actions: ['submit'] })
    const { calls } = mockApi(
      handlers({
        'GET /purchase-requests': list([request()]),
        'POST /purchase-requests': { purchase_request: created },
        'GET /purchase-requests/:id': { purchase_request: created },
      }),
    )
    const { user } = renderWithProviders(
      <>
        <PurchaseRequestsPage />
        <LocationProbe />
      </>,
      { route: '/purchase-requests?pane=new', path: PATHS, session: ADMIN },
    )

    const sheet = await screen.findByRole('dialog', { name: 'New purchase request' })
    await user.type(within(sheet).getByLabelText('Title'), 'Rover drivetrain bearings')

    await user.click(within(sheet).getByRole('combobox', { name: 'Project' }))
    await user.click(await screen.findByRole('option', { name: /Crater Cruncher Rover/ }))

    await user.click(within(sheet).getByRole('combobox', { name: 'Part for line 1' }))
    await user.click(await screen.findByRole('option', { name: /Bearing 608ZZ/ }))
    expect(within(sheet).getByLabelText('Description for line 1')).toHaveValue('Bearing 608ZZ')
    expect(within(sheet).getByLabelText('Vendor part number for line 1')).toHaveValue('608ZZ-SKF')
    expect(within(sheet).getByLabelText('Unit price for line 1')).toHaveValue('3.25')

    const quantity = within(sheet).getByLabelText('Quantity for line 1')
    await user.clear(quantity)
    await user.type(quantity, '4')
    await user.type(within(sheet).getByLabelText('Shipping'), '5')
    await user.type(within(sheet).getByLabelText('Tax'), '1.25')
    await waitFor(() => expect(screen.getByTestId('estimated-total')).toHaveTextContent('$19.25'))

    await user.click(within(sheet).getByRole('button', { name: 'Create request' }))
    await waitFor(() => expect(calls.some((call) => call.method === 'POST' && call.url === '/api/v1/purchase-requests')).toBe(true))
    expect(calls.find((call) => call.method === 'POST')!.body).toEqual({
      title: 'Rover drivetrain bearings',
      project_id: 'proj-1',
      vendor_id: null,
      needed_by: null,
      purpose: null,
      budget_code: null,
      shipping_amount: 5,
      tax_amount: 1.25,
      items: [
        {
          part_id: 'part-1',
          description: 'Bearing 608ZZ',
          vendor_part_number: '608ZZ-SKF',
          url: null,
          quantity: 4,
          unit_price: 3.25,
          receive_location_id: 'loc-1',
        },
      ],
    })

    expect(await screen.findByText('Purchase request created')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/purchase-requests/pr-new'))
  })

  it('adds and removes free-text lines and blocks a line with no description', async () => {
    const { calls } = mockApi(handlers({ 'GET /purchase-requests': list([request()]) }))
    const { user } = renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests?pane=new', path: PATHS, session: ADMIN })

    const sheet = await screen.findByRole('dialog', { name: 'New purchase request' })
    await user.type(within(sheet).getByLabelText('Title'), 'Consumables restock')
    await user.click(within(sheet).getByRole('button', { name: 'Add line' }))
    expect(within(sheet).getByLabelText('Description for line 2')).toBeInTheDocument()

    await user.type(within(sheet).getByLabelText('Description for line 1'), 'Blue shop towels')
    await user.click(within(sheet).getByRole('button', { name: 'Create request' }))
    expect(await within(sheet).findByText('Describe what to buy.')).toBeInTheDocument()
    expect(calls.some((call) => call.method === 'POST')).toBe(false)

    await user.click(within(sheet).getByRole('button', { name: 'Remove line 2' }))
    expect(within(sheet).queryByLabelText('Description for line 2')).not.toBeInTheDocument()
  })

  it('maps server errors keyed on a line onto that line', async () => {
    mockApi(
      handlers({
        'GET /purchase-requests': list([request()]),
        'POST /purchase-requests': {
          __error: { status: 400, code: 'validation', error: 'Please fix the highlighted fields.', errors: { title: 'This field is required.', 'items[0].quantity': 'Must be greater than 0.' } },
        },
      }),
    )
    const { user } = renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests?pane=new', path: PATHS, session: ADMIN })

    const sheet = await screen.findByRole('dialog', { name: 'New purchase request' })
    await user.type(within(sheet).getByLabelText('Title'), 'Bearings')
    await user.type(within(sheet).getByLabelText('Description for line 1'), 'Bearing 608ZZ')
    await user.click(within(sheet).getByRole('button', { name: 'Create request' }))

    expect(await within(sheet).findByText('This field is required.')).toBeInTheDocument()
    expect(within(sheet).getByText('Must be greater than 0.')).toBeInTheDocument()
    expect(within(sheet).getByLabelText('Quantity for line 1')).toHaveAttribute('aria-invalid', 'true')
  })

  it('edits a draft and replaces every line on PATCH', async () => {
    const draft = detail({ available_actions: ['submit', 'cancel'] })
    const { calls } = mockApi(
      handlers({
        'GET /purchase-requests': list([request()]),
        'GET /purchase-requests/:id': { purchase_request: draft },
        'PATCH /purchase-requests/:id': { purchase_request: draft },
      }),
    )
    const { user } = renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests/pr-1', path: PATHS, session: ADMIN })

    await user.click(await screen.findByRole('button', { name: 'Edit request' }))
    const sheet = await screen.findByRole('dialog', { name: 'Edit PR-12' })
    expect(within(sheet).getByLabelText('Title')).toHaveValue('Rover drivetrain bearings')
    expect(within(sheet).getByLabelText('Description for line 1')).toHaveValue('Bearing 608ZZ')
    expect(within(sheet).getByLabelText('Quantity for line 2')).toHaveValue('1')

    await user.click(within(sheet).getByRole('button', { name: 'Remove line 2' }))
    const quantity = within(sheet).getByLabelText('Quantity for line 1')
    await user.clear(quantity)
    await user.type(quantity, '24')
    await user.click(within(sheet).getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(calls.some((call) => call.method === 'PATCH')).toBe(true))
    const patch = calls.find((call) => call.method === 'PATCH')!
    expect(patch.url).toBe('/api/v1/purchase-requests/pr-1')
    expect(patch.body).toEqual({
      title: 'Rover drivetrain bearings',
      project_id: 'proj-1',
      vendor_id: 'v-1',
      needed_by: '2026-09-30',
      purpose: 'Rebuild the gearbox before the design review.',
      budget_code: 'CCR-FY26',
      shipping_amount: 12.5,
      tax_amount: 4.25,
      items: [
        {
          part_id: 'part-1',
          description: 'Bearing 608ZZ',
          vendor_part_number: '60355K54',
          url: 'https://www.mcmaster.com/60355K54',
          quantity: 24,
          unit_price: 3.25,
          receive_location_id: 'loc-1',
        },
      ],
    })
    expect(await screen.findByText('Purchase request updated')).toBeInTheDocument()
  })
})

/* Purchasing settings ------------------------------------------------------------ */

describe('Purchasing settings', () => {
  const SETTINGS = { purchasing: { advisor_review_threshold: 500, require_project_lead_approval: false, critical_parts_team_id: null } }

  it('loads the chapter settings and replaces the whole block on save', async () => {
    const { calls } = mockApi(
      handlers({
        'GET /purchase-requests': list([request()]),
        'GET /purchasing/settings': SETTINGS,
        'PUT /purchasing/settings': ({ body }: { body: unknown }) => ({ purchasing: body }),
      }),
    )
    const { user } = renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests', path: PATHS, session: ADMIN })

    await user.click(await screen.findByRole('button', { name: 'Purchasing settings' }))
    const dialog = await screen.findByRole('dialog', { name: 'Purchasing settings' })
    const threshold = await within(dialog).findByLabelText('Advisor review threshold')
    await waitFor(() => expect(threshold).toHaveValue('500'))

    await user.clear(threshold)
    await user.type(threshold, '750')
    await user.click(within(dialog).getByLabelText(/Require project lead approval/))
    await user.click(within(dialog).getByRole('combobox', { name: 'Critical parts team' }))
    await user.click(await screen.findByRole('option', { name: /Drivetrain/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Save settings' }))

    await waitFor(() => expect(calls.some((call) => call.method === 'PUT')).toBe(true))
    expect(calls.find((call) => call.method === 'PUT')!.body).toEqual({
      advisor_review_threshold: 750,
      require_project_lead_approval: true,
      critical_parts_team_id: 'team-1',
    })
    expect(await screen.findByText('Purchasing settings saved')).toBeInTheDocument()
  })

  it('shows a retryable error when the settings cannot be loaded', async () => {
    mockApi(
      handlers({
        'GET /purchase-requests': list([request()]),
        'GET /purchasing/settings': { __error: { status: 500, code: 'server_error', error: 'Settings unavailable' } },
      }),
    )
    const { user } = renderWithProviders(<PurchaseRequestsPage />, { route: '/purchase-requests', path: PATHS, session: ADMIN })

    await user.click(await screen.findByRole('button', { name: 'Purchasing settings' }))
    const dialog = await screen.findByRole('dialog', { name: 'Purchasing settings' })
    expect(await within(dialog).findByText('Could not load purchasing settings')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Retry' })).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Save settings' })).toBeDisabled()
  })
})
