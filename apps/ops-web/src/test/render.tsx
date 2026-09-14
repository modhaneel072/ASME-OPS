/**
 * Test helpers shared by feature tests.
 *
 *   const { user } = renderWithProviders(<LocationsPage />, { route: '/locations' })
 *   mockApi({ 'GET /locations': { items: [], next_cursor: null, total: 0 } })
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, type RenderOptions } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactElement, ReactNode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { vi } from 'vitest'
import type { Session } from '@/api/contracts/session'
import { SessionContext } from '@/lib/permissions'
import { ToastProvider } from '@/ui/Toast'

export const ADMIN_SESSION: Session = {
  user: { id: 1, name: 'Ada Admin', email: 'ada@uiowa.edu', avatar_url: null, username: 'ada', legacy_role: 'admin', major: null, graduation_year: null, last_login_at: null },
  organization: {
    id: 'org-1',
    name: 'ASME at the University of Iowa',
    slug: 'uiowa',
    logo_url: null,
    timezone: 'America/Chicago',
    academic_year_start_month: 8,
    settings: {},
    setup_completed_at: null,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
  },
  membership: { id: 'm-1', role: { id: 'r-1', name: 'Chapter Administrator', system_key: 'chapter_admin', is_custom: false }, status: 'active', title: null, joined_at: '2026-09-01T00:00:00Z' },
  permissions: Object.fromEntries(
    [
      'chapter.settings.manage',
      'chapter.setup.manage',
      'user.read',
      'user.manage',
      'role.manage',
      'team.read',
      'team.manage',
      'location.read',
      'location.manage',
      'category.read',
      'category.manage',
      'asset.read',
      'asset.manage',
      'asset.status.update',
      'vendor.read',
      'vendor.manage',
      'project.read',
      'project.read_private',
      'project.create',
      'project.manage',
      'project.archive',
      'milestone.manage',
      'work_order.read_all',
      'work_order.create',
      'work_order.edit',
      'work_order.assign',
      'work_order.start',
      'work_order.complete',
      'work_order.cancel',
      'work_order.comment',
      'work_order.log_time',
      'work_order.attach',
      'saved_filter.share',
      'report.view',
      'report.export',
      'audit.read',
      'notification.read',
    ].map((key) => [key, ['chapter']]),
  ),
  scope: { project_ids: [], team_ids: [], lead_team_ids: [] },
  setup: { banner_dismissed: false, completed: false },
  features: { realtime: 'polling', poll_seconds: 15 },
}

export function memberSession(overrides: Partial<Session> = {}): Session {
  return {
    ...ADMIN_SESSION,
    user: { ...ADMIN_SESSION.user, id: 3, name: 'Mo Member', email: 'mo@uiowa.edu', username: 'mo', legacy_role: 'member' },
    membership: { ...ADMIN_SESSION.membership, id: 'm-3', role: { id: 'r-5', name: 'Full Member', system_key: 'full_member', is_custom: false } },
    permissions: {
      'project.read': ['chapter'],
      'work_order.read_all': ['chapter'],
      'work_order.create': ['chapter'],
      'work_order.comment': ['chapter'],
      'work_order.attach': ['chapter'],
      'team.read': ['chapter'],
      'asset.read': ['chapter'],
      'location.read': ['chapter'],
      'category.read': ['chapter'],
      'vendor.read': ['chapter'],
      'report.view': ['chapter'],
      'notification.read': ['chapter'],
      'work_order.edit': ['own'],
      'work_order.start': ['assigned'],
      'work_order.complete': ['assigned'],
      'work_order.log_time': ['assigned'],
    },
    ...overrides,
  }
}

export interface ProvidersOptions extends Omit<RenderOptions, 'wrapper'> {
  session?: Session | null
  route?: string
  /** Route pattern(s) to mount the element under, e.g. '/locations/:locationId'. Defaults to the route itself. */
  path?: string | string[]
  queryClient?: QueryClient
}

export function createTestQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 }, mutations: { retry: false } } })
}

export function renderWithProviders(ui: ReactElement, { session = ADMIN_SESSION, route = '/', path, queryClient = createTestQueryClient(), ...options }: ProvidersOptions = {}) {
  const patterns = path ? (Array.isArray(path) ? path : [path]) : [route]
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <SessionContext.Provider value={session}>
            <MemoryRouter initialEntries={[route]}>
              <Routes>
                {patterns.map((pattern) => (
                  <Route key={pattern} path={pattern} element={children} />
                ))}
                <Route path="*" element={children} />
              </Routes>
            </MemoryRouter>
          </SessionContext.Provider>
        </ToastProvider>
      </QueryClientProvider>
    )
  }
  return { user: userEvent.setup(), queryClient, ...render(ui, { wrapper: Wrapper, ...options }) }
}

export type MockHandler = unknown | ((init: { url: URL; body: unknown; method: string }) => unknown)

/**
 * Mocks `fetch` for `/api/v1` calls. Keys are "METHOD /path" (path may contain
 * `:param` segments). Values are the payload (wrapped in the success envelope)
 * or a function returning it; return `{ __error: { status, code, error, errors, extra } }`
 * to simulate a failure (`extra` adds top-level envelope keys such as `retry_after`).
 */
export function mockApi(handlers: Record<string, MockHandler>) {
  const entries = Object.entries(handlers).map(([key, handler]) => {
    const [method, pattern] = key.split(' ')
    const regex = new RegExp('^' + pattern.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/:[A-Za-z_]+/g, '[^/]+') + '$')
    return { method, regex, handler }
  })
  const calls: Array<{ method: string; url: string; body: unknown }> = []
  const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url, 'http://test.local')
    const method = (init?.method ?? 'GET').toUpperCase()
    const path = url.pathname.replace(/^\/api\/v1/, '')
    let body: unknown = undefined
    if (typeof init?.body === 'string') {
      try {
        body = JSON.parse(init.body)
      } catch {
        body = init.body
      }
    }
    calls.push({ method, url: url.pathname + url.search, body })
    const match = entries.find((entry) => entry.method === method && entry.regex.test(path))
    if (!match) {
      return new Response(JSON.stringify({ ok: false, code: 'not_found', error: `No mock for ${method} ${path}` }), { status: 404, headers: { 'content-type': 'application/json' } })
    }
    const result = typeof match.handler === 'function' ? await (match.handler as (i: { url: URL; body: unknown; method: string }) => unknown)({ url, body, method }) : match.handler
    const failure = (result as { __error?: { status: number; code: string; error: string; errors?: Record<string, string>; extra?: Record<string, unknown> } } | null)?.__error
    if (failure) {
      return new Response(JSON.stringify({ ok: false, code: failure.code, error: failure.error, errors: failure.errors, ...(failure.extra ?? {}) }), { status: failure.status, headers: { 'content-type': 'application/json' } })
    }
    const { __extras, ...payload } = (result ?? {}) as Record<string, unknown> & { __extras?: Record<string, unknown> }
    return new Response(JSON.stringify({ ok: true, payload, ...(__extras ?? {}) }), { status: 200, headers: { 'content-type': 'application/json' } })
  })
  return { spy, calls }
}
