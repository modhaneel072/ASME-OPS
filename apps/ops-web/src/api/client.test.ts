import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, buildQuery, fieldErrors } from './client'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })
}

describe('api client', () => {
  afterEach(() => vi.restoreAllMocks())

  it('unwraps the success envelope and sends JSON with credentials', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ ok: true, payload: { hello: 'world' } }))
    const payload = await api.post<{ hello: string }>('/things', { a: 1 })
    expect(payload).toEqual({ hello: 'world' })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/v1/things')
    expect(init?.method).toBe('POST')
    expect(init?.credentials).toBe('same-origin')
    expect((init?.headers as Record<string, string>)['Content-Type']).toBe('application/json')
    expect(init?.body).toBe(JSON.stringify({ a: 1 }))
  })

  it('throws ApiError with code, message and field errors on failure', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ ok: false, code: 'validation', error: 'Fix fields.', errors: { title: 'Required' } }, 400))
    const error = await api.post('/things', {}).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    const apiError = error as ApiError
    expect(apiError.status).toBe(400)
    expect(apiError.code).toBe('validation')
    expect(apiError.isValidation).toBe(true)
    expect(fieldErrors(apiError)).toEqual({ title: 'Required' })
  })

  it('maps non-JSON failures and network errors to ApiError', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('<html>', { status: 502, headers: { 'content-type': 'text/html' } }))
    const gateway = (await api.get('/x').catch((e: unknown) => e)) as ApiError
    expect(gateway.code).toBe('http_502')

    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    const network = (await api.get('/x').catch((e: unknown) => e)) as ApiError
    expect(network.code).toBe('network_error')
    expect(network.status).toBe(0)
  })

  it('returns top-level extras alongside the payload', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ ok: true, payload: { items: [] }, tabs: { todo: 3, done: 1 } }))
    const { payload, extras } = await api.request<{ items: unknown[] }>('GET', '/work-orders')
    expect(payload.items).toEqual([])
    expect(extras.tabs).toEqual({ todo: 3, done: 1 })
  })

  it('sends multipart uploads with the required header and no JSON content type', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ ok: true, payload: {} }))
    const form = new FormData()
    form.append('file', new Blob(['x']), 'a.txt')
    await api.upload('/attachments', form)
    const headers = fetchMock.mock.calls[0][1]?.headers as Record<string, string>
    expect(headers['X-Requested-With']).toBe('ASME-Ops')
    expect(headers['Content-Type']).toBeUndefined()
  })

  it('builds query strings, joining arrays with commas and skipping empties', () => {
    expect(buildQuery({ q: 'rover', 'filter[status]': ['open', 'in_progress'], empty: '', missing: undefined, none: null, limit: 50 })).toBe('?q=rover&filter%5Bstatus%5D=open%2Cin_progress&limit=50')
    expect(buildQuery(undefined)).toBe('')
  })
})
