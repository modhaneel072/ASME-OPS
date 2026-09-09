import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { ApiError, errorMessage } from '@/api/client'
import { labelFor } from '@/api/contracts/common'
import { EMPTY_PROJECT_INPUT, PROJECT_STATUSES, ProjectInput, projectToInput, RISK_LEVELS, type Project, type RiskLevel } from '@/api/contracts/projects'
import { usePeopleOptions } from '@/api/queries/users'
import { Button, Combobox, DateInput, FieldRow, FormField, FormSection, InlineAlert, Input, SegmentedControl, Select, SideSheet, Textarea } from '@/ui'
import { applyServerErrors, unmappedServerErrors } from './shared'
import styles from './projects.module.css'

export interface ProjectFormProps {
  open: boolean
  mode: 'create' | 'edit'
  initial?: Project | null
  submitting: boolean
  error: unknown
  onSubmit: (values: ProjectInput) => Promise<void>
  onClose: () => void
}

const FORM_FIELDS = Object.keys(EMPTY_PROJECT_INPUT)
const RISK_SHORT: Record<RiskLevel, string> = { low: 'Low', medium: 'Medium', high: 'High', critical: 'Critical' }

export function ProjectForm({ open, mode, initial, submitting, error, onSubmit, onClose }: ProjectFormProps) {
  const people = usePeopleOptions()
  const form = useForm<ProjectInput>({ resolver: zodResolver(ProjectInput), defaultValues: EMPTY_PROJECT_INPUT })
  const { register, control, handleSubmit, reset, setError, formState } = form
  const leftover = unmappedServerErrors(error, FORM_FIELDS)

  useEffect(() => {
    if (!open) return
    reset(mode === 'edit' && initial ? projectToInput(initial) : EMPTY_PROJECT_INPUT)
  }, [open, mode, initial, reset])

  // Map server-side field errors onto the form.
  useEffect(() => {
    applyServerErrors(error, setError, FORM_FIELDS)
  }, [error, setError])

  const generalError = error && !(error instanceof ApiError && error.isValidation) ? errorMessage(error) : null
  const dirty = formState.isDirty

  return (
    <SideSheet
      open={open}
      onClose={onClose}
      title={mode === 'create' ? 'New Project' : `Edit ${initial?.name ?? 'project'}`}
      subtitle={mode === 'create' ? 'A project groups work orders, milestones, teams and documents for one effort.' : undefined}
      onRequestClose={() => (dirty && !submitting ? window.confirm('Discard your changes?') : true)}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="project-form" loading={submitting}>
            {mode === 'create' ? 'Create Project' : 'Save changes'}
          </Button>
        </>
      }
    >
      <form id="project-form" noValidate onSubmit={handleSubmit((values) => onSubmit(values))} style={{ display: 'grid', gap: 'var(--space-5)' }}>
        {generalError && <InlineAlert tone="danger">{generalError}</InlineAlert>}
        {leftover.length > 0 && (
          <InlineAlert tone="danger" title="Some fields need attention">
            {leftover.join(' ')}
          </InlineAlert>
        )}

        <FormSection title="Basics">
          <FormField label="Name" required error={formState.errors.name?.message}>
            <Input {...register('name')} data-autofocus placeholder="e.g. Crater Cruncher Rover" maxLength={200} />
          </FormField>
          <FieldRow>
            <FormField label="Code" optionalLabel hint="Leave blank to generate from the name" error={formState.errors.code?.message}>
              <Input {...register('code')} placeholder="CCR" maxLength={20} className="mono" style={{ textTransform: 'uppercase' }} />
            </FormField>
            <FormField label="Status" error={formState.errors.status?.message}>
              <Select {...register('status')}>
                {PROJECT_STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {labelFor(status)}
                  </option>
                ))}
              </Select>
            </FormField>
          </FieldRow>
          <FormField label="Description" optionalLabel error={formState.errors.description?.message}>
            <Textarea {...register('description')} rows={4} placeholder="Goal, scope and what done looks like." />
          </FormField>
          <FormField label="Visibility" asGroup error={formState.errors.visibility?.message}>
            <Controller
              control={control}
              name="visibility"
              render={({ field }) => (
                <>
                  <SegmentedControl
                    label="Visibility"
                    value={field.value}
                    onChange={field.onChange}
                    options={[
                      { value: 'chapter', label: 'Chapter' },
                      { value: 'private', label: 'Private' },
                    ]}
                  />
                  <p className={styles.segmentHelp}>{field.value === 'private' ? 'Only project members and officers with private access can see this project.' : 'Every chapter member can see this project and its work.'}</p>
                </>
              )}
            />
          </FormField>
          <FormField label="Risk" asGroup error={formState.errors.risk_level?.message}>
            <Controller
              control={control}
              name="risk_level"
              render={({ field }) => <SegmentedControl label="Risk" value={field.value} onChange={field.onChange} options={RISK_LEVELS.map((level) => ({ value: level, label: RISK_SHORT[level], tone: level === 'critical' ? ('danger' as const) : undefined }))} />}
            />
          </FormField>
        </FormSection>

        <FormSection title="People">
          <FieldRow>
            <FormField label="Lead" optionalLabel error={formState.errors.lead_user_id?.message}>
              <Controller control={control} name="lead_user_id" render={({ field }) => <Combobox<number> options={people.options} loading={people.isLoading} value={field.value ?? null} onChange={field.onChange} placeholder="Choose a member" emptyText="No matching members" />} />
            </FormField>
            <FormField label="Faculty advisor" optionalLabel error={formState.errors.faculty_advisor_user_id?.message}>
              <Controller control={control} name="faculty_advisor_user_id" render={({ field }) => <Combobox<number> options={people.options} loading={people.isLoading} value={field.value ?? null} onChange={field.onChange} placeholder="Choose an advisor" emptyText="No matching members" />} />
            </FormField>
          </FieldRow>
        </FormSection>

        <FormSection title="Schedule and budget">
          <FieldRow>
            <FormField label="Start date" optionalLabel error={formState.errors.start_date?.message}>
              <DateInput {...register('start_date')} />
            </FormField>
            <FormField label="Target date" optionalLabel error={formState.errors.target_date?.message}>
              <DateInput {...register('target_date')} />
            </FormField>
          </FieldRow>
          <FieldRow>
            <FormField label="Budget amount" optionalLabel hint="In US dollars" error={formState.errors.budget_amount?.message}>
              <Input {...register('budget_amount')} type="number" inputMode="decimal" min={0} step="0.01" placeholder="0.00" />
            </FormField>
            <FormField label="Academic year" optionalLabel hint="YYYY-YY, for example 2026-27" error={formState.errors.academic_year?.message}>
              <Input {...register('academic_year')} placeholder="2026-27" maxLength={12} />
            </FormField>
          </FieldRow>
          <FormField label="Competition" optionalLabel error={formState.errors.competition?.message}>
            <Input {...register('competition')} placeholder="e.g. NASA Lunabotics" maxLength={200} />
          </FormField>
        </FormSection>

        <FormSection title="Links">
          <FormField label="Repository URL" optionalLabel error={formState.errors.repository_url?.message}>
            <Input {...register('repository_url')} type="url" placeholder="https://github.com/…" />
          </FormField>
          <FormField label="CAD URL" optionalLabel error={formState.errors.cad_url?.message}>
            <Input {...register('cad_url')} type="url" placeholder="https://…" />
          </FormField>
          <FormField label="Requirements URL" optionalLabel error={formState.errors.requirements_url?.message}>
            <Input {...register('requirements_url')} type="url" placeholder="https://…" />
          </FormField>
          <FormField label="Public site project id" optionalLabel hint="legacy public site project id" error={formState.errors.public_project_id?.message}>
            <Input {...register('public_project_id')} type="number" inputMode="numeric" min={1} step={1} placeholder="e.g. 3" />
          </FormField>
        </FormSection>
      </form>
    </SideSheet>
  )
}
