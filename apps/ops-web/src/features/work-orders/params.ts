/**
 * URL search params are the source of truth for the Work Orders list: filters,
 * search, sort, tab and view. Links from other screens (e.g.
 * `/work-orders?filter[project]=<id>`) therefore work without extra state.
 */
import type { SavedFilter } from '@/api/contracts/saved-filters'
import { DEFAULT_WORK_ORDER_SORT, WORK_ORDER_FILTER_NAMES, WORK_ORDER_SORT_OPTIONS, type WorkOrderFilterName, type WorkOrderFilters, type WorkOrderSort } from '@/api/contracts/work-orders'

export type ListView = 'panel' | 'table'
export type ListTab = 'todo' | 'done'

export interface ListState {
  q: string
  tab: ListTab
  sort: WorkOrderSort
  view: ListView
  filters: WorkOrderFilters
}

/** Keys the create pane reads to prefill fields; they are not list state. */
export const PREFILL_KEYS = ['parent', 'project', 'category', 'asset', 'location', 'team'] as const

const SORT_VALUES = new Set<string>([...WORK_ORDER_SORT_OPTIONS.map((o) => o.value), '-due_at', 'priority', 'updated_at', 'created_at', '-number', '-title'])

export function filterKey(name: WorkOrderFilterName): string {
  return `filter[${name}]`
}

export function readFilter(params: URLSearchParams, name: WorkOrderFilterName): string[] {
  const raw = params.get(filterKey(name))
  if (!raw) return []
  return raw
    .split(',')
    .map((v) => v.trim())
    .filter(Boolean)
}

export function readListState(params: URLSearchParams): ListState {
  const filters: WorkOrderFilters = {}
  for (const name of WORK_ORDER_FILTER_NAMES) {
    const values = readFilter(params, name)
    if (values.length) filters[name] = values
  }
  const sort = params.get('sort') ?? ''
  return {
    q: params.get('q') ?? '',
    tab: params.get('tab') === 'done' ? 'done' : 'todo',
    sort: (SORT_VALUES.has(sort) ? sort : DEFAULT_WORK_ORDER_SORT) as WorkOrderSort,
    view: params.get('view') === 'table' ? 'table' : 'panel',
    filters,
  }
}

export function withFilter(params: URLSearchParams, name: WorkOrderFilterName, values: string[]): URLSearchParams {
  const next = new URLSearchParams(params)
  if (values.length) next.set(filterKey(name), values.join(','))
  else next.delete(filterKey(name))
  return next
}

export function withParam(params: URLSearchParams, key: string, value: string | null | undefined): URLSearchParams {
  const next = new URLSearchParams(params)
  if (value) next.set(key, value)
  else next.delete(key)
  return next
}

export function hasActiveFilters(state: ListState): boolean {
  return Boolean(state.q) || Object.values(state.filters).some((values) => values && values.length > 0)
}

export function clearFilters(params: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(params)
  for (const name of WORK_ORDER_FILTER_NAMES) next.delete(filterKey(name))
  next.delete('q')
  return next
}

/** Only the list-related keys, as a `?query` string (or empty). Used to build row links and back paths. */
export function listSearch(params: URLSearchParams): string {
  const next = new URLSearchParams()
  for (const [key, value] of params.entries()) {
    if (key === 'q' || key === 'sort' || key === 'tab' || key === 'view' || key.startsWith('filter[')) next.set(key, value)
  }
  const text = next.toString()
  return text ? `?${text}` : ''
}

/** Snapshot of the current params in the shape stored on a saved filter. */
export function savedFilterFromParams(params: URLSearchParams): { filter: Record<string, string>; sort: string; view_type: ListView } {
  const state = readListState(params)
  const filter: Record<string, string> = {}
  for (const [name, values] of Object.entries(state.filters)) if (values && values.length) filter[name] = values.join(',')
  if (state.q) filter.q = state.q
  if (state.tab !== 'todo') filter.tab = state.tab
  return { filter, sort: state.sort, view_type: state.view }
}

/** Applying a saved filter replaces the list params entirely. */
export function paramsFromSavedFilter(saved: SavedFilter): URLSearchParams {
  const next = new URLSearchParams()
  for (const [key, raw] of Object.entries(saved.filter ?? {})) {
    const value = Array.isArray(raw) ? raw.map(String).join(',') : raw === null || raw === undefined ? '' : String(raw)
    if (!value) continue
    if (key === 'q' || key === 'tab') next.set(key, value)
    else if ((WORK_ORDER_FILTER_NAMES as readonly string[]).includes(key)) next.set(`filter[${key}]`, value)
    else if (key.startsWith('filter[')) next.set(key, value)
  }
  if (typeof saved.sort === 'string' && SORT_VALUES.has(saved.sort)) next.set('sort', saved.sort)
  if (saved.view_type === 'table') next.set('view', 'table')
  return next
}
