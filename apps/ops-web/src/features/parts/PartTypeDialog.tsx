import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { ApiError, errorMessage } from '@/api/client'
import { PartTypeInput, type PartType } from '@/api/contracts/parts'
import { useCreatePartType } from '@/api/queries/parts'
import { Button, Dialog, FormField, InlineAlert, Input, useToast } from '@/ui'
import styles from './parts.module.css'

/** Suggested type colours (sent as hex; the palette is data, not styling). */
const SWATCHES = ['#475569', '#0878d1', '#00a878', '#e58a00', '#d84a4a', '#7c5ce7', '#0e7490', '#b45309']

export interface PartTypeDialogProps {
  open: boolean
  onClose: () => void
  /** Called with the new type after `POST /part-types` succeeds. */
  onCreated?: (type: PartType) => void
}

export function PartTypeDialog({ open, onClose, onCreated }: PartTypeDialogProps) {
  const toast = useToast()
  const create = useCreatePartType()
  const form = useForm<PartTypeInput>({ resolver: zodResolver(PartTypeInput), defaultValues: { name: '', color: SWATCHES[0] } })
  const { register, control, handleSubmit, reset, setError, formState } = form

  useEffect(() => {
    if (open) {
      reset({ name: '', color: SWATCHES[0] })
      create.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, reset])

  useEffect(() => {
    if (create.error instanceof ApiError && create.error.isValidation) {
      for (const [field, message] of Object.entries(create.error.errors)) setError(field as keyof PartTypeInput, { type: 'server', message })
    }
  }, [create.error, setError])

  const generalError = create.error && !(create.error instanceof ApiError && create.error.isValidation) ? errorMessage(create.error) : null

  const submit = async (values: PartTypeInput) => {
    try {
      const created = await create.mutateAsync(values)
      toast.success('Part type created', created.name)
      onCreated?.(created)
      onClose()
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not create the part type', errorMessage(error))
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      size="sm"
      title="New part type"
      description="Types group similar parts, e.g. Fastener, Electronics, Stock material."
      preventClose={create.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={create.isPending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="part-type-form" loading={create.isPending}>
            Create type
          </Button>
        </>
      }
    >
      <form id="part-type-form" noValidate className={styles.form} onSubmit={handleSubmit(submit)}>
        {generalError && <InlineAlert tone="danger">{generalError}</InlineAlert>}
        <FormField label="Name" required error={formState.errors.name?.message}>
          <Input {...register('name')} data-autofocus placeholder="e.g. Fastener" maxLength={120} />
        </FormField>
        <FormField label="Colour" error={formState.errors.color?.message} hint="Shown as a dot next to the type name.">
          <Controller
            control={control}
            name="color"
            render={({ field }) => (
              <div className={styles.colorRow}>
                <input type="color" className={styles.colorInput} value={field.value} onChange={(event) => field.onChange(event.target.value)} aria-label="Custom colour" />
                <div className={styles.swatches} role="group" aria-label="Suggested colours">
                  {SWATCHES.map((swatch) => (
                    <button key={swatch} type="button" className={styles.swatch} style={{ background: swatch }} aria-label={`Use colour ${swatch}`} aria-pressed={field.value === swatch} onClick={() => field.onChange(swatch)} />
                  ))}
                </div>
              </div>
            )}
          />
        </FormField>
      </form>
    </Dialog>
  )
}
