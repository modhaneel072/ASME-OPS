import { screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ADMIN_SESSION, memberSession, mockApi, renderWithProviders } from '@/test/render'
import SettingsPage from './index'

const ORGANIZATION = {
  id: 'org-1',
  name: 'ASME at the University of Iowa',
  slug: 'uiowa',
  logo_url: null,
  timezone: 'America/Chicago',
  academic_year_start_month: 8,
  settings: { profile_completed: false, chapter_short_name: 'ASME Iowa', default_due_days: 7 },
  setup_completed_at: null,
  created_at: '2026-09-01T00:00:00Z',
  updated_at: '2026-09-02T12:00:00Z',
}

const ROLES = [
  {
    id: 'r-1',
    name: 'Chapter Administrator',
    system_key: 'chapter_admin',
    is_custom: false,
    description: 'Runs the chapter workspace.',
    member_count: 1,
    grants: [
      { key: 'chapter.settings.manage', scope: 'chapter' },
      { key: 'work_order.edit', scope: 'chapter' },
    ],
  },
  {
    id: 'r-5',
    name: 'Full Member',
    system_key: 'full_member',
    is_custom: false,
    description: 'Active chapter member.',
    member_count: 12,
    grants: [
      { key: 'work_order.create', scope: 'chapter' },
      { key: 'work_order.edit', scope: 'own' },
      { key: 'work_order.start', scope: 'assigned' },
    ],
  },
  { id: 'r-9', name: 'Alumni Mentor', system_key: null, is_custom: true, description: null, member_count: 0, grants: [] },
]

function renderSettings(section: string, options: Parameters<typeof renderWithProviders>[1] = {}) {
  return renderWithProviders(<SettingsPage />, { route: `/settings/${section}`, path: '/settings/:section', ...options })
}

describe('SettingsPage navigation', () => {
  it('marks the current section in the sub-navigation and lists every section', () => {
    mockApi({ 'GET /organization': { organization: ORGANIZATION } })
    renderSettings('chapter')
    const nav = screen.getByRole('navigation', { name: 'Settings sections' })
    expect(within(nav).getByRole('link', { name: 'Chapter' })).toHaveAttribute('aria-current', 'page')
    expect(within(nav).getByRole('link', { name: 'Profile' })).not.toHaveAttribute('aria-current')
    expect(within(nav).getAllByRole('link')).toHaveLength(6)
  })

  it('renders the coming-soon pages for unbuilt sections', () => {
    mockApi({})
    const { unmount } = renderSettings('notifications')
    expect(screen.getByText('Notification settings arrives in Stage 7')).toBeInTheDocument()
    unmount()
    renderSettings('integrations')
    expect(screen.getByText('Integrations arrives in Stage 8')).toBeInTheDocument()
  })

  it('handles an unknown section without crashing', () => {
    mockApi({})
    renderSettings('nope')
    expect(screen.getByText('Settings section not found')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Go to Profile' })).toHaveAttribute('href', '/settings/profile')
  })
})

describe('Profile section', () => {
  it('shows the session identity, permission summary and log out, with no links out of ASME Ops', async () => {
    const { calls } = mockApi({ 'POST /auth/logout': {} })
    const { user } = renderSettings('profile')
    expect(screen.getByText('Ada Admin')).toBeInTheDocument()
    expect(screen.getByText('ada@uiowa.edu')).toBeInTheDocument()
    expect(screen.getAllByText('Chapter Administrator').length).toBeGreaterThan(0)
    expect(screen.getByText('Administrator')).toBeInTheDocument()
    expect(screen.getByText('Account role')).toBeInTheDocument()
    expect(document.querySelector('a[href^="/portal"]')).toBeNull()
    expect(screen.queryByText(/member portal/i)).not.toBeInTheDocument()

    const workOrders = screen.getByRole('list', { name: 'Work orders permissions' })
    expect(within(workOrders).getByText('create')).toBeInTheDocument()
    expect(within(workOrders).getAllByText('chapter').length).toBeGreaterThan(0)
    expect(screen.getByText(`${Object.keys(ADMIN_SESSION.permissions).length} permissions`)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Log out' }))
    await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url === '/api/v1/auth/logout')).toBe(true))
  })

  it('shows scoped permissions for a member', () => {
    mockApi({})
    renderSettings('profile', { session: memberSession() })
    const workOrders = screen.getByRole('list', { name: 'Work orders permissions' })
    const edit = within(workOrders).getByText('edit').closest('li') as HTMLElement
    expect(within(edit).getByText('own')).toBeInTheDocument()
  })
})

const PROFILE_SESSION = { ...ADMIN_SESSION, user: { ...ADMIN_SESSION.user, major: 'Mechanical Engineering', graduation_year: 2027, phone: '319-555-0100' } }

describe('Edit profile form', () => {
  it('prefills from the session, sends only changed fields and updates the cached session', async () => {
    const saved = { ...PROFILE_SESSION, user: { ...PROFILE_SESSION.user, major: 'Biomedical Engineering', graduation_year: 2028, phone: null } }
    const { calls } = mockApi({ 'PATCH /session/profile': { session: saved } })
    const { user, queryClient } = renderSettings('profile', { session: PROFILE_SESSION })
    const setQueryData = vi.spyOn(queryClient, 'setQueryData')
    const form = screen.getByRole('form', { name: 'Edit profile' })
    expect(within(form).getByLabelText('Name')).toHaveValue('Ada Admin')
    expect(within(form).getByLabelText('Major')).toHaveValue('Mechanical Engineering')
    expect(within(form).getByLabelText('Graduation year')).toHaveValue('2027')
    expect(within(form).getByLabelText('Phone')).toHaveValue('319-555-0100')
    expect(within(form).getByRole('button', { name: 'Save profile' })).toBeDisabled()

    await user.clear(within(form).getByLabelText('Major'))
    await user.type(within(form).getByLabelText('Major'), 'Biomedical Engineering')
    await user.clear(within(form).getByLabelText('Graduation year'))
    await user.type(within(form).getByLabelText('Graduation year'), '2028')
    await user.clear(within(form).getByLabelText('Phone'))
    await user.click(within(form).getByRole('button', { name: 'Save profile' }))

    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')).toBeTruthy())
    expect(calls.find((c) => c.method === 'PATCH')).toEqual({ method: 'PATCH', url: '/api/v1/session/profile', body: { major: 'Biomedical Engineering', graduation_year: 2028, phone: null } })
    expect(await screen.findByText('Profile saved')).toBeInTheDocument()
    expect(setQueryData).toHaveBeenCalledWith(['session'], saved)
    expect(within(form).getByLabelText('Major')).toHaveValue('Biomedical Engineering')
    expect(within(form).getByRole('button', { name: 'Save profile' })).toBeDisabled()
  })

  it('validates the graduation year locally and maps server field errors', async () => {
    const { calls } = mockApi({
      'PATCH /session/profile': { __error: { status: 400, code: 'validation', error: 'Validation failed.', errors: { name: 'Enter your full name.', phone: 'Enter a valid phone number.' } } },
    })
    const { user } = renderSettings('profile', { session: PROFILE_SESSION })
    const form = screen.getByRole('form', { name: 'Edit profile' })
    await user.clear(within(form).getByLabelText('Graduation year'))
    await user.type(within(form).getByLabelText('Graduation year'), '27')
    await user.click(within(form).getByRole('button', { name: 'Save profile' }))
    expect(await within(form).findByText('Enter a four-digit year, e.g. 2027.')).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'PATCH')).toHaveLength(0)

    await user.clear(within(form).getByLabelText('Graduation year'))
    await user.type(within(form).getByLabelText('Graduation year'), '2027')
    await user.clear(within(form).getByLabelText('Name'))
    await user.type(within(form).getByLabelText('Name'), 'A')
    await user.type(within(form).getByLabelText('Phone'), '1')
    await user.click(within(form).getByRole('button', { name: 'Save profile' }))
    expect(await within(form).findByText('Enter your full name.')).toBeInTheDocument()
    expect(within(form).getByLabelText('Name')).toHaveAttribute('aria-invalid', 'true')
    expect(within(form).getByText('Enter a valid phone number.')).toBeInTheDocument()
    expect(within(form).getByLabelText('Phone')).toHaveValue('319-555-01001')
    expect(screen.queryByText('Profile saved')).not.toBeInTheDocument()
  })
})

describe('Change password form', () => {
  async function fill(user: ReturnType<typeof renderSettings>['user'], current: string, next: string, confirm: string) {
    const form = screen.getByRole('form', { name: 'Change password' })
    await user.type(within(form).getByLabelText('Current password'), current)
    await user.type(within(form).getByLabelText('New password'), next)
    await user.type(within(form).getByLabelText('Confirm new password'), confirm)
    await user.click(within(form).getByRole('button', { name: 'Change password' }))
    return form
  }

  it('changes the password and clears the fields', async () => {
    const { calls } = mockApi({ 'POST /auth/change-password': { changed: true } })
    const { user } = renderSettings('profile')
    const form = await fill(user, 'old-password-1', 'new-password-1', 'new-password-1')
    expect(await screen.findByText('Password changed')).toBeInTheDocument()
    expect(calls.find((c) => c.method === 'POST')).toEqual({
      method: 'POST',
      url: '/api/v1/auth/change-password',
      body: { current_password: 'old-password-1', new_password: 'new-password-1', confirm_password: 'new-password-1' },
    })
    expect(within(form).getByLabelText('Current password')).toHaveValue('')
    expect(within(form).getByLabelText('New password')).toHaveValue('')
    expect(within(form).getByLabelText('Confirm new password')).toHaveValue('')
  })

  it('checks length and match before sending', async () => {
    const { calls } = mockApi({ 'POST /auth/change-password': { changed: true } })
    const { user } = renderSettings('profile')
    const form = await fill(user, 'old-password-1', 'short', 'short')
    expect(await within(form).findByText('Use at least 8 characters.')).toBeInTheDocument()
    await user.clear(within(form).getByLabelText('New password'))
    await user.type(within(form).getByLabelText('New password'), 'long-enough-1')
    await user.click(within(form).getByRole('button', { name: 'Change password' }))
    expect(await within(form).findByText('The passwords do not match.')).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'POST')).toHaveLength(0)
  })

  it('puts a wrong current password on its field and keeps the entries', async () => {
    mockApi({
      'POST /auth/change-password': { __error: { status: 400, code: 'validation', error: 'Validation failed.', errors: { current_password: 'Your current password is incorrect.' } } },
    })
    const { user } = renderSettings('profile')
    const form = await fill(user, 'wrong-password', 'new-password-1', 'new-password-1')
    expect(await within(form).findByText('Your current password is incorrect.')).toBeInTheDocument()
    expect(within(form).getByLabelText('Current password')).toHaveAttribute('aria-invalid', 'true')
    expect(within(form).getByLabelText('New password')).toHaveValue('new-password-1')
    expect(screen.queryByText('Password changed')).not.toBeInTheDocument()
  })
})

describe('Chapter section', () => {
  it('lets an administrator edit and save chapter settings', async () => {
    const { calls } = mockApi({
      'GET /organization': { organization: ORGANIZATION },
      'PATCH /organization': ({ body }: { body: unknown }) => {
        const input = body as { name: string; settings: Record<string, unknown> }
        return { organization: { ...ORGANIZATION, name: input.name, settings: { ...ORGANIZATION.settings, ...input.settings }, updated_at: '2026-09-03T00:00:00Z' } }
      },
    })
    const { user } = renderSettings('chapter')
    const name = await screen.findByLabelText('Chapter name')
    expect(name).toHaveValue('ASME at the University of Iowa')
    expect(screen.getByLabelText('Academic year starts')).toHaveValue('8')
    expect(screen.getByLabelText('Time zone')).toHaveValue('America/Chicago')
    expect(screen.getByLabelText('Default due window (days)')).toHaveValue('7')

    const save = screen.getByRole('button', { name: 'Save changes' })
    await user.clear(name)
    await user.type(name, 'ASME Iowa Chapter')
    await user.selectOptions(screen.getByLabelText('Academic year starts'), '9')
    await user.click(screen.getByLabelText(/Chapter profile is complete/))
    await user.type(screen.getByLabelText('Primary contact email'), 'asme@uiowa.edu')
    await user.click(save)

    await waitFor(() => expect(calls.find((c) => c.method === 'PATCH')).toBeTruthy())
    expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({
      name: 'ASME Iowa Chapter',
      timezone: 'America/Chicago',
      academic_year_start_month: 9,
      logo_url: null,
      settings: {
        profile_completed: true,
        chapter_short_name: 'ASME Iowa',
        primary_contact_email: 'asme@uiowa.edu',
        public_site_url: null,
        default_due_days: 7,
      },
    })
    expect(await screen.findByText('Chapter settings saved')).toBeInTheDocument()
    expect(screen.getByLabelText('Chapter name')).toHaveValue('ASME Iowa Chapter')
  })

  it('puts server validation errors next to the right fields and keeps the entered data', async () => {
    mockApi({
      'GET /organization': { organization: ORGANIZATION },
      'PATCH /organization': {
        __error: {
          status: 400,
          code: 'validation',
          error: 'Validation failed.',
          errors: { name: 'Keep this under 200 characters.', timezone: 'Unknown time zone. Use an IANA name such as America/Chicago.' },
        },
      },
    })
    const { user } = renderSettings('chapter')
    const name = await screen.findByLabelText('Chapter name')
    await user.clear(name)
    await user.type(name, 'Renamed chapter')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByText('Keep this under 200 characters.')).toBeInTheDocument()
    expect(screen.getByLabelText('Chapter name')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Chapter name')).toHaveValue('Renamed chapter')
    expect(screen.getByText('Unknown time zone. Use an IANA name such as America/Chicago.')).toBeInTheDocument()
    expect(screen.getByLabelText('Time zone')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.queryByText('Chapter settings saved')).not.toBeInTheDocument()
  })

  it('validates locally before sending and supports a custom time zone', async () => {
    const { calls } = mockApi({ 'GET /organization': { organization: ORGANIZATION }, 'PATCH /organization': { organization: ORGANIZATION } })
    const { user } = renderSettings('chapter')
    const site = await screen.findByLabelText('Public website')
    await user.type(site, 'not-a-url')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText('Enter a full URL starting with http:// or https://.')).toBeInTheDocument()
    expect(calls.filter((c) => c.method === 'PATCH')).toHaveLength(0)

    await user.selectOptions(screen.getByLabelText('Time zone'), 'Other (type it in)…')
    const custom = screen.getByLabelText('Custom time zone')
    await user.type(custom, 'America/Argentina/Cordoba')
    await user.clear(site)
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    await waitFor(() => expect(calls.filter((c) => c.method === 'PATCH')).toHaveLength(1))
    expect((calls.find((c) => c.method === 'PATCH')?.body as { timezone: string }).timezone).toBe('America/Argentina/Cordoba')
  })

  it('shows a toast and keeps the form when the server rejects with 403', async () => {
    mockApi({
      'GET /organization': { organization: ORGANIZATION },
      'PATCH /organization': { __error: { status: 403, code: 'forbidden', error: 'Missing permission chapter.settings.manage.' } },
    })
    const { user } = renderSettings('chapter')
    const name = await screen.findByLabelText('Chapter name')
    await user.type(name, '!')
    await user.click(screen.getByRole('button', { name: 'Save changes' }))
    expect(await screen.findByText('Could not save chapter settings')).toBeInTheDocument()
    expect(screen.getByText('Changes were not saved')).toBeInTheDocument()
    expect(screen.getByLabelText('Chapter name')).toHaveValue('ASME at the University of Iowa!')
  })

  it('asks before discarding unsaved changes', async () => {
    mockApi({ 'GET /organization': { organization: ORGANIZATION } })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const { user } = renderSettings('chapter')
    const name = await screen.findByLabelText('Chapter name')
    expect(screen.getByRole('button', { name: 'Discard' })).toBeDisabled()
    await user.type(name, ' Edited')
    await user.click(screen.getByRole('button', { name: 'Discard' }))
    expect(confirm).toHaveBeenCalled()
    expect(name).toHaveValue('ASME at the University of Iowa Edited')
    confirm.mockReturnValue(true)
    await user.click(screen.getByRole('button', { name: 'Discard' }))
    expect(name).toHaveValue('ASME at the University of Iowa')
    confirm.mockRestore()
  })

  it('shows a read-only summary to members without chapter.settings.manage', async () => {
    mockApi({ 'GET /organization': { organization: ORGANIZATION } })
    renderSettings('chapter', { session: memberSession() })
    expect(await screen.findByText('Chapter settings are managed by chapter administrators. You can review them here.')).toBeInTheDocument()
    expect(screen.getByText('ASME at the University of Iowa')).toBeInTheDocument()
    expect(screen.getByText('August')).toBeInTheDocument()
    expect(screen.getByText('7 days')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save changes' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Chapter name')).not.toBeInTheDocument()
  })

  it('shows an error with retry when the organization cannot be loaded', async () => {
    let attempts = 0
    mockApi({
      'GET /organization': () => {
        attempts += 1
        return attempts === 1 ? { __error: { status: 500, code: 'server_error', error: 'Try again later.' } } : { organization: ORGANIZATION }
      },
    })
    const { user } = renderSettings('chapter')
    expect(await screen.findByText('Chapter settings could not be loaded')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByLabelText('Chapter name')).toBeInTheDocument()
  })
})

describe('Roles section', () => {
  it('lists roles with member counts and expands grants grouped by scope', async () => {
    mockApi({ 'GET /roles': { items: ROLES, roles: ROLES, next_cursor: null, total: ROLES.length } })
    const { user } = renderSettings('roles')
    const list = await screen.findByRole('list', { name: 'Roles' })
    const rows = within(list).getAllByRole('listitem')
    expect(rows).toHaveLength(3)
    expect(within(rows[1]).getByText('12 members · 3 grants')).toBeInTheDocument()
    expect(within(rows[2]).getByText('Custom')).toBeInTheDocument()

    const toggle = within(rows[1]).getByRole('button', { name: /Full Member/ })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await user.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(within(rows[1]).getByText('Own records')).toBeInTheDocument()
    expect(within(within(rows[1]).getByRole('list', { name: 'Full Member grants at own scope' })).getByText('work_order.edit')).toBeInTheDocument()
    expect(within(within(rows[1]).getByRole('list', { name: 'Full Member grants at assigned scope' })).getByText('work_order.start')).toBeInTheDocument()

    await user.click(within(rows[2]).getByRole('button', { name: /Alumni Mentor/ }))
    expect(within(rows[2]).getByText('This role has no grants.')).toBeInTheDocument()
  })

  it('shows an inline error with retry', async () => {
    let attempts = 0
    mockApi({
      'GET /roles': () => {
        attempts += 1
        return attempts === 1 ? { __error: { status: 500, code: 'server_error', error: 'Boom.' } } : { items: ROLES, next_cursor: null, total: 3 }
      },
    })
    const { user } = renderSettings('roles')
    expect(await screen.findByText('Roles could not be loaded')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByRole('list', { name: 'Roles' })).toBeInTheDocument()
  })
})
