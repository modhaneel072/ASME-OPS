import { ChevronRight, MoreHorizontal, Pencil, Plus, Trash2, UserCog, Users2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError, errorMessage } from '@/api/client'
import { TEAM_SORTS, type Team, type TeamDetail, type TeamInput, type TeamMemberInput } from '@/api/contracts/teams'
import { useCreateTeam, useDeleteTeam, useSetTeamMembers, useTeam, useTeams, useUpdateTeam } from '@/api/queries/teams'
import { formatDateTime } from '@/lib/dates'
import { canOn, useCan, useSession, type ScopedObject } from '@/lib/permissions'
import {
  Avatar,
  AvatarStack,
  Badge,
  Button,
  Card,
  DetailPanel,
  Dialog,
  DropdownMenu,
  EmptyState,
  FieldList,
  IconButton,
  InlineAlert,
  ListRow,
  ListToolbarSpacer,
  MasterDetailLayout,
  SkeletonBlock,
  SkeletonRows,
  Stack,
  useToast,
} from '@/ui'
import { ManageMembersDialog } from './ManageMembersDialog'
import { TeamForm } from './TeamForm'
import styles from './teams-users.module.css'
import { oneOf, withParams } from './urlState'

/** What `canOn` needs to mirror `policy.can(ctx, "team.manage", team)`: the team itself and its project. */
export function teamScope(team: Pick<Team, 'id' | 'project'>): ScopedObject {
  return { team_id: team.id, project_id: team.project?.id ?? null }
}

export function TeamsTab({ teamId }: { teamId?: string }) {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()
  const session = useSession()
  const can = useCan()
  const canCreate = can('team.manage')

  const q = params.get('q') ?? ''
  const sort = oneOf(params.get('sort'), TEAM_SORTS, 'name')
  const pane = params.get('pane')

  const list = useTeams({ q: q || undefined, sort })
  const teams = useMemo(() => list.data?.items ?? [], [list.data])
  const selected = useTeam(teamId)
  const team = selected.data
  const canManageSelected = team ? canOn(session, 'team.manage', teamScope(team)) : false
  const paneOpen = pane === 'new' ? canCreate : pane === 'edit' ? Boolean(team) && canManageSelected : false

  const create = useCreateTeam()
  const update = useUpdateTeam(teamId ?? '')
  const remove = useDeleteTeam()
  const setMembers = useSetTeamMembers(teamId ?? '')
  const [membersOpen, setMembersOpen] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const openPane = (mode: 'new' | 'edit') => setParams(withParams(params, { pane: mode }))
  const closePane = () => setParams(withParams(params, { pane: null }))
  const clearSearch = () => setParams(withParams(params, { q: null }), { replace: true })
  const rowQuery = withParams(params, { pane: null }).toString()
  const rowLink = (id: string) => `/teams-users/teams/${id}${rowQuery ? `?${rowQuery}` : ''}`

  const submitForm = async (values: TeamInput) => {
    if (pane === 'edit' && teamId) {
      await update.mutateAsync(values)
      toast.success('Team updated')
      closePane()
    } else {
      const created = await create.mutateAsync(values)
      toast.success('Team created', created.name)
      navigate(`/teams-users/teams/${created.id}`)
    }
  }

  const closeMembers = () => {
    setMembersOpen(false)
    setMembers.reset()
  }
  const saveMembers = async (members: TeamMemberInput[]) => {
    if (!teamId) return
    try {
      await setMembers.mutateAsync({ members })
      toast.success('Members updated')
      closeMembers()
    } catch (error) {
      if (error instanceof ApiError && error.isForbidden) toast.error('You cannot manage this team’s members', error.message)
    }
  }

  const onDelete = async () => {
    if (!teamId) return
    try {
      await remove.mutateAsync(teamId)
      toast.success('Team deleted')
      setConfirmDelete(false)
      navigate('/teams-users/teams')
    } catch (error) {
      setConfirmDelete(false)
      toast.error('Could not delete team', errorMessage(error))
    }
  }

  const listContent = list.isPending ? (
    <SkeletonRows rows={8} />
  ) : list.isError ? (
    <div style={{ padding: 'var(--space-4)' }}>
      <InlineAlert
        tone="danger"
        title="Teams could not be loaded"
        actions={
          <Button size="sm" onClick={() => void list.refetch()}>
            Retry
          </Button>
        }
      >
        {errorMessage(list.error)}
      </InlineAlert>
    </div>
  ) : teams.length === 0 && q ? (
    <EmptyState
      compact
      illustration="search"
      title="No teams match"
      description={`Nothing matches “${q}”.`}
      action={
        <Button size="sm" onClick={clearSearch}>
          Clear search
        </Button>
      }
    />
  ) : teams.length === 0 ? (
    <EmptyState
      compact
      illustration="users"
      title="No teams yet"
      description="Group members into teams such as Wheels and Mobility or Electrical so work can be assigned to them."
      action={
        canCreate ? (
          <Button variant="primary" size="sm" leadingIcon={<Plus size={16} />} onClick={() => openPane('new')}>
            Create the first team
          </Button>
        ) : undefined
      }
    />
  ) : (
    <ul aria-label="Teams">
      {teams.map((row) => (
        <li key={row.id}>
          <ListRow
            to={rowLink(row.id)}
            selected={row.id === teamId}
            leading={<Users2 size={16} style={{ color: 'var(--color-text-muted)' }} aria-hidden="true" />}
            title={
              <span className={styles.inlineTitle}>
                {row.name}
                {row.project && (
                  <Badge tone="outline" size="sm" className="mono" title={row.project.name}>
                    {row.project.code}
                  </Badge>
                )}
              </span>
            }
            meta={
              <>
                <span>{row.member_count ?? 0} members</span>
                {row.leads.length > 0 && <span>Led by {row.leads.map((lead) => lead.name).join(', ')}</span>}
              </>
            }
            trailing={
              <span className={styles.rowTrailing}>
                {row.leads.length > 0 && <AvatarStack people={row.leads} />}
                <ChevronRight size={16} style={{ color: 'var(--color-text-disabled)' }} aria-hidden="true" />
              </span>
            }
            data-testid="team-row"
          />
        </li>
      ))}
    </ul>
  )

  const detail = !teamId ? (
    <EmptyState illustration="users" title="Select a team" description="Choose a team on the left to see its members, project and sub-teams." />
  ) : selected.isPending ? (
    <div style={{ padding: 'var(--space-6)' }}>
      <SkeletonBlock lines={5} />
    </div>
  ) : selected.isError ? (
    <div style={{ padding: 'var(--space-6)' }}>
      {selected.error instanceof ApiError && selected.error.isNotFound ? (
        <EmptyState illustration="search" title="Team not found" description="It may have been deleted, or it belongs to a project you cannot see." action={<Button onClick={() => navigate('/teams-users/teams')}>Back to teams</Button>} />
      ) : (
        <InlineAlert
          tone="danger"
          title="Could not load this team"
          actions={
            <Button size="sm" onClick={() => void selected.refetch()}>
              Retry
            </Button>
          }
        >
          {errorMessage(selected.error)}
        </InlineAlert>
      )}
    </div>
  ) : (
    <TeamDetailView team={selected.data} teams={teams} canManage={canManageSelected} onEdit={() => openPane('edit')} onManageMembers={() => setMembersOpen(true)} onDelete={() => setConfirmDelete(true)} />
  )

  return (
    <>
      <MasterDetailLayout
        detailOpen={Boolean(teamId)}
        backTo="/teams-users/teams"
        backLabel="Back to teams"
        listToolbar={
          <>
            <span>{list.data ? `${list.data.total ?? teams.length} teams` : ''}</span>
            <ListToolbarSpacer />
            {list.isFetching && !list.isPending && <span aria-live="polite">Updating…</span>}
          </>
        }
        list={listContent}
        detail={
          <>
            {detail}
            {paneOpen && (
              <TeamForm mode={pane === 'edit' ? 'edit' : 'create'} initial={pane === 'edit' ? team : null} teams={teams} submitting={create.isPending || update.isPending} onSubmit={submitForm} onClose={closePane} />
            )}
          </>
        }
      />
      {team && membersOpen && <ManageMembersDialog team={team} submitting={setMembers.isPending} error={setMembers.error} onSubmit={saveMembers} onClose={closeMembers} />}
      <Dialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        size="sm"
        title="Delete this team?"
        description="Teams that still own work orders, assets, sub-teams or saved filters cannot be deleted; reassign those first or deactivate the team instead."
        preventClose={remove.isPending}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmDelete(false)} disabled={remove.isPending}>
              Cancel
            </Button>
            <Button variant="danger" onClick={() => void onDelete()} loading={remove.isPending} data-autofocus>
              Delete
            </Button>
          </>
        }
      />
    </>
  )
}

function TeamDetailView({
  team,
  teams,
  canManage,
  onEdit,
  onManageMembers,
  onDelete,
}: {
  team: TeamDetail
  teams: Team[]
  canManage: boolean
  onEdit: () => void
  onManageMembers: () => void
  onDelete: () => void
}) {
  const parent = team.parent_team_id ? teams.find((row) => row.id === team.parent_team_id) : undefined
  const children = teams.filter((row) => row.parent_team_id === team.id)
  const members = team.members
  const leads = members.filter((member) => member.is_lead)

  return (
    <DetailPanel
      eyebrow={
        <>
          <Users2 size={12} aria-hidden="true" />
          {parent ? `Sub-team of ${parent.name}` : team.parent_team_id ? 'Sub-team' : 'Top-level team'}
        </>
      }
      title={
        <span className={styles.inlineTitle}>
          {team.name}
          {team.is_active === false && <Badge tone="neutral">Inactive</Badge>}
          {team.project && (
            <Badge tone="outline" className="mono" title={team.project.name}>
              {team.project.code}
            </Badge>
          )}
        </span>
      }
      subtitle={team.description || undefined}
      actions={
        canManage ? (
          <>
            <Button leadingIcon={<Pencil size={16} />} onClick={onEdit}>
              Edit
            </Button>
            <Button leadingIcon={<UserCog size={16} />} onClick={onManageMembers}>
              Manage members
            </Button>
            <DropdownMenu
              align="end"
              label="More actions"
              items={[{ key: 'delete', label: 'Delete team', icon: <Trash2 size={16} />, destructive: true, onSelect: onDelete }]}
              trigger={(props) => (
                <IconButton {...props} ref={props.ref} label="More actions">
                  <MoreHorizontal size={18} />
                </IconButton>
              )}
            />
          </>
        ) : undefined
      }
    >
      <Stack>
        <Card title="Details">
          <FieldList
            items={[
              { label: 'Project', value: team.project ? <Link to={`/projects/${team.project.id}`}>{team.project.name}</Link> : 'No project' },
              { label: 'Parent team', value: parent ? <Link to={`/teams-users/teams/${parent.id}`}>{parent.name}</Link> : team.parent_team_id ? '—' : 'None' },
              { label: 'Leads', value: leads.length > 0 ? leads.map((lead) => lead.user.name).join(', ') : 'No lead yet' },
              { label: 'Members', value: String(members.length) },
              { label: 'Created', value: formatDateTime(team.created_at) },
            ]}
          />
        </Card>
        <Card
          title={`Members (${members.length})`}
          flush
          actions={
            canManage ? (
              <Button size="sm" variant="ghost" leadingIcon={<UserCog size={14} />} onClick={onManageMembers}>
                Manage
              </Button>
            ) : undefined
          }
        >
          {members.length === 0 ? (
            <EmptyState
              compact
              illustration="users"
              title="No members yet"
              description="Add members so work can be assigned to this team."
              action={
                canManage ? (
                  <Button size="sm" variant="primary" onClick={onManageMembers}>
                    Add members
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <ul aria-label="Team members">
              {members.map((member) => (
                <li key={member.user.id}>
                  <ListRow
                    compact
                    to={`/teams-users/users/${member.user.id}`}
                    leading={<Avatar name={member.user.name} src={member.user.avatar_url} />}
                    title={
                      <span className={styles.inlineTitle}>
                        {member.user.name}
                        {member.is_lead && (
                          <Badge tone="gold" size="sm">
                            Lead
                          </Badge>
                        )}
                      </span>
                    }
                    meta={<span>{member.user.email}</span>}
                  />
                </li>
              ))}
            </ul>
          )}
        </Card>
        {children.length > 0 && (
          <Card title={`Sub-teams (${children.length})`} flush>
            <ul aria-label="Sub-teams">
              {children.map((child) => (
                <li key={child.id}>
                  <ListRow compact to={`/teams-users/teams/${child.id}`} leading={<Users2 size={14} aria-hidden="true" style={{ color: 'var(--color-text-muted)' }} />} title={child.name} meta={<span>{child.member_count ?? 0} members</span>} />
                </li>
              ))}
            </ul>
          </Card>
        )}
      </Stack>
    </DetailPanel>
  )
}
