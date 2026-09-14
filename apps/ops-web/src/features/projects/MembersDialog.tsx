import { useMemo, useState } from 'react'
import { ApiError, errorMessage } from '@/api/client'
import { PROJECT_ROLE_LABELS, PROJECT_ROLES, type MemberInput, type Project, type ProjectMember, type ProjectRole } from '@/api/contracts/projects'
import { useTeamOptions } from '@/api/queries/teams'
import { usePeopleOptions } from '@/api/queries/users'
import { Button, Combobox, Dialog, FormField, InlineAlert, Select } from '@/ui'
import styles from './projects.module.css'

export interface MembersDialogProps {
  open: boolean
  project: Project
  members: ProjectMember[]
  submitting: boolean
  error: unknown
  onSubmit: (members: MemberInput[]) => Promise<void>
  onClose: () => void
}

function toRole(value: string): ProjectRole {
  return (PROJECT_ROLES as readonly string[]).includes(value) ? (value as ProjectRole) : 'member'
}

/** The editor mounts only while open so its draft state starts fresh from `members` each time. */
export function MembersDialog(props: MembersDialogProps) {
  if (!props.open) return null
  return <MembersEditor {...props} />
}

function MembersEditor({ open, project, members, submitting, error, onSubmit, onClose }: MembersDialogProps) {
  const people = usePeopleOptions()
  const teams = useTeamOptions()
  const [rows, setRows] = useState<MemberInput[]>(() => members.map((member) => ({ user_id: member.user.id, project_role: toRole(member.project_role), team_id: member.team?.id ?? null })))
  const [localError, setLocalError] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)

  const nameFor = useMemo(() => {
    const byId = new Map<number, string>()
    for (const option of people.options) byId.set(option.value, option.label)
    for (const member of members) byId.set(member.user.id, member.user.name)
    return (id: number) => byId.get(id) ?? `Member #${id}`
  }, [people.options, members])

  // The picker lists every active member plus anyone already on the project (in case they are no longer active).
  const pickerOptions = useMemo(() => {
    const known = new Set(people.options.map((option) => option.value))
    const extra = members.filter((member) => !known.has(member.user.id)).map((member) => ({ value: member.user.id, label: member.user.name, meta: 'Inactive' }))
    return [...people.options, ...extra]
  }, [people.options, members])

  const selectedIds = rows.map((row) => row.user_id)
  const leadId = project.lead?.id ?? null

  const changeSelection = (ids: number[]) => {
    setDirty(true)
    setLocalError(null)
    setRows((current) => {
      const existing = new Map(current.map((row) => [row.user_id, row]))
      return ids.map((id) => existing.get(id) ?? { user_id: id, project_role: id === leadId ? 'lead' : 'member', team_id: null })
    })
  }

  const updateRow = (userId: number, patch: Partial<MemberInput>) => {
    setDirty(true)
    setRows((current) => current.map((row) => (row.user_id === userId ? { ...row, ...patch } : row)))
  }

  const submit = async () => {
    if (leadId && !selectedIds.includes(leadId)) {
      setLocalError(`${nameFor(leadId)} leads this project and must remain a member. Change the lead from Edit first.`)
      return
    }
    await onSubmit(rows)
  }

  const serverError = error instanceof ApiError ? (error.isValidation ? Object.values(error.errors).join(' ') : errorMessage(error)) : error ? errorMessage(error) : null
  const requestClose = () => {
    if (submitting) return
    if (dirty && !window.confirm('Discard your changes?')) return
    onClose()
  }

  return (
    <Dialog
      open={open}
      onClose={requestClose}
      size="lg"
      title="Manage members"
      description={`Choose who belongs to ${project.name} and the role each person plays.`}
      preventClose={submitting}
      footer={
        <>
          <Button variant="ghost" onClick={requestClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" onClick={() => void submit()} loading={submitting}>
            Save members
          </Button>
        </>
      }
    >
      <div style={{ display: 'grid', gap: 'var(--space-4)' }}>
        {(localError || serverError) && (
          <InlineAlert tone="danger" title="Members could not be saved">
            {localError ?? serverError}
          </InlineAlert>
        )}
        <FormField label="Members" hint="Search by name; the project lead is always a member.">
          <Combobox<number> multiple options={pickerOptions} loading={people.isLoading} value={selectedIds} onChange={changeSelection} placeholder="Add people" emptyText="No matching members" />
        </FormField>
        {rows.length > 0 && (
          <div className={styles.memberRows} role="group" aria-label="Member roles">
            <div className={styles.memberRow} aria-hidden="true">
              <span className={styles.helpText}>Person</span>
              <span className={styles.helpText}>Project role</span>
              <span className={styles.helpText}>Team</span>
            </div>
            {rows.map((row) => {
              const name = nameFor(row.user_id)
              const isLead = row.user_id === leadId
              return (
                <div key={row.user_id} className={styles.memberRow}>
                  <span className={styles.person}>
                    <span className={styles.personName}>{name}</span>
                    {isLead && <span className={styles.helpText}>(lead)</span>}
                  </span>
                  <Select compact aria-label={`Role for ${name}`} value={row.project_role} disabled={isLead} onChange={(event) => updateRow(row.user_id, { project_role: toRole(event.target.value) })}>
                    {PROJECT_ROLES.map((role) => (
                      <option key={role} value={role}>
                        {PROJECT_ROLE_LABELS[role]}
                      </option>
                    ))}
                  </Select>
                  <Select compact aria-label={`Team for ${name}`} value={row.team_id ?? ''} placeholder="No team" onChange={(event) => updateRow(row.user_id, { team_id: event.target.value || null })}>
                    {teams.options.map((team) => (
                      <option key={team.value} value={team.value}>
                        {team.label}
                      </option>
                    ))}
                  </Select>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </Dialog>
  )
}
