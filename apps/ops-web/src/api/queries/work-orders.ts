import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type Params } from '../client'
import {
  CompleteResponse,
  WorkOrderDetail,
  WorkOrderList,
  type CompleteInput,
  type CostEntryInput,
  type TimeEntryInput,
  type TransitionAction,
  type WorkOrderInput,
  type WorkOrderListParams,
} from '../contracts/work-orders'

export const workOrderKeys = {
  all: ['work-orders'] as const,
  lists: () => ['work-orders', 'list'] as const,
  list: (params: WorkOrderListParams) => ['work-orders', 'list', params] as const,
  detail: (id: string) => ['work-orders', 'detail', id] as const,
  search: (q: string) => ['work-orders', 'search', q] as const,
}

export function workOrderListQuery(params: WorkOrderListParams, cursor?: string | null): Params {
  const query: Params = {
    q: params.q,
    tab: params.tab,
    sort: params.sort,
    limit: params.limit ?? 50,
    cursor: cursor ?? undefined,
  }
  for (const [name, values] of Object.entries(params.filters ?? {})) {
    if (values && values.length) query[`filter[${name}]`] = values
  }
  return query
}

/** Cursor-paginated list; the first page also carries the To Do / Done tab counts. */
export function useWorkOrders(params: WorkOrderListParams, options: { enabled?: boolean } = {}) {
  return useInfiniteQuery({
    queryKey: workOrderKeys.list(params),
    queryFn: async ({ pageParam }) => WorkOrderList.parse(await api.get('/work-orders', { params: workOrderListQuery(params, pageParam) })),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    placeholderData: keepPreviousData,
    enabled: options.enabled ?? true,
  })
}

async function fetchDetail(id: string) {
  return WorkOrderDetail.parse((await api.get<{ work_order: unknown }>(`/work-orders/${id}`)).work_order)
}

export function useWorkOrder(id: string | undefined) {
  return useQuery({
    queryKey: workOrderKeys.detail(id ?? ''),
    queryFn: () => fetchDetail(id!),
    enabled: Boolean(id),
  })
}

/** Typeahead for dependency and parent pickers (`GET /work-orders?q=&limit=10`). */
export async function searchWorkOrders(q: string, signal?: AbortSignal) {
  const payload = WorkOrderList.parse(await api.get('/work-orders', { params: { q, limit: 10 }, signal }))
  return payload.items
}

function parseDetail(payload: { work_order: unknown }) {
  return WorkOrderDetail.parse(payload.work_order)
}

function useWorkOrderCache() {
  const client = useQueryClient()
  return {
    /** Store the fresh detail and refresh every list (counts, rows, children of the parent). */
    settle: async (detail?: WorkOrderDetail) => {
      if (detail) client.setQueryData(workOrderKeys.detail(detail.id), detail)
      await client.invalidateQueries({ queryKey: workOrderKeys.all })
    },
  }
}

export function useCreateWorkOrder() {
  const cache = useWorkOrderCache()
  return useMutation({
    mutationFn: async (input: WorkOrderInput) => parseDetail(await api.post<{ work_order: unknown }>('/work-orders', input)),
    onSuccess: (detail) => cache.settle(detail),
  })
}

export function useCreateSubWorkOrder(parentId: string) {
  const cache = useWorkOrderCache()
  return useMutation({
    mutationFn: async (input: WorkOrderInput) => parseDetail(await api.post<{ work_order: unknown }>(`/work-orders/${parentId}/sub-work-orders`, input)),
    onSuccess: () => cache.settle(),
  })
}

export function useUpdateWorkOrder(id: string) {
  const cache = useWorkOrderCache()
  return useMutation({
    mutationFn: async (input: Partial<WorkOrderInput>) => parseDetail(await api.patch<{ work_order: unknown }>(`/work-orders/${id}`, input)),
    onSuccess: (detail) => cache.settle(detail),
  })
}

export function useTransitionWorkOrder(id: string) {
  const cache = useWorkOrderCache()
  return useMutation({
    mutationFn: async ({ action, note }: { action: TransitionAction; note?: string }) => parseDetail(await api.post<{ work_order: unknown }>(`/work-orders/${id}/${action}`, note ? { note } : {})),
    onSuccess: (detail) => cache.settle(detail),
  })
}

export function useCompleteWorkOrder(id: string) {
  const cache = useWorkOrderCache()
  return useMutation({
    mutationFn: async (input: CompleteInput) => CompleteResponse.parse(await api.post(`/work-orders/${id}/complete`, input)),
    onSuccess: (result) => cache.settle(result.work_order),
  })
}

export function useDuplicateWorkOrder() {
  const cache = useWorkOrderCache()
  return useMutation({
    mutationFn: async (id: string) => parseDetail(await api.post<{ work_order: unknown }>(`/work-orders/${id}/duplicate`)),
    onSuccess: (detail) => cache.settle(detail),
  })
}

export function useSetAssignees(id: string) {
  const cache = useWorkOrderCache()
  return useMutation({
    mutationFn: async (input: { user_ids: number[]; team_ids: string[] }) => parseDetail(await api.put<{ work_order: unknown }>(`/work-orders/${id}/assignees`, input)),
    onSuccess: (detail) => cache.settle(detail),
  })
}

export function useSetWatchers(id: string) {
  const cache = useWorkOrderCache()
  return useMutation({
    mutationFn: async (input: { user_ids: number[] }) => parseDetail(await api.put<{ work_order: unknown }>(`/work-orders/${id}/watchers`, input)),
    onSuccess: (detail) => cache.settle(detail),
  })
}

export function useWatchWorkOrder(id: string) {
  const cache = useWorkOrderCache()
  return useMutation({
    mutationFn: async (watch: boolean) =>
      parseDetail(watch ? await api.post<{ work_order: unknown }>(`/work-orders/${id}/watch`) : await api.delete<{ work_order: unknown }>(`/work-orders/${id}/watch`)),
    onSuccess: (detail) => cache.settle(detail),
  })
}

export function useAddTimeEntry(id: string) {
  const cache = useWorkOrderCache()
  return useMutation({
    mutationFn: async (input: TimeEntryInput) => parseDetail(await api.post<{ work_order: unknown }>(`/work-orders/${id}/time-entries`, input)),
    onSuccess: (detail) => cache.settle(detail),
  })
}

export function useDeleteTimeEntry(id: string) {
  const cache = useWorkOrderCache()
  return useMutation({
    mutationFn: async (entryId: string) => parseDetail(await api.delete<{ work_order: unknown }>(`/work-orders/${id}/time-entries/${entryId}`)),
    onSuccess: (detail) => cache.settle(detail),
  })
}

export function useAddCostEntry(id: string) {
  const cache = useWorkOrderCache()
  return useMutation({
    mutationFn: async (input: CostEntryInput) => parseDetail(await api.post<{ work_order: unknown }>(`/work-orders/${id}/cost-entries`, input)),
    onSuccess: (detail) => cache.settle(detail),
  })
}

export function useDeleteCostEntry(id: string) {
  const cache = useWorkOrderCache()
  return useMutation({
    mutationFn: async (entryId: string) => parseDetail(await api.delete<{ work_order: unknown }>(`/work-orders/${id}/cost-entries/${entryId}`)),
    onSuccess: (detail) => cache.settle(detail),
  })
}

export function useAddDependency(id: string) {
  const cache = useWorkOrderCache()
  return useMutation({
    mutationFn: async (blockingWorkOrderId: string) => parseDetail(await api.post<{ work_order: unknown }>(`/work-orders/${id}/dependencies`, { blocking_work_order_id: blockingWorkOrderId })),
    onSuccess: (detail) => cache.settle(detail),
  })
}

export function useRemoveDependency(id: string) {
  const cache = useWorkOrderCache()
  return useMutation({
    mutationFn: async (dependencyId: string) => parseDetail(await api.delete<{ work_order: unknown }>(`/work-orders/${id}/dependencies/${dependencyId}`)),
    onSuccess: (detail) => cache.settle(detail),
  })
}
