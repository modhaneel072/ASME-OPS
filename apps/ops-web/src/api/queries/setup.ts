import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import { SetupProgress } from '../contracts/setup'
import { sessionKey } from './session'

/**
 * Setup Center queries. The `['setup']` family is also invalidated by other
 * features after they create records (locations, teams, …) and by the change
 * poller when the organization changes, so progress stays live.
 */
export const setupKeys = {
  all: ['setup'] as const,
  progress: () => ['setup', 'progress'] as const,
}

export function useSetupProgress() {
  return useQuery({
    queryKey: setupKeys.progress(),
    queryFn: async () => SetupProgress.parse(await api.get('/setup')),
  })
}

type SetupAction = 'dismiss-banner' | 'reopen-banner' | 'complete' | 'mark-guide-read'

/**
 * Every setup action returns the refreshed progress payload. We seed the cache
 * with it for an instant update, then invalidate `['setup']` and `['session']`
 * so the shell banner and derived counts are re-read from the server.
 */
function useSetupAction(action: SetupAction) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async () => SetupProgress.parse(await api.post(`/setup/${action}`)),
    onSuccess: (progress) => {
      client.setQueryData(setupKeys.progress(), progress)
      return Promise.all([client.invalidateQueries({ queryKey: setupKeys.all }), client.invalidateQueries({ queryKey: sessionKey })])
    },
  })
}

/** Hides the shell setup banner for the current user only. */
export function useDismissSetupBanner() {
  return useSetupAction('dismiss-banner')
}

/** Shows the shell setup banner again for the current user. */
export function useReopenSetupBanner() {
  return useSetupAction('reopen-banner')
}

/** Marks setup complete for the whole chapter (requires `chapter.setup.manage`). */
export function useCompleteSetup() {
  return useSetupAction('complete')
}

/** Records that the officer guide was read, chapter-wide (requires `chapter.setup.manage`). */
export function useMarkGuideRead() {
  return useSetupAction('mark-guide-read')
}
