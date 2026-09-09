import { expect, test, type APIRequestContext } from '@playwright/test'

/**
 * Scenario 12 – the legacy public site, portal, kiosk and JSON routes keep
 * working (or redirect) after ASME Ops was added. These are HTTP-level checks
 * against the Flask server itself, so they run against E2E_API_URL (default
 * http://127.0.0.1:5000) regardless of which origin serves the SPA.
 */
const API = process.env.E2E_API_URL ?? 'http://127.0.0.1:5000'

async function status(request: APIRequestContext, path: string, init: Parameters<APIRequestContext['fetch']>[1] = {}) {
  return request.fetch(`${API}${path}`, { maxRedirects: 0, ...init })
}

test.describe('legacy compatibility', () => {
  test('public site pages respond', async ({ request }) => {
    for (const path of ['/', '/who-we-are', '/executive-team', '/projects', '/events', '/gallery', '/join', '/contact', '/sponsors', '/login', '/signup', '/forgot-password', '/healthz']) {
      const response = await status(request, path)
      expect(response.status(), path).toBe(200)
    }
  })

  test('portal and kiosk routes still gate and render', async ({ request }) => {
    const portal = await status(request, '/portal')
    expect([301, 302, 303]).toContain(portal.status())
    expect(portal.headers()['location']).toContain('/login')
    const kiosk = await status(request, '/kiosk')
    expect(kiosk.status()).toBe(200)
    const checkin = await status(request, '/checkin')
    expect([200, 302]).toContain(checkin.status())
  })

  test('legacy ops aliases redirect while /app serves ASME Ops', async ({ request }) => {
    for (const path of ['/dashboard', '/inventory', '/prints', '/calendar', '/legacy/app']) {
      const response = await status(request, path)
      expect([301, 302, 303], path).toContain(response.status())
    }
    const app = await status(request, '/app/work-orders/anything')
    expect(app.status()).toBe(200)
    expect(app.headers()['content-type']).toContain('text/html')
    expect(app.headers()['cache-control']).toContain('no-store')
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
