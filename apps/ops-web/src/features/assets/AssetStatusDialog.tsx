import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { ApiError, errorMessage } from '@/api/client'
import { ASSET_STATUSES, ASSET_STATUS_LABELS, AssetStatusInput, DOWNTIME_TYPE_LABELS, DOWNTIME_TYPES, isOfflineStatus, toAssetStatusPayload, type Asset, type AssetStatusPayload } from '@/api/contracts/assets'
import { Button, Dialog, FormField, InlineAlert, Input, SegmentedControl, Select, Textarea } from '@/ui'
import styles from './assets.module.css'

export interface AssetStatusDialogProps {
  open: boolean
  asset: Asset
  submitting: boolean
  error: unknown
  onSubmit: (payload: AssetStatusPayload) => Promise<void>
  onClose: () => void
}

/** "Change status" → `POST /assets/:id/status`. Downtime fields only apply to offline statuses. */
export function AssetStatusDialog({ open, asset, submitting, error, onSubmit, onClose }: AssetStatusDialogProps) {
  const form = useForm<AssetStatusInput>({
    resolver: zodResolver(AssetStatusInput),
    defaultValues: { status: asset.status as AssetStatusInput['status'], downtime_type: null, downtime_reason: '', note: '' },
  })
  const { register, control, handleSubmit, reset, setError, setValue, watch, formState } = form
  const status = watch('status')
  const offline = isOfflineStatus(status)

  useEffect(() => {
    if (!open) return
    reset({ status: asset.status as AssetStatusInput['status'], downtime_type: null, downtime_reason: '', note: '' })
  }, [open, asset.status, reset])

  // Default the downtime type from the chosen offline status, as the server would.
  useEffect(() => {
    if (status === 'offline_planned') setValue('downtime_type', 'planned')
    else if (status === 'offline_unplanned') setValue('downtime_type', 'unplanned')
    else setValue('downtime_type', null)
  }, [status, setValue])

  useEffect(() => {
    if (error instanceof ApiError && error.isValidation) {
      for (const [field, message] of Object.entries(error.errors)) setError(field as keyof AssetStatusInput, { type: 'server', message })
    }
  }, [error, setError])

  const generalError = error && !(error instanceof ApiError && error.isValidation) ? errorMessage(error) : null

  return (
    <Dialog
      open={open}
      onClose={onClose}
      size="sm"
      title={`Change status of ${asset.name}`}
      description="Status changes are recorded in the asset history and notify the responsible people when equipment goes offline."
      preventClose={submitting}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="asset-status-form" loading={submitting}>
            Update status
          </Button>
        </>
      }
    >
      <form id="asset-status-form" noValidate className={styles.form} onSubmit={handleSubmit((values) => onSubmit(toAssetStatusPayload(values)))}>
        {generalError && <InlineAlert tone="danger">{generalError}</InlineAlert>}
        <FormField label="Status" required error={formState.errors.status?.message}>
          <Select {...register('status')} data-autofocus>
            {ASSET_STATUSES.map((value) => (
              <option key={value} value={value}>
                {ASSET_STATUS_LABELS[value]}
              </option>
            ))}
          </Select>
        </FormField>
        {offline && (
          <>
            <FormField label="Downtime type" asGroup error={formState.errors.downtime_type?.message}>
              <Controller
                control={control}
                name="downtime_type"
                render={({ field }) => (
                  <SegmentedControl<'planned' | 'unplanned'>
                    label="Downtime type"
                    value={field.value ?? 'planned'}
                    onChange={field.onChange}
                    options={DOWNTIME_TYPES.map((value) => ({ value, label: DOWNTIME_TYPE_LABELS[value] }))}
                  />
                )}
              />
            </FormField>
            <FormField label="Downtime reason" optionalLabel error={formState.errors.downtime_reason?.message} hint="A short cause, e.g. “Blown fuse” or “Scheduled calibration”.">
              <Input {...register('downtime_reason')} maxLength={160} placeholder="What took it offline?" />
            </FormField>
          </>
        )}
        <FormField label="Note" optionalLabel error={formState.errors.note?.message}>
          <Textarea {...register('note')} rows={3} placeholder="Anything the next person should know." />
        </FormField>
      </form>
    </Dialog>
  )
}
