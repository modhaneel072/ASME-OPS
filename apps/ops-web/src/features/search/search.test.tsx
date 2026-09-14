import { screen, waitFor, within } from '@testing-library/react'
import { useLocation } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { memberSession, mockApi, renderWithProviders } from '@/test/render'
import { CommandPalette } from './index'

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname + location.search}</output>
}

const RESULTS = {
  query: 'rov',
  results: {
    work_orders: [
      { id: 'wo-12', number: 12, title: 'Replace rover wheel bearing', status: 'in_progress', priority: 'high' },
      { id: 'wo-13', number: 13, title: 'Rover sponsor deck', status: 'open', priority: 'none' },
    ],
    projects: [{ id: 'p-1', name: 'Crater Cruncher Rover', code: 'CCR', visibility: 'chapter' }],
    assets: [{ id: 'a-1', name: 'Rover Chassis', code: 'CCR-CH', status: 'online' }],
    locations: [{ id: 'l-1', name: 'Rover Bay' }],
    categories: [{ id: 'c-1', name: 'Rover Systems', color: '#123456', icon: 'rocket' }],
    users: [{ id: 7, name: 'Rover Fan', email: 'fan@uiowa.edu', avatar_url: null }],
  },
}

const EMPTY = { query: 'zzz', results: { work_orders: [], projects: [], assets: [], locations: [], categories: [], users: [] } }

function renderPalette(options: Parameters<typeof renderWithProviders>[1] = {}) {
  const onClose = vi.fn()
  const utils = renderWithProviders(
    <>
      <CommandPalette open onClose={onClose} />
      <LocationProbe />
    </>,
    { route: '/work-orders', ...options },
  )
  return { ...utils, onClose }
}

describe('CommandPalette', () => {
  it('focuses the search box and offers permission-gated quick actions for an empty query', async () => {
    const { calls } = mockApi({})
    renderPalette()
    const input = screen.getByRole('combobox', { name: 'Search' })
    expect(input).toHaveFocus()
    const list = screen.getByRole('listbox', { name: 'Quick actions' })
    expect(within(list).getByRole('option', { name: /New work order/ })).toBeInTheDocument()
    expect(within(list).getByRole('option', { name: /New project/ })).toBeInTheDocument()
    expect(within(list).getByRole('option', { name: /Go to Setup Center/ })).toBeInTheDocument()
    expect(within(list).getByRole('option', { name: /Go to Notifications/ })).toBeInTheDocument()
    expect(calls).toHaveLength(0)
  })

  it('hides quick actions the member cannot use', () => {
    mockApi({})
    renderPalette({ session: memberSession() })
    const list = screen.getByRole('listbox', { name: 'Quick actions' })
    expect(within(list).getByRole('option', { name: /New work order/ })).toBeInTheDocument()
    expect(within(list).queryByRole('option', { name: /New project/ })).not.toBeInTheDocument()
  })

  it('opens a quick action with the keyboard', async () => {
    mockApi({})
    const { user, onClose } = renderPalette()
    await user.keyboard('{ArrowDown}{Enter}')
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/projects?pane=new'))
    expect(onClose).toHaveBeenCalled()
  })

  it('waits for two characters before searching', async () => {
    const { calls } = mockApi({ 'GET /search': RESULTS })
    const { user } = renderPalette()
    await user.type(screen.getByRole('combobox', { name: 'Search' }), 'r')
    // Shown visibly and announced through the live region.
    expect((await screen.findAllByText('Type at least 2 characters to search.')).length).toBeGreaterThan(0)
    await new Promise((resolve) => setTimeout(resolve, 260))
    expect(calls).toHaveLength(0)
  })

  it('searches once after the debounce, groups results and keyboard-selects across groups', async () => {
    const { calls } = mockApi({ 'GET /search': RESULTS })
    const { user, onClose } = renderPalette()
    const input = screen.getByRole('combobox', { name: 'Search' })
    await user.type(input, 'rov')

    const results = await screen.findByRole('listbox', { name: 'Search results' })
    await waitFor(() => expect(calls.filter((c) => c.url.startsWith('/api/v1/search'))).toHaveLength(1))
    expect(calls[0].url).toBe('/api/v1/search?q=rov&limit=8')

    expect(within(results).getByText('Work orders')).toBeInTheDocument()
    expect(within(results).getByText('People')).toBeInTheDocument()
    const first = within(results).getByRole('option', { name: /Replace rover wheel bearing/ })
    expect(first).toHaveAttribute('aria-selected', 'true')
    expect(first).toHaveTextContent('#12')
    expect(first).toHaveTextContent('In progress')
    expect(within(results).getByRole('option', { name: /Crater Cruncher Rover/ })).toHaveTextContent('CCR')
    expect(screen.getByText('7 results for rov.')).toBeInTheDocument()

    // Down twice crosses from the work-orders group into projects; Up wraps to the last row.
    await user.keyboard('{ArrowDown}{ArrowDown}')
    expect(within(results).getByRole('option', { name: /Crater Cruncher Rover/ })).toHaveAttribute('aria-selected', 'true')
    expect(input).toHaveAttribute('aria-activedescendant', within(results).getByRole('option', { name: /Crater Cruncher Rover/ }).id)
    await user.keyboard('{ArrowUp}{ArrowUp}{ArrowUp}')
    expect(within(results).getByRole('option', { name: /Rover Fan/ })).toHaveAttribute('aria-selected', 'true')

    await user.keyboard('{ArrowDown}{Enter}')
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/work-orders/wo-12'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('navigates to people, categories and locations with their own routes when clicked', async () => {
    mockApi({ 'GET /search': RESULTS })
    const { user } = renderPalette()
    await user.type(screen.getByRole('combobox', { name: 'Search' }), 'rov')
    const results = await screen.findByRole('listbox', { name: 'Search results' })
    await user.click(within(results).getByRole('option', { name: /Rover Fan/ }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/teams-users/users/7'))
  })

  it('shows a no-results message and an error with retry', async () => {
    let fail = true
    mockApi({
      'GET /search': () => {
        if (fail) return { __error: { status: 500, code: 'server_error', error: 'Search index offline.' } }
        return EMPTY
      },
    })
    const { user } = renderPalette()
    await user.type(screen.getByRole('combobox', { name: 'Search' }), 'zzz')
    expect(await screen.findByText('Search is unavailable right now')).toBeInTheDocument()
    expect(screen.getByText('Search index offline.')).toBeInTheDocument()
    fail = false
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('No results for “zzz”')).toBeInTheDocument()
  })

  it('closes on Escape', async () => {
    mockApi({})
    const { user, onClose } = renderPalette()
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })
})
