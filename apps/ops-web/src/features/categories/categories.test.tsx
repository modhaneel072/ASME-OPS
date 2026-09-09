import { screen, waitFor, within } from '@testing-library/react'
import { useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { memberSession, mockApi, renderWithProviders } from '@/test/render'
import CategoriesPage from './index'

const PATHS = ['/categories', '/categories/:categoryId']

const mechanical = {
  id: 'cat-1',
  name: 'Mechanical',
  color: '#0878d1',
  icon: 'wrench',
  description: 'Frames, drivetrain and mounts.',
  usage: { work_orders: 3 },
  created_at: '2026-09-01T14:00:00Z',
  updated_at: '2026-09-02T09:30:00Z',
  created_by: { id: 1, name: 'Ada Admin', email: 'ada@uiowa.edu', avatar_url: null },
}
const safety = {
  id: 'cat-2',
  name: 'Safety',
  color: '#d84a4a',
  icon: 'shield-alert',
  description: null,
  usage: { work_orders: 1 },
  created_at: '2026-09-01T14:05:00Z',
  updated_at: null,
  created_by: null,
}

function list(items: unknown[]) {
  return { items, next_cursor: null, total: items.length }
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{`${location.pathname}${location.search}`}</output>
}

function searchParam(url: string, key: string) {
  return new URL(url, 'http://test.local').searchParams.get(key)
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Categories list', () => {
  it('renders rows with usage counts and requests the default sort', async () => {
    const { calls } = mockApi({ 'GET /categories': list([mechanical, safety]) })
    renderWithProviders(<CategoriesPage />, { route: '/categories', path: PATHS })

    const rows = await screen.findAllByTestId('category-row')
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('Mechanical')
    expect(rows[0]).toHaveTextContent('3 work orders')
    expect(rows[1]).toHaveTextContent('1 work order')
    expect(screen.getByText('2 categories')).toBeInTheDocument()

    const request = calls.find((call) => call.method === 'GET' && call.url.startsWith('/api/v1/categories?'))
    expect(request).toBeDefined()
    expect(searchParam(request!.url, 'sort')).toBe('name')
    expect(searchParam(request!.url, 'q')).toBeNull()
  })

  it('shows the empty state with a create action for managers', async () => {
    mockApi({ 'GET /categories': list([]) })
    renderWithProviders(<CategoriesPage />, { route: '/categories', path: PATHS })

    expect(await screen.findByText('No categories yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add the first category' })).toBeInTheDocument()
  })

  it('shows a no-results state from the URL search and clears it', async () => {
    const { calls } = mockApi({
      'GET /categories': ({ url }: { url: URL }) => (url.searchParams.get('q') ? list([]) : list([mechanical])),
    })
    const { user } = renderWithProviders(<CategoriesPage />, { route: '/categories?q=zzz', path: PATHS })

    const empty = (await screen.findByText('No categories match')).closest('[role="status"]') as HTMLElement
    expect(screen.getByRole('searchbox', { name: 'Search' })).toHaveValue('zzz')
    await user.click(within(empty).getByRole('button', { name: 'Clear search' }))
    expect(await screen.findByTestId('category-row')).toHaveTextContent('Mechanical')
    expect(calls.some((call) => call.method === 'GET' && call.url.startsWith('/api/v1/categories?') && searchParam(call.url, 'q') === null)).toBe(true)
  })

  it('reads the sort from the URL and changes it through the view selector', async () => {
    const { calls } = mockApi({ 'GET /categories': list([mechanical, safety]) })
    const { user } = renderWithProviders(<CategoriesPage />, { route: '/categories?sort=-usage', path: PATHS })

    await screen.findAllByTestId('category-row')
    expect(searchParam(calls[0].url, 'sort')).toBe('-usage')

    await user.click(screen.getByRole('button', { name: 'Sort: Most used' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Newest' }))
    await waitFor(() => expect(calls.some((call) => call.method === 'GET' && searchParam(call.url, 'sort') === '-created_at')).toBe(true))
  })

  it('shows an inline error with a retry action when the list fails', async () => {
    let attempts = 0
    mockApi({
      'GET /categories': () => {
        attempts += 1
        return attempts === 1 ? { __error: { status: 500, code: 'server_error', error: 'Database unavailable.' } } : list([mechanical])
      },
    })
    const { user } = renderWithProviders(<CategoriesPage />, { route: '/categories', path: PATHS })

    expect(await screen.findByText('Categories could not be loaded')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByTestId('category-row')).toHaveTextContent('Mechanical')
  })
})

describe('Category detail', () => {
  it('deep links restore the selected category and the edit pane', async () => {
    mockApi({ 'GET /categories': list([mechanical, safety]), 'GET /categories/:id': { category: mechanical } })
    renderWithProviders(<CategoriesPage />, { route: '/categories/cat-1?pane=edit', path: PATHS })

    const sheet = await screen.findByRole('dialog', { name: 'Edit Mechanical' })
    expect(within(sheet).getByLabelText('Name')).toHaveValue('Mechanical')
    expect(within(sheet).getByLabelText('Hex value')).toHaveValue('#0878d1')
    expect(within(sheet).getByRole('radio', { name: 'Wrench' })).toBeChecked()
    expect(within(sheet).getByRole('radio', { name: 'Iowa blue' })).toBeChecked()
    expect(within(sheet).getByLabelText('Description')).toHaveValue('Frames, drivetrain and mounts.')
    expect(screen.getAllByTestId('category-row')).toHaveLength(2)
  })

  it('shows colour, icon, creator and usage with a link to the filtered work orders', async () => {
    mockApi({ 'GET /categories': list([mechanical]), 'GET /categories/:id': { category: mechanical } })
    renderWithProviders(<CategoriesPage />, { route: '/categories/cat-1', path: PATHS })

    expect(await screen.findByRole('heading', { level: 2, name: 'Mechanical' })).toBeInTheDocument()
    expect(screen.getByText('#0878d1')).toBeInTheDocument()
    expect(screen.getByText(/by Ada Admin/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Used by 3 work orders' })).toHaveAttribute('href', '/work-orders?filter[category]=cat-1')
  })

  it('"Use in New Work Order" navigates with the category query param', async () => {
    mockApi({ 'GET /categories': list([mechanical]), 'GET /categories/:id': { category: mechanical } })
    const { user } = renderWithProviders(
      <>
        <CategoriesPage />
        <LocationProbe />
      </>,
      { route: '/categories/cat-1', path: PATHS },
    )

    await user.click(await screen.findByRole('button', { name: 'Use in New Work Order' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/work-orders/new?category=cat-1')
  })

  it('hides manage controls for members but keeps the work-order action', async () => {
    mockApi({ 'GET /categories': list([mechanical]), 'GET /categories/:id': { category: mechanical } })
    const { user } = renderWithProviders(<CategoriesPage />, { route: '/categories/cat-1', path: PATHS, session: memberSession() })

    expect(await screen.findByRole('button', { name: 'Use in New Work Order' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'New Category' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'More actions' })).not.toBeInTheDocument()

    await user.keyboard('n')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('ignores ?pane=new for sessions without category.manage', async () => {
    mockApi({ 'GET /categories': list([]) })
    renderWithProviders(<CategoriesPage />, { route: '/categories?pane=new', path: PATHS, session: memberSession() })

    expect(await screen.findByText('No categories yet')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add the first category' })).not.toBeInTheDocument()
  })

  it('shows a not-found state for a missing category', async () => {
    mockApi({ 'GET /categories': list([mechanical]), 'GET /categories/:id': { __error: { status: 404, code: 'not_found', error: 'Not found.' } } })
    renderWithProviders(<CategoriesPage />, { route: '/categories/missing', path: PATHS })

    expect(await screen.findByText('Category not found')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back to categories' })).toBeInTheDocument()
  })
})

describe('Create category', () => {
  const created = { ...safety, id: 'cat-9', name: 'Calibration', color: '#ffcd00', icon: 'ruler', description: 'Instrument checks', usage: { work_orders: 0 } }

  it('posts the chosen name, colour, icon and description, then opens the new category', async () => {
    const { calls } = mockApi({
      'GET /categories': list([mechanical]),
      'POST /categories': { category: created },
      'GET /categories/:id': { category: created },
    })
    const { user } = renderWithProviders(
      <>
        <CategoriesPage />
        <LocationProbe />
      </>,
      { route: '/categories?sort=-usage', path: PATHS },
    )

    await user.click(await screen.findByRole('button', { name: 'New Category' }))
    const sheet = await screen.findByRole('dialog', { name: 'New Category' })
    expect(within(sheet).getByLabelText('Name')).toHaveFocus()

    await user.type(within(sheet).getByLabelText('Name'), 'Calibration')
    await user.click(within(sheet).getByRole('radio', { name: 'Iowa gold' }))
    expect(within(sheet).getByLabelText('Hex value')).toHaveValue('#ffcd00')
    await user.type(within(sheet).getByRole('searchbox', { name: 'Search icons' }), 'measure')
    expect(within(sheet).queryByRole('radio', { name: 'Wrench' })).not.toBeInTheDocument()
    await user.click(within(sheet).getByRole('radio', { name: 'Ruler' }))
    await user.type(within(sheet).getByLabelText('Description'), 'Instrument checks')
    await user.click(within(sheet).getByRole('button', { name: 'Create Category' }))

    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true))
    const post = calls.find((call) => call.method === 'POST')!
    expect(post.url).toBe('/api/v1/categories')
    expect(post.body).toEqual({ name: 'Calibration', color: '#ffcd00', icon: 'ruler', description: 'Instrument checks' })

    expect(await screen.findByText('Category created')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/categories/cat-9?sort=-usage'))
    expect(screen.queryByRole('dialog', { name: 'New Category' })).not.toBeInTheDocument()
    expect(await screen.findByRole('heading', { level: 2, name: 'Calibration' })).toBeInTheDocument()
  })

  it('keeps the form open and shows server validation errors next to the fields', async () => {
    mockApi({
      'GET /categories': list([mechanical]),
      'POST /categories': { __error: { status: 400, code: 'validation', error: 'Please fix the highlighted fields.', errors: { name: 'A category with this name already exists.' } } },
    })
    const { user } = renderWithProviders(<CategoriesPage />, { route: '/categories?pane=new', path: PATHS })

    const sheet = await screen.findByRole('dialog', { name: 'New Category' })
    await user.type(within(sheet).getByLabelText('Name'), 'mechanical')
    await user.click(within(sheet).getByRole('button', { name: 'Create Category' }))

    expect(await within(sheet).findByText('A category with this name already exists.')).toBeInTheDocument()
    expect(within(sheet).getByLabelText('Name')).toHaveValue('mechanical')
    expect(within(sheet).getByLabelText('Name')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.queryByText('Category created')).not.toBeInTheDocument()
  })

  it('rejects an invalid hex colour before sending anything', async () => {
    const { calls } = mockApi({ 'GET /categories': list([mechanical]) })
    const { user } = renderWithProviders(<CategoriesPage />, { route: '/categories?pane=new', path: PATHS })

    const sheet = await screen.findByRole('dialog', { name: 'New Category' })
    await user.type(within(sheet).getByLabelText('Name'), 'Welding')
    const hex = within(sheet).getByLabelText('Hex value')
    await user.clear(hex)
    await user.type(hex, '#12')
    await user.click(within(sheet).getByRole('button', { name: 'Create Category' }))

    expect(await within(sheet).findByText('Use a six-digit hex colour such as #0878d1.')).toBeInTheDocument()
    expect(calls.some((call) => call.method === 'POST')).toBe(false)
  })

  it('surfaces a 403 from the server as a toast', async () => {
    mockApi({
      'GET /categories': list([mechanical]),
      'POST /categories': { __error: { status: 403, code: 'forbidden', error: 'You do not have permission to manage categories.' } },
    })
    const { user } = renderWithProviders(<CategoriesPage />, { route: '/categories?pane=new', path: PATHS })

    const sheet = await screen.findByRole('dialog', { name: 'New Category' })
    await user.type(within(sheet).getByLabelText('Name'), 'Welding')
    await user.click(within(sheet).getByRole('button', { name: 'Create Category' }))

    expect(await screen.findByText('Could not save category')).toBeInTheDocument()
    expect(screen.getByText('You do not have permission to manage categories.', { selector: 'p' })).toBeInTheDocument()
  })

  it('opens the pane with "n", closes it with Escape and focuses search with "/"', async () => {
    mockApi({ 'GET /categories': list([mechanical]) })
    const { user } = renderWithProviders(<CategoriesPage />, { route: '/categories', path: PATHS })
    await screen.findByTestId('category-row')

    await user.keyboard('n')
    const sheet = await screen.findByRole('dialog', { name: 'New Category' })
    expect(within(sheet).getByLabelText('Name')).toHaveFocus()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())

    await user.keyboard('/')
    expect(screen.getByRole('searchbox', { name: 'Search' })).toHaveFocus()
  })

  it('asks before discarding a dirty form', async () => {
    mockApi({ 'GET /categories': list([mechanical]) })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const { user } = renderWithProviders(<CategoriesPage />, { route: '/categories?pane=new', path: PATHS })

    const sheet = await screen.findByRole('dialog', { name: 'New Category' })
    await user.type(within(sheet).getByLabelText('Name'), 'Draft')
    await user.click(within(sheet).getByRole('button', { name: 'Close panel' }))
    expect(confirm).toHaveBeenCalledWith('Discard your changes?')
    expect(screen.getByRole('dialog', { name: 'New Category' })).toBeInTheDocument()
  })
})

describe('Edit and delete category', () => {
  it('patches the category and shows a toast', async () => {
    const { calls } = mockApi({
      'GET /categories': list([mechanical]),
      'GET /categories/:id': { category: mechanical },
      'PATCH /categories/:id': ({ body }: { body: unknown }) => ({ category: { ...mechanical, ...(body as object) } }),
    })
    const { user } = renderWithProviders(<CategoriesPage />, { route: '/categories/cat-1', path: PATHS })

    await user.click(await screen.findByRole('button', { name: 'Edit' }))
    const sheet = await screen.findByRole('dialog', { name: 'Edit Mechanical' })
    const name = within(sheet).getByLabelText('Name')
    await user.clear(name)
    await user.type(name, 'Mechanical Systems')
    await user.click(within(sheet).getByRole('radio', { name: 'Hammer' }))
    await user.click(within(sheet).getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(calls.some((call) => call.method === 'PATCH')).toBe(true))
    const patch = calls.find((call) => call.method === 'PATCH')!
    expect(patch.url).toBe('/api/v1/categories/cat-1')
    expect(patch.body).toEqual({ name: 'Mechanical Systems', color: '#0878d1', icon: 'hammer', description: 'Frames, drivetrain and mounts.' })
    expect(await screen.findByText('Category updated')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('confirms deletion and surfaces a 409 category_in_use as a toast', async () => {
    const { calls } = mockApi({
      'GET /categories': list([mechanical]),
      'GET /categories/:id': { category: mechanical },
      'DELETE /categories/:id': { __error: { status: 409, code: 'category_in_use', error: 'This category is still used by work orders.' } },
    })
    const { user } = renderWithProviders(<CategoriesPage />, { route: '/categories/cat-1', path: PATHS })

    await user.click(await screen.findByRole('button', { name: 'More actions' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Delete category' }))
    const dialog = await screen.findByRole('dialog', { name: 'Delete this category?' })
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }))

    await waitFor(() => expect(calls.some((call) => call.method === 'DELETE' && call.url === '/api/v1/categories/cat-1')).toBe(true))
    expect(await screen.findByText('Category is in use')).toBeInTheDocument()
    expect(screen.getByText('This category is still used by work orders.')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Delete this category?' })).not.toBeInTheDocument())
    expect(screen.getByRole('heading', { level: 2, name: 'Mechanical' })).toBeInTheDocument()
  })

  it('deletes an unused category and returns to the list', async () => {
    mockApi({
      'GET /categories': list([mechanical]),
      'GET /categories/:id': { category: mechanical },
      'DELETE /categories/:id': { id: 'cat-1', deleted: true },
    })
    const { user } = renderWithProviders(
      <>
        <CategoriesPage />
        <LocationProbe />
      </>,
      { route: '/categories/cat-1', path: PATHS },
    )

    await user.click(await screen.findByRole('button', { name: 'More actions' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Delete category' }))
    const dialog = await screen.findByRole('dialog', { name: 'Delete this category?' })
    await user.click(within(dialog).getByRole('button', { name: 'Delete' }))

    expect(await screen.findByText('Category deleted')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/categories'))
    expect(screen.getByText('Select a category')).toBeInTheDocument()
  })
})
