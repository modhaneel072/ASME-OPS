import { screen, waitFor, within } from '@testing-library/react'
import { useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Session } from '@/api/contracts/session'
import { ADMIN_SESSION, memberSession, mockApi, renderWithProviders } from '@/test/render'
import PartsPage from './index'

const PATHS = ['/parts', '/parts/:partId']

/* Sessions ------------------------------------------------------------------- */

function withPermissions(base: Session, keys: string[]): Session {
  return { ...base, permissions: { ...base.permissions, ...Object.fromEntries(keys.map((key) => [key, ['chapter']])) } }
}

/** Inventory manager: reads stock, moves stock and may ask for purchases. */
const MANAGER = withPermissions(ADMIN_SESSION, ['inventory.read', 'inventory.manage', 'purchase.submit', 'vendor.read'])
/** Full member: sees stock, changes nothing. */
const READER = withPermissions(memberSession(), ['inventory.read'])

/* Fixtures ------------------------------------------------------------------- */

const bearing = {
  id: 'p-1',
  name: '608ZZ bearing',
  sku: 'BRG-608',
  unit: 'each',
  description: 'Skate bearing used across the rover drivetrain.',
  part_type: { id: 'pt-1', name: 'Bearings', color: '#0878d1' },
  manufacturer: 'NSK',
  manufacturer_part_number: '608ZZ-NSK',
  unit_cost: 1.25,
  is_critical: true,
  minimum_stock: 20,
  maximum_stock: 100,
  reorder_quantity: 50,
  default_location: { id: 'loc-1', name: 'Shop shelf A' },
  qr_code: null,
  is_active: true,
  totals: { on_hand: 12, reserved: 2, available: 10, ordered: 25 },
  stock_state: 'low',
  preferred_vendor: { id: 'v-1', name: 'McMaster-Carr' },
  created_at: '2026-09-01T12:00:00Z',
  updated_at: '2026-09-10T12:00:00Z',
}

const filament = {
  ...bearing,
  id: 'p-2',
  name: 'PLA filament, black',
  sku: null,
  unit: 'spool',
  description: null,
  part_type: null,
  manufacturer: null,
  manufacturer_part_number: null,
  unit_cost: null,
  is_critical: false,
  minimum_stock: null,
  maximum_stock: null,
  reorder_quantity: null,
  default_location: null,
  totals: { on_hand: 6, reserved: 0, available: 6, ordered: 0 },
  stock_state: 'ok',
  preferred_vendor: null,
}

const bearingDetail = {
  ...bearing,
  balances: [{ location: { id: 'loc-1', name: 'Shop shelf A' }, on_hand: 12, reserved: 2, available: 10 }],
  vendors: [
    { vendor: { id: 'v-1', name: 'McMaster-Carr' }, vendor_part_number: '5972K11', url: 'https://www.mcmaster.com/5972K11', preferred: true, last_price: 1.2, last_ordered_at: '2026-09-05T00:00:00Z' },
  ],
  assets: [{ id: 'a-1', name: 'Rover drivetrain', code: 'ROV-1', status: 'online' }],
  open_purchase_requests: [{ id: 'pr-1', number: 12, display_number: 'PR-12', title: 'Bearings restock', status: 'ordered', outstanding_quantity: 25 }],
  recent_transactions: [],
}

const receiptRow = {
  id: 't-1',
  type: 'receipt',
  part: { id: 'p-1', name: '608ZZ bearing', sku: 'BRG-608', unit: 'each' },
  location: { id: 'loc-1', name: 'Shop shelf A' },
  quantity: 10,
  on_hand_delta: 10,
  reserved_delta: 0,
  on_hand_after: 12,
  reserved_after: 2,
  counted_quantity: null,
  unit_cost: 1.25,
  work_order: null,
  purchase_request: null,
  reference_transaction_id: null,
  note: 'Opening stock',
  created_by: { id: 1, name: 'Ada Admin', email: 'ada@uiowa.edu', avatar_url: null },
  created_at: '2026-09-09T15:00:00Z',
}

const locations = {
  items: [
    { id: 'loc-1', name: 'Shop shelf A', description: null, parent_id: null, building: null, room: null, is_default: true, path: ['Shop shelf A'], created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z' },
    { id: 'loc-2', name: 'Cold storage', description: null, parent_id: null, building: null, room: null, is_default: false, path: ['Cold storage'], created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z' },
  ],
  next_cursor: null,
  total: 2,
}

function partsPayload(items: unknown[], counts = { low: 1, out: 0 }) {
  return { items, next_cursor: null, total: items.length, stock_counts: counts }
}

function list(items: unknown[]) {
  return { items, next_cursor: null, total: items.length }
}

/** Everything the screen loads before the user touches anything. */
function baseMocks(overrides: Record<string, unknown> = {}) {
  return mockApi({
    'GET /parts': partsPayload([bearing, filament]),
    'GET /parts/:id': { part: bearingDetail },
    'GET /parts/:id/transactions': list([receiptRow]),
    'GET /part-types': list([{ id: 'pt-1', name: 'Bearings', color: '#0878d1', part_count: 4 }]),
    'GET /vendors': list([{ id: 'v-1', name: 'McMaster-Carr' }, { id: 'v-2', name: 'DigiKey' }]),
    'GET /locations': locations,
    'GET /assets': list([{ id: 'a-1', name: 'Rover drivetrain', code: 'ROV-1', status: 'online', types: [] }, { id: 'a-2', name: '3D Printer 01', code: 'PRN-01', status: 'online', types: [] }]),
    'GET /work-orders': list([{ id: 'wo-1', number: 41, title: 'Rebuild drivetrain', status: 'open', assignees: [] }]),
    ...overrides,
  })
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>
}

function searchParam(url: string, key: string) {
  return new URL(url, 'http://test.local').searchParams.get(key)
}

function lastCall(calls: Array<{ method: string; url: string; body: unknown }>, method: string, path: string) {
  return [...calls].reverse().find((call) => call.method === method && call.url.split('?')[0] === `/api/v1${path}`)
}

afterEach(() => {
  vi.restoreAllMocks()
})

/* List ------------------------------------------------------------------------ */

describe('Parts list', () => {
  it('shows each part with its stock state, quantities, shelf and preferred vendor', async () => {
    const { calls } = baseMocks()
    renderWithProviders(<PartsPage />, { route: '/parts', path: PATHS, session: MANAGER })

    const rows = await screen.findAllByTestId('part-row')
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('608ZZ bearing')
    expect(rows[0]).toHaveTextContent('BRG-608')
    expect(within(rows[0]).getByText('Low stock')).toBeInTheDocument()
    expect(within(rows[0]).getByText('Critical')).toBeInTheDocument()
    expect(rows[0]).toHaveTextContent('Shop shelf A')
    expect(rows[0]).toHaveTextContent('McMaster-Carr')
    expect(rows[1]).toHaveTextContent('No SKU')

    const request = calls.find((call) => call.method === 'GET' && call.url.startsWith('/api/v1/parts?'))!
    expect(searchParam(request.url, 'filter[active]')).toBe('true')
    expect(searchParam(request.url, 'sort')).toBe('name')
    expect(searchParam(request.url, 'filter[stock]')).toBeNull()
  })

  it('takes the tab badges from stock_counts and asks for the stock state the tab names', async () => {
    const { calls } = baseMocks()
    const { user } = renderWithProviders(<PartsPage />, { route: '/parts', path: PATHS, session: MANAGER })

    const lowTab = await screen.findByRole('tab', { name: /Low stock/ })
    await waitFor(() => expect(lowTab).toHaveTextContent('1'))
    expect(screen.getByRole('tab', { name: /Out of stock/ })).toHaveTextContent('0')

    await user.click(lowTab)
    await waitFor(() => expect(calls.some((call) => searchParam(call.url, 'filter[stock]') === 'low')).toBe(true))
  })

  it('filters by part type through the chip and keeps it in the URL', async () => {
    const { calls } = baseMocks()
    const { user } = renderWithProviders(<PartsPage />, { route: '/parts', path: PATHS, session: MANAGER })

    await screen.findAllByTestId('part-row')
    await user.click(screen.getByRole('button', { name: /^Type/ }))
    await user.click(await screen.findByRole('checkbox', { name: /Bearings/ }))

    await waitFor(() => expect(calls.some((call) => searchParam(call.url, 'filter[type]') === 'pt-1')).toBe(true))
  })

  it('offers a way out when a search matches nothing', async () => {
    baseMocks({ 'GET /parts': partsPayload([]) })
    const { user } = renderWithProviders(<PartsPage />, { route: '/parts?q=titanium', path: PATHS, session: MANAGER })

    expect(await screen.findByText('No parts match')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Clear search and filters' }))
    expect(screen.queryByText(/Nothing matches “titanium”/)).not.toBeInTheDocument()
  })

  it('shows the first-run empty state with a create action', async () => {
    baseMocks({ 'GET /parts': partsPayload([], { low: 0, out: 0 }) })
    renderWithProviders(<PartsPage />, { route: '/parts', path: PATHS, session: MANAGER })

    expect(await screen.findByText('No parts yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add the first part' })).toBeInTheDocument()
  })

  it('shows an inline error with a retry when the list fails', async () => {
    let attempts = 0
    baseMocks({
      'GET /parts': () => {
        attempts += 1
        return attempts === 1 ? { __error: { status: 500, code: 'server_error', error: 'Database unavailable.' } } : partsPayload([bearing])
      },
    })
    const { user } = renderWithProviders(<PartsPage />, { route: '/parts', path: PATHS, session: MANAGER })

    expect(await screen.findByText('Parts could not be loaded')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByTestId('part-row')).toHaveTextContent('608ZZ bearing')
  })
})

/* Detail ---------------------------------------------------------------------- */

describe('Part detail', () => {
  it('renders stock, shelves, vendors, spare-for assets, open orders and history', async () => {
    baseMocks()
    renderWithProviders(<PartsPage />, { route: '/parts/p-1', path: PATHS, session: MANAGER })

    expect(await screen.findByRole('heading', { level: 2, name: /608ZZ bearing/ })).toBeInTheDocument()
    const panel = screen.getByRole('article')
    expect(within(panel).getByText('10 each')).toBeInTheDocument()
    expect(within(panel).getByText('On order')).toBeInTheDocument()

    const shelves = screen.getByRole('table', { name: /each location/ })
    expect(within(shelves).getByRole('link', { name: 'Shop shelf A' })).toBeInTheDocument()

    expect(within(screen.getByRole('list', { name: 'Vendors' })).getByText('Preferred')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Rover drivetrain' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'PR-12' })).toBeInTheDocument()
    expect(screen.getByText('25 each outstanding')).toBeInTheDocument()

    const history = await screen.findByRole('table', { name: /movement of this part/ })
    expect(within(history).getByText('Receipt')).toBeInTheDocument()
    expect(within(history).getByText('+10')).toBeInTheDocument()
    expect(within(history).getByText('Opening stock')).toBeInTheDocument()
  })

  it('shows a not-found state for a stale link', async () => {
    baseMocks({ 'GET /parts/:id': { __error: { status: 404, code: 'not_found', error: 'Not found.' } } })
    renderWithProviders(<PartsPage />, { route: '/parts/missing', path: PATHS, session: MANAGER })

    expect(await screen.findByText('Part not found')).toBeInTheDocument()
  })

  it('hides every stock action from someone who only reads inventory', async () => {
    baseMocks()
    const { user } = renderWithProviders(<PartsPage />, { route: '/parts/p-1', path: PATHS, session: READER })

    expect(await screen.findByRole('heading', { level: 2, name: /608ZZ bearing/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'New Part' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Receive' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Issue' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Adjust' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Transfer' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Count' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'More actions' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit vendors' })).not.toBeInTheDocument()

    await user.keyboard('n')
    expect(screen.queryByRole('dialog', { name: 'New Part' })).not.toBeInTheDocument()
  })
})

/* Create and edit -------------------------------------------------------------- */

describe('New part', () => {
  it('refuses a nameless part and a maximum below the minimum before sending anything', async () => {
    const { calls } = baseMocks()
    const { user } = renderWithProviders(<PartsPage />, { route: '/parts?pane=new', path: PATHS, session: MANAGER })

    const sheet = await screen.findByRole('dialog', { name: 'New Part' })
    await user.type(within(sheet).getByLabelText('Minimum stock'), '10')
    await user.type(within(sheet).getByLabelText('Maximum stock'), '5')
    await user.click(within(sheet).getByRole('button', { name: 'Create Part' }))

    expect(await within(sheet).findByText('Give the part a name.')).toBeInTheDocument()
    expect(within(sheet).getByText('Maximum stock must be at least the minimum stock.')).toBeInTheDocument()
    expect(calls.some((call) => call.method === 'POST')).toBe(false)
  })

  it('posts blanks as null and opens the part it created', async () => {
    const created = { ...bearingDetail, id: 'p-9', name: 'M4 nylon lock nut', sku: 'FAS-M4N' }
    const { calls } = baseMocks({ 'POST /parts': { part: created }, 'GET /parts/:id': { part: created } })
    const { user } = renderWithProviders(
      <>
        <PartsPage />
        <LocationProbe />
      </>,
      { route: '/parts?pane=new', path: PATHS, session: MANAGER },
    )

    const sheet = await screen.findByRole('dialog', { name: 'New Part' })
    await user.type(within(sheet).getByLabelText('Name'), 'M4 nylon lock nut')
    await user.type(within(sheet).getByLabelText('SKU'), 'FAS-M4N')
    await user.type(within(sheet).getByLabelText('Minimum stock'), '100')
    await user.click(within(sheet).getByRole('checkbox', { name: /Critical part/ }))
    await user.click(within(sheet).getByRole('button', { name: 'Create Part' }))

    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true))
    expect(lastCall(calls, 'POST', '/parts')!.body).toEqual({
      name: 'M4 nylon lock nut',
      sku: 'FAS-M4N',
      description: null,
      part_type_id: null,
      manufacturer: null,
      manufacturer_part_number: null,
      unit: 'each',
      unit_cost: null,
      is_critical: true,
      minimum_stock: 100,
      maximum_stock: null,
      reorder_quantity: null,
      default_location_id: null,
      qr_code: null,
      is_active: true,
    })
    expect(await screen.findByText('Part created')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/parts/p-9'))
  })

  it('keeps the sheet open and puts a duplicate-SKU error on the field', async () => {
    baseMocks({ 'POST /parts': { __error: { status: 400, code: 'validation', error: 'Please fix the highlighted fields.', errors: { sku: 'This SKU is already used by another part.' } } } })
    const { user } = renderWithProviders(<PartsPage />, { route: '/parts?pane=new', path: PATHS, session: MANAGER })

    const sheet = await screen.findByRole('dialog', { name: 'New Part' })
    await user.type(within(sheet).getByLabelText('Name'), 'Another bearing')
    await user.type(within(sheet).getByLabelText('SKU'), 'BRG-608')
    await user.click(within(sheet).getByRole('button', { name: 'Create Part' }))

    expect(await within(sheet).findByText('This SKU is already used by another part.')).toBeInTheDocument()
    expect(within(sheet).getByLabelText('SKU')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.queryByText('Part created')).not.toBeInTheDocument()
  })
})

/* Movements -------------------------------------------------------------------- */

describe('Stock movements', () => {
  it('receives stock at the default shelf with a unit cost', async () => {
    const { calls } = baseMocks({ 'POST /parts/:id/transactions': { transaction: receiptRow, part: bearing } })
    const { user } = renderWithProviders(<PartsPage />, { route: '/parts/p-1', path: PATHS, session: MANAGER })

    await user.click(await screen.findByRole('button', { name: 'Receive' }))
    const dialog = await screen.findByRole('dialog', { name: /Receive 608ZZ bearing/ })
    await user.type(within(dialog).getByLabelText('Quantity'), '25')
    await user.type(within(dialog).getByLabelText('Unit cost'), '1.4')
    await user.click(within(dialog).getByRole('button', { name: 'Receive' }))

    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true))
    expect(lastCall(calls, 'POST', '/parts/p-1/transactions')!.body).toEqual({ type: 'receipt', quantity: 25, location_id: 'loc-1', unit_cost: 1.4 })
    expect(await screen.findByText('Stock updated')).toBeInTheDocument()
  })

  it('requires a reason on an adjustment and sends the direction', async () => {
    const { calls } = baseMocks({ 'POST /parts/:id/transactions': { transaction: receiptRow, part: bearing } })
    const { user } = renderWithProviders(<PartsPage />, { route: '/parts/p-1', path: PATHS, session: MANAGER })

    await user.click(await screen.findByRole('button', { name: 'Adjust' }))
    const dialog = await screen.findByRole('dialog', { name: /Adjust 608ZZ bearing/ })
    await user.type(within(dialog).getByLabelText('Quantity'), '2')
    await user.click(within(dialog).getByRole('button', { name: 'Adjust' }))

    expect(await within(dialog).findByText('Say why the quantity changed.')).toBeInTheDocument()
    expect(calls.some((call) => call.method === 'POST')).toBe(false)

    await user.click(within(dialog).getByRole('radio', { name: 'Decrease' }))
    await user.type(within(dialog).getByLabelText('Note'), 'Two were bent.')
    await user.click(within(dialog).getByRole('button', { name: 'Adjust' }))

    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true))
    expect(lastCall(calls, 'POST', '/parts/p-1/transactions')!.body).toEqual({
      type: 'adjustment',
      quantity: 2,
      location_id: 'loc-1',
      direction: 'decrease',
      note: 'Two were bent.',
    })
  })

  it('explains a 409 from the ledger inside the dialog', async () => {
    baseMocks({
      'POST /parts/:id/transactions': {
        __error: {
          status: 409,
          code: 'insufficient_stock',
          error: 'There is not enough stock at that location.',
          extra: { on_hand: 12, reserved: 2, requested: 40 },
        },
      },
    })
    const { user } = renderWithProviders(<PartsPage />, { route: '/parts/p-1', path: PATHS, session: MANAGER })

    await user.click(await screen.findByRole('button', { name: 'Issue' }))
    const dialog = await screen.findByRole('dialog', { name: /Issue 608ZZ bearing/ })
    await user.type(within(dialog).getByLabelText('Quantity'), '40')
    await user.click(within(dialog).getByRole('button', { name: 'Issue' }))

    expect(await within(dialog).findByText(/There is not enough stock at that location\./)).toBeInTheDocument()
    expect(within(dialog).getByText(/That location holds 12 with 2 reserved\./)).toBeInTheDocument()
  })

  it('refuses a transfer that does not move anywhere', async () => {
    const { calls } = baseMocks({ 'POST /inventory/transfers': { transactions: [receiptRow], part: bearing } })
    const { user } = renderWithProviders(<PartsPage />, { route: '/parts/p-1', path: PATHS, session: MANAGER })

    await user.click(await screen.findByRole('button', { name: 'Transfer' }))
    const dialog = await screen.findByRole('dialog', { name: /Transfer 608ZZ bearing/ })
    await user.type(within(dialog).getByLabelText('Quantity'), '4')
    await user.click(within(dialog).getByLabelText('To'))
    await user.click(await screen.findByRole('option', { name: /Shop shelf A/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Transfer' }))

    expect(await within(dialog).findByText('Choose a different location.')).toBeInTheDocument()
    expect(calls.some((call) => call.method === 'POST')).toBe(false)
  })

  it('moves stock between two shelves', async () => {
    const { calls } = baseMocks({ 'POST /inventory/transfers': { transactions: [receiptRow], part: bearing } })
    const { user } = renderWithProviders(<PartsPage />, { route: '/parts/p-1', path: PATHS, session: MANAGER })

    await user.click(await screen.findByRole('button', { name: 'Transfer' }))
    const dialog = await screen.findByRole('dialog', { name: /Transfer 608ZZ bearing/ })
    await user.type(within(dialog).getByLabelText('Quantity'), '4')
    await user.click(within(dialog).getByLabelText('To'))
    await user.click(await screen.findByRole('option', { name: /Cold storage/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Transfer' }))

    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true))
    expect(lastCall(calls, 'POST', '/inventory/transfers')!.body).toEqual({
      part_id: 'p-1',
      from_location_id: 'loc-1',
      to_location_id: 'loc-2',
      quantity: 4,
    })
    expect(await screen.findByText('Stock transferred')).toBeInTheDocument()
  })

  it('records a cycle count as one line for this part', async () => {
    const { calls } = baseMocks({
      'POST /inventory/cycle-counts': { lines: [{ part: { id: 'p-1', name: '608ZZ bearing', sku: 'BRG-608', unit: 'each' }, expected: 12, counted: 11, delta: -1 }] },
    })
    const { user } = renderWithProviders(<PartsPage />, { route: '/parts/p-1', path: PATHS, session: MANAGER })

    await user.click(await screen.findByRole('button', { name: 'Count' }))
    const dialog = await screen.findByRole('dialog', { name: /Count 608ZZ bearing/ })
    await user.type(within(dialog).getByLabelText('Counted quantity'), '11')
    expect(within(dialog).getByText(/Difference: −1 each/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Record count' }))

    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true))
    expect(lastCall(calls, 'POST', '/inventory/cycle-counts')!.body).toEqual({
      location_id: 'loc-1',
      lines: [{ part_id: 'p-1', counted_quantity: 11 }],
    })
    expect(await screen.findByText('Count recorded')).toBeInTheDocument()
  })
})

/* Vendor and asset editors ------------------------------------------------------ */

describe('Vendor and asset editors', () => {
  it('replaces the vendor list, keeping one vendor preferred', async () => {
    const { calls } = baseMocks({ 'PUT /parts/:id/vendors': { part: bearingDetail } })
    const { user } = renderWithProviders(<PartsPage />, { route: '/parts/p-1', path: PATHS, session: MANAGER })

    await user.click(await screen.findByRole('button', { name: 'Edit vendors' }))
    const dialog = await screen.findByRole('dialog', { name: /Vendors for 608ZZ bearing/ })

    await user.click(within(dialog).getByLabelText('Vendor to add'))
    await user.click(await screen.findByRole('option', { name: /DigiKey/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Add' }))
    await user.type(within(dialog).getByLabelText('DigiKey order number'), 'DK-608')
    await user.click(within(dialog).getByRole('button', { name: 'Save vendors' }))

    await waitFor(() => expect(calls.some((call) => call.method === 'PUT')).toBe(true))
    expect(lastCall(calls, 'PUT', '/parts/p-1/vendors')!.body).toEqual({
      vendors: [
        { vendor_id: 'v-1', vendor_part_number: '5972K11', url: 'https://www.mcmaster.com/5972K11', preferred: true, last_price: 1.2 },
        { vendor_id: 'v-2', vendor_part_number: 'DK-608', url: null, preferred: false, last_price: null },
      ],
    })
    expect(await screen.findByText('Vendors updated')).toBeInTheDocument()
  })

  it('rejects a vendor link that is not a URL', async () => {
    const { calls } = baseMocks({ 'PUT /parts/:id/vendors': { part: bearingDetail } })
    const { user } = renderWithProviders(<PartsPage />, { route: '/parts/p-1', path: PATHS, session: MANAGER })

    await user.click(await screen.findByRole('button', { name: 'Edit vendors' }))
    const dialog = await screen.findByRole('dialog', { name: /Vendors for 608ZZ bearing/ })
    const link = within(dialog).getByLabelText('McMaster-Carr link')
    await user.clear(link)
    await user.type(link, 'mcmaster.com')
    await user.click(within(dialog).getByRole('button', { name: 'Save vendors' }))

    expect(await within(dialog).findByText('Start the link with http:// or https://.')).toBeInTheDocument()
    expect(calls.some((call) => call.method === 'PUT')).toBe(false)
  })

  it('replaces the spare-for asset list', async () => {
    const { calls } = baseMocks({ 'PUT /parts/:id/assets': { part: bearingDetail } })
    const { user } = renderWithProviders(<PartsPage />, { route: '/parts/p-1', path: PATHS, session: MANAGER })

    await user.click(await screen.findByRole('button', { name: 'Edit assets' }))
    const dialog = await screen.findByRole('dialog', { name: /spare for/ })
    await user.click(within(dialog).getByLabelText('Assets'))
    await user.click(await screen.findByRole('option', { name: /3D Printer 01/ }))
    await user.click(within(dialog).getByRole('button', { name: 'Save assets' }))

    await waitFor(() => expect(calls.some((call) => call.method === 'PUT')).toBe(true))
    expect(lastCall(calls, 'PUT', '/parts/p-1/assets')!.body).toEqual({ asset_ids: ['a-1', 'a-2'] })
  })
})

/* Low stock → purchase requests -------------------------------------------------- */

describe('Low stock tab', () => {
  it('turns the selected parts into draft purchase requests and goes to them', async () => {
    const { calls } = baseMocks({
      'POST /purchase-requests/from-low-stock': { purchase_requests: [{ id: 'pr-9', number: 13, display_number: 'PR-13', title: 'McMaster-Carr restock', status: 'draft' }] },
    })
    const { user } = renderWithProviders(
      <>
        <PartsPage />
        <LocationProbe />
      </>,
      { route: '/parts?tab=low', path: PATHS, session: MANAGER },
    )

    await user.click(await screen.findByRole('checkbox', { name: 'Select 608ZZ bearing' }))
    expect(screen.getByText('1 part selected')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Create purchase requests' }))

    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true))
    expect(lastCall(calls, 'POST', '/purchase-requests/from-low-stock')!.body).toEqual({ part_ids: ['p-1'] })
    expect(await screen.findByText('Draft purchase request created')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/purchase-requests'))
  })

  it('offers no selection at all to someone who cannot ask for purchases', async () => {
    baseMocks()
    renderWithProviders(<PartsPage />, { route: '/parts?tab=low', path: PATHS, session: READER })

    await screen.findAllByTestId('part-row')
    expect(screen.queryByRole('checkbox', { name: 'Select 608ZZ bearing' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Create purchase requests' })).not.toBeInTheDocument()
  })
})
