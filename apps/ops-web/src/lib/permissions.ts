import { createContext, useContext } from 'react'
import type { Session } from '@/api/contracts/session'

export const SessionContext = createContext<Session | null>(null)

/** The current session. Only rendered inside `RequireSession`, so never null there. */
export function useSession(): Session {
  const session = useContext(SessionContext)
  if (!session) throw new Error('useSession must be used inside RequireSession')
  return session
}

export type Scope = 'chapter' | 'project' | 'team' | 'assigned' | 'own'

/** Coarse client-side check: does the user hold `key` at any scope? The server
 * enforces object-level scope; this only decides which controls to render. */
export function hasPermission(session: Session | null, key: string): boolean {
  return Boolean(session?.permissions[key]?.length)
}

export function scopesFor(session: Session | null, key: string): Scope[] {
  return (session?.permissions[key] ?? []) as Scope[]
}

export function useCan(): (key: string, ...more: string[]) => boolean {
  const session = useContext(SessionContext)
  return (key, ...more) => [key, ...more].some((k) => hasPermission(session, k))
}

export interface ScopedObject {
  project?: { id: string } | null
  project_id?: string | null
  team?: { id: string } | null
  team_id?: string | null
  assignees?: Array<{ id: number }>
  assignee_teams?: Array<{ id: string }>
  created_by?: { id: number } | null
  owner?: { id: number } | null
}

/** Mirrors `asme.ops.policy.can` closely enough to decide whether to show an
 * action; the API is still the authority. */
export function canOn(session: Session, key: string, obj: ScopedObject | null | undefined): boolean {
  const scopes = scopesFor(session, key)
  if (scopes.length === 0) return false
  if (scopes.includes('chapter') || !obj) return true
  const projectId = obj.project?.id ?? obj.project_id ?? null
  if (scopes.includes('project') && projectId && session.scope.project_ids.includes(projectId)) return true
  const teamIds = new Set<string>()
  if (obj.team?.id) teamIds.add(obj.team.id)
  if (obj.team_id) teamIds.add(obj.team_id)
  for (const t of obj.assignee_teams ?? []) teamIds.add(t.id)
  if (scopes.includes('team')) {
    const allowed = key.endsWith('.read') || key.endsWith('.read_all') || key.endsWith('.view') ? session.scope.team_ids : session.scope.lead_team_ids
    if ([...teamIds].some((id) => allowed.includes(id))) return true
  }
  if (scopes.includes('assigned')) {
    if ((obj.assignees ?? []).some((u) => u.id === session.user.id)) return true
    if ([...teamIds].some((id) => session.scope.team_ids.includes(id))) return true
  }
  if (scopes.includes('own')) {
    if (obj.created_by?.id === session.user.id || obj.owner?.id === session.user.id) return true
  }
  return false
}
