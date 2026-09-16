import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo } from 'react'
import { api, type Params } from '../client'
import {
  CreatedPurchaseRequests,
  CycleCountResult,
  InventoryTransactionList,
  Part,
  PartDetail,
  PartList,
  PartType,
  PartTypeList,
  type CountPayload,
  type MovementPayload,
  type PartListParams,
  type PartPayload,
  type PartTransactionParams,
  type PartTypeInput,
  type TransferPayload,
  type VendorLinkPayload,
} from '../contracts/parts'
import type { ComboOption } from '@/ui/Form'

export const partKeys = {
  all: ['parts'] as const,
  lists: ['parts', 'list'] as const,
  list: (params: PartListParams) => ['parts', 'list', params] as const,
  detail: (id: string) => ['parts', 'detail', id] as const,
  transactions: (id: string, params: PartTransactionParams) => ['parts', 'transactions', id, params] as const,
  types: ['parts', 'types'] as const,
}

const PAGE_SIZE = 50

export function partListQuery(params: PartListParams, cursor?: string | null): Params {
  return {
    q: params.q,
    'filter[type]': params.type,
    'filter[location]': params.location,
    'filter[vendor]': params.vendor,
    'filter[asset]': params.asset,
    'filter[stock]': params.stock,
    'filter[critical]': params.critical,
    'filter[active]': params.active,
    sort: params.sort ?? 'name',
    limit: params.limit ?? PAGE_SIZE,
    cursor: cursor ?? undefined,
  }
}

/** Cursor-paginated catalogue; every page carries `stock_counts` for the tabs. */
export function useParts(params: PartListParams, options: { enabled?: boolean } = {}) {
  return useInfiniteQuery({
    queryKey: partKeys.list(params),
    queryFn: async ({ pageParam }) => PartList.parse(await api.get('/parts', { params: partListQuery(params, pageParam) })),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    placeholderData: keepPreviousData,
    enabled: options.enabled ?? true,
  })
}

export function usePart(id: string | undefined) {
  return useQuery({
    queryKey: partKeys.detail(id ?? ''),
    queryFn: async () => PartDetail.parse((await api.get<{ part: unknown }>(`/parts/${id}`)).part),
    enabled: Boolean(id),
  })
}

/** Newest-first ledger for one part (`GET /parts/:id/transactions`). */
export function usePartTransactions(id: string | undefined, params: PartTransactionParams = {}, options: { enabled?: boolean } = {}) {
  return useInfiniteQuery({
    queryKey: partKeys.transactions(id ?? '', params),
    queryFn: async ({ pageParam }) =>
      InventoryTransactionList.parse(
        await api.get(`/parts/${id}/transactions`, {
          params: { 'filter[type]': params.type, 'filter[location]': params.location, limit: params.limit ?? 20, cursor: pageParam ?? undefined },
        }),
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    enabled: Boolean(id) && (options.enabled ?? true),
  })
}

export function usePartTypes() {
  return useQuery({
    queryKey: partKeys.types,
    queryFn: async () => PartTypeList.parse(await api.get('/part-types')).items,
    staleTime: 60 * 1000,
  })
}

export function usePartTypeOptions(): { options: ComboOption<string>[]; isLoading: boolean } {
  const query = usePartTypes()
  return useMemo(() => {
    const items = query.data ?? []
    return {
      options: items.map((type) => ({ value: type.id, label: type.name, meta: type.part_count !== undefined ? `${type.part_count} parts` : undefined })),
      isLoading: query.isPending,
    }
  }, [query.data, query.isPending])
}

/**
 * A movement changes stock, so it invalidates far more than the parts cache:
 * work-order part lines, the setup checklist and purchase requests all read the
 * same numbers.
 */
function useInvalidateParts() {
  const client = useQueryClient()
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: partKeys.all }),
      client.invalidateQueries({ queryKey: ['work-order-parts'] }),
      client.invalidateQueries({ queryKey: ['setup'] }),
    ])
}

function useSettlePart() {
  const client = useQueryClient()
  const invalidate = useInvalidateParts()
  return async (detail?: PartDetail) => {
    if (detail) client.setQueryData(partKeys.detail(detail.id), detail)
    await invalidate()
  }
}

async function partDetailCall(method: 'post' | 'patch' | 'put', path: string, body?: unknown): Promise<PartDetail> {
  const payload = await api[method]<{ part: unknown }>(path, body ?? {})
  return PartDetail.parse(payload.part)
}

export function useCreatePart() {
  const settle = useSettlePart()
  return useMutation({
    mutationFn: (input: PartPayload) => partDetailCall('post', '/parts', input),
    onSuccess: settle,
  })
}

export function useUpdatePart(id: string) {
  const settle = useSettlePart()
  return useMutation({
    mutationFn: (input: Partial<PartPayload>) => partDetailCall('patch', `/parts/${id}`, input),
    onSuccess: settle,
  })
}

export function useSetPartVendors(id: string) {
  const settle = useSettlePart()
  return useMutation({
    mutationFn: (vendors: VendorLinkPayload[]) => partDetailCall('put', `/parts/${id}/vendors`, { vendors }),
    onSuccess: settle,
  })
}

export function useSetPartAssets(id: string) {
  const settle = useSettlePart()
  return useMutation({
    mutationFn: (assetIds: string[]) => partDetailCall('put', `/parts/${id}/assets`, { asset_ids: assetIds }),
    onSuccess: settle,
  })
}

export function useCreatePartType() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (input: PartTypeInput) => PartType.parse((await api.post<{ part_type: unknown }>('/part-types', input)).part_type),
    onSuccess: () => client.invalidateQueries({ queryKey: partKeys.types }),
  })
}

/** `POST /parts/:id/transactions` — receipt, issue, return, adjustment or scrap. */
export function useRecordMovement(id: string) {
  const invalidate = useInvalidateParts()
  return useMutation({
    mutationFn: async (input: MovementPayload) => Part.parse((await api.post<{ part: unknown }>(`/parts/${id}/transactions`, input)).part),
    onSuccess: () => invalidate(),
  })
}

export function useTransferStock() {
  const invalidate = useInvalidateParts()
  return useMutation({
    mutationFn: async (input: TransferPayload) => Part.parse((await api.post<{ part: unknown }>('/inventory/transfers', input)).part),
    onSuccess: () => invalidate(),
  })
}

export function useCycleCount() {
  const invalidate = useInvalidateParts()
  return useMutation({
    mutationFn: async (input: CountPayload) => CycleCountResult.parse(await api.post('/inventory/cycle-counts', input)),
    onSuccess: () => invalidate(),
  })
}

/** `POST /purchase-requests/from-low-stock` — one draft per preferred vendor. */
export function useCreatePurchaseRequestsFromLowStock() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (partIds: string[]) => CreatedPurchaseRequests.parse(await api.post('/purchase-requests/from-low-stock', { part_ids: partIds })).purchase_requests,
    onSuccess: () => Promise.all([client.invalidateQueries({ queryKey: partKeys.all }), client.invalidateQueries({ queryKey: ['purchase-requests'] })]),
  })
}
