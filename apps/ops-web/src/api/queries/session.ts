import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../client'
import { LoginResponse, Session } from '../contracts/session'

export const sessionKey = ['session'] as const

export type SessionState =
  | { status: 'loading'; session: null; error: null }
  | { status: 'anonymous'; session: null; error: null }
  | { status: 'no_membership'; session: null; error: ApiError }
  | { status: 'error'; session: null; error: unknown }
  | { status: 'ready'; session: Session; error: null }

export function useSessionQuery() {
  return useQuery({
    queryKey: sessionKey,
    queryFn: async () => Session.parse(await api.get('/session')),
    retry: false,
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: true,
  })
}

export function useSessionState(): SessionState {
  const query = useSessionQuery()
  if (query.isPending) return { status: 'loading', session: null, error: null }
  if (query.isError) {
    const error = query.error
    if (error instanceof ApiError && error.isAuth) return { status: 'anonymous', session: null, error: null }
    if (error instanceof ApiError && error.code === 'no_membership') return { status: 'no_membership', session: null, error }
    return { status: 'error', session: null, error }
  }
  return { status: 'ready', session: query.data, error: null }
}

export function useLogin() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (input: { identifier: string; password: string }) => LoginResponse.parse(await api.post('/auth/login', input)),
    onSuccess: async (data) => {
      if (data.session) client.setQueryData(sessionKey, data.session)
      await client.invalidateQueries({ queryKey: sessionKey })
    },
  })
}

export function useLogout() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.post('/auth/logout'),
    onSettled: async () => {
      client.clear()
      await client.invalidateQueries({ queryKey: sessionKey })
    },
  })
}

export function useSetPreference() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: unknown }) => api.put(`/preferences/${key}`, { value }),
    onSuccess: () => client.invalidateQueries({ queryKey: sessionKey }),
  })
}
