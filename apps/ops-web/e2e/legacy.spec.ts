import { expect, test, type APIRequestContext } from '@playwright/test'

/**
 * Scenario 12 – the repository serves only ASME Ops. The former public website,
 * member/admin portal, kiosk, standalone sign-in pages and legacy ops aliases
 * are gone, /app serves the SPA (including its signed-out account pages) and
 * the JSON APIs keep their envelopes. These are HTTP-level checks against the
 * Flask server itself, so they run against E2E_API_URL (default
 * http://127.0.0.1:5000) regardless of which origin serves the SPA.
 */
const API = process.env.E2E_API_URL ?? 'http://127.0.0.1:5000'

const REMOVED_PAGES = [
  '/who-we-are',
  '/executive-team',
  '/projects',
  '/events',
  '/gallery',
  '/join',
  '/contact',
  '/sponsors',
  '/portal',
  '/kiosk',
  '/checkin',
  '/login',
  '/signup',
  '/admin-login',
  '/logout',
  '/forgot-password',
  '/reset-password/some-token',
  '/dashboard',
  '/inventory',
  '/prints',
  '/calendar',
  '/legacy/app',
]

async function status(request: APIRequestContext, path: string, init: Parameters<APIRequestContext['fetch']>[1] = {}) {
  return request.fetch(`${API}${path}`, { maxRedirects: 0, ...init })
}

test.describe('ASME Ops only', () => {
  test('removed website, portal, kiosk and sign-in pages are not served', async ({ request }) => {
    const root = await status(request, '/')
    expect(root.status()).toBe(302)
    expect(root.headers()['location']).toBe('/app')
    for (const path of REMOVED_PAGES) {
      const response = await status(request, path)
      expect(response.status(), path).toBe(404)
    }
  })

  test('/app serves ASME Ops, including the signed-out account pages', async ({ request }) => {
    for (const path of ['/app/work-orders/anything', '/app/auth/login', '/app/auth/forgot-password', '/app/auth/reset-password?token=abc']) {
      const app = await status(request, path)
      expect(app.status(), path).toBe(200)
      expect(app.headers()['content-type'], path).toContain('text/html')
      expect(app.headers()['cache-control'], path).toContain('no-store')
    }
    const health = await status(request, '/healthz')
    expect(health.status()).toBe(200)
  })

  test('legacy and ops JSON APIs keep their envelopes', async ({ request }) => {
    const health = await status(request, '/api/v1/health')
    expect(health.status()).toBe(200)
    expect((await health.json()).ok).toBe(true)

    const me = await status(request, '/api/v1/me')
    expect(me.status()).toBe(401)
    expect((await me.json()).code).toBe('login_required')

    const session = await status(request, '/api/v1/session')
    expect(session.status()).toBe(401)

    const missing = await status(request, '/api/v1/does-not-exist')
    expect(missing.status()).toBe(404)
    expect(await missing.json()).toEqual({ ok: false, code: 'not_found', error: 'Not found.' })

    const formPost = await status(request, '/api/v1/work-orders', { method: 'POST', form: { title: 'x' } })
    expect([401, 415]).toContain(formPost.status())
  })
})
