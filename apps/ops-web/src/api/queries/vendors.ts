import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import { Vendor, VendorList, type VendorListParams, type VendorPayload } from '../contracts/vendors'
import type { ComboOption } from '@/ui/Form'

export const vendorKeys = {
  all: ['vendors'] as const,
  list: (params: VendorListParams) => ['vendors', 'list', params] as const,
  detail: (id: string) => ['vendors', 'detail', id] as const,
}

export function useVendors(params: VendorListParams = {}) {
  return useQuery({
    queryKey: vendorKeys.list(params),
    queryFn: async () => VendorList.parse(await api.get('/vendors', { params: { q: params.q, 'filter[active]': params.active, sort: params.sort ?? 'name', limit: params.limit ?? 200, cursor: params.cursor } })),
    placeholderData: keepPreviousData,
  })
}

export function useVendorOptions(): { options: ComboOption<string>[]; isLoading: boolean } {
  const query = useVendors({ active: 'true', limit: 200 })
  const options = (query.data?.items ?? []).map((vendor) => ({ value: vendor.id, label: vendor.name }))
  return { options, isLoading: query.isPending }
}

export function useVendor(id: string | undefined) {
  return useQuery({
    queryKey: vendorKeys.detail(id ?? ''),
    queryFn: async () => Vendor.parse((await api.get<{ vendor: unknown }>(`/vendors/${id}`)).vendor),
    enabled: Boolean(id),
  })
}

function useInvalidateVendors() {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: vendorKeys.all })
}

export function useCreateVendor() {
  const invalidate = useInvalidateVendors()
  return useMutation({
    mutationFn: async (input: VendorPayload) => Vendor.parse((await api.post<{ vendor: unknown }>('/vendors', input)).vendor),
    onSuccess: () => invalidate(),
  })
}

/** Also the way to retire a vendor: `PATCH { is_active: false }` (there is no delete). */
export function useUpdateVendor(id: string) {
  const invalidate = useInvalidateVendors()
  return useMutation({
    mutationFn: async (input: Partial<VendorPayload>) => Vendor.parse((await api.patch<{ vendor: unknown }>(`/vendors/${id}`, input)).vendor),
    onSuccess: () => invalidate(),
  })
}
