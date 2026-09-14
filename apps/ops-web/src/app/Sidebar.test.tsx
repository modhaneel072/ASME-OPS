import { screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { mockApi, renderWithProviders } from '@/test/render'
import { Sidebar } from './Sidebar'

const UNREAD = { 'GET /notifications': { items: [], next_cursor: null, total: 0, __extras: { unread_count: 0 } } }

function renderSidebar(collapsed: boolean) {
  return renderWithProviders(<Sidebar collapsed={collapsed} onToggleCollapsed={vi.fn()} mobileOpen={false} onCloseMobile={vi.fn()} />, { route: '/work-orders' })
}

describe('Sidebar account area', () => {
  it('only offers in-app account actions', async () => {
    mockApi(UNREAD)
    const { user } = renderSidebar(false)
    await user.click(screen.getByRole('button', { name: 'Account menu for Ada Admin' }))
    const menu = await screen.findByRole('menu')
    expect(within(menu).getAllByRole('menuitem').map((item) => item.textContent)).toEqual(['Profile', 'Settings', 'Log out'])
    expect(within(menu).queryByText(/portal|website/i)).not.toBeInTheDocument()
  })

  it('sends Help / Support to the chapter email in the expanded sidebar', () => {
    mockApi(UNREAD)
    renderSidebar(false)
    const help = screen.getByRole('link', { name: 'Help / Support: email asme@uiowa.edu' })
    expect(help).toHaveAttribute('href', 'mailto:asme@uiowa.edu')
    expect(help).toHaveTextContent('Help / Support')
  })

  it('sends Help / Support to the chapter email in the collapsed sidebar', () => {
    mockApi(UNREAD)
    renderSidebar(true)
    expect(screen.getByRole('link', { name: 'Help / Support: email asme@uiowa.edu' })).toHaveAttribute('href', 'mailto:asme@uiowa.edu')
    expect(document.querySelector('a[href^="/portal"], a[href="/"]')).toBeNull()
  })
})
