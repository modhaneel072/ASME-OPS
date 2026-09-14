import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { ApiError, errorMessage } from '@/api/client'
import { labelFor } from '@/api/contracts/common'
import { MILESTONE_STATUSES, MilestoneInput, milestoneToInput, type Milestone } from '@/api/contracts/projects'
import { usePeopleOptions } from '@/api/queries/users'
import { Button, Combobox, DateInput, Dialog, FieldRow, FormField, InlineAlert, Input, Select, Textarea } from '@/ui'
import { applyServerErrors, unmappedServerErrors } from './shared'

export interface MilestoneDialogProps {
  open: boolean
  milestone: Milestone | null
  submitting: boolean
  error: unknown
  onSubmit: (values: MilestoneInput) => Promise<void>
  onClose: () => void
}

const FIELDS = ['name', 'description', 'due_date', 'owner_user_id', 'weight', 'status']

export function MilestoneDialog({ open, milestone, submitting, error, onSubmit, onClose }: MilestoneDialogProps) {
  const people = usePeopleOptions()
  const { register, control, handleSubmit, reset, setError, formState } = useForm<MilestoneInput>({ resolver: zodResolver(MilestoneInput), defaultValues: milestoneToInput(null) })
  const leftover = unmappedServerErrors(error, FIELDS)

  useEffect(() => {
    if (!open) return
    reset(milestoneToInput(milestone))
  }, [open, milestone, reset])

  useEffect(() => {
    applyServerErrors(error, setError, FIELDS)
  }, [error, setError])

  const generalError = error && !(error instanceof ApiError && error.isValidation) ? errorMessage(error) : null
  const requestClose = () => {
    if (submitting) return
    if (formState.isDirty && !window.confirm('Discard your changes?')) return
    onClose()
  }

  return (
    <Dialog
      open={open}
      onClose={requestClose}
      title={milestone ? `Edit ${milestone.name}` : 'Add milestone'}
      description={milestone ? undefined : 'Milestones mark the checkpoints a project must reach.'}
      preventClose={submitting}
      footer={
        <>
          <Button variant="ghost" onClick={requestClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="milestone-form" loading={submitting}>
            {milestone ? 'Save changes' : 'Add milestone'}
          </Button>
        </>
      }
    >
      <form id="milestone-form" noValidate onSubmit={handleSubmit((values) => onSubmit(values))} style={{ display: 'grid', gap: 'var(--space-4)' }}>
        {generalError && <InlineAlert tone="danger">{generalError}</InlineAlert>}
        {leftover.length > 0 && <InlineAlert tone="danger">{leftover.join(' ')}</InlineAlert>}
        <FormField label="Name" required error={formState.errors.name?.message}>
          <Input {...register('name')} data-autofocus placeholder="e.g. Critical design review" maxLength={200} />
        </FormField>
        <FormField label="Description" optionalLabel error={formState.errors.description?.message}>
          <Textarea {...register('description')} rows={3} placeholder="What must be true for this milestone to count as done." />
        </FormField>
        <FieldRow>
          <FormField label="Due date" optionalLabel error={formState.errors.due_date?.message}>
            <DateInput {...register('due_date')} />
          </FormField>
          <FormField label="Owner" optionalLabel error={formState.errors.owner_user_id?.message}>
            <Controller control={control} name="owner_user_id" render={({ field }) => <Combobox<number> options={people.options} loading={people.isLoading} value={field.value ?? null} onChange={field.onChange} placeholder="Choose a member" emptyText="No matching members" />} />
          </FormField>
        </FieldRow>
        <FieldRow>
          <FormField label="Weight" hint="Heavier milestones count more toward completion" error={formState.errors.weight?.message}>
            <Input {...register('weight', { valueAsNumber: true })} type="number" inputMode="numeric" min={1} step={1} />
          </FormField>
          <FormField label="Status" error={formState.errors.status?.message}>
            <Select {...register('status')}>
              {MILESTONE_STATUSES.filter((status) => status !== 'missed').map((status) => (
                <option key={status} value={status}>
                  {labelFor(status)}
                </option>
              ))}
            </Select>
          </FormField>
        </FieldRow>
      </form>
    </Dialog>
  )
}
