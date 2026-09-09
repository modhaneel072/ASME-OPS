/**
 * Thin fetch wrapper around the ASME Ops JSON API.
 *
 * Every response uses the envelope `{ ok: true, payload, ...extras }` or
 * `{ ok: false, code, error, errors? }`. `api.get/post/...` return the payload
 * and throw `ApiError` on failure; `api.request` returns payload plus extras
 * for endpoints that add top-level keys (for example work-order tab counts).
 */

export type Params = Record<string, string | number | boolean | null | undefined | Array<string | number>>

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly errors: Record<string, string>
  readonly extra: Record<string, unknown>

  constructor(status: number, code: string, message: string, errors?: Record<string, string>, extra: Record<string, unknown> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.errors = errors ?? {}
    this.extra = extra
  }

  get isAuth(): boolean {
    return this.status === 401
  }

  get isForbidden(): boolean {
    return this.status === 403
  }

  get isNotFound(): boolean {
    return this.status === 404
  }

  get isValidation(): boolean {
    return this.code === 'validation'
  }
}

export interface RequestOptions {
  params?: Params
  body?: unknown
  form?: FormData
  signal?: AbortSignal
  headers?: Record<string, string>
}

export interface Envelope<T> {
  payload: T
  extras: Record<string, unknown>
}

export const API_BASE = '/api/v1'
export const UPLOAD_HEADER = { 'X-Requested-With': 'ASME-Ops' } as const

export function buildQuery(params?: Params): string {
  if (!params) return ''
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    if (Array.isArray(value)) {
      if (value.length === 0) continue
      search.set(key, value.join(','))
    } else {
      search.set(key, String(value))
    }
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

async function parseBody(response: Response): Promise<Record<string, unknown> | null> {
  const type = response.headers.get('content-type') ?? ''
  if (!type.includes('application/json')) return null
  try {
    return (await response.json()) as Record<string, unknown>
  } catch {
    return null
  }
}

export async function request<T>(method: string, path: string, options: RequestOptions = {}): Promise<Envelope<T>> {
  const url = `${API_BASE}${path}${buildQuery(options.params)}`
  const headers: Record<string, string> = { Accept: 'application/json', ...options.headers }
  let body: BodyInit | undefined
  if (options.form) {
    body = options.form
    Object.assign(headers, UPLOAD_HEADER)
  } else if (options.body !== undefined || ['POST', 'PATCH', 'PUT'].includes(method)) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body ?? {})
  }
  let response: Response
  try {
    response = await fetch(url, { method, headers, body, credentials: 'same-origin', signal: options.signal })
  } catch (error) {
    if ((error as Error).name === 'AbortError') throw error
    throw new ApiError(0, 'network_error', 'Could not reach the server. Check your connection and try again.')
  }
  const json = await parseBody(response)
  if (!response.ok || !json || json.ok !== true) {
    const code = (json?.code as string | undefined) ?? (response.status === 0 ? 'network_error' : `http_${response.status}`)
    const message = (json?.error as string | undefined) ?? response.statusText ?? 'Request failed.'
    const { ok: _ok, code: _code, error: _error, errors, ...rest } = json ?? {}
    throw new ApiError(response.status, code, message, errors as Record<string, string> | undefined, rest)
  }
  const { ok: _ok, payload, ...extras } = json
  return { payload: payload as T, extras }
}

export const api = {
  request,
  get: <T>(path: string, options?: RequestOptions) => request<T>('GET', path, options).then((r) => r.payload),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) => request<T>('POST', path, { ...options, body }).then((r) => r.payload),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) => request<T>('PATCH', path, { ...options, body }).then((r) => r.payload),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) => request<T>('PUT', path, { ...options, body }).then((r) => r.payload),
  delete: <T>(path: string, options?: RequestOptions) => request<T>('DELETE', path, options).then((r) => r.payload),
  upload: <T>(path: string, form: FormData, options?: RequestOptions) => request<T>('POST', path, { ...options, form }).then((r) => r.payload),
}

/** Turns a `{ field: message }` map from a validation error into form errors. */
export function fieldErrors(error: unknown): Record<string, string> {
  return error instanceof ApiError && error.isValidation ? error.errors : {}
}

export function errorMessage(error: unknown, fallback = 'Something went wrong.'): string {
  if (error instanceof ApiError) return error.message || fallback
  if (error instanceof Error) return error.message || fallback
  return fallback
}
