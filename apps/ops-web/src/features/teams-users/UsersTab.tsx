import { zodResolver } from '@hookform/resolvers/zod'
import { ChevronRight, Users2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError, errorMessage } from '@/api/client'
import { labelFor } from '@/api/contracts/common'
import type { Session } from '@/api/contracts/session'
import { MEMBER_STATUSES, MemberAccessInput, USER_SORTS, type Member, type MemberStatus, type MemberUpdateInput, type Role } from '@/api/contracts/users'
import { useTeamOptions } from '@/api/queries/teams'
import { useRoles, useUpdateUser, useUser, useUsers } from '@/api/queries/users'
import { formatDateTime } from '@/lib/dates'
import { useCan, useSession } from '@/lib/permissions'
import {
  Avatar,
  Badge,
  Button,
  Card,
  DetailPanel,
  EmptyState,
  FieldList,
  FieldRow,
  FilterChip,
  FormField,
  InlineAlert,
  Input,
  ListRow,
  ListToolbarSpacer,
  MasterDetailLayout,
  SegmentedControl,
  Select,
  SkeletonBlock,
  SkeletonRows,
  Stack,
  StatusBadge,
  useToast,
} from '@/ui'
import { InviteDialog } from './InviteDialog'
import styles from './teams-users.module.css'
import { listParam, oneOf, withParams } from './urlState'

export const SELF_HINT = 'You cannot change your own role or status'

const STATUS_OPTIONS = MEMBER_STATUSES.map((status) => ({ value: status, label: labelFor(status) }))
type FilterKey = 'filter[role]' | 'filter[status]' | 'filter[team]'

function memberStatus(value: string): MemberStatus {
  return (MEMBER_STATUSES as readonly string[]).includes(value) ? (value as MemberStatus) : 'active'
}

export function UsersTab({ userId: rawUserId }: { userId?: string }) {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const session = useSession()
  const can = useCan()
  const canManage = can('user.manage')

  const q = params.get('q') ?? ''
  const roleFilter = listParam(params, 'filter[role]')
  const statusFilter = listParam(params, 'filter[status]')
  const teamFilter = listParam(params, 'filter[team]')
  const sort = oneOf(params.get('sort'), USER_SORTS, 'name')
  const pane = params.get('pane')
  const hasFilters = Boolean(q) || roleFilter.length > 0 || statusFilter.length > 0 || teamFilter.length > 0

  const userId = rawUserId !== undefined && /^\d+$/.test(rawUserId) ? Number(rawUserId) : undefined
  const badId = rawUserId !== undefined && userId === undefined

  const list = useUsers({ q: q || undefined, role: roleFilter, status: statusFilter, team: teamFilter, sort })
  const members = useMemo(() => list.data?.items ?? [], [list.data])
  const roles = useRoles()
  const teamOptions = useTeamOptions()
  const selected = useUser(userId)

  const setFilter = (key: FilterKey, value: string[]) => setParams(withParams(params, { [key]: value }))
  const clearFilters = () => setParams(withParams(params, { q: null, 'filter[role]': null, 'filter[status]': null, 'filter[team]': null }), { replace: true })
  const closePane = () => setParams(withParams(params, { pane: null }))
  const rowQuery = withParams(params, { pane: null }).toString()
  const rowLink = (id: number) => `/teams-users/users/${id}${rowQuery ? `?${rowQuery}` : ''}`

  const roleOptions = useMemo(() => (roles.data ?? []).filter((role) => role.system_key).map((role) => ({ value: role.system_key as string, label: role.name })), [roles.data])
  const teamFilterOptions = useMemo(() => teamOptions.options.map((option) => ({ value: option.value, label: option.label })), [teamOptions.options])

  const listContent = list.isPending ? (
    <SkeletonRows rows={8} avatar />
  ) : list.isError ? (
    <div style={{ padding: 'var(--space-4)' }}>
      <InlineAlert
        tone="danger"
        title="Members could not be loaded"
        actions={
          <Button size="sm" onClick={() => void list.refetch()}>
            Retry
          </Button>
        }
      >
        {errorMessage(list.error)}
      </InlineAlert>
    </div>
  ) : members.length === 0 && hasFilters ? (
    <EmptyState
      compact
      illustration="search"
      title="No members match"
      description={q ? `Nothing matches “${q}” with the current filters.` : 'No one matches the current filters.'}
      action={
        <Button size="sm" onClick={clearFilters}>
          Clear filters
        </Button>
      }
    />
  ) : members.length === 0 ? (
    <EmptyState
      compact
      illustration="users"
      title="No members yet"
      description="Invite chapter members so they can be added to teams and assigned work."
      action={
        canManage ? (
          <Button variant="primary" size="sm" onClick={() => setParams(withParams(params, { pane: 'invite' }))}>
            Invite a member
          </Button>
        ) : undefined
      }
    />
  ) : (
    <ul aria-label="Members">
      {members.map((member) => (
        <li key={member.id}>
          <ListRow
            to={rowLink(member.user.id)}
            selected={member.user.id === userId}
            leading={<Avatar name={member.user.name} src={member.user.avatar_url} />}
            title={
              <span className={styles.inlineTitle}>
                {member.user.name}
                <StatusBadge status={member.status} size="sm" />
                {member.user.id === session.user.id && (
                  <Badge tone="outline" size="sm">
                    You
                  </Badge>
                )}
              </span>
            }
            meta={
              <>
                <span>{member.user.email}</span>
                <span>{member.role.name}</span>
                {member.teams.length > 0 && (
                  <span className={styles.chips}>
                    {member.teams.map((team) => (
                      <Badge key={team.id} tone="neutral" size="sm">
                        {team.name}
                      </Badge>
                    ))}
                  </span>
                )}
              </>
            }
            trailing={<ChevronRight size={16} style={{ color: 'var(--color-text-disabled)' }} aria-hidden="true" />}
            data-testid="member-row"
          />
        </li>
      ))}
    </ul>
  )

  const notFound = <EmptyState illustration="search" title="Member not found" description="They may have left the chapter, or the link is out of date." action={<Button onClick={() => navigate('/teams-users/users')}>Back to members</Button>} />

  const detail = badId ? (
    <div style={{ padding: 'var(--space-6)' }}>{notFound}</div>
  ) : userId === undefined ? (
    <EmptyState illustration="users" title="Select a member" description="Choose someone on the left to see their profile, teams and access." />
  ) : selected.isPending ? (
    <div style={{ padding: 'var(--space-6)' }}>
      <SkeletonBlock lines={5} />
    </div>
  ) : selected.isError ? (
    <div style={{ padding: 'var(--space-6)' }}>
      {selected.error instanceof ApiError && selected.error.isNotFound ? (
        notFound
      ) : (
        <InlineAlert
          tone="danger"
          title="Could not load this member"
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
    <MemberDetailView member={selected.data} session={session} canManage={canManage} roles={roles.data ?? []} />
  )

  return (
    <>
      <div className={styles.filterStrip} role="group" aria-label="Filters">
        <FilterChip label="Role" options={roleOptions} value={roleFilter} onChange={(value) => setFilter('filter[role]', value)} loading={roles.isPending} emptyText="No roles" />
        <FilterChip label="Status" options={STATUS_OPTIONS} value={statusFilter} onChange={(value) => setFilter('filter[status]', value)} />
        <FilterChip label="Team" options={teamFilterOptions} value={teamFilter} onChange={(value) => setFilter('filter[team]', value)} loading={teamOptions.isLoading} searchable emptyText="No teams yet" />
        {hasFilters && (
          <Button variant="link" size="sm" onClick={clearFilters}>
            Clear all
          </Button>
        )}
      </div>
      <MasterDetailLayout
        detailOpen={rawUserId !== undefined}
        backTo="/teams-users/users"
        backLabel="Back to members"
        listToolbar={
          <>
            <span>{list.data ? `${list.data.total ?? members.length} members` : ''}</span>
            <ListToolbarSpacer />
            {list.isFetching && !list.isPending && <span aria-live="polite">Updating…</span>}
          </>
        }
        list={listContent}
        detail={detail}
      />
      {pane === 'invite' && canManage && <InviteDialog roles={roles.data ?? []} onClose={closePane} onDone={(member) => navigate(`/teams-users/users/${member.user.id}`)} />}
    </>
  )
}

function MemberDetailView({ member, session, canManage, roles }: { member: Member; session: Session; canManage: boolean; roles: Role[] }) {
  const isSelf = member.user.id === session.user.id
  // `user_ref` carries no username or legacy role; the session does for yourself.
  const username = member.user.username ?? (isSelf ? session.user.username : undefined)
  const legacyRole = member.user.legacy_role ?? (isSelf ? session.user.legacy_role : undefined)
  const profile = [
    { label: 'Email', value: <a href={`mailto:${member.user.email}`}>{member.user.email}</a> },
    ...(username ? [{ label: 'Username', value: username }] : []),
    { label: 'Title', value: member.title || '—' },
    { label: 'Role', value: member.role.name },
    { label: 'Joined', value: formatDateTime(member.joined_at) },
    { label: 'Last sign-in', value: member.last_login_at ? formatDateTime(member.last_login_at) : 'Never' },
    ...(legacyRole ? [{ label: 'Legacy portal role', value: labelFor(legacyRole) }] : []),
  ]

  return (
    <DetailPanel
      eyebrow={member.role.name}
      title={
        <span className={styles.titleWithAvatar}>
          <Avatar name={member.user.name} src={member.user.avatar_url} size="lg" />
          {member.user.name}
          <StatusBadge status={member.status} />
          {isSelf && <Badge tone="outline">You</Badge>}
        </span>
      }
      subtitle={member.user.email}
    >
      <Stack>
        <Card title="Profile">
          <FieldList items={profile} />
        </Card>
        <Card title={`Teams (${member.teams.length})`} flush>
          {member.teams.length === 0 ? (
            <EmptyState compact illustration="users" title="Not on a team yet" description="Team leads and administrators add members from the team’s page." />
          ) : (
            <ul aria-label="Teams">
              {member.teams.map((team) => (
                <li key={team.id}>
                  <ListRow compact to={`/teams-users/teams/${team.id}`} leading={<Users2 size={14} aria-hidden="true" style={{ color: 'var(--color-text-muted)' }} />} title={team.name} />
                </li>
              ))}
            </ul>
          )}
        </Card>
        {canManage && <AccessCard key={`${member.id}:${member.role.id}:${member.status}:${member.title ?? ''}`} member={member} roles={roles} isSelf={isSelf} />}
      </Stack>
    </DetailPanel>
  )
}

/**
 * "Role & access": PATCH /users/:id with only the changed keys. Keyed by the
 * member's current values from the parent so a saved change remounts it with
 * fresh defaults.
 */
function AccessCard({ member, roles, isSelf }: { member: Member; roles: Role[]; isSelf: boolean }) {
  const toast = useToast()
  const update = useUpdateUser(member.user.id)
  const [conflict, setConflict] = useState<string | null>(null)
  const form = useForm<MemberAccessInput>({
    resolver: zodResolver(MemberAccessInput),
    defaultValues: { role_id: member.role.id, status: memberStatus(member.status), title: member.title ?? '' },
  })
  const { register, control, handleSubmit, setError, formState } = form
  const roleKnown = roles.some((role) => role.id === member.role.id)

  const submit = handleSubmit(async (values) => {
    const body: MemberUpdateInput = {}
    if (!isSelf && values.role_id !== member.role.id) body.role_id = values.role_id
    if (!isSelf && values.status !== member.status && (values.status === 'active' || values.status === 'suspended')) body.status = values.status
    const title = (values.title ?? '').trim()
    if (title !== (member.title ?? '')) body.title = title || null
    if (Object.keys(body).length === 0) return
    setConflict(null)
    try {
      await update.mutateAsync(body)
      toast.success('Member updated')
    } catch (error) {
      if (error instanceof ApiError && error.isValidation) {
        for (const [field, message] of Object.entries(error.errors)) {
          if (field === 'role_id' || field === 'role_key') setError('role_id', { type: 'server', message })
          else if (field === 'status' || field === 'title') setError(field, { type: 'server', message })
          else setConflict(message)
        }
      } else if (error instanceof ApiError && error.isForbidden) {
        toast.error('You cannot change this member', error.message)
      } else {
        // 409 cannot_modify_self / last_admin and anything unexpected: keep the entered values.
        setConflict(errorMessage(error))
      }
    }
  })

  return (
    <Card title="Role & access">
      <form onSubmit={submit} noValidate className={styles.formGrid} aria-label="Role and access">
        {isSelf && <InlineAlert tone="info">{SELF_HINT}.</InlineAlert>}
        {conflict && (
          <InlineAlert tone="danger" title="Change not applied">
            {conflict}
          </InlineAlert>
        )}
        <FieldRow>
          <FormField label="Role" error={formState.errors.role_id?.message}>
            <Controller
              control={control}
              name="role_id"
              render={({ field }) => (
                <Select value={field.value} onChange={field.onChange} onBlur={field.onBlur} name={field.name} ref={field.ref} disabled={isSelf}>
                  {!roleKnown && <option value={member.role.id}>{member.role.name}</option>}
                  {roles.map((role) => (
                    <option key={role.id} value={role.id}>
                      {role.name}
                    </option>
                  ))}
                </Select>
              )}
            />
          </FormField>
          <FormField label="Status" asGroup error={formState.errors.status?.message} hint={member.status === 'invited' && !isSelf ? 'Invited members become active when they first sign in; you can activate them now or suspend the invitation.' : undefined}>
            {isSelf ? (
              <div className={styles.staticControl}>
                <StatusBadge status={member.status} />
              </div>
            ) : (
              <Controller
                control={control}
                name="status"
                render={({ field }) => (
                  <SegmentedControl<MemberStatus>
                    label="Status"
                    value={field.value}
                    onChange={field.onChange}
                    options={[
                      { value: 'active', label: 'Active' },
                      { value: 'suspended', label: 'Suspended', tone: 'danger' },
                    ]}
                  />
                )}
              />
            )}
          </FormField>
        </FieldRow>
        <FormField label="Title" optionalLabel error={formState.errors.title?.message} hint="Shown next to their name, e.g. Treasurer or Wheels lead.">
          <Input {...register('title')} maxLength={120} placeholder="No title" />
        </FormField>
        <div className={styles.formFooter}>
          <Button variant="primary" type="submit" loading={update.isPending} disabled={!formState.isDirty}>
            Save changes
          </Button>
        </div>
      </form>
    </Card>
  )
}
