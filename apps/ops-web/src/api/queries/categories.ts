import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import { Category, CategoryList, type CategoryListParams, type CategoryPayload } from '../contracts/categories'
import type { ComboOption } from '@/ui/Form'

export const categoryKeys = {
  all: ['categories'] as const,
  list: (params: CategoryListParams) => ['categories', 'list', params] as const,
  detail: (id: string) => ['categories', 'detail', id] as const,
}

export function useCategories(params: CategoryListParams = {}) {
  return useQuery({
    queryKey: categoryKeys.list(params),
    queryFn: async () => CategoryList.parse(await api.get('/categories', { params: { q: params.q, sort: params.sort ?? 'name', limit: params.limit ?? 200, cursor: params.cursor } })),
    placeholderData: keepPreviousData,
  })
}

export function useCategoryOptions(): { options: ComboOption<string>[]; isLoading: boolean; byId: Map<string, { name: string; color: string }> } {
  const query = useCategories({ limit: 200 })
  const items = query.data?.items ?? []
  return {
    options: items.map((category) => ({ value: category.id, label: category.name })),
    isLoading: query.isPending,
    byId: new Map(items.map((category) => [category.id, { name: category.name, color: category.color }])),
  }
}

export function useCategory(id: string | undefined) {
  return useQuery({
    queryKey: categoryKeys.detail(id ?? ''),
    queryFn: async () => Category.parse((await api.get<{ category: unknown }>(`/categories/${id}`)).category),
    enabled: Boolean(id),
  })
}

function useInvalidateCategories() {
  const client = useQueryClient()
  return () => Promise.all([client.invalidateQueries({ queryKey: categoryKeys.all }), client.invalidateQueries({ queryKey: ['setup'] })])
}

export function useCreateCategory() {
  const invalidate = useInvalidateCategories()
  return useMutation({
    mutationFn: async (input: CategoryPayload) => Category.parse((await api.post<{ category: unknown }>('/categories', input)).category),
    onSuccess: () => invalidate(),
  })
}

export function useUpdateCategory(id: string) {
  const invalidate = useInvalidateCategories()
  return useMutation({
    mutationFn: async (input: Partial<CategoryPayload>) => Category.parse((await api.patch<{ category: unknown }>(`/categories/${id}`, input)).category),
    onSuccess: () => invalidate(),
  })
}

export function useDeleteCategory() {
  const invalidate = useInvalidateCategories()
  return useMutation({
    mutationFn: (id: string) => api.delete<{ id: string; deleted: boolean }>(`/categories/${id}`),
    onSuccess: () => invalidate(),
  })
}
