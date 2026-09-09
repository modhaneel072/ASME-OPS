import { screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { memberSession, mockApi, renderWithProviders } from '@/test/render'
import TeamsUsersPage from '.'
import { groupPermissionKeys } from './permissionGroups'
import { ROLES, ROUTE_PATHS, listOf } from './testFixtures'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('permission grouping', () => {
  it('orders groups by module and parks unknown prefixes under Later stages', () => {
    const groups = groupPermissionKeys(['request.submit', 'work_order.edit', 'team.manage', 'team.read', 'chapter.setup.manage', 'sponsor.manage'])
    expect(groups.map((group) => group.label)).toEqual(['Chapter', 'Teams', 'Work orders', 'Later stages'])
    expect(groups[1].keys).toEqual(['team.manage', 'team.read'])
    expect(groups[3].keys).toEqual(['request.submit', 'sponsor.manage'])
  })
})

describe('Roles tab', () => {
  it('renders the read-only matrix with role columns, member counts, scopes and no-access cells', async () => {
    mockApi({ 'GET /roles': listOf(ROLES) })
    renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/roles', path: ROUTE_PATHS, session: memberSession() })
    const table = await screen.findByRole('table')
    expect(screen.getByRole('tab', { name: 'Roles' })).toHaveAttribute('aria-selected', 'true')
    // read-only: no primary action for anyone on this tab
    expect(screen.queryByRole('button', { name: 'New Team' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Invite member' })).not.toBeInTheDocument()

    const headers = within(table).getAllByRole('columnheader')
    expect(headers.map((header) => header.textContent)).toEqual(['Permission', 'Chapter Administrator1 member', 'Team Lead1 member', 'Full Member3 members'])

    for (const label of ['Chapter', 'Users', 'Teams', 'Work orders', 'Later stages']) {
      expect(within(table).getByRole('rowheader', { name: label })).toBeInTheDocument()
    }
    expect(within(table).queryByRole('rowheader', { name: 'Locations' })).not.toBeInTheDocument()

    const manage = within(table).getByRole('row', { name: /team\.manage/ })
    const cells = within(manage).getAllByRole('cell')
    expect(cells.map((cell) => cell.textContent)).toEqual(['C', 'T', '—no access'])
    expect(within(cells[0]).getByTitle('Chapter: anywhere in the chapter')).toHaveTextContent('C')
    expect(within(cells[1]).getByTitle(/^Team:/)).toHaveTextContent('T')
    expect(within(cells[2]).getByText('no access')).toHaveClass('sr-only')

    const edit = within(table).getByRole('row', { name: /work_order\.edit/ })
    expect(within(edit).getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['C', 'T', 'O'])
    expect(within(edit).getByTitle(/^Own:/)).toBeInTheDocument()

    const later = within(table).getByRole('row', { name: /request\.submit/ })
    expect(within(later).getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['C', '—no access', 'C'])
  })

  it('shows an inline error with Retry when roles cannot be loaded', async () => {
    let attempts = 0
    mockApi({
      'GET /roles': () => {
        attempts += 1
        return attempts === 1 ? { __error: { status: 500, code: 'server_error', error: 'Database unavailable.' } } : listOf(ROLES)
      },
    })
    const { user } = renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/roles', path: ROUTE_PATHS })
    expect(await screen.findByText('Roles could not be loaded')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('table')).toBeInTheDocument()
  })

  it('renders not-found for an unknown tab', async () => {
    mockApi({})
    renderWithProviders(<TeamsUsersPage />, { route: '/teams-users/nope', path: ROUTE_PATHS })
    expect(await screen.findByText('Page not found')).toBeInTheDocument()
  })
})
