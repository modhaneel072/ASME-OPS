/**
 * TanStack Query hooks for `/purchase-requests` and `/purchasing/settings`.
 *
 * The list is cursor-paginated and its first page carries the `tabs` counts.
 * Every mutation stores the fresh detail it gets back and then invalidates the
 * lists, because an action changes both the row and the tab counts. The part
 * picker reads `GET /parts` through a deliberately small schema so the purchase
 * request screens do not depend on the shape of the Parts feature.
 */

import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Params } from '../client'
import {
  PartPickerList,
  PurchaseRequestDetail,
  PurchaseRequestList,
  PurchasingSettings,
  type PurchaseRequestAction,
  type PurchaseRequestListParams,
  type PurchaseRequestPayload,
  type PurchasingSettingsPayload,
  PURCHASE_REQUEST_ACTION_PATHS,
} from '../contracts/purchaseRequests'

const PAGE_SIZE = 50

export const purchaseRequestKeys = {
  all: ['purchase-requests'] as const,
  lists: ['purchase-requests', 'list'] as const,
  list: (params: PurchaseRequestListParams) => ['purchase-requests', 'list', params] as const,
  detail: (id: string) => ['purchase-requests', 'detail', id] as const,
  partOptions: (q: string) => ['purchase-requests', 'part-options', q] as const,
  settings: ['purchasing', 'settings'] as const,
}

export function purchaseRequestListQuery(params: PurchaseRequestListParams, cursor?: string | null): Params {
  return {
    q: params.q,
    tab: params.tab,
    'filter[status]': params.status,
    'filter[project]': params.project,
    'filter[vendor]': params.vendor,
    'filter[requester]': params.requester,
    sort: params.sort,
    limit: params.limit ?? PAGE_SIZE,
    cursor: cursor ?? undefined,
  }
}

/** Cursor-paginated list; the first page also carries the tab counts. */
export function usePurchaseRequests(params: PurchaseRequestListParams, options: { enabled?: boolean } = {}) {
  return useInfiniteQuery({
    queryKey: purchaseRequestKeys.list(params),
    queryFn: async ({ pageParam }) => PurchaseRequestList.parse(await api.get('/purchase-requests', { params: purchaseRequestListQuery(params, pageParam) })),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    placeholderData: keepPreviousData,
    enabled: options.enabled ?? true,
  })
}

function parseDetail(payload: { purchase_request: unknown }) {
  return PurchaseRequestDetail.parse(payload.purchase_request)
}

export function usePurchaseRequest(id: string | undefined) {
  return useQuery({
    queryKey: purchaseRequestKeys.detail(id ?? ''),
    queryFn: async () => parseDetail(await api.get<{ purchase_request: unknown }>(`/purchase-requests/${id}`)),
    enabled: Boolean(id),
  })
}

function usePurchaseRequestCache() {
  const client = useQueryClient()
  return async (detail?: PurchaseRequestDetail) => {
    if (detail) client.setQueryData(purchaseRequestKeys.detail(detail.id), detail)
    await Promise.all([client.invalidateQueries({ queryKey: purchaseRequestKeys.all }), client.invalidateQueries({ queryKey: ['parts'] }), client.invalidateQueries({ queryKey: ['notifications'] })])
  }
}

export function useCreatePurchaseRequest() {
  const settle = usePurchaseRequestCache()
  return useMutation({
    mutationFn: async (input: PurchaseRequestPayload) => parseDetail(await api.post<{ purchase_request: unknown }>('/purchase-requests', input)),
    onSuccess: (detail) => settle(detail),
  })
}

/** `PATCH /purchase-requests/:id` - drafts only; `items` replaces every line. */
export function useUpdatePurchaseRequest(id: string) {
  const settle = usePurchaseRequestCache()
  return useMutation({
    mutationFn: async (input: Partial<PurchaseRequestPayload>) => parseDetail(await api.patch<{ purchase_request: unknown }>(`/purchase-requests/${id}`, input)),
    onSuccess: (detail) => settle(detail),
  })
}

/** One hook for every workflow action; the body shape depends on the action. */
export function usePurchaseRequestAction(id: string) {
  const settle = usePurchaseRequestCache()
  return useMutation({
    mutationFn: async ({ action, body }: { action: PurchaseRequestAction; body?: unknown }) =>
      parseDetail(await api.post<{ purchase_request: unknown }>(`/purchase-requests/${id}/${PURCHASE_REQUEST_ACTION_PATHS[action]}`, body ?? {})),
    onSuccess: (detail) => settle(detail),
  })
}

/** Line-item part picker. Only enabled while the picker is open. */
export function usePartPicker(q: string, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: purchaseRequestKeys.partOptions(q),
    queryFn: async () => PartPickerList.parse(await api.get('/parts', { params: { q: q || undefined, 'filter[active]': 'true', sort: 'name', limit: 25 } })).items,
    enabled: options.enabled ?? true,
    placeholderData: keepPreviousData,
    staleTime: 30 * 1000,
  })
}

export function usePurchasingSettings(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: purchaseRequestKeys.settings,
    queryFn: async () => PurchasingSettings.parse((await api.get<{ purchasing: unknown }>('/purchasing/settings')).purchasing),
    enabled: options.enabled ?? true,
  })
}

export function useUpdatePurchasingSettings() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (input: PurchasingSettingsPayload) => PurchasingSettings.parse((await api.put<{ purchasing: unknown }>('/purchasing/settings', input)).purchasing),
    onSuccess: (settings) => {
      client.setQueryData(purchaseRequestKeys.settings, settings)
      return client.invalidateQueries({ queryKey: ['session'] })
    },
  })
}
