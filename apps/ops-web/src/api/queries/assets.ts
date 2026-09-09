import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo } from 'react'
import { api } from '../client'
import {
  Asset,
  AssetHierarchy,
  AssetHistory,
  AssetList,
  AssetOpenWorkOrderList,
  AssetStatusHistory,
  AssetType,
  AssetTypeList,
  type AssetHierarchyParams,
  type AssetListParams,
  type AssetPayload,
  type AssetStatusPayload,
  type AssetTypeInput,
} from '../contracts/assets'
import type { ComboOption } from '@/ui/Form'

export const assetKeys = {
  all: ['assets'] as const,
  list: (params: AssetListParams) => ['assets', 'list', params] as const,
  hierarchy: (params: AssetHierarchyParams) => ['assets', 'hierarchy', params] as const,
  detail: (id: string) => ['assets', 'detail', id] as const,
  history: (id: string) => ['assets', 'history', id] as const,
  openWork: (id: string) => ['assets', 'open-work', id] as const,
  types: ['assets', 'types'] as const,
}

export function useAssets(params: AssetListParams = {}, options: { enabled?: boolean } = {}) {
  return useQuery({
    enabled: options.enabled ?? true,
    queryKey: assetKeys.list(params),
    queryFn: async () =>
      AssetList.parse(
        await api.get('/assets', {
          params: {
            q: params.q,
            'filter[status]': params.status,
            'filter[criticality]': params.criticality,
            'filter[type]': params.type,
            'filter[project]': params.project,
            'filter[location]': params.location,
            'filter[team]': params.team,
            'filter[parent]': params.parent,
            'filter[active]': params.active,
            sort: params.sort ?? 'name',
            limit: params.limit ?? 200,
            cursor: params.cursor,
          },
        }),
      ),
    placeholderData: keepPreviousData,
  })
}

export function useAssetOptions(filter: Pick<AssetListParams, 'project' | 'location'> = {}): { options: ComboOption<string>[]; isLoading: boolean } {
  const query = useAssets({ ...filter, limit: 200 })
  const options = (query.data?.items ?? []).map((asset) => ({ value: asset.id, label: asset.name, meta: asset.code ?? asset.location?.name }))
  return { options, isLoading: query.isPending }
}

/** `GET /assets?view=hierarchy`: active, visible assets as a forest. Only project/location filters apply server-side. */
export function useAssetHierarchy(params: AssetHierarchyParams = {}, options: { enabled?: boolean } = {}) {
  return useQuery({
    enabled: options.enabled ?? true,
    queryKey: assetKeys.hierarchy(params),
    queryFn: async () =>
      AssetHierarchy.parse(await api.get('/assets', { params: { view: 'hierarchy', 'filter[project]': params.project, 'filter[location]': params.location } })),
    placeholderData: keepPreviousData,
  })
}

export function useAsset(id: string | undefined) {
  return useQuery({
    queryKey: assetKeys.detail(id ?? ''),
    queryFn: async () => Asset.parse((await api.get<{ asset: unknown }>(`/assets/${id}`)).asset),
    enabled: Boolean(id),
  })
}

export function useAssetHistory(id: string | undefined, limit = 100) {
  return useQuery({
    queryKey: assetKeys.history(id ?? ''),
    queryFn: async () => AssetHistory.parse(await api.get(`/assets/${id}/history`, { params: { limit } })).items,
    enabled: Boolean(id),
  })
}

/** Open work orders that reference the asset (`GET /work-orders?filter[asset]=…&tab=todo&limit=10`). */
export function useAssetOpenWork(id: string | undefined) {
  return useQuery({
    queryKey: assetKeys.openWork(id ?? ''),
    queryFn: async () => AssetOpenWorkOrderList.parse(await api.get('/work-orders', { params: { 'filter[asset]': id, tab: 'todo', limit: 10, sort: '-updated_at' } })),
    enabled: Boolean(id),
  })
}

export function useAssetTypes() {
  return useQuery({
    queryKey: assetKeys.types,
    queryFn: async () => AssetTypeList.parse(await api.get('/asset-types')).items,
    staleTime: 60 * 1000,
  })
}

export function useAssetTypeOptions(): { options: ComboOption<string>[]; isLoading: boolean; byId: Map<string, AssetType> } {
  const query = useAssetTypes()
  return useMemo(() => {
    const items = query.data ?? []
    return {
      options: items.map((type) => ({ value: type.id, label: type.name, meta: type.asset_count !== undefined ? `${type.asset_count} assets` : undefined })),
      isLoading: query.isPending,
      byId: new Map(items.map((type) => [type.id, type])),
    }
  }, [query.data, query.isPending])
}

function descendantsOf(all: Asset[], id: string): Set<string> {
  const out = new Set<string>([id])
  let grew = true
  while (grew) {
    grew = false
    for (const asset of all) {
      if (asset.parent_id && out.has(asset.parent_id) && !out.has(asset.id)) {
        out.add(asset.id)
        grew = true
      }
    }
  }
  return out
}

/** Parent picker options: every active asset except `excludeId` and its descendants (a parent cycle is rejected by the server too). */
export function useAssetParentOptions(excludeId?: string | null): { options: ComboOption<string>[]; isLoading: boolean } {
  const query = useAssets({ limit: 200 })
  return useMemo(() => {
    const items = query.data?.items ?? []
    const excluded = excludeId ? descendantsOf(items, excludeId) : new Set<string>()
    return {
      options: items.filter((asset) => !excluded.has(asset.id)).map((asset) => ({ value: asset.id, label: asset.name, meta: asset.code ?? asset.location?.name ?? undefined })),
      isLoading: query.isPending,
    }
  }, [query.data, query.isPending, excludeId])
}

function useInvalidateAssets() {
  const client = useQueryClient()
  return () => Promise.all([client.invalidateQueries({ queryKey: assetKeys.all }), client.invalidateQueries({ queryKey: ['setup'] }), client.invalidateQueries({ queryKey: ['locations'] })])
}

export function useCreateAsset() {
  const invalidate = useInvalidateAssets()
  return useMutation({
    mutationFn: async (input: AssetPayload) => Asset.parse((await api.post<{ asset: unknown }>('/assets', input)).asset),
    onSuccess: () => invalidate(),
  })
}

export function useUpdateAsset(id: string) {
  const invalidate = useInvalidateAssets()
  return useMutation({
    mutationFn: async (input: Partial<AssetPayload>) => Asset.parse((await api.patch<{ asset: unknown }>(`/assets/${id}`, input)).asset),
    onSuccess: () => invalidate(),
  })
}

export function useChangeAssetStatus(id: string) {
  const invalidate = useInvalidateAssets()
  return useMutation({
    mutationFn: async (input: AssetStatusPayload) => {
      const payload = await api.post<{ asset: unknown; history: unknown }>(`/assets/${id}/status`, input)
      return { asset: Asset.parse(payload.asset), history: AssetStatusHistory.parse(payload.history) }
    },
    onSuccess: () => invalidate(),
  })
}

export function useCreateAssetType() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (input: AssetTypeInput) => AssetType.parse((await api.post<{ asset_type: unknown }>('/asset-types', input)).asset_type),
    onSuccess: () => client.invalidateQueries({ queryKey: assetKeys.types }),
  })
}
