import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../client'
import {
  ChangePasswordResult,
  ForgotPasswordResult,
  LoginResponse,
  ProfileUpdateResult,
  ResetPasswordResult,
  ResetTokenInfo,
  Session,
  type ProfilePatch,
} from '../contracts/session'

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

/* Account flows ---------------------------------------------------------------- */

export const resetTokenKey = (token: string) => ['auth', 'reset-token', token] as const

/** True when the API rejected a reset or invite token as unknown, used or expired. */
export function isInvalidTokenError(error: unknown): boolean {
  return error instanceof ApiError && (error.code === 'invalid_token' || error.isNotFound)
}

/** Human-readable text for a 429 `rate_limited` response, including the wait when the server gives one. */
export function rateLimitMessage(error: unknown): string | null {
  if (!(error instanceof ApiError) || (error.code !== 'rate_limited' && error.status !== 429)) return null
  const seconds = Number(error.extra.retry_after)
  if (!Number.isFinite(seconds) || seconds <= 0) return 'Too many attempts. Wait a few minutes and try again.'
  if (seconds < 60) return `Too many attempts. Try again in ${Math.ceil(seconds)} ${Math.ceil(seconds) === 1 ? 'second' : 'seconds'}.`
  const minutes = Math.ceil(seconds / 60)
  return `Too many attempts. Try again in ${minutes} ${minutes === 1 ? 'minute' : 'minutes'}.`
}

export function useForgotPassword() {
  return useMutation({
    mutationFn: async (input: { email: string }) => ForgotPasswordResult.parse(await api.post('/auth/forgot-password', input)),
  })
}

/** Checks a reset or invite token. The token travels in the request body, never in a URL, so it cannot land in server logs. */
export function useResetToken(token: string) {
  return useQuery({
    queryKey: resetTokenKey(token),
    queryFn: async () => ResetTokenInfo.parse(await api.post('/auth/reset-password/status', { token })),
    enabled: token.length > 0,
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })
}

export function useResetPassword() {
  return useMutation({
    mutationFn: async (input: { token: string; password: string; confirm_password: string }) => ResetPasswordResult.parse(await api.post('/auth/reset-password', input)),
  })
}

export function useChangePassword() {
  return useMutation({
    mutationFn: async (input: { current_password: string; new_password: string; confirm_password: string }) =>
      ChangePasswordResult.parse(await api.post('/auth/change-password', input)),
  })
}

export function useUpdateProfile() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (input: ProfilePatch) => ProfileUpdateResult.parse(await api.patch('/session/profile', input)).session,
    onSuccess: (session) => {
      client.setQueryData(sessionKey, session)
    },
  })
}
