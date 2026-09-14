import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import { SavedFilter, SavedFilterLists, type SavedFilterEntity, type SavedFilterInput, type SavedFilterPatch } from '../contracts/saved-filters'

export const savedFilterKeys = {
  all: ['saved-filters'] as const,
  list: (entity: SavedFilterEntity) => ['saved-filters', 'list', entity] as const,
}

/** `{ personal, shared }` for one entity type (`GET /saved-filters?entity_type=`). */
export function useSavedFilters(entity: SavedFilterEntity) {
  return useQuery({
    queryKey: savedFilterKeys.list(entity),
    queryFn: async () => SavedFilterLists.parse(await api.get('/saved-filters', { params: { entity_type: entity } })),
    staleTime: 60_000,
  })
}

function useInvalidateSavedFilters() {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: savedFilterKeys.all })
}

export function useCreateSavedFilter() {
  const invalidate = useInvalidateSavedFilters()
  return useMutation({
    mutationFn: async (input: SavedFilterInput) => SavedFilter.parse((await api.post<{ saved_filter: unknown }>('/saved-filters', input)).saved_filter),
    onSuccess: () => invalidate(),
  })
}

export function useUpdateSavedFilter() {
  const invalidate = useInvalidateSavedFilters()
  return useMutation({
    mutationFn: async ({ id, ...patch }: SavedFilterPatch & { id: string }) => SavedFilter.parse((await api.patch<{ saved_filter: unknown }>(`/saved-filters/${id}`, patch)).saved_filter),
    onSuccess: () => invalidate(),
  })
}

export function useDeleteSavedFilter() {
  const invalidate = useInvalidateSavedFilters()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/saved-filters/${id}`),
    onSuccess: () => invalidate(),
  })
}
