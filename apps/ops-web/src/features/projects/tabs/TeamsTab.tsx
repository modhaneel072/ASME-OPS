import { Users } from 'lucide-react'
import { PROJECT_ROLE_LABELS, type Project, type ProjectMember, type ProjectRole } from '@/api/contracts/projects'
import { useTeams } from '@/api/queries/teams'
import { formatDate } from '@/lib/dates'
import { Avatar, Badge, Button, Card, EmptyState, ListRow, Stack } from '@/ui'
import { QueryState } from '../shared'
import styles from '../projects.module.css'

const ROLE_ORDER: Record<string, number> = { lead: 0, advisor: 1, member: 2, viewer: 3 }

export function TeamsTab({ project, members, canManage, onManageMembers }: { project: Project; members: ProjectMember[]; canManage: boolean; onManageMembers: () => void }) {
  const teams = useTeams({ project: [project.id] })
  const sorted = [...members].sort((a, b) => (ROLE_ORDER[a.project_role] ?? 9) - (ROLE_ORDER[b.project_role] ?? 9) || a.user.name.localeCompare(b.user.name))

  return (
    <Stack>
      <Card
        title={`Members (${members.length})`}
        flush
        actions={
          canManage ? (
            <Button size="sm" variant="primary" leadingIcon={<Users size={14} />} onClick={onManageMembers}>
              Manage members
            </Button>
          ) : undefined
        }
      >
        {sorted.length === 0 ? (
          <EmptyState compact illustration="users" title="No members yet" description="Add the people working on this project so their roles and teams are clear." action={canManage ? <Button size="sm" variant="primary" onClick={onManageMembers}>Add members</Button> : undefined} />
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Member</th>
                  <th scope="col">Project role</th>
                  <th scope="col">Team</th>
                  <th scope="col">Joined</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((member) => (
                  <tr key={member.user.id}>
                    <td>
                      <span className={styles.person}>
                        <Avatar name={member.user.name} src={member.user.avatar_url} />
                        <span>
                          <span className={styles.personName}>{member.user.name}</span>
                          <span className={styles.personEmail}>{member.user.email}</span>
                        </span>
                      </span>
                    </td>
                    <td>
                      <Badge tone={member.project_role === 'lead' ? 'gold' : member.project_role === 'advisor' ? 'purple' : 'neutral'} size="sm">
                        {PROJECT_ROLE_LABELS[member.project_role as ProjectRole] ?? member.project_role}
                      </Badge>
                    </td>
                    <td>{member.team?.name ?? <span className={styles.muted}>—</span>}</td>
                    <td className={styles.muted}>{formatDate(member.joined_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Teams" flush>
        <QueryState isPending={teams.isPending} isError={teams.isError} error={teams.error} onRetry={() => void teams.refetch()} title="Teams could not be loaded">
          {(teams.data?.items ?? []).length === 0 ? (
            <EmptyState compact illustration="users" title="No teams linked" description="Teams are assigned to a project from Teams and Users." />
          ) : (
            <ul aria-label="Teams">
              {teams.data?.items.map((team) => (
                <li key={team.id}>
                  <ListRow compact to={`/teams-users/teams/${team.id}`} title={team.name} meta={<span>{team.member_count ?? 0} members{team.leads.length ? ` · led by ${team.leads.map((lead) => lead.name).join(', ')}` : ''}</span>} />
                </li>
              ))}
            </ul>
          )}
        </QueryState>
      </Card>
    </Stack>
  )
}
