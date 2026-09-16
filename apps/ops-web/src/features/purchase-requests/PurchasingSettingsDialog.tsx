/**
 * Chapter purchasing settings (`GET|PUT /purchasing/settings`), reachable only
 * from this screen and only for someone with `chapter.settings.manage`.
 *
 * PUT replaces the whole block, so the form always sends all three keys - a
 * blank threshold really does mean "no advisor step", not "leave it alone".
 */

import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { ApiError, errorMessage } from '@/api/client'
import { PurchasingSettingsInput, purchasingSettingsFormValues, toPurchasingSettingsPayload, type PurchasingSettingsInput as SettingsValues } from '@/api/contracts/purchaseRequests'
import { usePurchasingSettings, useUpdatePurchasingSettings } from '@/api/queries/purchaseRequests'
import { useTeamOptions } from '@/api/queries/teams'
import { Button, Checkbox, Combobox, Dialog, FormField, InlineAlert, Input, SkeletonBlock, useToast } from '@/ui'
import styles from './purchase-requests.module.css'

export function PurchasingSettingsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null
  return <PurchasingSettingsDialogBody onClose={onClose} />
}

function PurchasingSettingsDialogBody({ onClose }: { onClose: () => void }) {
  const toast = useToast()
  const settings = usePurchasingSettings()
  const update = useUpdatePurchasingSettings()
  const teams = useTeamOptions()

  const form = useForm<SettingsValues>({ resolver: zodResolver(PurchasingSettingsInput), defaultValues: purchasingSettingsFormValues(null) })
  const { control, register, handleSubmit, reset, setError, formState } = form

  // The dialog opens before the settings arrive; seed the form once they do.
  useEffect(() => {
    if (settings.data) reset(purchasingSettingsFormValues(settings.data))
  }, [settings.data, reset])

  useEffect(() => {
    if (update.error instanceof ApiError && update.error.isValidation) {
      for (const [field, message] of Object.entries(update.error.errors)) {
        if (['advisor_review_threshold', 'require_project_lead_approval', 'critical_parts_team_id'].includes(field)) {
          setError(field as keyof SettingsValues, { type: 'server', message })
        }
      }
    }
  }, [update.error, setError])

  const general = update.error && !(update.error instanceof ApiError && update.error.isValidation) ? errorMessage(update.error) : null

  const submit = handleSubmit(async (values) => {
    try {
      await update.mutateAsync(toPurchasingSettingsPayload(values))
      toast.success('Purchasing settings saved')
      onClose()
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not save purchasing settings', errorMessage(error))
    }
  })

  return (
    <Dialog
      open
      onClose={onClose}
      title="Purchasing settings"
      description="How purchase requests are routed for approval in this chapter."
      preventClose={update.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={update.isPending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="purchasing-settings-form" loading={update.isPending} disabled={settings.isPending || settings.isError}>
            Save settings
          </Button>
        </>
      }
    >
      {settings.isPending ? (
        <SkeletonBlock lines={4} />
      ) : settings.isError ? (
        <InlineAlert
          tone="danger"
          title="Could not load purchasing settings"
          actions={
            <Button size="sm" onClick={() => void settings.refetch()}>
              Retry
            </Button>
          }
        >
          {errorMessage(settings.error)}
        </InlineAlert>
      ) : (
        <form id="purchasing-settings-form" className={styles.form} noValidate onSubmit={(event) => void submit(event)}>
          {general && <InlineAlert tone="danger">{general}</InlineAlert>}
          <FormField
            label="Advisor review threshold"
            optionalLabel
            hint="Requests at or above this estimated total also need faculty-advisor sign-off. Leave blank for no advisor step."
            error={formState.errors.advisor_review_threshold?.message}
          >
            <Input {...register('advisor_review_threshold')} inputMode="decimal" data-autofocus placeholder="e.g. 500.00" />
          </FormField>
          <Controller
            control={control}
            name="require_project_lead_approval"
            render={({ field }) => (
              <FormField label="Project lead approval" asGroup error={formState.errors.require_project_lead_approval?.message}>
                <Checkbox
                  name={field.name}
                  checked={field.value}
                  onChange={field.onChange}
                  label="Require project lead approval"
                  hint="Requests tied to a project go to that project's lead before the treasurer."
                />
              </FormField>
            )}
          />
          <Controller
            control={control}
            name="critical_parts_team_id"
            render={({ field }) => (
              <FormField label="Critical parts team" optionalLabel asGroup hint="Its leads are also notified when a critical part runs low." error={formState.errors.critical_parts_team_id?.message}>
                <Combobox options={teams.options} loading={teams.isLoading} value={field.value ?? null} onChange={field.onChange} placeholder="No team" aria-label="Critical parts team" />
              </FormField>
            )}
          />
        </form>
      )}
    </Dialog>
  )
}
