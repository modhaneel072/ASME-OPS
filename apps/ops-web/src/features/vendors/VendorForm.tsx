import { zodResolver } from '@hookform/resolvers/zod'
import { useCallback, useEffect, useMemo, useRef } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { ApiError, errorMessage } from '@/api/client'
import { VendorInput, type Vendor, type VendorPayload } from '@/api/contracts/vendors'
import { Button, Checkbox, FieldRow, FormField, InlineAlert, Input, SideSheet, Textarea } from '@/ui'
import styles from './vendors.module.css'

export interface VendorFormProps {
  open: boolean
  mode: 'create' | 'edit'
  /** Existing vendor when editing. */
  initial?: Vendor | null
  submitting: boolean
  error: unknown
  onSubmit: (values: VendorPayload) => Promise<void>
  onClose: () => void
}

const FIELDS: ReadonlyArray<keyof VendorInput> = ['name', 'contact_name', 'email', 'phone', 'website', 'notes', 'is_active']

function orNull(value: string): string | null {
  const trimmed = value.trim()
  return trimmed ? trimmed : null
}

/** Create/edit pane. The inner form mounts fresh whenever the pane opens. */
export function VendorForm(props: VendorFormProps) {
  if (!props.open) return null
  return <VendorFormBody {...props} />
}

function VendorFormBody({ mode, initial, submitting, error, onSubmit, onClose }: VendorFormProps) {
  const editing = mode === 'edit'
  const form = useForm<VendorInput>({
    resolver: zodResolver(VendorInput),
    defaultValues: {
      name: editing ? (initial?.name ?? '') : '',
      contact_name: editing ? (initial?.contact_name ?? '') : '',
      email: editing ? (initial?.email ?? '') : '',
      phone: editing ? (initial?.phone ?? '') : '',
      website: editing ? (initial?.website ?? '') : '',
      notes: editing ? (initial?.notes ?? '') : '',
      is_active: editing ? (initial?.is_active ?? true) : true,
    },
  })
  const { register, control, handleSubmit, setError, setFocus, formState } = form

  // Start on the first field (the pane's own autofocus lands on its close button).
  useEffect(() => {
    setFocus('name')
  }, [setFocus])

  // The pane reads onRequestClose from its mount-time closure, so look up the live state.
  const dirty = formState.isDirty
  const closeState = useRef({ dirty, submitting })
  useEffect(() => {
    closeState.current = { dirty, submitting }
  }, [dirty, submitting])
  const confirmClose = useCallback(() => (closeState.current.dirty && !closeState.current.submitting ? window.confirm('Discard your changes?') : true), [])

  useEffect(() => {
    if (error instanceof ApiError && error.isValidation) {
      for (const [field, message] of Object.entries(error.errors)) {
        if ((FIELDS as readonly string[]).includes(field)) setError(field as keyof VendorInput, { type: 'server', message })
      }
    }
  }, [error, setError])

  const unmappedServerErrors = useMemo(() => {
    if (!(error instanceof ApiError && error.isValidation)) return []
    return Object.entries(error.errors)
      .filter(([field]) => !(FIELDS as readonly string[]).includes(field))
      .map(([field, message]) => `${field}: ${message}`)
  }, [error])
  const generalError = error && !(error instanceof ApiError && error.isValidation) ? errorMessage(error) : null

  return (
    <SideSheet
      open
      onClose={onClose}
      title={mode === 'create' ? 'New Vendor' : `Edit ${initial?.name ?? 'vendor'}`}
      subtitle={mode === 'create' ? 'Suppliers and service providers the chapter orders from or sends work to.' : undefined}
      onRequestClose={confirmClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="vendor-form" loading={submitting}>
            {mode === 'create' ? 'Create Vendor' : 'Save changes'}
          </Button>
        </>
      }
    >
      <form
        id="vendor-form"
        noValidate
        className={styles.form}
        onSubmit={handleSubmit(async (values) => {
          await onSubmit({
            name: values.name,
            contact_name: orNull(values.contact_name),
            email: orNull(values.email),
            phone: orNull(values.phone),
            website: orNull(values.website),
            notes: orNull(values.notes),
            is_active: values.is_active,
          })
        })}
      >
        {generalError && <InlineAlert tone="danger">{generalError}</InlineAlert>}
        {unmappedServerErrors.length > 0 && (
          <InlineAlert tone="danger" title="Please fix the following">
            <ul>
              {unmappedServerErrors.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </InlineAlert>
        )}

        <FormField label="Name" required error={formState.errors.name?.message}>
          <Input {...register('name')} data-autofocus placeholder="e.g. McMaster-Carr" maxLength={200} autoComplete="organization" />
        </FormField>
        <FormField label="Contact name" optionalLabel error={formState.errors.contact_name?.message}>
          <Input {...register('contact_name')} placeholder="Sales desk or account rep" maxLength={160} />
        </FormField>
        <FieldRow>
          <FormField label="Email" optionalLabel error={formState.errors.email?.message}>
            <Input {...register('email')} type="email" placeholder="orders@example.com" maxLength={160} autoComplete="off" />
          </FormField>
          <FormField label="Phone" optionalLabel error={formState.errors.phone?.message}>
            <Input {...register('phone')} type="tel" placeholder="+1 319 555 0100" maxLength={40} autoComplete="off" />
          </FormField>
        </FieldRow>
        <FormField label="Website" optionalLabel error={formState.errors.website?.message} hint="Include http:// or https://.">
          <Input {...register('website')} type="url" placeholder="https://www.example.com" maxLength={300} autoComplete="off" />
        </FormField>
        <FormField label="Notes" optionalLabel error={formState.errors.notes?.message}>
          <Textarea {...register('notes')} rows={4} placeholder="Payment terms, account numbers to quote, who to ask for." />
        </FormField>
        <Controller
          control={control}
          name="is_active"
          render={({ field }) => (
            <FormField label="Status" asGroup error={formState.errors.is_active?.message}>
              <Checkbox name={field.name} checked={field.value} onChange={field.onChange} label="Active vendor" hint="Inactive vendors stay on past work orders and purchases but are hidden from pickers." />
            </FormField>
          )}
        />
      </form>
    </SideSheet>
  )
}
