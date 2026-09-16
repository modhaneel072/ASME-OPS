/**
 * The purchase-request list keeps its whole state in the URL - tab, search,
 * sort, filters and which pane is open - so a link restores exactly what the
 * sender was looking at and the browser's Back button does the right thing.
 */

import {
  DEFAULT_PURCHASE_REQUEST_SORT,
  DEFAULT_PURCHASE_REQUEST_TAB,
  PURCHASE_REQUEST_SORTS,
  PURCHASE_REQUEST_TABS,
  type PurchaseRequestSort,
  type PurchaseRequestTab,
} from '@/api/contracts/purchaseRequests'

export type FilterKey = 'status' | 'project' | 'vendor'
export const FILTER_KEYS: readonly FilterKey[] = ['status', 'project', 'vendor']

export type Filters = Record<FilterKey, string[]>

export interface ListState {
  tab: PurchaseRequestTab
  sort: PurchaseRequestSort
  q: string
  filters: Filters
}

function filterParam(key: FilterKey): string {
  return `filter[${key}]`
}

export function readTab(params: URLSearchParams): PurchaseRequestTab {
  const raw = params.get('tab')
  return raw && (PURCHASE_REQUEST_TABS as readonly string[]).includes(raw) ? (raw as PurchaseRequestTab) : DEFAULT_PURCHASE_REQUEST_TAB
}

export function readSort(params: URLSearchParams): PurchaseRequestSort {
  const raw = params.get('sort')
  return raw && (PURCHASE_REQUEST_SORTS as readonly string[]).includes(raw) ? (raw as PurchaseRequestSort) : DEFAULT_PURCHASE_REQUEST_SORT
}

export function readFilters(params: URLSearchParams): Filters {
  const filters = {} as Filters
  for (const key of FILTER_KEYS) {
    const raw = params.get(filterParam(key))
    filters[key] = raw ? raw.split(',').map((value) => value.trim()).filter(Boolean) : []
  }
  return filters
}

export function readListState(params: URLSearchParams): ListState {
  return { tab: readTab(params), sort: readSort(params), q: (params.get('q') ?? '').trim(), filters: readFilters(params) }
}

export function withParam(params: URLSearchParams, key: string, value: string | null): URLSearchParams {
  const next = new URLSearchParams(params)
  if (value) next.set(key, value)
  else next.delete(key)
  return next
}

export function withFilter(params: URLSearchParams, key: FilterKey, values: string[]): URLSearchParams {
  return withParam(params, filterParam(key), values.length ? values.join(',') : null)
}

export function clearFilters(params: URLSearchParams): URLSearchParams {
  const next = new URLSearchParams(params)
  next.delete('q')
  for (const key of FILTER_KEYS) next.delete(filterParam(key))
  return next
}

export function hasActiveFilters(state: ListState): boolean {
  return FILTER_KEYS.some((key) => state.filters[key].length > 0)
}

/** The list's own query string, with any open pane dropped. */
export function listSearch(params: URLSearchParams): string {
  const next = new URLSearchParams(params)
  next.delete('pane')
  const text = next.toString()
  return text ? `?${text}` : ''
}
