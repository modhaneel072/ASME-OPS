import { useMemo, useState } from 'react'
import { ApiError, errorMessage } from '@/api/client'
import type { TeamDetail, TeamMemberInput } from '@/api/contracts/teams'
import { usePeopleOptions } from '@/api/queries/users'
import { Button, Checkbox, Combobox, Dialog, FormField, InlineAlert, type ComboOption } from '@/ui'
import styles from './teams-users.module.css'

export interface ManageMembersDialogProps {
  team: TeamDetail
  submitting: boolean
  /** The last `PUT /teams/:id/members` failure, if any. */
  error: unknown
  onSubmit: (members: TeamMemberInput[]) => Promise<void>
  onClose: () => void
}

function sameSet(a: number[], b: number[]): boolean {
  if (a.length !== b.length) return false
  const other = new Set(b)
  return a.every((value) => other.has(value))
}

/**
 * Replaces a team's membership. Mounted only while open, so the selection is
 * seeded from `team.members` at mount time and a refetch cannot reset edits.
 */
export function ManageMembersDialog({ team, submitting, error, onSubmit, onClose }: ManageMembersDialogProps) {
  const people = usePeopleOptions()
  const initialIds = useMemo(() => team.members.map((member) => member.user.id), [team.members])
  const initialLeads = useMemo(() => team.members.filter((member) => member.is_lead).map((member) => member.user.id), [team.members])
  const [selected, setSelected] = useState<number[]>(initialIds)
  const [leads, setLeads] = useState<number[]>(initialLeads)

  // Current members who are no longer active (invited/suspended) are not in
  // the people picker; keep them selectable so their tokens still render and
  // the admin can remove them. The server rejects re-saving inactive members
  // with a clear message that lands in the alert below.
  const options = useMemo<ComboOption<number>[]>(() => {
    const known = new Set(people.options.map((option) => option.value))
    const extra = team.members.filter((member) => !known.has(member.user.id)).map((member) => ({ value: member.user.id, label: member.user.name, meta: member.user.email }))
    return [...people.options, ...extra]
  }, [people.options, team.members])
  const byValue = useMemo(() => new Map(options.map((option) => [option.value, option])), [options])

  const dirty = !sameSet(selected, initialIds) || !sameSet(leads, initialLeads)

  const requestClose = () => {
    if (submitting) return
    if (dirty && !window.confirm('Discard your changes to the team’s members?')) return
    onClose()
  }

  const changeSelected = (next: number[]) => {
    setSelected(next)
    setLeads((current) => current.filter((id) => next.includes(id)))
  }
  const toggleLead = (id: number, checked: boolean) => setLeads((current) => (checked ? [...current, id] : current.filter((value) => value !== id)))
  const save = () => {
    void onSubmit(selected.map((id) => ({ user_id: id, is_lead: leads.includes(id) })))
  }

  const problem =
    error instanceof ApiError && error.isValidation
      ? (error.errors.members ?? Object.values(error.errors)[0] ?? error.message)
      : error && !(error instanceof ApiError && error.isForbidden)
        ? errorMessage(error)
        : null

  return (
    <Dialog
      open
      onClose={requestClose}
      title={`Manage members · ${team.name}`}
      description="Choose who belongs to this team and who leads it. Leads can edit the team and assign its work."
      preventClose={submitting}
      footer={
        <>
          <Button variant="ghost" onClick={requestClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" onClick={save} loading={submitting} disabled={!dirty}>
            Save members
          </Button>
        </>
      }
    >
      <div className={styles.formGrid}>
        {problem && (
          <InlineAlert tone="danger" title="Members were not saved">
            {problem}
          </InlineAlert>
        )}
        <FormField label="Members" hint="Only active chapter members can join a team.">
          <Combobox<number> multiple options={options} loading={people.isLoading} value={selected} onChange={changeSelected} placeholder="Add people" emptyText="No matching members" />
        </FormField>
        <fieldset className={styles.leadList}>
          <legend className={styles.leadLegend}>Team leads</legend>
          {selected.length === 0 ? (
            <p className={styles.hint}>Add members first, then choose who leads the team.</p>
          ) : (
            selected.map((id) => {
              const person = byValue.get(id)
              return <Checkbox key={id} label={`Team lead: ${person?.label ?? `member #${id}`}`} hint={person?.meta} checked={leads.includes(id)} onChange={(checked) => toggleLead(id, checked)} />
            })
          )}
        </fieldset>
      </div>
    </Dialog>
  )
}
