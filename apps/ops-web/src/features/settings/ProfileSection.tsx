import { ExternalLink, LogOut } from 'lucide-react'
import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { labelFor } from '@/api/contracts/common'
import { useLogout } from '@/api/queries/session'
import { formatDate, formatDateTime } from '@/lib/dates'
import { useSession } from '@/lib/permissions'
import { Avatar, Badge, Button, Card, FieldList, Stack, type BadgeTone } from '@/ui'
import styles from './settings.module.css'

const SCOPE_TONES: Record<string, BadgeTone> = {
  chapter: 'info',
  project: 'purple',
  team: 'gold',
  assigned: 'success',
  own: 'neutral',
}

const GROUP_LABELS: Record<string, string> = {
  chapter: 'Chapter',
  user: 'Users',
  role: 'Roles',
  team: 'Teams',
  location: 'Locations',
  category: 'Categories',
  asset: 'Assets',
  vendor: 'Vendors',
  project: 'Projects',
  milestone: 'Milestones',
  work_order: 'Work orders',
  saved_filter: 'Saved filters',
  report: 'Reporting',
  audit: 'Audit',
  notification: 'Notifications',
  request: 'Requests',
  inventory: 'Inventory',
  purchase: 'Purchasing',
  procedure: 'Procedures',
  plan: 'Maintenance plans',
  meter: 'Meters',
  automation: 'Automations',
  dashboard: 'Dashboards',
  message: 'Messages',
  sponsor: 'Sponsors',
}

const LEGACY_ROLE_LABELS: Record<string, string> = {
  admin: 'Administrator',
  team_leader: 'Team leader',
  member: 'Member',
}

export function ProfileSection() {
  const session = useSession()
  const navigate = useNavigate()
  const logout = useLogout()

  const groups = useMemo(() => {
    const byGroup = new Map<string, Array<{ key: string; scopes: string[] }>>()
    for (const [key, scopes] of Object.entries(session.permissions)) {
      if (!scopes.length) continue
      const group = key.split('.')[0]
      const entry = byGroup.get(group) ?? []
      entry.push({ key, scopes })
      byGroup.set(group, entry)
    }
    return [...byGroup.entries()]
      .map(([group, keys]) => ({ group, label: GROUP_LABELS[group] ?? labelFor(group), keys: keys.sort((a, b) => a.key.localeCompare(b.key)) }))
      .sort((a, b) => a.label.localeCompare(b.label))
  }, [session.permissions])

  const { user, membership } = session

  return (
    <Stack>
      <Card title="Profile">
        <Stack>
          <div className={styles.identity}>
            <Avatar name={user.name} src={user.avatar_url} size="lg" />
            <div className={styles.identityText}>
              <div className={styles.identityName}>{user.name}</div>
              <div className={styles.identityEmail}>{user.email}</div>
              <div className={styles.identityBadges}>
                <Badge tone="info">{membership.role.name}</Badge>
                {membership.title && <Badge tone="outline">{membership.title}</Badge>}
                <Badge tone={membership.status === 'active' ? 'success' : 'warning'} dot>
                  {labelFor(membership.status)}
                </Badge>
              </div>
            </div>
          </div>
          <FieldList
            items={[
              { label: 'Username', value: user.username || '—' },
              { label: 'Member portal role', value: LEGACY_ROLE_LABELS[user.legacy_role] ?? labelFor(user.legacy_role) },
              { label: 'Chapter role', value: membership.title ? `${membership.role.name} · ${membership.title}` : membership.role.name },
              { label: 'Major', value: user.major || '—' },
              { label: 'Graduation year', value: user.graduation_year ? String(user.graduation_year) : '—' },
              { label: 'Joined', value: formatDate(membership.joined_at) },
              { label: 'Last sign-in', value: user.last_login_at ? formatDateTime(user.last_login_at) : '—' },
            ]}
          />
          <div className={styles.actions}>
            <a className={styles.inlineLink} href="/portal/member/profile">
              <ExternalLink size={14} aria-hidden="true" />
              Edit profile in the member portal
            </a>
            <span style={{ flex: 1 }} />
            <Button
              variant="secondary"
              leadingIcon={<LogOut size={16} />}
              loading={logout.isPending}
              onClick={() => logout.mutate(undefined, { onSettled: () => navigate('/auth/login', { replace: true }) })}
            >
              Log out
            </Button>
          </div>
        </Stack>
      </Card>

      <Card title="What you can do" actions={<span style={{ fontSize: 'var(--text-caption)', color: 'var(--color-text-muted)' }}>{Object.keys(session.permissions).length} permissions</span>}>
        {groups.length === 0 ? (
          <p style={{ color: 'var(--color-text-muted)' }}>Your role has no permissions in this chapter yet.</p>
        ) : (
          <div className={styles.permissionGroups}>
            {groups.map(({ group, label, keys }) => (
              <div key={group} className={styles.permissionGroup}>
                <div className={styles.permissionGroupName}>{label}</div>
                <ul className={styles.permissionList} aria-label={`${label} permissions`}>
                  {keys.map(({ key, scopes }) => (
                    <li key={key} className={styles.permission}>
                      <span>{key.slice(group.length + 1)}</span>
                      {scopes.map((scope) => (
                        <Badge key={scope} tone={SCOPE_TONES[scope] ?? 'neutral'} size="sm" title={`Scope: ${scope}`}>
                          {scope}
                        </Badge>
                      ))}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </Card>
    </Stack>
  )
}
