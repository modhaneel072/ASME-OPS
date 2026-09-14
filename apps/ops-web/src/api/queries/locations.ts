import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import { Location, LocationList, type LocationInput, type LocationListParams, type LocationTreeNode } from '../contracts/locations'

export const locationKeys = {
  all: ['locations'] as const,
  list: (params: LocationListParams) => ['locations', 'list', params] as const,
  tree: () => ['locations', 'tree'] as const,
  detail: (id: string) => ['locations', 'detail', id] as const,
}

export function useLocations(params: LocationListParams) {
  return useQuery({
    queryKey: locationKeys.list(params),
    queryFn: async () =>
      LocationList.parse(
        await api.get('/locations', {
          params: {
            q: params.q,
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

export function useLocationTree() {
  return useQuery({
    queryKey: locationKeys.tree(),
    queryFn: async () => {
      const payload = await api.get<{ items: LocationTreeNode[] }>('/locations', { params: { view: 'tree' } })
      return payload.items
    },
  })
}

export function useLocation(id: string | undefined) {
  return useQuery({
    queryKey: locationKeys.detail(id ?? ''),
    queryFn: async () => Location.parse((await api.get<{ location: unknown }>(`/locations/${id}`)).location),
    enabled: Boolean(id),
  })
}

function useInvalidateLocations() {
  const client = useQueryClient()
  return () => Promise.all([client.invalidateQueries({ queryKey: locationKeys.all }), client.invalidateQueries({ queryKey: ['setup'] })])
}

export function useCreateLocation() {
  const invalidate = useInvalidateLocations()
  return useMutation({
    mutationFn: async (input: LocationInput) => Location.parse((await api.post<{ location: unknown }>('/locations', input)).location),
    onSuccess: () => invalidate(),
  })
}

export function useUpdateLocation(id: string) {
  const invalidate = useInvalidateLocations()
  return useMutation({
    mutationFn: async (input: Partial<LocationInput>) => Location.parse((await api.patch<{ location: unknown }>(`/locations/${id}`, input)).location),
    onSuccess: () => invalidate(),
  })
}

export function useDeleteLocation() {
  const invalidate = useInvalidateLocations()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/locations/${id}`),
    onSuccess: () => invalidate(),
  })
}

export function useMakeDefaultLocation() {
  const invalidate = useInvalidateLocations()
  return useMutation({
    mutationFn: (id: string) => api.post(`/locations/${id}/make-default`),
    onSuccess: () => invalidate(),
  })
}
