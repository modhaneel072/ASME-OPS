import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useMemo } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { ApiError, errorMessage } from '@/api/client'
import { LocationInput, type Location } from '@/api/contracts/locations'
import { Button, Combobox, FieldRow, FormField, InlineAlert, Input, SideSheet, Textarea } from '@/ui'

export interface LocationFormProps {
  open: boolean
  mode: 'create' | 'edit'
  /** Existing location when editing; when creating, may carry a preselected parent. */
  initial?: Partial<Location> | null
  locations: Location[]
  submitting: boolean
  error: unknown
  onSubmit: (values: LocationInput) => Promise<void>
  onClose: () => void
}

function descendants(all: Location[], id: string): Set<string> {
  const out = new Set<string>([id])
  let grew = true
  while (grew) {
    grew = false
    for (const location of all) {
      if (location.parent_id && out.has(location.parent_id) && !out.has(location.id)) {
        out.add(location.id)
        grew = true
      }
    }
  }
  return out
}

export function LocationForm({ open, mode, initial, locations, submitting, error, onSubmit, onClose }: LocationFormProps) {
  const form = useForm<LocationInput>({
    resolver: zodResolver(LocationInput),
    defaultValues: { name: '', description: '', parent_id: null, building: '', room: '' },
  })
  const { register, control, handleSubmit, reset, setError, formState } = form

  useEffect(() => {
    if (!open) return
    reset({
      name: mode === 'edit' ? (initial?.name ?? '') : '',
      description: mode === 'edit' ? (initial?.description ?? '') : '',
      parent_id: initial?.parent_id ?? null,
      building: mode === 'edit' ? (initial?.building ?? '') : '',
      room: mode === 'edit' ? (initial?.room ?? '') : '',
    })
  }, [open, mode, initial, reset])

  // Map server-side field errors onto the form.
  useEffect(() => {
    if (error instanceof ApiError && error.isValidation) {
      for (const [field, message] of Object.entries(error.errors)) setError(field as keyof LocationInput, { type: 'server', message })
    }
  }, [error, setError])

  const initialId = initial?.id
  const parentOptions = useMemo(() => {
    const excluded = mode === 'edit' && initialId ? descendants(locations, initialId) : new Set<string>()
    return locations
      .filter((location) => !excluded.has(location.id))
      .map((location) => ({ value: location.id, label: location.name, meta: location.path.slice(0, -1).join(' › ') || undefined }))
  }, [locations, mode, initialId])

  const generalError = error && !(error instanceof ApiError && error.isValidation) ? errorMessage(error) : null
  const dirty = formState.isDirty

  return (
    <SideSheet
      open={open}
      onClose={onClose}
      title={mode === 'create' ? 'New Location' : `Edit ${initial?.name ?? 'location'}`}
      subtitle={mode === 'create' ? 'Locations organise assets, parts and work.' : undefined}
      onRequestClose={() => (dirty && !submitting ? window.confirm('Discard your changes?') : true)}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="location-form" loading={submitting}>
            {mode === 'create' ? 'Create Location' : 'Save changes'}
          </Button>
        </>
      }
    >
      <form
        id="location-form"
        noValidate
        onSubmit={handleSubmit(async (values) => {
          await onSubmit({
            ...values,
            description: values.description || '',
            building: values.building || '',
            room: values.room || '',
            parent_id: values.parent_id ?? null,
          })
        })}
        style={{ display: 'grid', gap: 'var(--space-4)' }}
      >
        {generalError && <InlineAlert tone="danger">{generalError}</InlineAlert>}
        <FormField label="Name" required error={formState.errors.name?.message}>
          <Input {...register('name')} data-autofocus placeholder="e.g. Robotics Lab" maxLength={160} />
        </FormField>
        <FormField label="Parent location" optionalLabel error={formState.errors.parent_id?.message} hint="Nest this location under another one, e.g. a bench inside a lab.">
          <Controller control={control} name="parent_id" render={({ field }) => <Combobox options={parentOptions} value={field.value ?? null} onChange={field.onChange} placeholder="No parent (top level)" emptyText="No matching locations" />} />
        </FormField>
        <FieldRow>
          <FormField label="Building" optionalLabel error={formState.errors.building?.message}>
            <Input {...register('building')} placeholder="Engineering Student Center" maxLength={160} />
          </FormField>
          <FormField label="Room" optionalLabel error={formState.errors.room?.message}>
            <Input {...register('room')} placeholder="1245" maxLength={80} />
          </FormField>
        </FieldRow>
        <FormField label="Description" optionalLabel error={formState.errors.description?.message}>
          <Textarea {...register('description')} rows={4} placeholder="What lives here, who has access, anything a new member should know." />
        </FormField>
      </form>
    </SideSheet>
  )
}
