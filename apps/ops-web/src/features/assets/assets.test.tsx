import { screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { memberSession, mockApi, renderWithProviders } from '@/test/render'
import AssetsPage from '.'

/* Fixtures ------------------------------------------------------------------- */

const LOCATION = { id: 'loc-1', name: 'Robotics Lab' }
const PROJECT = { id: 'proj-1', name: 'Crater Cruncher Rover', code: 'CCR', visibility: 'chapter' as const }
const TEAM = { id: 'team-1', name: 'Robotic Arm' }
const OWNER = { id: 3, name: 'Mo Member', email: 'mo@uiowa.edu', avatar_url: null }
const PRINTER_TYPE = { id: 'type-1', name: 'Printer', color: '#0878d1', icon: 'printer', asset_count: 1 }
const VEHICLE_TYPE = { id: 'type-2', name: 'Vehicle', color: '#00a878', icon: 'car', asset_count: 1 }

function asset(overrides: Record<string, unknown> = {}) {
  return {
    id: 'asset-1',
    name: '3D Printer 01',
    code: 'PRN-01',
    description: 'Prusa MK4 on the back bench',
    parent_id: null,
    project: PROJECT,
    location: LOCATION,
    team: TEAM,
    owner: OWNER,
    manufacturer: 'Prusa',
    model: 'MK4',
    serial_number: 'SN-123',
    purchase_date: '2025-08-15',
    purchase_cost: 1099.5,
    warranty_end: '2027-08-15',
    criticality: 'high',
    status: 'online',
    qr_code: null,
    custom_fields: { nozzle_mm: 0.4 },
    is_active: true,
    types: [{ id: PRINTER_TYPE.id, name: PRINTER_TYPE.name, color: PRINTER_TYPE.color }],
    child_count: 0,
    open_work_order_count: 2,
    created_at: '2026-09-01T10:00:00Z',
    updated_at: '2026-09-08T12:00:00Z',
    ...overrides,
  }
}

const ROVER = asset({ id: 'asset-2', name: 'Crater Cruncher Rover', code: 'CCR-01', criticality: 'none', status: 'offline_planned', types: [{ id: VEHICLE_TYPE.id, name: 'Vehicle', color: '#00a878' }], open_work_order_count: 0 })
const ARM = asset({ id: 'asset-3', name: 'Robotic Arm', code: 'CCR-ARM', parent_id: 'asset-2', criticality: 'medium', types: [], open_work_order_count: 1 })
const GRIPPER = asset({ id: 'asset-4', name: 'End Effector', code: 'CCR-ARM-EE', parent_id: 'asset-3', criticality: 'low', status: 'do_not_track', types: [], open_work_order_count: 0 })

const list = (items: unknown[]) => ({ items, next_cursor: null, total: items.length })

function baseHandlers(extra: Record<string, unknown> = {}) {
  return {
    'GET /asset-types': list([PRINTER_TYPE, VEHICLE_TYPE]),
    'GET /projects': list([{ ...PRINTER_TYPE, ...PROJECT, status: 'active', visibility: 'chapter' }]),
    'GET /locations': list([{ ...LOCATION, description: null, parent_id: null, building: null, room: null, is_default: false, path: ['Robotics Lab'], asset_count: 3, open_work_order_count: 0, created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z' }, { id: 'loc-default', name: 'General', description: null, parent_id: null, building: null, room: null, is_default: true, path: ['General'], asset_count: 0, open_work_order_count: 0, created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z' }]),
    'GET /teams': list([{ ...TEAM, leads: [], member_count: 4 }]),
    'GET /users': list([{ id: 'm-3', user: OWNER, role: { id: 'r-5', name: 'Full Member', system_key: 'full_member' }, status: 'active', teams: [] }]),
    'GET /work-orders': list([{ id: 'wo-1', number: 41, title: 'Replace nozzle', status: 'open', priority: 'high', due_at: '2026-09-12T17:00:00Z', is_overdue: false, assignees: [] }]),
    'GET /assets/:assetId/history': {
      items: [
        { kind: 'status', id: 'h-1', from_status: 'offline_unplanned', to_status: 'online', downtime_type: null, downtime_reason: null, note: 'Back in service', started_at: '2026-09-08T12:00:00Z', ended_at: null, changed_by: OWNER, work_order_id: null, at: '2026-09-08T12:00:00Z' },
        { kind: 'status', id: 'h-0', from_status: 'online', to_status: 'offline_unplanned', downtime_type: 'unplanned', downtime_reason: 'Blown fuse', note: null, started_at: '2026-09-07T12:00:00Z', ended_at: '2026-09-08T12:00:00Z', changed_by: OWNER, work_order_id: null, at: '2026-09-07T12:00:00Z' },
        { kind: 'work_order', id: 'wo-1', number: 41, title: 'Replace nozzle', status: 'open', at: '2026-09-06T12:00:00Z' },
        { kind: 'audit', id: 'a-1', event_type: 'asset.created', entity_type: 'asset', entity_id: 'asset-1', actor: OWNER, summary: 'Created asset 3D Printer 01', before: null, after: {}, metadata: null, occurred_at: '2026-09-01T10:00:00Z', at: '2026-09-01T10:00:00Z' },
      ],
    },
    ...extra,
  }
}

afterEach(() => {
  vi.restoreAllMocks()
})

/* List views ------------------------------------------------------------------ */

describe('Assets list', () => {
  it('renders panel rows with status, criticality, location, types and open work', async () => {
    mockApi(baseHandlers({ 'GET /assets': list([asset(), ROVER]) }))
    renderWithProviders(<AssetsPage />, { route: '/assets', path: ['/assets', '/assets/:assetId'] })
    const rows = await screen.findAllByTestId('asset-row')
    expect(rows).toHaveLength(2)
    const printer = within(rows[0])
    expect(printer.getByText('3D Printer 01')).toBeInTheDocument()
    expect(printer.getByText('PRN-01')).toBeInTheDocument()
    expect(printer.getByText('Online')).toBeInTheDocument()
    expect(printer.getByText('High criticality')).toBeInTheDocument()
    expect(printer.getByText('Robotics Lab')).toBeInTheDocument()
    expect(printer.getByText('Printer')).toBeInTheDocument()
    expect(printer.getByText('2 open work')).toBeInTheDocument()
    // criticality "none" is hidden in lists
    expect(within(rows[1]).queryByText(/criticality/i)).not.toBeInTheDocument()
    expect(within(rows[1]).getByText('Offline (planned)')).toBeInTheDocument()
    expect(screen.getByText('2 assets')).toBeInTheDocument()
  })

  it('shows the empty state with a create action for managers', async () => {
    mockApi(baseHandlers({ 'GET /assets': list([]) }))
    renderWithProviders(<AssetsPage />, { route: '/assets', path: ['/assets', '/assets/:assetId'] })
    expect(await screen.findByText('No assets yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add the first asset' })).toBeInTheDocument()
  })

  it('shows a no-results state with a clear action when filters are active', async () => {
    mockApi(baseHandlers({ 'GET /assets': list([]) }))
    renderWithProviders(<AssetsPage />, { route: '/assets?filter[status]=retired', path: ['/assets', '/assets/:assetId'] })
    expect(await screen.findByText('No assets match')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Clear search and filters' })).toBeInTheDocument()
  })

  it('passes URL filters and search through to the API', async () => {
    const { calls } = mockApi(baseHandlers({ 'GET /assets': list([asset()]) }))
    renderWithProviders(<AssetsPage />, { route: '/assets?filter[location]=loc-1&filter[status]=online,retired&sort=-updated_at&q=prusa', path: ['/assets', '/assets/:assetId'] })
    await screen.findAllByTestId('asset-row')
    const request = calls.find((c) => c.url.startsWith('/api/v1/assets?'))
    expect(request).toBeDefined()
    const url = new URL(`http://test.local${request!.url}`)
    expect(url.searchParams.get('filter[location]')).toBe('loc-1')
    expect(url.searchParams.get('filter[status]')).toBe('online,retired')
    expect(url.searchParams.get('sort')).toBe('-updated_at')
    expect(url.searchParams.get('q')).toBe('prusa')
    // the Location chip reflects the URL
    expect(screen.getByRole('button', { name: /Location.*Robotics Lab/ })).toBeInTheDocument()
  })

  it('shows an inline error with retry when the list fails', async () => {
    let attempts = 0
    mockApi(
      baseHandlers({
        'GET /assets': () => {
          attempts += 1
          return attempts === 1 ? { __error: { status: 500, code: 'server_error', error: 'Database unavailable' } } : list([asset()])
        },
      }),
    )
    const { user } = renderWithProviders(<AssetsPage />, { route: '/assets', path: ['/assets', '/assets/:assetId'] })
    expect(await screen.findByText('Assets could not be loaded')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findAllByTestId('asset-row')).toHaveLength(1)
  })

  it('hides every manage control for a member session', async () => {
    mockApi(baseHandlers({ 'GET /assets': list([]), 'GET /assets/:assetId': { asset: asset() } }))
    renderWithProviders(<AssetsPage />, { route: '/assets/asset-1', path: ['/assets', '/assets/:assetId'], session: memberSession() })
    expect(await screen.findByRole('heading', { level: 2, name: /3D Printer 01/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'New Asset' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Change status' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add the first asset' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add sub-asset' })).not.toBeInTheDocument()
  })

  it('opens the create pane with "n" only when the session may manage assets', async () => {
    mockApi(baseHandlers({ 'GET /assets': list([asset()]) }))
    const { user } = renderWithProviders(<AssetsPage />, { route: '/assets', path: ['/assets', '/assets/:assetId'], session: memberSession() })
    await screen.findAllByTestId('asset-row')
    await user.keyboard('n')
    expect(screen.queryByRole('dialog', { name: 'New Asset' })).not.toBeInTheDocument()
  })
})

/* Table view ------------------------------------------------------------------ */

describe('Assets table view', () => {
  it('renders the columns and maps header sorting to the sort param', async () => {
    const { calls } = mockApi(baseHandlers({ 'GET /assets': list([asset(), ROVER]) }))
    const { user } = renderWithProviders(<AssetsPage />, { route: '/assets?view=table', path: ['/assets', '/assets/:assetId'] })
    const table = await screen.findByRole('table')
    for (const header of ['Name', 'Code', 'Status', 'Criticality', 'Types', 'Location', 'Project', 'Team', 'Open work', 'Updated']) {
      expect(within(table).getByRole('columnheader', { name: new RegExp(`^${header}`) })).toBeInTheDocument()
    }
    expect(within(table).getByText('Crater Cruncher Rover', { selector: 'span' })).toBeInTheDocument()
    await user.click(within(table).getByRole('button', { name: /^Status/ }))
    await waitFor(() => {
      const sorted = calls.filter((c) => c.url.startsWith('/api/v1/assets?')).map((c) => new URL(`http://test.local${c.url}`).searchParams.get('sort'))
      expect(sorted).toContain('status')
    })
    expect(within(table).getByRole('columnheader', { name: /^Status/ })).toHaveAttribute('aria-sort', 'ascending')
    // Code is not sortable
    expect(within(table).queryByRole('button', { name: /^Code/ })).not.toBeInTheDocument()
  })

  it('navigates to the asset when a row is clicked and keeps the view', async () => {
    mockApi(baseHandlers({ 'GET /assets': list([asset()]), 'GET /assets/:assetId': { asset: asset() } }))
    const { user } = renderWithProviders(<AssetsPage />, { route: '/assets?view=table', path: ['/assets', '/assets/:assetId'] })
    await user.click(await screen.findByRole('row', { name: 'Open 3D Printer 01' }))
    expect(await screen.findByRole('heading', { level: 2, name: /3D Printer 01/ })).toBeInTheDocument()
    expect(screen.getByRole('table')).toBeInTheDocument()
  })
})

/* Hierarchy view ------------------------------------------------------------- */

describe('Assets hierarchy view', () => {
  const tree = () => ({
    items: [
      { ...ROVER, children: [{ ...ARM, children: [{ ...GRIPPER, children: [] }] }] },
      { ...asset(), children: [] },
    ],
    next_cursor: null,
    total: 4,
  })

  it('requests the hierarchy view and renders nested rows with levels, status text and toggles', async () => {
    const { calls } = mockApi(baseHandlers({ 'GET /assets': ({ url }: { url: URL }) => (url.searchParams.get('view') === 'hierarchy' ? tree() : list([])) }))
    renderWithProviders(<AssetsPage />, { route: '/assets?view=hierarchy', path: ['/assets', '/assets/:assetId'] })
    const treeEl = await screen.findByRole('tree', { name: 'Asset hierarchy' })
    const items = within(treeEl).getAllByRole('treeitem')
    expect(items.map((el) => el.getAttribute('aria-level'))).toEqual(['1', '2', '3', '1'])
    expect(within(items[0]).getByText('Crater Cruncher Rover')).toBeInTheDocument()
    expect(within(items[0]).getByText('CCR-01')).toBeInTheDocument()
    expect(within(items[0]).getByText('Offline (planned)')).toBeInTheDocument()
    expect(within(items[0]).getByRole('button', { name: 'Collapse Crater Cruncher Rover' })).toHaveAttribute('aria-expanded', 'true')
    expect(items[2]).not.toHaveAttribute('aria-expanded')
    expect(calls.some((c) => c.url.includes('view=hierarchy'))).toBe(true)
    // the paged list is not fetched in hierarchy mode
    expect(calls.filter((c) => c.url.startsWith('/api/v1/assets?') && !c.url.includes('view=hierarchy'))).toHaveLength(0)
  })

  it('supports arrow-key navigation, collapse/expand and Enter to open', async () => {
    mockApi(baseHandlers({ 'GET /assets': ({ url }: { url: URL }) => (url.searchParams.get('view') === 'hierarchy' ? tree() : list([])), 'GET /assets/:assetId': { asset: ARM } }))
    const { user } = renderWithProviders(<AssetsPage />, { route: '/assets?view=hierarchy', path: ['/assets', '/assets/:assetId'] })
    const treeEl = await screen.findByRole('tree')
    const first = within(treeEl).getAllByRole('treeitem')[0]
    first.focus()
    expect(first).toHaveFocus()

    await user.keyboard('{ArrowLeft}')
    expect(first).toHaveAttribute('aria-expanded', 'false')
    expect(within(treeEl).getAllByRole('treeitem')).toHaveLength(2)

    await user.keyboard('{ArrowRight}')
    expect(first).toHaveAttribute('aria-expanded', 'true')
    expect(within(treeEl).getAllByRole('treeitem')).toHaveLength(4)

    await user.keyboard('{ArrowDown}')
    const arm = within(treeEl).getAllByRole('treeitem')[1]
    expect(arm).toHaveFocus()
    expect(within(arm).getByText('Robotic Arm')).toBeInTheDocument()

    await user.keyboard('{ArrowDown}{ArrowLeft}')
    // ArrowLeft on a leaf moves focus to its parent
    expect(arm).toHaveFocus()

    await user.keyboard('{ArrowUp}')
    expect(first).toHaveFocus()

    await user.keyboard('{ArrowDown}{Enter}')
    expect(await screen.findByRole('heading', { level: 2, name: /Robotic Arm/ })).toBeInTheDocument()
    expect(within(treeEl).getAllByRole('treeitem')[1]).toHaveAttribute('aria-selected', 'true')
  })

  it('applies status filters and search to the tree client-side, keeping ancestors', async () => {
    mockApi(baseHandlers({ 'GET /assets': ({ url }: { url: URL }) => (url.searchParams.get('view') === 'hierarchy' ? tree() : list([])) }))
    renderWithProviders(<AssetsPage />, { route: '/assets?view=hierarchy&filter[status]=do_not_track', path: ['/assets', '/assets/:assetId'] })
    const treeEl = await screen.findByRole('tree')
    const items = within(treeEl).getAllByRole('treeitem')
    expect(items).toHaveLength(3)
    expect(within(items[0]).getByText('Crater Cruncher Rover')).toBeInTheDocument()
    expect(within(items[1]).getByText('Robotic Arm')).toBeInTheDocument()
    expect(within(items[2]).getByText('End Effector')).toBeInTheDocument()
    expect(within(treeEl).queryByText('3D Printer 01')).not.toBeInTheDocument()
  })
})

/* Detail ----------------------------------------------------------------------- */

describe('Asset detail', () => {
  it('renders header, details, hierarchy, open work and history', async () => {
    mockApi(
      baseHandlers({
        'GET /assets': ({ url }: { url: URL }) => (url.searchParams.get('filter[parent]') === 'asset-2' ? list([ARM]) : list([asset(), ROVER])),
        'GET /assets/:assetId': ({ url }: { url: URL }) => ({ asset: url.pathname.endsWith('asset-2') ? ROVER : asset() }),
      }),
    )
    renderWithProviders(<AssetsPage />, { route: '/assets/asset-2', path: ['/assets', '/assets/:assetId'] })
    const heading = await screen.findByRole('heading', { level: 2, name: /Crater Cruncher Rover/ })
    expect(within(heading).getByText('Offline (planned)')).toBeInTheDocument()
    const details = screen.getByRole('region', { name: 'Details' }).parentElement!
    expect(within(details).getByRole('link', { name: 'Robotics Lab' })).toHaveAttribute('href', '/locations/loc-1')
    expect(within(details).getByRole('link', { name: 'Crater Cruncher Rover' })).toHaveAttribute('href', '/projects/proj-1')
    expect(within(details).getByText('Robotic Arm', { selector: 'dd' })).toBeInTheDocument()
    expect(within(details).getByText(/Aug 15, 2025 · \$1,099\.50/)).toBeInTheDocument()
    expect(within(details).getByText('nozzle_mm')).toBeInTheDocument()

    // sub-assets card
    const subAssets = await screen.findByRole('list', { name: 'Sub-assets' })
    expect(within(subAssets).getByRole('link', { name: /Robotic Arm/ })).toHaveAttribute('href', '/assets/asset-3')
    expect(screen.getByText('Hierarchy (1 sub-assets)')).toBeInTheDocument()

    // open work card
    const work = await screen.findByRole('list', { name: 'Open work orders' })
    expect(within(work).getByRole('link', { name: /#41.*Replace nozzle/ })).toHaveAttribute('href', '/work-orders/wo-1')

    // history
    expect(await screen.findByText('Back in service')).toBeInTheDocument()
    expect(screen.getByText(/Downtime: Unplanned — Blown fuse/)).toBeInTheDocument()
    expect(screen.getByText('Created asset 3D Printer 01')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: /#41.*Replace nozzle/ })).toHaveLength(2)
  })

  it('shows a not-found state for a missing asset', async () => {
    mockApi(baseHandlers({ 'GET /assets': list([]), 'GET /assets/:assetId': { __error: { status: 404, code: 'not_found', error: 'Not found' } } }))
    renderWithProviders(<AssetsPage />, { route: '/assets/nope', path: ['/assets', '/assets/:assetId'] })
    expect(await screen.findByText('Asset not found')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back to assets' })).toBeInTheDocument()
  })

  it('offers work-order navigation from the More menu', async () => {
    mockApi(baseHandlers({ 'GET /assets': list([asset()]), 'GET /assets/:assetId': { asset: asset() } }))
    const { user } = renderWithProviders(<AssetsPage />, { route: '/assets/asset-1', path: ['/assets', '/assets/:assetId', '/work-orders'] })
    await screen.findByRole('heading', { level: 2, name: /3D Printer 01/ })
    await user.click(screen.getByRole('button', { name: 'More actions' }))
    const menu = screen.getByRole('menu')
    expect(within(menu).getByRole('menuitem', { name: 'Add sub-asset' })).toBeInTheDocument()
    expect(within(menu).getByRole('menuitem', { name: 'New work order for this asset' })).toBeInTheDocument()
    expect(within(menu).getByRole('menuitem', { name: 'Go to work orders' })).toBeInTheDocument()
  })
})

/* Status change ----------------------------------------------------------------- */

describe('Change status', () => {
  it('posts status, downtime type, reason and note, then toasts', async () => {
    const { calls } = mockApi(
      baseHandlers({
        'GET /assets': list([asset()]),
        'GET /assets/:assetId': { asset: asset() },
        'POST /assets/:assetId/status': ({ body }: { body: unknown }) => ({
          asset: asset({ status: (body as { status: string }).status }),
          history: { id: 'h-9', from_status: 'online', to_status: (body as { status: string }).status, downtime_type: 'unplanned', downtime_reason: 'Tip burned out', note: null, started_at: '2026-09-09T00:00:00Z', ended_at: null, changed_by: OWNER, work_order_id: null },
        }),
      }),
    )
    const { user } = renderWithProviders(<AssetsPage />, { route: '/assets/asset-1', path: ['/assets', '/assets/:assetId'] })
    await screen.findByRole('heading', { level: 2, name: /3D Printer 01/ })
    await user.click(screen.getByRole('button', { name: 'Change status' }))
    const dialog = screen.getByRole('dialog', { name: /Change status of 3D Printer 01/ })
    expect(within(dialog).queryByRole('radiogroup', { name: 'Downtime type' })).not.toBeInTheDocument()
    await user.selectOptions(within(dialog).getByLabelText('Status'), 'offline_unplanned')
    const downtime = within(dialog).getByRole('radiogroup', { name: 'Downtime type' })
    expect(within(downtime).getByRole('radio', { name: 'Unplanned' })).toHaveAttribute('aria-checked', 'true')
    await user.click(within(downtime).getByRole('radio', { name: 'Planned' }))
    await user.type(within(dialog).getByLabelText('Downtime reason'), 'Tip burned out')
    await user.type(within(dialog).getByLabelText('Note'), 'Ordered a replacement')
    await user.click(within(dialog).getByRole('button', { name: 'Update status' }))

    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url === '/api/v1/assets/asset-1/status')).toBe(true))
    const post = calls.find((c) => c.method === 'POST' && c.url === '/api/v1/assets/asset-1/status')!
    expect(post.body).toEqual({ status: 'offline_unplanned', downtime_type: 'planned', downtime_reason: 'Tip burned out', note: 'Ordered a replacement' })
    expect(await screen.findByText('Status updated')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('dialog', { name: /Change status/ })).not.toBeInTheDocument())
  })

  it('maps server validation errors onto the dialog fields', async () => {
    mockApi(
      baseHandlers({
        'GET /assets': list([asset()]),
        'GET /assets/:assetId': { asset: asset() },
        'POST /assets/:assetId/status': { __error: { status: 400, code: 'validation', error: 'Please fix the highlighted fields.', errors: { downtime_reason: 'Keep it under 160 characters.' } } },
      }),
    )
    const { user } = renderWithProviders(<AssetsPage />, { route: '/assets/asset-1', path: ['/assets', '/assets/:assetId'] })
    await screen.findByRole('heading', { level: 2, name: /3D Printer 01/ })
    await user.click(screen.getByRole('button', { name: 'Change status' }))
    const dialog = screen.getByRole('dialog', { name: /Change status/ })
    await user.selectOptions(within(dialog).getByLabelText('Status'), 'offline_planned')
    await user.click(within(dialog).getByRole('button', { name: 'Update status' }))
    expect(await within(dialog).findByText('Keep it under 160 characters.')).toBeInTheDocument()
    expect(within(dialog).getByLabelText('Downtime reason')).toHaveAttribute('aria-invalid', 'true')
  })

  it('is available to a safety officer holding only asset.status.update', async () => {
    const safety = memberSession({ permissions: { ...memberSession().permissions, 'asset.status.update': ['chapter'] } })
    mockApi(baseHandlers({ 'GET /assets': list([asset()]), 'GET /assets/:assetId': { asset: asset() } }))
    renderWithProviders(<AssetsPage />, { route: '/assets/asset-1', path: ['/assets', '/assets/:assetId'], session: safety })
    await screen.findByRole('heading', { level: 2, name: /3D Printer 01/ })
    expect(screen.getByRole('button', { name: 'Change status' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
  })

  it('surfaces a 403 as a toast', async () => {
    mockApi(
      baseHandlers({
        'GET /assets': list([asset()]),
        'GET /assets/:assetId': { asset: asset() },
        'POST /assets/:assetId/status': { __error: { status: 403, code: 'forbidden', error: 'You cannot change the status of this asset.' } },
      }),
    )
    const { user } = renderWithProviders(<AssetsPage />, { route: '/assets/asset-1', path: ['/assets', '/assets/:assetId'] })
    await screen.findByRole('heading', { level: 2, name: /3D Printer 01/ })
    await user.click(screen.getByRole('button', { name: 'Change status' }))
    await user.selectOptions(screen.getByLabelText('Status'), 'retired')
    await user.click(screen.getByRole('button', { name: 'Update status' }))
    expect(await screen.findByText('Could not change status')).toBeInTheDocument()
    // toast description plus the inline alert inside the still-open dialog
    expect(screen.getAllByText('You cannot change the status of this asset.').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByRole('dialog', { name: /Change status/ })).toBeInTheDocument()
  })
})

/* Create / edit ---------------------------------------------------------------- */

describe('Create and edit', () => {
  it('opens the pane via ?pane=new, defaults the location, posts the body and navigates to the new asset', async () => {
    const created = asset({ id: 'asset-9', name: 'Soldering Station 01', code: 'SS-01', types: [], project: null, team: null, owner: null })
    const { calls } = mockApi(
      baseHandlers({
        'GET /assets': list([asset()]),
        'GET /assets/:assetId': { asset: created },
        'POST /assets': { asset: created },
      }),
    )
    const { user } = renderWithProviders(<AssetsPage />, { route: '/assets', path: ['/assets', '/assets/:assetId'] })
    await screen.findAllByTestId('asset-row')
    await user.click(screen.getByRole('button', { name: 'New Asset' }))
    const sheet = await screen.findByRole('dialog', { name: 'New Asset' })
    expect(sheet).toContainElement(document.activeElement as HTMLElement)

    // the default location is preselected once locations load
    await waitFor(() => expect(within(sheet).getByText('General')).toBeInTheDocument())

    await user.type(within(sheet).getByLabelText('Name'), 'Soldering Station 01')
    await user.type(within(sheet).getByLabelText('Code'), 'SS-01')
    await user.click(within(sheet).getByRole('radio', { name: 'Medium' }))
    await user.selectOptions(within(sheet).getByLabelText('Initial status'), 'offline_planned')
    await user.type(within(sheet).getByLabelText('Manufacturer'), 'Hakko')
    await user.type(within(sheet).getByLabelText('Purchase cost'), '249.99')
    await user.type(within(sheet).getByLabelText('Purchase date'), '2026-01-15')

    // pick a type through the combobox
    await user.click(within(sheet).getByRole('combobox', { name: 'Types' }))
    await user.click(await screen.findByRole('option', { name: /Printer/ }))

    await user.click(within(sheet).getByRole('button', { name: 'Create Asset' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url === '/api/v1/assets')).toBe(true))
    const post = calls.find((c) => c.method === 'POST' && c.url === '/api/v1/assets')!
    expect(post.body).toEqual({
      name: 'Soldering Station 01',
      code: 'SS-01',
      description: null,
      type_ids: ['type-1'],
      parent_id: null,
      project_id: null,
      location_id: 'loc-default',
      responsible_team_id: null,
      owner_user_id: null,
      manufacturer: 'Hakko',
      model: null,
      serial_number: null,
      purchase_date: '2026-01-15',
      purchase_cost: 249.99,
      warranty_end: null,
      criticality: 'medium',
      status: 'offline_planned',
    })
    expect(await screen.findByText('Asset created')).toBeInTheDocument()
    expect(await screen.findByRole('heading', { level: 2, name: /Soldering Station 01/ })).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: 'New Asset' })).not.toBeInTheDocument()
  })

  it('maps server validation errors (code uniqueness) onto the right field and keeps the entered data', async () => {
    mockApi(
      baseHandlers({
        'GET /assets': list([asset()]),
        'POST /assets': { __error: { status: 400, code: 'validation', error: 'Please fix the highlighted fields.', errors: { code: 'This code is already used by another asset.', owner_user_id: 'Choose an active member of this chapter.' } } },
      }),
    )
    const { user } = renderWithProviders(<AssetsPage />, { route: '/assets?pane=new', path: ['/assets', '/assets/:assetId'] })
    const sheet = await screen.findByRole('dialog', { name: 'New Asset' })
    await user.type(within(sheet).getByLabelText('Name'), 'Another Printer')
    await user.type(within(sheet).getByLabelText('Code'), 'PRN-01')
    await user.click(within(sheet).getByRole('button', { name: 'Create Asset' }))
    expect(await within(sheet).findByText('This code is already used by another asset.')).toBeInTheDocument()
    expect(within(sheet).getByText('Choose an active member of this chapter.')).toBeInTheDocument()
    expect(within(sheet).getByLabelText('Code')).toHaveAttribute('aria-invalid', 'true')
    expect(within(sheet).getByLabelText('Name')).toHaveValue('Another Printer')
    expect(sheet).toBeInTheDocument()
  })

  it('shows a client-side error before posting when the name is missing', async () => {
    const { calls } = mockApi(baseHandlers({ 'GET /assets': list([asset()]) }))
    const { user } = renderWithProviders(<AssetsPage />, { route: '/assets?pane=new', path: ['/assets', '/assets/:assetId'] })
    const sheet = await screen.findByRole('dialog', { name: 'New Asset' })
    await user.click(within(sheet).getByRole('button', { name: 'Create Asset' }))
    expect(await within(sheet).findByText('Give the asset a name.')).toBeInTheDocument()
    expect(calls.some((c) => c.method === 'POST')).toBe(false)
  })

  it('edits an existing asset with PATCH, omitting status, and prefills the fields', async () => {
    const { calls } = mockApi(
      baseHandlers({
        'GET /assets': list([asset(), ROVER]),
        'GET /assets/:assetId': { asset: asset() },
        'PATCH /assets/:assetId': ({ body }: { body: unknown }) => ({ asset: asset(body as Record<string, unknown>) }),
      }),
    )
    const { user } = renderWithProviders(<AssetsPage />, { route: '/assets/asset-1', path: ['/assets', '/assets/:assetId'] })
    await screen.findByRole('heading', { level: 2, name: /3D Printer 01/ })
    await user.click(screen.getByRole('button', { name: 'Edit' }))
    const sheet = await screen.findByRole('dialog', { name: 'Edit 3D Printer 01' })
    expect(within(sheet).getByLabelText('Name')).toHaveValue('3D Printer 01')
    expect(within(sheet).getByLabelText('Serial number')).toHaveValue('SN-123')
    expect(within(sheet).getByLabelText('Purchase cost')).toHaveValue('1099.5')
    expect(within(sheet).queryByLabelText('Initial status')).not.toBeInTheDocument()
    expect(within(sheet).getByRole('radio', { name: 'High' })).toHaveAttribute('aria-checked', 'true')
    // self is excluded from the parent picker
    await user.click(within(sheet).getByPlaceholderText('No parent (top level)'))
    const listbox = await screen.findByRole('listbox')
    expect(within(listbox).queryByRole('option', { name: /3D Printer 01/ })).not.toBeInTheDocument()
    expect(within(listbox).getByRole('option', { name: /Crater Cruncher Rover/ })).toBeInTheDocument()
    await user.keyboard('{Escape}')

    await user.clear(within(sheet).getByLabelText('Model'))
    await user.type(within(sheet).getByLabelText('Model'), 'MK4S')
    await user.click(within(sheet).getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH' && c.url === '/api/v1/assets/asset-1')).toBe(true))
    const patch = calls.find((c) => c.method === 'PATCH')!
    const body = patch.body as Record<string, unknown>
    expect(body.model).toBe('MK4S')
    expect(body.type_ids).toEqual(['type-1'])
    expect(body.owner_user_id).toBe(3)
    expect(body.purchase_cost).toBe(1099.5)
    expect(body).not.toHaveProperty('status')
    expect(await screen.findByText('Asset updated')).toBeInTheDocument()
  })

  it('creates an asset type inline and adds it to the selected types', async () => {
    const types: unknown[] = [PRINTER_TYPE, VEHICLE_TYPE]
    const { calls } = mockApi(
      baseHandlers({
        'GET /assets': list([asset()]),
        'GET /asset-types': () => list(types),
        'POST /asset-types': ({ body }: { body: unknown }) => {
          const created = { id: 'type-3', name: (body as { name: string }).name, color: (body as { color: string }).color, icon: 'box', asset_count: 0 }
          types.push(created)
          return { asset_type: created }
        },
      }),
    )
    const { user } = renderWithProviders(<AssetsPage />, { route: '/assets?pane=new', path: ['/assets', '/assets/:assetId'] })
    const sheet = await screen.findByRole('dialog', { name: 'New Asset' })
    await user.click(within(sheet).getByRole('button', { name: 'Create type' }))
    const dialog = await screen.findByRole('dialog', { name: 'New asset type' })
    await user.type(within(dialog).getByLabelText('Name'), 'Hand tool')
    await user.click(within(dialog).getByRole('button', { name: 'Use colour #00a878' }))
    await user.click(within(dialog).getByRole('button', { name: 'Create type' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url === '/api/v1/asset-types')).toBe(true))
    expect(calls.find((c) => c.method === 'POST' && c.url === '/api/v1/asset-types')!.body).toEqual({ name: 'Hand tool', color: '#00a878' })
    expect(await screen.findByText('Asset type created')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'New asset type' })).not.toBeInTheDocument())
    // the new type is tokenised in the form once the type list refetches
    await waitFor(() => expect(within(sheet).getByRole('button', { name: 'Remove Hand tool' })).toBeInTheDocument())
  })

  it('does not offer "Create type" to sessions without asset.manage', async () => {
    // A member cannot open the pane at all; assert through the split-button absence and direct URL.
    mockApi(baseHandlers({ 'GET /assets': list([asset()]) }))
    renderWithProviders(<AssetsPage />, { route: '/assets?pane=new', path: ['/assets', '/assets/:assetId'], session: memberSession() })
    const sheet = await screen.findByRole('dialog', { name: 'New Asset' })
    expect(within(sheet).queryByRole('button', { name: 'Create type' })).not.toBeInTheDocument()
  })

  it('prefills the parent when adding a sub-asset from the detail', async () => {
    mockApi(baseHandlers({ 'GET /assets': list([asset(), ROVER]), 'GET /assets/:assetId': { asset: ROVER } }))
    const { user } = renderWithProviders(<AssetsPage />, { route: '/assets/asset-2', path: ['/assets', '/assets/:assetId'] })
    await screen.findByRole('heading', { level: 2, name: /Crater Cruncher Rover/ })
    await user.click(screen.getByRole('button', { name: 'Add sub-asset' }))
    const sheet = await screen.findByRole('dialog', { name: 'New sub-asset' })
    // parent and the parent's project (which happens to share the rover's name) are both prefilled
    expect(within(sheet).getAllByText('Crater Cruncher Rover', { selector: 'span' })).toHaveLength(2)
    expect(within(sheet).queryByPlaceholderText('No parent (top level)')).not.toBeInTheDocument()
  })
})
