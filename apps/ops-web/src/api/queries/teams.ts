import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import { TeamDetail, TeamList, type TeamInput, type TeamListParams, type TeamMembersInput } from '../contracts/teams'
import type { ComboOption } from '@/ui/Form'

export const teamKeys = {
  all: ['teams'] as const,
  list: (params: TeamListParams) => ['teams', 'list', params] as const,
  detail: (id: string) => ['teams', 'detail', id] as const,
}

export function useTeams(params: TeamListParams = {}) {
  return useQuery({
    queryKey: teamKeys.list(params),
    queryFn: async () =>
      TeamList.parse(await api.get('/teams', { params: { q: params.q, 'filter[project]': params.project, 'filter[active]': params.active, sort: params.sort ?? 'name', limit: params.limit ?? 200, cursor: params.cursor } })),
    placeholderData: keepPreviousData,
  })
}

export function useTeamOptions(): { options: ComboOption<string>[]; isLoading: boolean } {
  const query = useTeams({ limit: 200 })
  const options = (query.data?.items ?? []).map((team) => ({ value: team.id, label: team.name, meta: team.project?.code }))
  return { options, isLoading: query.isPending }
}

/* ---- Teams / Users feature ------------------------------------------------- */

export function useTeam(id: string | undefined) {
  return useQuery({
    queryKey: teamKeys.detail(id ?? ''),
    queryFn: async () => TeamDetail.parse((await api.get<{ team: unknown }>(`/teams/${id}`)).team),
    enabled: Boolean(id),
  })
}

/** Teams appear on member rows and in the Setup Center, and membership changes
 * can alter the session's lead_team_ids, so those families are refreshed too. */
function useInvalidateTeams() {
  const client = useQueryClient()
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: teamKeys.all }),
      client.invalidateQueries({ queryKey: ['users'] }),
      client.invalidateQueries({ queryKey: ['setup'] }),
      client.invalidateQueries({ queryKey: ['session'] }),
    ])
}

export function useCreateTeam() {
  const invalidate = useInvalidateTeams()
  return useMutation({
    mutationFn: async (input: TeamInput) => TeamDetail.parse((await api.post<{ team: unknown }>('/teams', input)).team),
    onSuccess: () => invalidate(),
  })
}

export function useUpdateTeam(id: string) {
  const invalidate = useInvalidateTeams()
  return useMutation({
    mutationFn: async (input: Partial<TeamInput> & { is_active?: boolean }) => TeamDetail.parse((await api.patch<{ team: unknown }>(`/teams/${id}`, input)).team),
    onSuccess: () => invalidate(),
  })
}

export function useDeleteTeam() {
  const invalidate = useInvalidateTeams()
  return useMutation({
    mutationFn: (id: string) => api.delete<{ deleted: boolean; id: string }>(`/teams/${id}`),
    onSuccess: () => invalidate(),
  })
}

export function useSetTeamMembers(id: string) {
  const invalidate = useInvalidateTeams()
  return useMutation({
    mutationFn: async (input: TeamMembersInput) => TeamDetail.parse((await api.put<{ team: unknown }>(`/teams/${id}/members`, input)).team),
    onSuccess: () => invalidate(),
  })
}
