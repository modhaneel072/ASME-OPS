import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import { InviteResult, Member, MemberList, Role, type InviteRequest, type MemberUpdateInput, type UserListParams } from '../contracts/users'
import type { ComboOption } from '@/ui/Form'

export const userKeys = {
  all: ['users'] as const,
  list: (params: UserListParams) => ['users', 'list', params] as const,
  detail: (id: number) => ['users', 'detail', id] as const,
  roles: ['users', 'roles'] as const,
}

export function useUsers(params: UserListParams = {}) {
  return useQuery({
    queryKey: userKeys.list(params),
    queryFn: async () =>
      MemberList.parse(
        await api.get('/users', {
          params: { q: params.q, 'filter[role]': params.role, 'filter[status]': params.status, 'filter[team]': params.team, sort: params.sort ?? 'name', limit: params.limit ?? 200, cursor: params.cursor },
        }),
      ),
    placeholderData: keepPreviousData,
  })
}

export function useRoles() {
  return useQuery({
    queryKey: userKeys.roles,
    queryFn: async () => {
      const payload = await api.get<{ roles?: unknown[]; items?: unknown[] }>('/roles')
      return (payload.roles ?? payload.items ?? []).map((r) => Role.parse(r))
    },
    staleTime: 5 * 60 * 1000,
  })
}

/** Active members as picker options (assignees, leads, owners). */
export function usePeopleOptions(): { options: ComboOption<number>[]; isLoading: boolean } {
  const query = useUsers({ status: ['active'], limit: 200 })
  const options = (query.data?.items ?? []).map((member) => ({ value: member.user.id, label: member.user.name, meta: member.role.name }))
  return { options, isLoading: query.isPending }
}

/* ---- Teams / Users feature ------------------------------------------------- */

/** One directory entry by legacy `users.id` (`GET /users/:id`). */
export function useUser(id: number | undefined) {
  return useQuery({
    queryKey: userKeys.detail(id ?? 0),
    queryFn: async () => Member.parse((await api.get<{ member: unknown }>(`/users/${id}`)).member),
    enabled: id !== undefined && Number.isFinite(id),
  })
}

/** Role counts live on `/roles`, team rows show members, Setup Center counts
 * active memberships, and a title change to yourself shows in the session. */
function useInvalidateUsers() {
  const client = useQueryClient()
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: userKeys.all }),
      client.invalidateQueries({ queryKey: ['teams'] }),
      client.invalidateQueries({ queryKey: ['setup'] }),
      client.invalidateQueries({ queryKey: ['session'] }),
    ])
}

export function useInviteUser() {
  const invalidate = useInvalidateUsers()
  return useMutation({
    mutationFn: async (input: InviteRequest) => InviteResult.parse(await api.post('/users/invite', input)),
    onSuccess: () => invalidate(),
  })
}

export function useUpdateUser(id: number) {
  const invalidate = useInvalidateUsers()
  return useMutation({
    mutationFn: async (input: MemberUpdateInput) => Member.parse((await api.patch<{ member: unknown }>(`/users/${id}`, input)).member),
    onSuccess: () => invalidate(),
  })
}
