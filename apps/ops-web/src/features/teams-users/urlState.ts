import { useCallback, useState } from 'react'
import type { SetURLSearchParams } from 'react-router-dom'

/** Route segments of /teams-users/:tab. */
export const TABS = ['teams', 'users', 'roles'] as const
export type Tab = (typeof TABS)[number]

/** `/teams-users` defaults to Teams; anything that is not a known tab is a 404. */
export function parseTab(raw: string | undefined): Tab | null {
  if (raw === undefined) return 'teams'
  return (TABS as readonly string[]).includes(raw) ? (raw as Tab) : null
}

export type ParamChanges = Record<string, string | readonly string[] | null | undefined>

/** Copy of `params` with `changes` applied; empty values remove the key. */
export function withParams(params: URLSearchParams, changes: ParamChanges): URLSearchParams {
  const next = new URLSearchParams(params)
  for (const [key, value] of Object.entries(changes)) {
    if (value === null || value === undefined || value === '' || (Array.isArray(value) && value.length === 0)) next.delete(key)
    else next.set(key, Array.isArray(value) ? value.join(',') : String(value))
  }
  return next
}

/** Comma-separated multi-value param, e.g. `filter[status]=active,invited`. */
export function listParam(params: URLSearchParams, key: string): string[] {
  return (params.get(key) ?? '')
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
}

export function oneOf<T extends string>(raw: string | null, allowed: readonly T[], fallback: T): T {
  return raw !== null && (allowed as readonly string[]).includes(raw) ? (raw as T) : fallback
}

/** True when the key press happened inside a text control, so page shortcuts stay quiet. */
export function isTypingTarget(event: KeyboardEvent): boolean {
  const target = event.target as HTMLElement | null
  return Boolean(target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable))
}

/**
 * Keeps the search box in step with `?q=`: the input updates immediately, the
 * URL after the SearchField debounce, and an external URL change (back button,
 * tab switch, a deep link) flows back into the input. `debounced` is the value
 * lists should query with.
 */
export function useUrlSearch(params: URLSearchParams, setParams: SetURLSearchParams) {
  const urlQuery = params.get('q') ?? ''
  const [query, setQuery] = useState(urlQuery)
  const [seen, setSeen] = useState(urlQuery)
  const [written, setWritten] = useState(urlQuery)
  if (seen !== urlQuery) {
    setSeen(urlQuery)
    if (written !== urlQuery) {
      setQuery(urlQuery)
      setWritten(urlQuery)
    }
  }
  const commit = useCallback(
    (value: string) => {
      if (value === urlQuery) return
      setWritten(value)
      setParams(withParams(params, { q: value }), { replace: true })
    },
    [params, setParams, urlQuery],
  )
  return { query, setQuery, commit, debounced: urlQuery }
}
