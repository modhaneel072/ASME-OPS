import { DEFAULT_PART_SORT, PART_SORTS, type PartSort } from '@/api/contracts/parts'

/** The three list tabs; each one is a `filter[stock]` value the server understands. */
export const PART_TABS = ['all', 'low', 'out'] as const
export type PartTab = (typeof PART_TABS)[number]

export const TAB_LABELS: Record<PartTab, string> = { all: 'All', low: 'Low stock', out: 'Out of stock' }

/** `filter[stock]` for a tab; the All tab does not filter by stock at all. */
export function stockFilterFor(tab: PartTab): string[] | undefined {
  return tab === 'all' ? undefined : [tab]
}

export const FILTER_KEYS = ['type', 'location', 'vendor'] as const
export type FilterKey = (typeof FILTER_KEYS)[number]
export type PartFilters = Record<FilterKey, string[]>

export function readTab(params: URLSearchParams): PartTab {
  const raw = params.get('tab')
  return (PART_TABS as readonly string[]).includes(raw ?? '') ? (raw as PartTab) : 'all'
}

export function readSort(params: URLSearchParams): PartSort {
  const raw = params.get('sort')
  return (PART_SORTS as readonly string[]).includes(raw ?? '') ? (raw as PartSort) : DEFAULT_PART_SORT
}

/** `filter[type]=a,b` → `['a','b']`; repeated keys merge, as on the server. */
export function readFilters(params: URLSearchParams): PartFilters {
  const filters = {} as PartFilters
  for (const key of FILTER_KEYS) {
    const values = params
      .getAll(`filter[${key}]`)
      .flatMap((raw) => raw.split(','))
      .map((value) => value.trim())
      .filter(Boolean)
    filters[key] = Array.from(new Set(values))
  }
  return filters
}

/** `filter[critical]=true` narrows to critical parts; absent means "all parts". */
export function readCritical(params: URLSearchParams): 'true' | undefined {
  return params.get('filter[critical]') === 'true' ? 'true' : undefined
}

export function hasActiveFilters(filters: PartFilters, critical: 'true' | undefined): boolean {
  return Boolean(critical) || FILTER_KEYS.some((key) => filters[key].length > 0)
}

export function writeFilter(params: URLSearchParams, key: FilterKey, values: string[]): URLSearchParams {
  const next = new URLSearchParams(params)
  next.delete(`filter[${key}]`)
  if (values.length) next.set(`filter[${key}]`, values.join(','))
  return next
}

export function writeCritical(params: URLSearchParams, on: boolean): URLSearchParams {
  const next = new URLSearchParams(params)
  if (on) next.set('filter[critical]', 'true')
  else next.delete('filter[critical]')
  return next
}

export function writeTab(params: URLSearchParams, tab: PartTab): URLSearchParams {
  const next = new URLSearchParams(params)
  if (tab === 'all') next.delete('tab')
  else next.set('tab', tab)
  return next
}

export function writeSort(params: URLSearchParams, sort: PartSort): URLSearchParams {
  const next = new URLSearchParams(params)
  if (sort === DEFAULT_PART_SORT) next.delete('sort')
  else next.set('sort', sort)
  return next
}

export function clearFilters(params: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(params)
  for (const key of FILTER_KEYS) next.delete(`filter[${key}]`)
  next.delete('filter[critical]')
  next.delete('q')
  return next
}

/** Search string carried between list and detail links (pane state stays behind). */
export function listSearch(params: URLSearchParams): string {
  const next = new URLSearchParams(params)
  next.delete('pane')
  const text = next.toString()
  return text ? `?${text}` : ''
}

/** Clicking a sortable column header: same column flips direction, a new one starts ascending. */
export function nextSort(current: PartSort, column: 'name' | 'sku' | 'available' | 'updated_at'): PartSort {
  const descending: PartSort = `-${column}` as PartSort
  if (current === column) return descending
  if (current === descending) return column as PartSort
  // Stock and recency read best newest/largest first.
  return column === 'available' || column === 'updated_at' ? descending : (column as PartSort)
}

export function sortDirection(current: PartSort, column: string): 'ascending' | 'descending' | undefined {
  if (current === column) return 'ascending'
  if (current === `-${column}`) return 'descending'
  return undefined
}
