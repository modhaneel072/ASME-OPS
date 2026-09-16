import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo } from 'react'
import { api } from '../client'
import {
  PartInventory,
  PartPickerList,
  WorkOrderPartsPayload,
  type AddPartPayload,
  type PartLineAction,
  type PartPickerItem,
  type PartQuantityPayload,
  type UpdatePartPayload,
} from '../contracts/workOrderParts'
import { workOrderKeys } from './work-orders'

export const workOrderPartKeys = {
  all: ['work-order-parts'] as const,
  list: (workOrderId: string) => ['work-order-parts', 'list', workOrderId] as const,
  pickers: ['work-order-parts', 'picker'] as const,
  picker: (q: string) => ['work-order-parts', 'picker', q] as const,
  inventories: ['work-order-parts', 'inventory'] as const,
  inventory: (partId: string) => ['work-order-parts', 'inventory', partId] as const,
}

const PART_PICKER_LIMIT = 20

function partsPath(workOrderId: string, suffix = ''): string {
  return `/work-orders/${workOrderId}/parts${suffix}`
}

/** Every part line of a work order plus `readiness_summary` and `parts_outstanding`. */
export function useWorkOrderParts(workOrderId: string | undefined, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: workOrderPartKeys.list(workOrderId ?? ''),
    queryFn: async () => WorkOrderPartsPayload.parse(await api.get(partsPath(workOrderId!))),
    enabled: Boolean(workOrderId) && (options.enabled ?? true),
  })
}

/**
 * Every mutation answers with the whole list, so the cache is replaced rather
 * than patched. Issuing and returning also write cost entries and move stock, so
 * the work-order detail and any parts screen are refreshed too.
 */
function useSettleParts(workOrderId: string) {
  const client = useQueryClient()
  return async (payload: WorkOrderPartsPayload) => {
    client.setQueryData(workOrderPartKeys.list(workOrderId), payload)
    await Promise.all([
      client.invalidateQueries({ queryKey: workOrderKeys.detail(workOrderId) }),
      client.invalidateQueries({ queryKey: ['parts'] }),
      client.invalidateQueries({ queryKey: workOrderPartKeys.pickers }),
      client.invalidateQueries({ queryKey: workOrderPartKeys.inventories }),
    ])
  }
}

async function postParts(path: string, body?: unknown) {
  return WorkOrderPartsPayload.parse(await api.post(path, body ?? {}))
}

export function useAddWorkOrderPart(workOrderId: string) {
  const settle = useSettleParts(workOrderId)
  return useMutation({
    mutationFn: (input: AddPartPayload) => postParts(partsPath(workOrderId), input),
    onSuccess: settle,
  })
}

export function useUpdateWorkOrderPart(workOrderId: string) {
  const settle = useSettleParts(workOrderId)
  return useMutation({
    mutationFn: async ({ lineId, input }: { lineId: string; input: UpdatePartPayload }) =>
      WorkOrderPartsPayload.parse(await api.patch(partsPath(workOrderId, `/${lineId}`), input)),
    onSuccess: settle,
  })
}

export function useRemoveWorkOrderPart(workOrderId: string) {
  const settle = useSettleParts(workOrderId)
  return useMutation({
    mutationFn: async (lineId: string) => WorkOrderPartsPayload.parse(await api.delete(partsPath(workOrderId, `/${lineId}`))),
    onSuccess: settle,
  })
}

/** `reserve`, `release`, `kit`, `stage`, `issue` and `return` share one route shape. */
export function useWorkOrderPartAction(workOrderId: string) {
  const settle = useSettleParts(workOrderId)
  return useMutation({
    mutationFn: ({ lineId, action, input }: { lineId: string; action: PartLineAction; input?: PartQuantityPayload }) =>
      postParts(partsPath(workOrderId, `/${lineId}/${action}`), input),
    onSuccess: settle,
  })
}

export function useReleaseAllWorkOrderParts(workOrderId: string) {
  const settle = useSettleParts(workOrderId)
  return useMutation({
    mutationFn: () => postParts(partsPath(workOrderId, '/release-all')),
    onSuccess: settle,
  })
}

/* Part picker ------------------------------------------------------------------- */

/** Active parts for the add-part picker (`GET /parts`, needs `inventory.read`). */
export function usePartPicker(q: string, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: workOrderPartKeys.picker(q),
    queryFn: async () =>
      PartPickerList.parse(
        await api.get('/parts', { params: { q: q || undefined, 'filter[active]': 'true', sort: 'name', limit: PART_PICKER_LIMIT } }),
      ).items,
    enabled: options.enabled ?? true,
    placeholderData: keepPreviousData,
  })
}

export function usePartPickerOptions(q: string, options: { enabled?: boolean } = {}): {
  items: PartPickerItem[]
  byId: Map<string, PartPickerItem>
  isLoading: boolean
  error: unknown
} {
  const query = usePartPicker(q, options)
  return useMemo(() => {
    const items = query.data ?? []
    return { items, byId: new Map(items.map((part) => [part.id, part])), isLoading: query.isPending && query.fetchStatus !== 'idle', error: query.error }
  }, [query.data, query.isPending, query.fetchStatus, query.error])
}

/** Stock per location for the chosen part (`GET /parts/:id/inventory`). */
export function usePartInventory(partId: string | null | undefined, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: workOrderPartKeys.inventory(partId ?? ''),
    queryFn: async () => PartInventory.parse(await api.get(`/parts/${partId}/inventory`)),
    enabled: Boolean(partId) && (options.enabled ?? true),
  })
}
