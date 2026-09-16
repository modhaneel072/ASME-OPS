/**
 * The New / Edit purchase request side sheet.
 *
 * The line-item editor is the heart of it: a part picker fills in the
 * description, the last price the chapter paid and the location the part is
 * normally stocked at, while a line with no part is simply free text. Totals are
 * recomputed on every keystroke with the same rounding rule the server uses, so
 * the number in the summary is the number that comes back from the API.
 */

import { zodResolver } from '@hookform/resolvers/zod'
import { Plus, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Controller, useFieldArray, useForm, type Control, type UseFormSetValue } from 'react-hook-form'
import { ApiError, errorMessage } from '@/api/client'
import {
  MAX_PURCHASE_REQUEST_ITEMS,
  PurchaseRequestInput,
  blankLine,
  lineTotal,
  purchaseRequestFormValues,
  toFormPath,
  toPurchaseRequestPayload,
  totalsFor,
  type PurchaseRequestDetail,
  type PurchaseRequestInput as PurchaseRequestValues,
  type PurchaseRequestPayload,
} from '@/api/contracts/purchaseRequests'
import { useLocations } from '@/api/queries/locations'
import { useProjectOptions } from '@/api/queries/projects'
import { usePartPicker } from '@/api/queries/purchaseRequests'
import { useVendorOptions } from '@/api/queries/vendors'
import { formatMoney } from '@/lib/dates'
import { Button, Combobox, DateInput, FieldRow, FormField, IconButton, InlineAlert, Input, SideSheet, Textarea } from '@/ui'
import styles from './purchase-requests.module.css'

let lineSeq = 0
const nextKey = () => `line-${(lineSeq += 1)}`

export interface PurchaseRequestFormProps {
  open: boolean
  mode: 'create' | 'edit'
  initial?: PurchaseRequestDetail | null
  submitting: boolean
  error: unknown
  onSubmit: (payload: PurchaseRequestPayload) => Promise<void>
  onClose: () => void
}

export function PurchaseRequestForm(props: PurchaseRequestFormProps) {
  if (!props.open) return null
  return <PurchaseRequestFormBody {...props} />
}

function PurchaseRequestFormBody({ mode, initial, submitting, error, onSubmit, onClose }: PurchaseRequestFormProps) {
  const editing = mode === 'edit'
  const defaults = useMemo<PurchaseRequestValues>(() => {
    if (editing && initial) {
      const values = purchaseRequestFormValues(initial)
      return values.items.length ? values : { ...values, items: [blankLine(nextKey())] }
    }
    return {
      title: '',
      project_id: null,
      vendor_id: null,
      needed_by: '',
      purpose: '',
      budget_code: '',
      shipping_amount: '',
      tax_amount: '',
      items: [blankLine(nextKey())],
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const form = useForm<PurchaseRequestValues>({ resolver: zodResolver(PurchaseRequestInput), defaultValues: defaults })
  const { control, register, handleSubmit, setError, setFocus, setValue, watch, formState } = form
  const items = useFieldArray({ control, name: 'items' })

  const projects = useProjectOptions()
  const vendors = useVendorOptions()
  const locations = useLocations({ limit: 200 })
  const locationOptions = useMemo(() => (locations.data?.items ?? []).map((location) => ({ value: location.id, label: location.path.join(' › ') })), [locations.data])

  useEffect(() => {
    setFocus('title')
  }, [setFocus])

  // The sheet reads onRequestClose from its mount-time closure, so look up live state.
  const dirty = formState.isDirty
  const closeState = useRef({ dirty, submitting })
  useEffect(() => {
    closeState.current = { dirty, submitting }
  }, [dirty, submitting])
  const confirmClose = useCallback(() => (closeState.current.dirty && !closeState.current.submitting ? window.confirm('Discard your changes?') : true), [])

  // Server field errors, including the `items[2].quantity` spelling.
  const [unmapped, setUnmapped] = useState<string[]>([])
  useEffect(() => {
    if (!(error instanceof ApiError && error.isValidation)) {
      setUnmapped([])
      return
    }
    const leftovers: string[] = []
    for (const [field, message] of Object.entries(error.errors)) {
      const path = toFormPath(field)
      const root = path.split('.')[0]
      if (['title', 'project_id', 'vendor_id', 'needed_by', 'purpose', 'budget_code', 'shipping_amount', 'tax_amount', 'items'].includes(root)) {
        setError(path as never, { type: 'server', message })
      } else {
        leftovers.push(`${field}: ${message}`)
      }
    }
    setUnmapped(leftovers)
  }, [error, setError])

  const general = error && !(error instanceof ApiError && error.isValidation) ? errorMessage(error) : null

  const watchedItems = watch('items')
  const shipping = watch('shipping_amount')
  const tax = watch('tax_amount')
  const totals = totalsFor(watchedItems ?? [], shipping, tax)

  const addLine = () => {
    if (items.fields.length >= MAX_PURCHASE_REQUEST_ITEMS) return
    items.append(blankLine(nextKey()))
  }

  return (
    <SideSheet
      open
      wide
      onClose={onClose}
      title={editing ? `Edit ${initial?.display_number ?? 'purchase request'}` : 'New purchase request'}
      subtitle={editing ? 'Drafts can be edited until they are submitted.' : 'Ask the chapter to buy parts, tools or materials.'}
      onRequestClose={confirmClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="purchase-request-form" loading={submitting}>
            {editing ? 'Save changes' : 'Create request'}
          </Button>
        </>
      }
      footerStart={<span className={styles.lineTotal}>Total {formatMoney(totals.total)}</span>}
    >
      <form
        id="purchase-request-form"
        noValidate
        className={styles.form}
        onSubmit={handleSubmit(async (values) => {
          await onSubmit(toPurchaseRequestPayload(values))
        })}
      >
        {general && <InlineAlert tone="danger">{general}</InlineAlert>}
        {unmapped.length > 0 && (
          <InlineAlert tone="danger" title="Please fix the following">
            <ul>
              {unmapped.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </InlineAlert>
        )}

        <FormField label="Title" required error={formState.errors.title?.message}>
          <Input {...register('title')} data-autofocus maxLength={200} placeholder="e.g. Rover drivetrain bearings" />
        </FormField>

        <FieldRow>
          <Controller
            control={control}
            name="project_id"
            render={({ field }) => (
              <FormField label="Project" optionalLabel asGroup error={formState.errors.project_id?.message} hint="Charges the project's budget.">
                <Combobox options={projects.options} loading={projects.isLoading} value={field.value ?? null} onChange={field.onChange} placeholder="No project" aria-label="Project" />
              </FormField>
            )}
          />
          <Controller
            control={control}
            name="vendor_id"
            render={({ field }) => (
              <FormField label="Vendor" optionalLabel asGroup error={formState.errors.vendor_id?.message}>
                <Combobox options={vendors.options} loading={vendors.isLoading} value={field.value ?? null} onChange={field.onChange} placeholder="No vendor yet" aria-label="Vendor" />
              </FormField>
            )}
          />
        </FieldRow>

        <FieldRow>
          <FormField label="Needed by" optionalLabel error={formState.errors.needed_by?.message}>
            <DateInput {...register('needed_by')} />
          </FormField>
          <FormField label="Budget code" optionalLabel error={formState.errors.budget_code?.message}>
            <Input {...register('budget_code')} maxLength={60} placeholder="e.g. BAJA-FY26" />
          </FormField>
        </FieldRow>

        <FormField label="Purpose" optionalLabel hint="Why the chapter needs this." error={formState.errors.purpose?.message}>
          <Textarea {...register('purpose')} rows={3} placeholder="What it is for and why it cannot wait." />
        </FormField>

        <fieldset className={styles.lineEditor}>
          <legend className={styles.lineTitle}>Line items</legend>
          {formState.errors.items?.root?.message && <InlineAlert tone="danger">{formState.errors.items.root.message}</InlineAlert>}
          {formState.errors.items?.message && <InlineAlert tone="danger">{formState.errors.items.message}</InlineAlert>}
          {items.fields.map((field, index) => (
            <LineFields
              key={field.id}
              index={index}
              control={control}
              register={register}
              setValue={setValue}
              errors={formState.errors.items?.[index]}
              locationOptions={locationOptions}
              locationsLoading={locations.isPending}
              total={lineTotal(watchedItems?.[index]?.quantity, watchedItems?.[index]?.unit_price)}
              canRemove={items.fields.length > 1}
              onRemove={() => items.remove(index)}
            />
          ))}
          <div>
            <Button size="sm" leadingIcon={<Plus size={16} />} onClick={addLine} disabled={items.fields.length >= MAX_PURCHASE_REQUEST_ITEMS}>
              Add line
            </Button>
          </div>
        </fieldset>

        <FieldRow>
          <FormField label="Shipping" optionalLabel error={formState.errors.shipping_amount?.message}>
            <Input {...register('shipping_amount')} inputMode="decimal" placeholder="0.00" />
          </FormField>
          <FormField label="Tax" optionalLabel error={formState.errors.tax_amount?.message}>
            <Input {...register('tax_amount')} inputMode="decimal" placeholder="0.00" />
          </FormField>
        </FieldRow>

        <div className={styles.summary} aria-live="polite">
          <div className={styles.summaryRow}>
            <span>Items</span>
            <span>{formatMoney(totals.subtotal)}</span>
          </div>
          <div className={styles.summaryRow}>
            <span>Shipping</span>
            <span>{formatMoney(totals.shipping)}</span>
          </div>
          <div className={styles.summaryRow}>
            <span>Tax</span>
            <span>{formatMoney(totals.tax)}</span>
          </div>
          <div className={`${styles.summaryRow} ${styles.summaryRow_total}`}>
            <span>Estimated total</span>
            <span data-testid="estimated-total">{formatMoney(totals.total)}</span>
          </div>
        </div>
      </form>
    </SideSheet>
  )
}

/* One editable line ------------------------------------------------------------- */

interface LineFieldsProps {
  index: number
  control: Control<PurchaseRequestValues>
  register: ReturnType<typeof useForm<PurchaseRequestValues>>['register']
  setValue: UseFormSetValue<PurchaseRequestValues>
  errors?: Partial<Record<'description' | 'quantity' | 'unit_price' | 'url' | 'vendor_part_number' | 'part_id', { message?: string }>>
  locationOptions: Array<{ value: string; label: string }>
  locationsLoading: boolean
  total: number
  canRemove: boolean
  onRemove: () => void
}

function LineFields({ index, control, register, setValue, errors, locationOptions, locationsLoading, total, canRemove, onRemove }: LineFieldsProps) {
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query), 250)
    return () => window.clearTimeout(timer)
  }, [query])
  const parts = usePartPicker(debounced)
  const partOptions = useMemo(
    () => (parts.data ?? []).map((part) => ({ value: part.id, label: part.name, meta: part.sku ?? part.manufacturer_part_number ?? undefined })),
    [parts.data],
  )

  return (
    <div className={styles.lineCard}>
      <div className={styles.lineHeader}>
        <span className={styles.lineTitle}>Line {index + 1}</span>
        {canRemove && (
          <IconButton label={`Remove line ${index + 1}`} size="sm" variant="ghost" onClick={onRemove}>
            <Trash2 size={16} />
          </IconButton>
        )}
      </div>

      <Controller
        control={control}
        name={`items.${index}.part_id` as const}
        render={({ field }) => (
          <FormField label={`Part for line ${index + 1}`} optionalLabel asGroup hint="Pick a stocked part, or leave blank for a free-text line." error={errors?.part_id?.message}>
            <Combobox
              options={partOptions}
              loading={parts.isPending}
              onSearch={setQuery}
              emptyText={debounced ? 'No parts match' : 'Type to search parts'}
              value={field.value ?? null}
              placeholder="Free-text line"
              aria-label={`Part for line ${index + 1}`}
              onChange={(value) => {
                field.onChange(value)
                const part = (parts.data ?? []).find((candidate) => candidate.id === value)
                if (!part) return
                setValue(`items.${index}.description` as const, part.name, { shouldDirty: true, shouldValidate: true })
                if (part.manufacturer_part_number) setValue(`items.${index}.vendor_part_number` as const, part.manufacturer_part_number, { shouldDirty: true })
                if (part.unit_cost !== null && part.unit_cost !== undefined) setValue(`items.${index}.unit_price` as const, String(part.unit_cost), { shouldDirty: true, shouldValidate: true })
                if (part.default_location) setValue(`items.${index}.receive_location_id` as const, part.default_location.id, { shouldDirty: true })
              }}
            />
          </FormField>
        )}
      />

      <FormField label={`Description for line ${index + 1}`} required error={errors?.description?.message}>
        <Input {...register(`items.${index}.description` as const)} maxLength={300} placeholder="What to buy" />
      </FormField>

      <FieldRow>
        <FormField label={`Vendor part number for line ${index + 1}`} optionalLabel error={errors?.vendor_part_number?.message}>
          <Input {...register(`items.${index}.vendor_part_number` as const)} maxLength={160} />
        </FormField>
        <FormField label={`Link for line ${index + 1}`} optionalLabel error={errors?.url?.message}>
          <Input {...register(`items.${index}.url` as const)} type="url" maxLength={500} placeholder="https://" />
        </FormField>
      </FieldRow>

      <div className={styles.lineNumbers}>
        <FormField label={`Quantity for line ${index + 1}`} required error={errors?.quantity?.message}>
          <Input {...register(`items.${index}.quantity` as const)} inputMode="decimal" />
        </FormField>
        <FormField label={`Unit price for line ${index + 1}`} optionalLabel error={errors?.unit_price?.message}>
          <Input {...register(`items.${index}.unit_price` as const)} inputMode="decimal" placeholder="0.00" />
        </FormField>
        <span className={styles.lineTotal} aria-live="polite">
          {formatMoney(total)}
        </span>
      </div>

      <Controller
        control={control}
        name={`items.${index}.receive_location_id` as const}
        render={({ field }) => (
          <FormField label={`Receive at for line ${index + 1}`} optionalLabel asGroup hint="Where the part lands when it arrives.">
            <Combobox
              options={locationOptions}
              loading={locationsLoading}
              value={field.value ?? null}
              onChange={field.onChange}
              placeholder="Default location"
              aria-label={`Receive at for line ${index + 1}`}
            />
          </FormField>
        )}
      />
    </div>
  )
}
