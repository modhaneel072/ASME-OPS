import { screen, waitFor, within } from '@testing-library/react'
import { useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { memberSession, mockApi, renderWithProviders } from '@/test/render'
import VendorsPage from './index'

const PATHS = ['/vendors', '/vendors/:vendorId']

const mcmaster = {
  id: 'v-1',
  name: 'McMaster-Carr',
  contact_name: 'Sales Desk',
  email: 'sales@mcmaster.com',
  phone: '+1 630 555 0100',
  website: 'https://www.mcmaster.com',
  address: {},
  notes: 'Net 30.\nQuote the chapter account number.',
  is_active: true,
  created_at: '2026-09-01T14:00:00Z',
  updated_at: '2026-09-02T09:30:00Z',
}
const retired = {
  id: 'v-2',
  name: 'Old Supplier',
  contact_name: null,
  email: null,
  phone: null,
  website: null,
  address: {},
  notes: null,
  is_active: false,
  created_at: '2026-08-01T14:00:00Z',
  updated_at: '2026-08-15T09:30:00Z',
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

describe('Vendors list', () => {
  it('renders rows with contact and status and asks for active vendors by default', async () => {
    const { calls } = mockApi({ 'GET /vendors': list([mcmaster]) })
    renderWithProviders(<VendorsPage />, { route: '/vendors', path: PATHS })

    const row = await screen.findByTestId('vendor-row')
    expect(row).toHaveTextContent('McMaster-Carr')
    expect(row).toHaveTextContent('Sales Desk')
    expect(row).toHaveTextContent('sales@mcmaster.com')
    expect(within(row).getByText('Active')).toBeInTheDocument()
    expect(screen.getByText('1 vendor')).toBeInTheDocument()

    const request = calls.find((call) => call.method === 'GET' && call.url.startsWith('/api/v1/vendors?'))!
    expect(searchParam(request.url, 'filter[active]')).toBe('true')
    expect(searchParam(request.url, 'sort')).toBe('name')
  })

  it('shows the empty state with a create action for managers', async () => {
    mockApi({ 'GET /vendors': list([]) })
    renderWithProviders(<VendorsPage />, { route: '/vendors', path: PATHS })

    expect(await screen.findByText('No vendors yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add the first vendor' })).toBeInTheDocument()
  })

  it('switches to inactive vendors through the Active filter chip', async () => {
    const { calls } = mockApi({
      'GET /vendors': ({ url }: { url: URL }) => (url.searchParams.get('filter[active]') === 'false' ? list([retired]) : list([mcmaster])),
    })
    const { user } = renderWithProviders(<VendorsPage />, { route: '/vendors', path: PATHS })

    expect(await screen.findByTestId('vendor-row')).toHaveTextContent('McMaster-Carr')
    await user.click(screen.getByRole('button', { name: /^Active/ }))
    await user.click(await screen.findByRole('radio', { name: 'Inactive' }))

    await waitFor(() => expect(calls.some((call) => call.method === 'GET' && searchParam(call.url, 'filter[active]') === 'false')).toBe(true))
    const row = await screen.findByText('Old Supplier')
    expect(within(row.closest('a')!).getByText('Inactive')).toBeInTheDocument()
  })

  it('reads the inactive filter from a deep link and shows a no-results state with a clear action', async () => {
    const { calls } = mockApi({
      'GET /vendors': ({ url }: { url: URL }) => (url.searchParams.get('filter[active]') === 'false' ? list([]) : list([mcmaster])),
    })
    const { user } = renderWithProviders(<VendorsPage />, { route: '/vendors?filter[active]=false', path: PATHS })

    expect(await screen.findByText('No vendors match')).toBeInTheDocument()
    expect(searchParam(calls[0].url, 'filter[active]')).toBe('false')
    await user.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(await screen.findByTestId('vendor-row')).toHaveTextContent('McMaster-Carr')
  })

  it('shows an inline error with a retry action when the list fails', async () => {
    let attempts = 0
    mockApi({
      'GET /vendors': () => {
        attempts += 1
        return attempts === 1 ? { __error: { status: 500, code: 'server_error', error: 'Database unavailable.' } } : list([mcmaster])
      },
    })
    const { user } = renderWithProviders(<VendorsPage />, { route: '/vendors', path: PATHS })

    expect(await screen.findByText('Vendors could not be loaded')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByTestId('vendor-row')).toHaveTextContent('McMaster-Carr')
  })
})

describe('Vendor detail', () => {
  it('renders contact links, notes and record dates', async () => {
    mockApi({ 'GET /vendors': list([mcmaster]), 'GET /vendors/:id': { vendor: mcmaster } })
    renderWithProviders(<VendorsPage />, { route: '/vendors/v-1', path: PATHS })

    expect(await screen.findByRole('heading', { level: 2, name: /McMaster-Carr/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'sales@mcmaster.com' })).toHaveAttribute('href', 'mailto:sales@mcmaster.com')
    expect(screen.getByRole('link', { name: '+1 630 555 0100' })).toHaveAttribute('href', 'tel:+16305550100')
    const website = screen.getByRole('link', { name: /www\.mcmaster\.com/ })
    expect(website).toHaveAttribute('href', 'https://www.mcmaster.com')
    expect(website).toHaveAttribute('target', '_blank')
    expect(screen.getByText(/Quote the chapter account number\./)).toBeInTheDocument()
  })

  it('hides manage controls for members', async () => {
    mockApi({ 'GET /vendors': list([mcmaster]), 'GET /vendors/:id': { vendor: mcmaster } })
    const { user } = renderWithProviders(<VendorsPage />, { route: '/vendors/v-1', path: PATHS, session: memberSession() })

    expect(await screen.findByRole('heading', { level: 2, name: /McMaster-Carr/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'New Vendor' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'More actions' })).not.toBeInTheDocument()

    await user.keyboard('n')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows a not-found state for a missing vendor', async () => {
    mockApi({ 'GET /vendors': list([mcmaster]), 'GET /vendors/:id': { __error: { status: 404, code: 'not_found', error: 'Not found.' } } })
    renderWithProviders(<VendorsPage />, { route: '/vendors/missing', path: PATHS })

    expect(await screen.findByText('Vendor not found')).toBeInTheDocument()
  })

  it('deactivates a vendor from the More menu with a PATCH', async () => {
    const { calls } = mockApi({
      'GET /vendors': list([mcmaster]),
      'GET /vendors/:id': { vendor: mcmaster },
      'PATCH /vendors/:id': ({ body }: { body: unknown }) => ({ vendor: { ...mcmaster, ...(body as object) } }),
    })
    const { user } = renderWithProviders(<VendorsPage />, { route: '/vendors/v-1', path: PATHS })

    await user.click(await screen.findByRole('button', { name: 'More actions' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Deactivate vendor' }))

    await waitFor(() => expect(calls.some((call) => call.method === 'PATCH')).toBe(true))
    const patch = calls.find((call) => call.method === 'PATCH')!
    expect(patch.url).toBe('/api/v1/vendors/v-1')
    expect(patch.body).toEqual({ is_active: false })
    expect(await screen.findByText('Vendor deactivated')).toBeInTheDocument()
  })

  it('surfaces a 403 on deactivate as a toast', async () => {
    mockApi({
      'GET /vendors': list([mcmaster]),
      'GET /vendors/:id': { vendor: mcmaster },
      'PATCH /vendors/:id': { __error: { status: 403, code: 'forbidden', error: 'You do not have permission to manage vendors.' } },
    })
    const { user } = renderWithProviders(<VendorsPage />, { route: '/vendors/v-1', path: PATHS })

    await user.click(await screen.findByRole('button', { name: 'More actions' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Deactivate vendor' }))
    expect(await screen.findByText('Could not deactivate vendor')).toBeInTheDocument()
    expect(screen.getByText('You do not have permission to manage vendors.')).toBeInTheDocument()
  })
})

describe('Create and edit vendor', () => {
  const created = { ...retired, id: 'v-9', name: 'DigiKey', email: 'sales@digikey.com', website: 'https://www.digikey.com', is_active: true }

  it('posts the form with blanks as null and opens the new vendor', async () => {
    const { calls } = mockApi({
      'GET /vendors': list([mcmaster]),
      'POST /vendors': { vendor: created },
      'GET /vendors/:id': { vendor: created },
    })
    const { user } = renderWithProviders(
      <>
        <VendorsPage />
        <LocationProbe />
      </>,
      { route: '/vendors', path: PATHS },
    )

    await user.click(await screen.findByRole('button', { name: 'New Vendor' }))
    const sheet = await screen.findByRole('dialog', { name: 'New Vendor' })
    expect(within(sheet).getByLabelText('Name')).toHaveFocus()
    expect(within(sheet).getByRole('checkbox', { name: /Active vendor/ })).toBeChecked()

    await user.type(within(sheet).getByLabelText('Name'), 'DigiKey')
    await user.type(within(sheet).getByLabelText('Email'), 'Sales@DigiKey.com')
    await user.type(within(sheet).getByLabelText('Website'), 'https://www.digikey.com')
    await user.click(within(sheet).getByRole('button', { name: 'Create Vendor' }))

    await waitFor(() => expect(calls.some((call) => call.method === 'POST')).toBe(true))
    const post = calls.find((call) => call.method === 'POST')!
    expect(post.url).toBe('/api/v1/vendors')
    expect(post.body).toEqual({ name: 'DigiKey', contact_name: null, email: 'Sales@DigiKey.com', phone: null, website: 'https://www.digikey.com', notes: null, is_active: true })

    expect(await screen.findByText('Vendor created')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/vendors/v-9'))
    expect(await screen.findByRole('heading', { level: 2, name: /DigiKey/ })).toBeInTheDocument()
  })

  it('keeps the form open and maps server validation errors onto the right fields', async () => {
    mockApi({
      'GET /vendors': list([mcmaster]),
      'POST /vendors': {
        __error: {
          status: 400,
          code: 'validation',
          error: 'Please fix the highlighted fields.',
          errors: { name: 'A vendor with this name already exists.', email: 'Enter a valid email address.' },
        },
      },
    })
    const { user } = renderWithProviders(<VendorsPage />, { route: '/vendors?pane=new', path: PATHS })

    const sheet = await screen.findByRole('dialog', { name: 'New Vendor' })
    await user.type(within(sheet).getByLabelText('Name'), 'mcmaster-carr')
    await user.type(within(sheet).getByLabelText('Email'), 'orders@mcmaster.com')
    await user.click(within(sheet).getByRole('button', { name: 'Create Vendor' }))

    expect(await within(sheet).findByText('A vendor with this name already exists.')).toBeInTheDocument()
    expect(within(sheet).getByText('Enter a valid email address.')).toBeInTheDocument()
    expect(within(sheet).getByLabelText('Name')).toHaveAttribute('aria-invalid', 'true')
    expect(within(sheet).getByLabelText('Email')).toHaveAttribute('aria-invalid', 'true')
    expect(within(sheet).getByLabelText('Name')).toHaveValue('mcmaster-carr')
    expect(screen.queryByText('Vendor created')).not.toBeInTheDocument()
  })

  it('validates the website scheme locally before sending', async () => {
    const { calls } = mockApi({ 'GET /vendors': list([mcmaster]) })
    const { user } = renderWithProviders(<VendorsPage />, { route: '/vendors?pane=new', path: PATHS })

    const sheet = await screen.findByRole('dialog', { name: 'New Vendor' })
    await user.type(within(sheet).getByLabelText('Name'), 'Grainger')
    await user.type(within(sheet).getByLabelText('Website'), 'grainger.com')
    await user.click(within(sheet).getByRole('button', { name: 'Create Vendor' }))

    expect(await within(sheet).findByText('Start the website with http:// or https://.')).toBeInTheDocument()
    expect(calls.some((call) => call.method === 'POST')).toBe(false)
  })

  it('edits a vendor from a deep-linked pane and PATCHes every field', async () => {
    const { calls } = mockApi({
      'GET /vendors': list([mcmaster]),
      'GET /vendors/:id': { vendor: mcmaster },
      'PATCH /vendors/:id': ({ body }: { body: unknown }) => ({ vendor: { ...mcmaster, ...(body as object) } }),
    })
    const { user } = renderWithProviders(<VendorsPage />, { route: '/vendors/v-1?pane=edit', path: PATHS })

    const sheet = await screen.findByRole('dialog', { name: 'Edit McMaster-Carr' })
    expect(within(sheet).getByLabelText('Contact name')).toHaveValue('Sales Desk')
    const phone = within(sheet).getByLabelText('Phone')
    await user.clear(phone)
    await user.type(phone, '555-0199')
    await user.click(within(sheet).getByRole('checkbox', { name: /Active vendor/ }))
    await user.click(within(sheet).getByRole('button', { name: 'Save changes' }))

    await waitFor(() => expect(calls.some((call) => call.method === 'PATCH')).toBe(true))
    const patch = calls.find((call) => call.method === 'PATCH')!
    expect(patch.url).toBe('/api/v1/vendors/v-1')
    expect(patch.body).toEqual({
      name: 'McMaster-Carr',
      contact_name: 'Sales Desk',
      email: 'sales@mcmaster.com',
      phone: '555-0199',
      website: 'https://www.mcmaster.com',
      notes: 'Net 30.\nQuote the chapter account number.',
      is_active: false,
    })
    expect(await screen.findByText('Vendor updated')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('asks before discarding a dirty form', async () => {
    mockApi({ 'GET /vendors': list([mcmaster]) })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const { user } = renderWithProviders(<VendorsPage />, { route: '/vendors?pane=new', path: PATHS })

    const sheet = await screen.findByRole('dialog', { name: 'New Vendor' })
    await user.type(within(sheet).getByLabelText('Name'), 'Draft')
    await user.keyboard('{Escape}')
    expect(confirm).toHaveBeenCalledWith('Discard your changes?')
    expect(screen.getByRole('dialog', { name: 'New Vendor' })).toBeInTheDocument()
  })
})
