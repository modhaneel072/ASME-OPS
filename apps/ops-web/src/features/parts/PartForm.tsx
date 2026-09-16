import { zodResolver } from '@hookform/resolvers/zod'
import { Plus } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { ApiError, errorMessage } from '@/api/client'
import { EMPTY_PART_INPUT, PART_UNITS, PartInput, partToInput, toPartPayload, type Part, type PartPayload } from '@/api/contracts/parts'
import { useLocations } from '@/api/queries/locations'
import { usePartTypeOptions } from '@/api/queries/parts'
import { Button, Checkbox, Combobox, FieldRow, FormField, FormSection, InlineAlert, Input, Select, SideSheet, Textarea } from '@/ui'
import { PartTypeDialog } from './PartTypeDialog'
import styles from './parts.module.css'

export interface PartFormProps {
  open: boolean
  mode: 'create' | 'edit'
  initial?: Partial<Part> | null
  /** Receipts maintain the unit cost once the part has ledger history. */
  unitCostLocked?: boolean
  canManageTypes: boolean
  submitting: boolean
  error: unknown
  onSubmit: (payload: PartPayload) => Promise<void>
  onClose: () => void
}

/** New / edit part side sheet. Fields and limits mirror `services/parts.py::PART_SPEC`. */
export function PartForm({ open, mode, initial, unitCostLocked, canManageTypes, submitting, error, onSubmit, onClose }: PartFormProps) {
  const form = useForm<PartInput>({ resolver: zodResolver(PartInput), defaultValues: EMPTY_PART_INPUT })
  const { register, control, handleSubmit, reset, setError, getValues, setValue, formState } = form
  const [typeDialog, setTypeDialog] = useState(false)

  const types = usePartTypeOptions()
  const locations = useLocations({ limit: 200 })
  const locationOptions = useMemo(
    () =>
      (locations.data?.items ?? []).map((location) => ({
        value: location.id,
        label: location.name,
        meta: location.path.length > 1 ? location.path.slice(0, -1).join(' › ') : location.is_default ? 'Default' : undefined,
      })),
    [locations.data],
  )

  useEffect(() => {
    if (!open) return
    reset(mode === 'edit' && initial ? partToInput(initial) : EMPTY_PART_INPUT)
  }, [open, mode, initial, reset])

  useEffect(() => {
    if (!(error instanceof ApiError)) return
    if (error.isValidation) {
      for (const [field, message] of Object.entries(error.errors)) {
        if (field in EMPTY_PART_INPUT) setError(field as keyof PartInput, { type: 'server', message })
      }
    }
  }, [error, setError])

  const generalError = error && !(error instanceof ApiError && error.isValidation) ? errorMessage(error) : null
  const dirty = formState.isDirty

  return (
    <SideSheet
      open={open}
      onClose={onClose}
      title={mode === 'create' ? 'New Part' : `Edit ${initial?.name ?? 'part'}`}
      subtitle={mode === 'create' ? 'Fasteners, stock material, electronics and consumables the chapter keeps on the shelf.' : undefined}
      onRequestClose={() => (dirty && !submitting ? window.confirm('Discard your changes?') : true)}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="part-form" loading={submitting}>
            {mode === 'create' ? 'Create Part' : 'Save changes'}
          </Button>
        </>
      }
    >
      <form id="part-form" noValidate className={styles.form} onSubmit={handleSubmit((values) => onSubmit(toPartPayload(values, { includeUnitCost: !unitCostLocked })))}>
        {generalError && <InlineAlert tone="danger">{generalError}</InlineAlert>}

        <FormField label="Name" required error={formState.errors.name?.message}>
          <Input {...register('name')} data-autofocus placeholder="e.g. M4 × 12 socket head cap screw" maxLength={200} />
        </FormField>
        <FieldRow>
          <FormField label="SKU" optionalLabel error={formState.errors.sku?.message} hint="Your own shelf number. Must be unique.">
            <Input {...register('sku')} placeholder="FAS-M4-12" maxLength={60} className="mono" />
          </FormField>
          <FormField label="Unit" required error={formState.errors.unit?.message} hint="How the chapter counts it.">
            <Select {...register('unit')}>
              {PART_UNITS.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </Select>
          </FormField>
        </FieldRow>
        <FormField label="Description" optionalLabel error={formState.errors.description?.message}>
          <Textarea {...register('description')} rows={3} placeholder="What it is and what it is normally used for." />
        </FormField>
        <FormField
          label="Part type"
          optionalLabel
          error={formState.errors.part_type_id?.message}
          hint={
            canManageTypes ? (
              <span className={styles.inlineActions}>
                <span>Group similar parts.</span>
                <Button variant="link" size="sm" leadingIcon={<Plus size={14} />} onClick={() => setTypeDialog(true)}>
                  Create type
                </Button>
              </span>
            ) : (
              'Group similar parts.'
            )
          }
        >
          <Controller
            control={control}
            name="part_type_id"
            render={({ field }) => <Combobox options={types.options} loading={types.isLoading} value={field.value} onChange={field.onChange} placeholder="No type" emptyText="No part types yet" />}
          />
        </FormField>
        <Controller
          control={control}
          name="is_critical"
          render={({ field }) => (
            <Checkbox label="Critical part" hint="Running out stops work: low stock also escalates to the critical-parts team." checked={field.value} onChange={field.onChange} />
          )}
        />

        <FormSection title="Stock levels">
          <FieldRow>
            <FormField label="Minimum stock" optionalLabel error={formState.errors.minimum_stock?.message} hint="Below this, the part counts as low.">
              <Input {...register('minimum_stock')} inputMode="decimal" placeholder="0" />
            </FormField>
            <FormField label="Maximum stock" optionalLabel error={formState.errors.maximum_stock?.message} hint="What a full shelf looks like.">
              <Input {...register('maximum_stock')} inputMode="decimal" placeholder="0" />
            </FormField>
          </FieldRow>
          <FieldRow>
            <FormField label="Reorder quantity" optionalLabel error={formState.errors.reorder_quantity?.message} hint="Suggested quantity on a purchase request.">
              <Input {...register('reorder_quantity')} inputMode="decimal" placeholder="0" />
            </FormField>
            <FormField label="Default location" optionalLabel error={formState.errors.default_location_id?.message} hint="Where movements land unless another shelf is chosen.">
              <Controller
                control={control}
                name="default_location_id"
                render={({ field }) => <Combobox options={locationOptions} loading={locations.isPending} value={field.value} onChange={field.onChange} placeholder="No default" emptyText="No locations" />}
              />
            </FormField>
          </FieldRow>
        </FormSection>

        <FormSection title="Make and cost">
          <FieldRow>
            <FormField label="Manufacturer" optionalLabel error={formState.errors.manufacturer?.message}>
              <Input {...register('manufacturer')} placeholder="McMaster-Carr" maxLength={160} />
            </FormField>
            <FormField label="Manufacturer part number" optionalLabel error={formState.errors.manufacturer_part_number?.message}>
              <Input {...register('manufacturer_part_number')} placeholder="91290A115" maxLength={160} className="mono" />
            </FormField>
          </FieldRow>
          <FormField
            label="Unit cost"
            optionalLabel
            error={formState.errors.unit_cost?.message}
            hint={unitCostLocked ? 'Maintained by receipts now that this part has inventory history.' : 'USD per unit. Receipts keep it up to date from here on.'}
          >
            <Input {...register('unit_cost')} inputMode="decimal" placeholder="0.00" disabled={unitCostLocked} />
          </FormField>
        </FormSection>

        <FormSection title="Tracking">
          <FormField label="QR or barcode" optionalLabel error={formState.errors.qr_code?.message} hint="Scanned at the shelf to open this part.">
            <Input {...register('qr_code')} maxLength={160} className="mono" />
          </FormField>
          {mode === 'edit' && (
            <Controller
              control={control}
              name="is_active"
              render={({ field }) => <Checkbox label="Active part" hint="Retired parts stay in the ledger but drop out of pickers and the default list." checked={field.value} onChange={field.onChange} />}
            />
          )}
        </FormSection>
      </form>

      <PartTypeDialog
        open={typeDialog}
        onClose={() => setTypeDialog(false)}
        onCreated={(type) => {
          if (!getValues('part_type_id')) setValue('part_type_id', type.id, { shouldDirty: true })
        }}
      />
    </SideSheet>
  )
}
