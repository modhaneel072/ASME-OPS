import type { Role } from '@/api/contracts/users'

/** Scope ladder from asme/ops/permissions.py, broadest first. */
export const SCOPES = ['chapter', 'project', 'team', 'assigned', 'own'] as const
export type Scope = (typeof SCOPES)[number]

export const SCOPE_ABBR: Record<Scope, string> = { chapter: 'C', project: 'P', team: 'T', assigned: 'A', own: 'O' }
export const SCOPE_LABELS: Record<Scope, string> = { chapter: 'Chapter', project: 'Project', team: 'Team', assigned: 'Assigned', own: 'Own' }
export const SCOPE_TITLES: Record<Scope, string> = {
  chapter: 'Chapter: anywhere in the chapter',
  project: 'Project: only records in projects the member belongs to',
  team: 'Team: only records owned by a team the member leads (or belongs to, for read permissions)',
  assigned: 'Assigned: only records assigned to the member or one of their teams',
  own: 'Own: only records the member created',
}

export function isScope(value: string): value is Scope {
  return (SCOPES as readonly string[]).includes(value)
}

/** Display order of the permission-key prefixes enforced today; everything else is a later stage. */
export const PERMISSION_GROUPS: ReadonlyArray<{ prefix: string; label: string }> = [
  { prefix: 'chapter', label: 'Chapter' },
  { prefix: 'user', label: 'Users' },
  { prefix: 'role', label: 'Roles' },
  { prefix: 'team', label: 'Teams' },
  { prefix: 'location', label: 'Locations' },
  { prefix: 'category', label: 'Categories' },
  { prefix: 'asset', label: 'Assets' },
  { prefix: 'vendor', label: 'Vendors' },
  { prefix: 'project', label: 'Projects' },
  { prefix: 'milestone', label: 'Milestones' },
  { prefix: 'work_order', label: 'Work orders' },
  { prefix: 'saved_filter', label: 'Saved filters' },
  { prefix: 'report', label: 'Reports' },
  { prefix: 'audit', label: 'Audit' },
  { prefix: 'notification', label: 'Notifications' },
]
export const LATER_STAGES_LABEL = 'Later stages'

export interface PermissionGroup {
  label: string
  keys: string[]
}

/** Buckets keys by the text before the first dot, in PERMISSION_GROUPS order, sorted within a bucket. */
export function groupPermissionKeys(keys: Iterable<string>): PermissionGroup[] {
  const buckets = new Map<string, string[]>(PERMISSION_GROUPS.map((group) => [group.prefix, []]))
  const later: string[] = []
  for (const key of new Set(keys)) {
    const bucket = buckets.get(key.split('.')[0])
    if (bucket) bucket.push(key)
    else later.push(key)
  }
  const groups: PermissionGroup[] = []
  for (const group of PERMISSION_GROUPS) {
    const bucket = buckets.get(group.prefix) ?? []
    if (bucket.length > 0) groups.push({ label: group.label, keys: bucket.sort() })
  }
  if (later.length > 0) groups.push({ label: LATER_STAGES_LABEL, keys: later.sort() })
  return groups
}

/** role id -> permission key -> scope. */
export type ScopeMatrix = Map<string, Map<string, Scope>>

/**
 * The client has no copy of the permission registry, so the row set is the
 * union of every role's grants (Chapter Administrator holds every key).
 */
export function buildScopeMatrix(roles: Role[]): { matrix: ScopeMatrix; keys: string[] } {
  const matrix: ScopeMatrix = new Map()
  const keys = new Set<string>()
  for (const role of roles) {
    const byKey = new Map<string, Scope>()
    for (const grant of role.grants ?? []) {
      if (!isScope(grant.scope)) continue
      byKey.set(grant.key, grant.scope)
      keys.add(grant.key)
    }
    matrix.set(role.id, byKey)
  }
  return { matrix, keys: [...keys] }
}
