import { zodResolver } from '@hookform/resolvers/zod'
import { Plus, Star, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Controller, useFieldArray, useForm } from 'react-hook-form'
import { ApiError, errorMessage } from '@/api/client'
import {
  AssetLinksInput,
  MAX_VENDOR_LINKS,
  toVendorLinksPayload,
  vendorLinksToInput,
  VendorLinksInput,
  type PartDetail,
  type VendorLinkPayload,
} from '@/api/contracts/parts'
import { useAssetOptions } from '@/api/queries/assets'
import { useVendorOptions } from '@/api/queries/vendors'
import { Badge, Button, Combobox, Dialog, FormField, IconButton, InlineAlert, Input } from '@/ui'
import styles from './parts.module.css'

/* Vendors ------------------------------------------------------------------------ */

/** `vendors[2].url` (server) → `vendors.2.url` (react-hook-form). */
function toFormPath(field: string): string {
  return field.replace(/\[(\d+)\]/g, '.$1')
}

export interface VendorsDialogProps {
  open: boolean
  part: PartDetail
  submitting: boolean
  error: unknown
  onSubmit: (vendors: VendorLinkPayload[]) => Promise<void>
  onClose: () => void
}

/**
 * Replaces the part's vendor list (`PUT /parts/:id/vendors`). The whole list is
 * sent every time, which is why the dialog starts from the current one and why
 * removing a row here removes the link.
 */
export function VendorsDialog({ open, part, submitting, error, onSubmit, onClose }: VendorsDialogProps) {
  const form = useForm<VendorLinksInput>({ resolver: zodResolver(VendorLinksInput), defaultValues: { vendors: [] } })
  const { control, register, handleSubmit, reset, setError, watch, setValue, formState } = form
  const { fields, append, remove } = useFieldArray({ control, name: 'vendors' })
  const vendors = useVendorOptions()
  const [picked, setPicked] = useState<string | null>(null)
  const rows = watch('vendors')

  const nameFor = useMemo(() => new Map(vendors.options.map((option) => [option.value, option.label])), [vendors.options])
  const available = useMemo(() => vendors.options.filter((option) => !rows?.some((row) => row.vendor_id === option.value)), [vendors.options, rows])

  useEffect(() => {
    if (!open) return
    reset(vendorLinksToInput(part.vendors))
    setPicked(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, part.id, reset])

  useEffect(() => {
    if (!(error instanceof ApiError) || !error.isValidation) return
    for (const [field, message] of Object.entries(error.errors)) {
      setError(toFormPath(field) as `vendors.${number}.url`, { type: 'server', message })
    }
  }, [error, setError])

  const generalError = error && !(error instanceof ApiError && error.isValidation) ? errorMessage(error) : null
  const listError = formState.errors.vendors?.message ?? formState.errors.vendors?.root?.message

  const addPicked = () => {
    if (!picked || fields.length >= MAX_VENDOR_LINKS) return
    append({ vendor_id: picked, vendor_part_number: '', url: '', preferred: fields.length === 0, last_price: '' })
    setPicked(null)
  }

  const makePreferred = (index: number) => {
    rows.forEach((_, position) => setValue(`vendors.${position}.preferred`, position === index, { shouldDirty: true }))
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      size="lg"
      title={`Vendors for ${part.name}`}
      description="Who sells this part, their ordering number and the last price paid. The preferred vendor is the one a purchase request defaults to."
      preventClose={submitting}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="part-vendors-form" loading={submitting}>
            Save vendors
          </Button>
        </>
      }
    >
      <form id="part-vendors-form" noValidate className={styles.form} onSubmit={handleSubmit((values) => onSubmit(toVendorLinksPayload(values).vendors))}>
        {generalError && <InlineAlert tone="danger">{generalError}</InlineAlert>}
        {listError && <InlineAlert tone="danger">{listError}</InlineAlert>}

        <FormField label="Add a vendor" hint="Vendors come from the Vendors screen.">
          <div className={styles.inlineActions}>
            <div style={{ flex: 1, minWidth: 180 }}>
              <Combobox options={available} loading={vendors.isLoading} value={picked} onChange={setPicked} placeholder="Choose a vendor" emptyText="No more vendors" aria-label="Vendor to add" />
            </div>
            <Button leadingIcon={<Plus size={16} />} onClick={addPicked} disabled={!picked}>
              Add
            </Button>
          </div>
        </FormField>

        {fields.length === 0 ? (
          <p className={styles.muted}>No vendors linked yet.</p>
        ) : (
          <ul aria-label="Linked vendors" style={{ display: 'grid', gap: 'var(--space-3)' }}>
            {fields.map((field, index) => {
              const vendorId = rows?.[index]?.vendor_id ?? field.vendor_id
              const name = nameFor.get(vendorId) ?? part.vendors.find((link) => link.vendor.id === vendorId)?.vendor.name ?? 'Vendor'
              const errors = formState.errors.vendors?.[index]
              return (
                <li key={field.id} className={styles.vendorRow}>
                  <div className={styles.vendorRowHead}>
                    <span className={styles.vendorRowTitle}>{name}</span>
                    {rows?.[index]?.preferred ? (
                      <Badge tone="success" size="sm">
                        Preferred
                      </Badge>
                    ) : (
                      <Button size="sm" variant="ghost" leadingIcon={<Star size={14} />} onClick={() => makePreferred(index)}>
                        Make preferred
                      </Button>
                    )}
                    <IconButton size="sm" variant="ghost" label={`Remove ${name}`} onClick={() => remove(index)}>
                      <Trash2 size={16} />
                    </IconButton>
                  </div>
                  {errors?.vendor_id?.message && <InlineAlert tone="danger">{errors.vendor_id.message}</InlineAlert>}
                  {errors?.preferred?.message && <InlineAlert tone="danger">{errors.preferred.message}</InlineAlert>}
                  <div className={styles.vendorGrid}>
                    <FormField label={`${name} order number`} optionalLabel error={errors?.vendor_part_number?.message}>
                      <Input {...register(`vendors.${index}.vendor_part_number`)} maxLength={160} className="mono" placeholder="91290A115" />
                    </FormField>
                    <FormField label={`${name} link`} optionalLabel error={errors?.url?.message}>
                      <Input {...register(`vendors.${index}.url`)} maxLength={500} placeholder="https://" />
                    </FormField>
                    <FormField label={`${name} last price`} optionalLabel error={errors?.last_price?.message}>
                      <Input {...register(`vendors.${index}.last_price`)} inputMode="decimal" placeholder="0.00" />
                    </FormField>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </form>
    </Dialog>
  )
}

/* Spare-for assets ---------------------------------------------------------------- */

export interface AssetsDialogProps {
  open: boolean
  part: PartDetail
  submitting: boolean
  error: unknown
  onSubmit: (assetIds: string[]) => Promise<void>
  onClose: () => void
}

/** Replaces the "spare part for" list (`PUT /parts/:id/assets`). */
export function AssetsDialog({ open, part, submitting, error, onSubmit, onClose }: AssetsDialogProps) {
  const form = useForm<AssetLinksInput>({ resolver: zodResolver(AssetLinksInput), defaultValues: { asset_ids: [] } })
  const { control, handleSubmit, reset, setError, formState } = form
  const assets = useAssetOptions()

  useEffect(() => {
    if (!open) return
    reset({ asset_ids: part.assets.map((asset) => asset.id) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, part.id, reset])

  useEffect(() => {
    if (!(error instanceof ApiError) || !error.isValidation) return
    const message = error.errors.asset_ids
    if (message) setError('asset_ids', { type: 'server', message })
  }, [error, setError])

  const generalError = error && !(error instanceof ApiError && error.isValidation) ? errorMessage(error) : null

  return (
    <Dialog
      open={open}
      onClose={onClose}
      size="sm"
      title={`Assets ${part.name} is a spare for`}
      description="Linking a part to the equipment it fits makes it findable from the asset, and from a work order on that asset."
      preventClose={submitting}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="part-assets-form" loading={submitting}>
            Save assets
          </Button>
        </>
      }
    >
      <form id="part-assets-form" noValidate className={styles.form} onSubmit={handleSubmit((values) => onSubmit(values.asset_ids))}>
        {generalError && <InlineAlert tone="danger">{generalError}</InlineAlert>}
        <FormField label="Assets" error={formState.errors.asset_ids?.message} hint="Only assets you can see are listed.">
          <Controller
            control={control}
            name="asset_ids"
            render={({ field }) => (
              <Combobox multiple options={assets.options} loading={assets.isLoading} value={field.value} onChange={field.onChange} placeholder="Add assets" emptyText="No matching assets" />
            )}
          />
        </FormField>
      </form>
    </Dialog>
  )
}
