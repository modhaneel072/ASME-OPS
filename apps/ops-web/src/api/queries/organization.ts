import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import { Organization, type OrganizationPatch } from '../contracts/organization'

export const organizationKeys = {
  all: ['organization'] as const,
  detail: ['organization', 'detail'] as const,
}

/** `GET /organization` (any member). */
export function useOrganization() {
  return useQuery({
    queryKey: organizationKeys.detail,
    queryFn: async () => Organization.parse((await api.get<{ organization: unknown }>('/organization')).organization),
    staleTime: 60_000,
  })
}

/** `PATCH /organization` (chapter.settings.manage). Refreshes the session, which embeds the organization. */
export function useUpdateOrganization() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (input: OrganizationPatch) => Organization.parse((await api.patch<{ organization: unknown }>('/organization', input)).organization),
    onSuccess: async (organization) => {
      client.setQueryData(organizationKeys.detail, organization)
      await Promise.all([client.invalidateQueries({ queryKey: ['session'] }), client.invalidateQueries({ queryKey: organizationKeys.all }), client.invalidateQueries({ queryKey: ['setup'] })])
    },
  })
}
