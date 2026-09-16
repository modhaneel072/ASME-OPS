import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Session } from '@/api/contracts/session'
import type { WorkOrderPart } from '@/api/contracts/workOrderParts'
import { ADMIN_SESSION, memberSession, mockApi, renderWithProviders } from '@/test/render'
import { makeDetail, type HandlerInit } from './testData'
import { PartsReadinessBadge, WorkOrderPartsSection } from './WorkOrderPartsSection'

afterEach(() => vi.restoreAllMocks())

const WORK_ORDER = makeDetail()

const BOLT = {
  id: 'part-1',
  name: 'M5 hex bolt',
  sku: 'BOLT-M5',
  unit: 'each',
  stock_state: 'ok',
  totals: { on_hand: 40, reserved: 4, available: 36, ordered: 0 },
}

const LAB = { id: 'loc-1', name: 'Robotics Lab' }

function makeLine(overrides: Partial<WorkOrderPart> = {}): WorkOrderPart {
  return {
    id: 'wop-1',
    part: BOLT,
    location: LAB,
    quantity_planned: 6,
    quantity_reserved: 0,
    quantity_issued: 0,
    quantity_returned: 0,
    readiness: 'assigned',
    note: null,
    created_at: '2026-09-10T12:00:00Z',
    ...overrides,
  }
}

function partsPayload(items: WorkOrderPart[], readiness = 'assigned', outstanding = 0) {
  return { items, work_order_parts: items, readiness_summary: items.length ? readiness : 'none', parts_outstanding: outstanding }
}

/** ADMIN_SESSION holds `work_order.edit` and `work_order.log_time` but no inventory keys. */
function sessionWith(...keys: string[]): Session {
  return { ...ADMIN_SESSION, permissions: { ...ADMIN_SESSION.permissions, ...Object.fromEntries(keys.map((key) => [key, ['chapter']])) } }
}

const PART_LIST = { items: [{ ...BOLT, default_location: LAB, is_active: true }], next_cursor: null, total: 1 }
const PART_INVENTORY = {
  balances: [{ location: LAB, on_hand: 40, reserved: 4, available: 36 }],
  totals: BOLT.totals,
}

function renderSection(handlers: Parameters<typeof mockApi>[0], session: Session = ADMIN_SESSION) {
  const api = mockApi(handlers)
  const view = renderWithProviders(<WorkOrderPartsSection workOrder={WORK_ORDER} />, { route: '/work-orders/wo-1', session })
  return { ...view, ...api }
}

async function openRowMenu(user: ReturnType<typeof renderWithProviders>['user'], partName = BOLT.name) {
  await user.click(await screen.findByRole('button', { name: `Actions for ${partName}` }))
  return screen.findByRole('menu')
}

describe('Work-order parts section', () => {
  it('lists each line with its quantities, readiness and a stock-state warning', async () => {
    const line = makeLine({
      quantity_planned: 6,
      quantity_reserved: 2,
      quantity_issued: 1,
      readiness: 'reserved',
      part: { ...BOLT, stock_state: 'low', totals: { on_hand: 3, reserved: 2, available: 1, ordered: 0 } },
    })
    renderSection({ 'GET /work-orders/:id/parts': partsPayload([line], 'reserved', 1) })

    const table = await screen.findByRole('table', { name: 'Parts' })
    const row = within(table).getAllByRole('row')[1]
    expect(within(row).getByText('M5 hex bolt')).toBeInTheDocument()
    expect(within(row).getByText('BOLT-M5')).toBeInTheDocument()
    expect(within(row).getByText('Robotics Lab')).toBeInTheDocument()
    expect(within(row).getByText('Low stock')).toBeInTheDocument()
    expect(within(row).getAllByText('Reserved').length).toBeGreaterThan(0)
    const cells = within(row).getAllByRole('cell')
    expect(cells[2]).toHaveTextContent('6')
    expect(cells[3]).toHaveTextContent('2')
    expect(cells[4]).toHaveTextContent('1')
    expect(cells[5]).toHaveTextContent('0')
    // planned 6 - issued 1 = 5 still needed, 2 already held, only 1 available.
    expect(within(row).getByText(/Short by 2 each/)).toBeInTheDocument()
    expect(screen.getByText('1 line still reserved')).toBeInTheDocument()
  })

  it('shows the loading skeleton, then an error state with retry', async () => {
    let fail = true
    const { user } = renderSection({
      'GET /work-orders/:id/parts': () => (fail ? { __error: { status: 500, code: 'server_error', error: 'Inventory is offline.' } } : partsPayload([makeLine()])),
    })
    expect(screen.getByLabelText('Loading')).toBeInTheDocument()
    expect(await screen.findByText('Could not load the parts')).toBeInTheDocument()
    expect(screen.getByText('Inventory is offline.')).toBeInTheDocument()
    fail = false
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('table', { name: 'Parts' })).toBeInTheDocument()
  })

  it('offers the empty state with Add part to an editor', async () => {
    renderSection({ 'GET /work-orders/:id/parts': partsPayload([]) })
    expect(await screen.findByText('No parts planned')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Add part' }).length).toBeGreaterThan(0)
  })

  it('hides every action from a member who may neither edit nor work the order', async () => {
    renderSection({ 'GET /work-orders/:id/parts': partsPayload([makeLine({ quantity_reserved: 2 })], 'reserved', 1) }, memberSession())
    await screen.findByRole('table', { name: 'Parts' })
    expect(screen.queryByRole('button', { name: 'Add part' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Release all' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: `Actions for ${BOLT.name}` })).not.toBeInTheDocument()
  })

  it('hides kit and stage without inventory.manage and offers them with it', async () => {
    const handlers = { 'GET /work-orders/:id/parts': partsPayload([makeLine()]) }
    const first = renderSection(handlers)
    const menu = await openRowMenu(first.user)
    expect(within(menu).getByRole('menuitem', { name: 'Reserve…' })).toBeInTheDocument()
    expect(within(menu).getByRole('menuitem', { name: 'Issue…' })).toBeInTheDocument()
    expect(within(menu).queryByRole('menuitem', { name: 'Mark kitted' })).not.toBeInTheDocument()
    expect(within(menu).queryByRole('menuitem', { name: 'Mark staged' })).not.toBeInTheDocument()
    first.unmount()
    vi.restoreAllMocks()

    const second = renderSection(handlers, sessionWith('inventory.manage', 'inventory.read'))
    const managerMenu = await openRowMenu(second.user)
    expect(within(managerMenu).getByRole('menuitem', { name: 'Mark kitted' })).toBeInTheDocument()
    expect(within(managerMenu).getByRole('menuitem', { name: 'Mark staged' })).toBeInTheDocument()
  })

  it('adds a part through the dialog and posts the picked location and quantity', async () => {
    const line = makeLine()
    const { user, calls } = renderSection({
      'GET /work-orders/:id/parts': partsPayload([]),
      'GET /parts': PART_LIST,
      'GET /parts/:id/inventory': PART_INVENTORY,
      'POST /work-orders/:id/parts': partsPayload([line]),
    })
    await user.click((await screen.findAllByRole('button', { name: 'Add part' }))[0])
    const dialog = await screen.findByRole('dialog', { name: 'Add a part to #12' })

    // The combobox list renders in a portal, so it lives outside the dialog node.
    await user.click(within(dialog).getByRole('combobox', { name: 'Part' }))
    await user.click(await screen.findByRole('option', { name: /M5 hex bolt/ }))
    await waitFor(() => expect(within(dialog).getByLabelText(/Location/)).toHaveValue('loc-1'))

    const quantity = within(dialog).getByLabelText(/Quantity planned/)
    await user.clear(quantity)
    await user.type(quantity, '6')
    await user.type(within(dialog).getByLabelText('Note'), 'Front hub')
    await user.click(within(dialog).getByRole('button', { name: 'Add part' }))

    await waitFor(() => expect(calls.find((c) => c.method === 'POST' && c.url === '/api/v1/work-orders/wo-1/parts')).toBeTruthy())
    expect(calls.find((c) => c.method === 'POST' && c.url === '/api/v1/work-orders/wo-1/parts')?.body).toEqual({
      part_id: 'part-1',
      location_id: 'loc-1',
      quantity_planned: 6,
      note: 'Front hub',
    })
    expect(await screen.findByText('M5 hex bolt added to #12')).toBeInTheDocument()
  })

  it('refuses an add without a part or a quantity before calling the API', async () => {
    const { user, calls } = renderSection({
      'GET /work-orders/:id/parts': partsPayload([]),
      'GET /parts': PART_LIST,
      'GET /parts/:id/inventory': PART_INVENTORY,
    })
    await user.click((await screen.findAllByRole('button', { name: 'Add part' }))[0])
    const dialog = await screen.findByRole('dialog', { name: 'Add a part to #12' })
    await user.clear(within(dialog).getByLabelText(/Quantity planned/))
    await user.click(within(dialog).getByRole('button', { name: 'Add part' }))
    expect(await within(dialog).findByText('Choose a part.')).toBeInTheDocument()
    expect(await within(dialog).findByText('Enter how many are needed.')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
  })

  it('reserves the remaining need and posts the quantity', async () => {
    const line = makeLine({ quantity_planned: 6, quantity_reserved: 2 })
    const { user, calls } = renderSection({
      'GET /work-orders/:id/parts': partsPayload([line], 'reserved', 1),
      'POST /work-orders/:id/parts/:lineId/reserve': partsPayload([{ ...line, quantity_reserved: 6 }], 'reserved', 1),
    })
    const menu = await openRowMenu(user)
    await user.click(within(menu).getByRole('menuitem', { name: 'Reserve…' }))
    const dialog = await screen.findByRole('dialog', { name: 'Reserve M5 hex bolt' })
    // planned 6 - reserved 2 = 4 still reservable, prefilled.
    expect(within(dialog).getByLabelText(/Quantity/)).toHaveValue('4')
    expect(within(dialog).getByText(/At most 4 each can still be reserved/)).toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Reserve' }))

    await waitFor(() => expect(calls.find((c) => c.url.endsWith('/reserve'))).toBeTruthy())
    expect(calls.find((c) => c.url.endsWith('/reserve'))?.body).toEqual({ quantity: 4 })
    expect(await screen.findByText('M5 hex bolt reserved')).toBeInTheDocument()
  })

  it('shows the server field error when an issue runs out of stock', async () => {
    const line = makeLine({ quantity_planned: 6 })
    const { user } = renderSection({
      'GET /work-orders/:id/parts': partsPayload([line]),
      'POST /work-orders/:id/parts/:lineId/issue': {
        __error: { status: 400, code: 'validation', error: 'Validation failed.', errors: { quantity: 'Only 1 each is on hand.' } },
      },
    })
    const menu = await openRowMenu(user)
    await user.click(within(menu).getByRole('menuitem', { name: 'Issue…' }))
    const dialog = await screen.findByRole('dialog', { name: 'Issue M5 hex bolt' })
    await user.click(within(dialog).getByRole('button', { name: 'Issue' }))
    expect(await within(dialog).findByText('Only 1 each is on hand.')).toBeInTheDocument()
  })

  it('posts the return quantity for an issued line', async () => {
    const line = makeLine({ quantity_planned: 6, quantity_issued: 6, readiness: 'issued' })
    const { user, calls } = renderSection({
      'GET /work-orders/:id/parts': partsPayload([line], 'issued'),
      'POST /work-orders/:id/parts/:lineId/return': partsPayload([{ ...line, quantity_returned: 2 }], 'issued'),
    })
    const menu = await openRowMenu(user)
    await user.click(within(menu).getByRole('menuitem', { name: 'Return…' }))
    const dialog = await screen.findByRole('dialog', { name: 'Return M5 hex bolt' })
    const quantity = within(dialog).getByLabelText(/Quantity/)
    await user.clear(quantity)
    await user.type(quantity, '2')
    await user.click(within(dialog).getByRole('button', { name: 'Return' }))
    await waitFor(() => expect(calls.find((c) => c.url.endsWith('/return'))?.body).toEqual({ quantity: 2 }))
  })

  it('edits the planned quantity and surfaces the issued-quantity rule from the server', async () => {
    const line = makeLine({ quantity_planned: 6, quantity_issued: 4 })
    const { user, calls } = renderSection({
      'GET /work-orders/:id/parts': partsPayload([line]),
      'PATCH /work-orders/:id/parts/:lineId': ({ body }: HandlerInit) =>
        (body as { quantity_planned: number }).quantity_planned < 4
          ? { __error: { status: 400, code: 'validation', error: 'Validation failed.', errors: { quantity_planned: 'At least 4 has already been issued.' } } }
          : partsPayload([{ ...line, quantity_planned: (body as { quantity_planned: number }).quantity_planned }]),
    })
    const menu = await openRowMenu(user)
    await user.click(within(menu).getByRole('menuitem', { name: 'Edit planned quantity' }))
    const dialog = await screen.findByRole('dialog', { name: 'Edit M5 hex bolt' })
    const quantity = within(dialog).getByLabelText(/Quantity planned/)
    await user.clear(quantity)
    await user.type(quantity, '2')
    await user.click(within(dialog).getByRole('button', { name: 'Save part' }))
    expect(await within(dialog).findByText('At least 4 has already been issued.')).toBeInTheDocument()

    await user.clear(quantity)
    await user.type(quantity, '8')
    await user.click(within(dialog).getByRole('button', { name: 'Save part' }))
    await waitFor(() => expect(calls.filter((c) => c.method === 'PATCH').at(-1)?.body).toEqual({ quantity_planned: 8, note: null }))
  })

  it('removes an untouched line and disables Remove once stock is held', async () => {
    const clean = makeLine()
    const { user, calls } = renderSection({
      'GET /work-orders/:id/parts': partsPayload([clean]),
      'DELETE /work-orders/:id/parts/:lineId': partsPayload([]),
    })
    const menu = await openRowMenu(user)
    await user.click(within(menu).getByRole('menuitem', { name: 'Remove part' }))
    await user.click(within(await screen.findByRole('dialog', { name: 'Remove M5 hex bolt?' })).getByRole('button', { name: 'Remove part' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.url === '/api/v1/work-orders/wo-1/parts/wop-1')).toBe(true))
    expect(await screen.findByText('No parts planned')).toBeInTheDocument()
  })

  it('disables Remove while something is reserved', async () => {
    const { user } = renderSection({ 'GET /work-orders/:id/parts': partsPayload([makeLine({ quantity_reserved: 2 })], 'reserved', 1) })
    const menu = await openRowMenu(user)
    expect(within(menu).getByRole('menuitem', { name: 'Remove part' })).toHaveAttribute('aria-disabled', 'true')
  })

  it('releases every reservation from the section header', async () => {
    const line = makeLine({ quantity_reserved: 3, readiness: 'reserved' })
    const { user, calls } = renderSection({
      'GET /work-orders/:id/parts': partsPayload([line], 'reserved', 1),
      'POST /work-orders/:id/parts/release-all': partsPayload([{ ...line, quantity_reserved: 0, readiness: 'assigned' }]),
    })
    await user.click(await screen.findByRole('button', { name: 'Release all' }))
    await waitFor(() => expect(calls.some((c) => c.url === '/api/v1/work-orders/wo-1/parts/release-all')).toBe(true))
    expect(await screen.findByText('Reservations released')).toBeInTheDocument()
  })

  it('warns when a line has no location and blocks the stock actions', async () => {
    const { user } = renderSection({ 'GET /work-orders/:id/parts': partsPayload([makeLine({ location: null })]) })
    expect(await screen.findByText(/Choose a location before reserving or issuing/)).toBeInTheDocument()
    const menu = await openRowMenu(user)
    expect(within(menu).getByRole('menuitem', { name: 'Reserve…' })).toHaveAttribute('aria-disabled', 'true')
    expect(within(menu).getByRole('menuitem', { name: 'Issue…' })).toHaveAttribute('aria-disabled', 'true')
  })
})

describe('PartsReadinessBadge', () => {
  it('shows the least advanced readiness across the lines', async () => {
    mockApi({ 'GET /work-orders/:id/parts': partsPayload([makeLine({ readiness: 'staged' })], 'staged') })
    renderWithProviders(<PartsReadinessBadge workOrderId="wo-1" />, { route: '/work-orders/wo-1' })
    expect(await screen.findByText('Parts: Staged')).toBeInTheDocument()
  })

  it('renders nothing when the work order has no parts', async () => {
    mockApi({ 'GET /work-orders/:id/parts': partsPayload([]) })
    const { container } = renderWithProviders(<PartsReadinessBadge workOrderId="wo-1" />, { route: '/work-orders/wo-1' })
    await waitFor(() => expect(container).toBeEmptyDOMElement())
  })
})
