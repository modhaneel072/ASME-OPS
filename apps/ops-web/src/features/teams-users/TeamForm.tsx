import { zodResolver } from '@hookform/resolvers/zod'
import { useMemo, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { ApiError, errorMessage } from '@/api/client'
import { TeamInput, type Team, type TeamDetail } from '@/api/contracts/teams'
import { useProjectOptions } from '@/api/queries/projects'
import { Button, Combobox, FormField, InlineAlert, Input, SideSheet, Textarea, useToast } from '@/ui'
import styles from './teams-users.module.css'

export interface TeamFormProps {
  mode: 'create' | 'edit'
  /** The team being edited; ignored when creating. */
  initial?: TeamDetail | null
  /** Visible teams, used for the parent picker (self and descendants are excluded). */
  teams: Team[]
  submitting: boolean
  /** Performs the request; rejections are mapped onto the form here. */
  onSubmit: (values: TeamInput) => Promise<void>
  onClose: () => void
}

const FIELDS: ReadonlyArray<keyof TeamInput> = ['name', 'description', 'parent_team_id', 'project_id']

function descendants(all: Team[], id: string): Set<string> {
  const out = new Set<string>([id])
  let grew = true
  while (grew) {
    grew = false
    for (const team of all) {
      if (team.parent_team_id && out.has(team.parent_team_id) && !out.has(team.id)) {
        out.add(team.id)
        grew = true
      }
    }
  }
  return out
}

/**
 * Create / edit pane for a team. Mounted only while open so the defaults are
 * taken from `initial` at mount time; the parent unmounts it to close.
 */
export function TeamForm({ mode, initial, teams, submitting, onSubmit, onClose }: TeamFormProps) {
  const toast = useToast()
  const projects = useProjectOptions()
  const [generalError, setGeneralError] = useState<string | null>(null)
  const editing = mode === 'edit' ? initial : null
  const form = useForm<TeamInput>({
    resolver: zodResolver(TeamInput),
    defaultValues: {
      name: editing?.name ?? '',
      description: editing?.description ?? '',
      parent_team_id: editing?.parent_team_id ?? null,
      project_id: editing?.project?.id ?? null,
    },
  })
  const { register, control, handleSubmit, setError, formState } = form

  const editingId = editing?.id
  const parentOptions = useMemo(() => {
    const excluded = editingId ? descendants(teams, editingId) : new Set<string>()
    return teams.filter((team) => !excluded.has(team.id)).map((team) => ({ value: team.id, label: team.name, meta: team.project?.code }))
  }, [teams, editingId])

  const requestClose = () => {
    if (formState.isDirty && !submitting && !window.confirm('Discard your changes?')) return false
    onClose()
    return true
  }

  const submit = handleSubmit(async (values) => {
    setGeneralError(null)
    try {
      await onSubmit({
        name: values.name.trim(),
        description: values.description?.trim() ?? '',
        parent_team_id: values.parent_team_id ?? null,
        project_id: values.project_id ?? null,
      })
    } catch (error) {
      if (error instanceof ApiError && error.isValidation) {
        for (const [field, message] of Object.entries(error.errors)) {
          if ((FIELDS as readonly string[]).includes(field)) setError(field as keyof TeamInput, { type: 'server', message })
          else setGeneralError(message)
        }
      } else if (error instanceof ApiError && error.isForbidden) {
        toast.error('You cannot change this team', error.message)
      } else {
        setGeneralError(errorMessage(error))
      }
    }
  })

  return (
    <SideSheet
      open
      onClose={onClose}
      onRequestClose={requestClose}
      title={mode === 'create' ? 'New Team' : `Edit ${editing?.name ?? 'team'}`}
      subtitle={mode === 'create' ? 'Teams group chapter members so work can be assigned to them together.' : undefined}
      footer={
        <>
          <Button variant="ghost" onClick={() => requestClose()} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="team-form" loading={submitting}>
            {mode === 'create' ? 'Create Team' : 'Save changes'}
          </Button>
        </>
      }
    >
      <form id="team-form" noValidate onSubmit={submit} className={styles.formGrid}>
        {generalError && <InlineAlert tone="danger">{generalError}</InlineAlert>}
        <FormField label="Name" required error={formState.errors.name?.message}>
          <Input {...register('name')} data-autofocus placeholder="e.g. Wheels and Mobility" maxLength={160} />
        </FormField>
        <FormField label="Project" optionalLabel error={formState.errors.project_id?.message} hint="Attach the team to the project it works on.">
          <Controller
            control={control}
            name="project_id"
            render={({ field }) => <Combobox options={projects.options} loading={projects.isLoading} value={field.value ?? null} onChange={field.onChange} placeholder="No project" emptyText="No matching projects" />}
          />
        </FormField>
        <FormField label="Parent team" optionalLabel error={formState.errors.parent_team_id?.message} hint="Nest this team under another one, e.g. Software under Robotic Arm.">
          <Controller
            control={control}
            name="parent_team_id"
            render={({ field }) => <Combobox options={parentOptions} value={field.value ?? null} onChange={field.onChange} placeholder="No parent (top level)" emptyText="No matching teams" />}
          />
        </FormField>
        <FormField label="Description" optionalLabel error={formState.errors.description?.message}>
          <Textarea {...register('description')} rows={4} placeholder="What the team owns, when it meets, anything a new member should know." />
        </FormField>
      </form>
    </SideSheet>
  )
}
