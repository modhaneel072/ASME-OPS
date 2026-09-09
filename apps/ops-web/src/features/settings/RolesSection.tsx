import { ChevronRight, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage } from '@/api/client'
import type { Role } from '@/api/contracts/users'
import { useRoles } from '@/api/queries/users'
import { useCan } from '@/lib/permissions'
import { Badge, Button, Card, EmptyState, InlineAlert, SkeletonRows, Stack, type BadgeTone } from '@/ui'
import styles from './settings.module.css'

const SCOPE_ORDER = ['chapter', 'project', 'team', 'assigned', 'own']
const SCOPE_TONES: Record<string, BadgeTone> = { chapter: 'info', project: 'purple', team: 'gold', assigned: 'success', own: 'neutral' }
const SCOPE_LABELS: Record<string, string> = { chapter: 'Chapter-wide', project: 'Own projects', team: 'Own teams', assigned: 'Assigned work', own: 'Own records' }

export function RolesSection() {
  const roles = useRoles()
  const can = useCan()
  const canSeeUsers = can('user.read', 'team.read')

  return (
    <Stack>
      <Card
        title="Roles"
        flush
        actions={canSeeUsers ? <Link to="/teams-users/users" style={{ fontSize: 'var(--text-label)', fontWeight: 600 }}>Manage members</Link> : undefined}
      >
        {roles.isPending ? (
          <SkeletonRows rows={6} />
        ) : roles.isError ? (
          <div style={{ padding: 'var(--space-4)' }}>
            <InlineAlert
              tone="danger"
              title="Roles could not be loaded"
              actions={
                <Button size="sm" onClick={() => void roles.refetch()}>
                  Retry
                </Button>
              }
            >
              {errorMessage(roles.error)}
            </InlineAlert>
          </div>
        ) : roles.data.length === 0 ? (
          <EmptyState compact illustration="users" title="No roles yet" description="Roles are created when the chapter is set up." />
        ) : (
          <ul className={styles.roleList} aria-label="Roles">
            {roles.data.map((role) => (
              <RoleRow key={role.id} role={role} />
            ))}
          </ul>
        )}
      </Card>
      <p style={{ fontSize: 'var(--text-caption)', color: 'var(--color-text-muted)' }}>
        Roles are read-only here. The full permission matrix and member assignments live under Teams / Users.
      </p>
    </Stack>
  )
}

function RoleRow({ role }: { role: Role }) {
  const [open, setOpen] = useState(false)
  const grants = role.grants ?? []
  const byScope = SCOPE_ORDER.map((scope) => ({ scope, keys: grants.filter((grant) => grant.scope === scope).map((grant) => grant.key) })).filter((entry) => entry.keys.length > 0)
  const panelId = `role-grants-${role.id}`
  const count = role.member_count ?? 0
  return (
    <li className={styles.role}>
      <button type="button" className={styles.roleHeader} aria-expanded={open} aria-controls={panelId} onClick={() => setOpen((value) => !value)}>
        <ChevronRight size={16} className={`${styles.roleChevron} ${open ? styles.roleChevron_open : ''}`} aria-hidden="true" />
        <span className={styles.roleBody}>
          <span className={styles.roleName}>
            {role.name}
            {role.is_custom ? (
              <Badge tone="outline" size="sm">
                Custom
              </Badge>
            ) : (
              <Badge tone="neutral" size="sm" title="Built-in role">
                <ShieldCheck size={11} aria-hidden="true" /> System
              </Badge>
            )}
          </span>
          {role.description && <span className={styles.roleDescription}>{role.description}</span>}
        </span>
        <span className={styles.roleCount}>
          {count} {count === 1 ? 'member' : 'members'} · {grants.length} {grants.length === 1 ? 'grant' : 'grants'}
        </span>
      </button>
      {open && (
        <div id={panelId} className={styles.grants}>
          {byScope.length === 0 ? (
            <p className={styles.grantEmpty}>This role has no grants.</p>
          ) : (
            <div className={styles.grantScopes}>
              {byScope.map(({ scope, keys }) => (
                <div key={scope} className={styles.grantScope}>
                  <Badge tone={SCOPE_TONES[scope] ?? 'neutral'} title={`Scope: ${scope}`}>
                    {SCOPE_LABELS[scope] ?? scope}
                  </Badge>
                  <ul className={styles.permissionList} aria-label={`${role.name} grants at ${scope} scope`}>
                    {keys.map((key) => (
                      <li key={key} className={styles.permission}>
                        {key}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </li>
  )
}
