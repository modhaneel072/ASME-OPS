import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Controller, useForm } from 'react-hook-form'
import { ApiError, errorMessage } from '@/api/client'
import {
  ADJUSTMENT_DIRECTIONS,
  CountInput,
  formatQuantity,
  MOVEMENT_LABELS,
  MovementInput,
  NOTE_REQUIRED_TYPES,
  toCountPayload,
  toMovementPayload,
  toTransferPayload,
  TransferInput,
  WORK_ORDER_TYPES,
  type CountPayload,
  type MovementPayload,
  type MovementType,
  type PartBalance,
  type PartDetail,
  type TransferPayload,
} from '@/api/contracts/parts'
import { useLocations } from '@/api/queries/locations'
import { searchWorkOrders, workOrderKeys } from '@/api/queries/work-orders'
import { Button, Combobox, Dialog, FormField, InlineAlert, Input, SegmentedControl, Textarea, type ComboOption } from '@/ui'
import styles from './parts.module.css'

/* Shared helpers ---------------------------------------------------------------- */

/** A 409 from the ledger names the location that came up short. */
function stockConflict(error: unknown): string | null {
  if (!(error instanceof ApiError) || error.code !== 'insufficient_stock') return null
  const onHand = error.extra.on_hand
  const reserved = error.extra.reserved
  const detail = typeof onHand === 'number' ? ` That location holds ${formatQuantity(onHand)}${typeof reserved === 'number' && reserved > 0 ? ` with ${formatQuantity(reserved)} reserved` : ''}.` : ''
  return `${error.message}${detail}`
}

function generalErrorOf(error: unknown): string | null {
  if (!error) return null
  if (error instanceof ApiError && error.isValidation) return null
  return stockConflict(error) ?? errorMessage(error)
}

/** Location options for the whole chapter, annotated with what this part holds there. */
function useLocationOptions(balances: PartBalance[], unit: string): { options: ComboOption<string>[]; isLoading: boolean } {
  const locations = useLocations({ limit: 200 })
  return useMemo(() => {
    const held = new Map<string, PartBalance>()
    for (const balance of balances) if (balance.location) held.set(balance.location.id, balance)
    const options = (locations.data?.items ?? []).map((location) => {
      const balance = held.get(location.id)
      return {
        value: location.id,
        label: location.name,
        meta: balance ? `${formatQuantity(balance.on_hand)} ${unit} on hand` : location.is_default ? 'Default' : undefined,
      }
    })
    return { options, isLoading: locations.isPending }
  }, [locations.data, locations.isPending, balances, unit])
}

function defaultLocationId(part: PartDetail): string | null {
  return part.default_location?.id ?? part.balances.find((balance) => balance.location)?.location?.id ?? null
}

/** `{ field: message }` from a 400, keyed by the form fields that exist here. */
function fieldMessages(error: unknown, fields: readonly string[]): Array<[string, string]> {
  if (!(error instanceof ApiError) || !error.isValidation) return []
  return Object.entries(error.errors).filter(([field]) => fields.includes(field))
}

/* Receive / Issue / Return / Adjust / Scrap ------------------------------------- */

const MOVEMENT_FIELDS = ['type', 'location_id', 'quantity', 'direction', 'unit_cost', 'work_order_id', 'note'] as const

const MOVEMENT_DESCRIPTIONS: Record<MovementType, string> = {
  receipt: 'Stock arriving on the shelf. A unit cost here re-weights the part’s average cost.',
  issue: 'Stock leaving the shelf. Link a work order to charge the parts cost to it.',
  return: 'Unused stock coming back. Linked to a work order it credits the parts cost back.',
  adjustment: 'Correct the system quantity to match reality. The reason is recorded in the ledger.',
  scrap: 'Stock written off: damaged, expired or lost.',
}

export interface MovementDialogProps {
  open: boolean
  type: MovementType
  part: PartDetail
  submitting: boolean
  error: unknown
  onSubmit: (payload: MovementPayload) => Promise<void>
  onClose: () => void
}

/** One ledger movement at a single location (`POST /parts/:id/transactions`). */
export function MovementDialog({ open, type, part, submitting, error, onSubmit, onClose }: MovementDialogProps) {
  const form = useForm<MovementInput>({
    resolver: zodResolver(MovementInput),
    defaultValues: { type, location_id: null, quantity: '', direction: null, unit_cost: '', work_order_id: null, note: '' },
  })
  const { register, control, handleSubmit, reset, setError, formState } = form
  const locations = useLocationOptions(part.balances, part.unit)
  const [workOrderQuery, setWorkOrderQuery] = useState('')
  const linksWorkOrder = WORK_ORDER_TYPES.includes(type)

  const workOrders = useQuery({
    queryKey: workOrderKeys.search(workOrderQuery),
    queryFn: () => searchWorkOrders(workOrderQuery),
    enabled: open && linksWorkOrder,
  })
  const workOrderOptions = useMemo<ComboOption<string>[]>(() => (workOrders.data ?? []).map((row) => ({ value: row.id, label: `#${row.number} ${row.title}` })), [workOrders.data])

  useEffect(() => {
    if (!open) return
    reset({
      type,
      location_id: defaultLocationId(part),
      quantity: '',
      direction: type === 'adjustment' ? 'increase' : null,
      unit_cost: '',
      work_order_id: null,
      note: '',
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, type, part.id, reset])

  useEffect(() => {
    for (const [field, message] of fieldMessages(error, MOVEMENT_FIELDS)) setError(field as keyof MovementInput, { type: 'server', message })
  }, [error, setError])

  const generalError = generalErrorOf(error)
  const label = MOVEMENT_LABELS[type]

  return (
    <Dialog
      open={open}
      onClose={onClose}
      size="sm"
      title={`${label} ${part.name}`}
      description={MOVEMENT_DESCRIPTIONS[type]}
      preventClose={submitting}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="part-movement-form" loading={submitting}>
            {label}
          </Button>
        </>
      }
    >
      <form id="part-movement-form" noValidate className={styles.form} onSubmit={handleSubmit((values) => onSubmit(toMovementPayload(values)))}>
        {generalError && <InlineAlert tone="danger">{generalError}</InlineAlert>}
        <FormField label="Location" error={formState.errors.location_id?.message} hint="Where the stock sits.">
          <Controller
            control={control}
            name="location_id"
            render={({ field }) => <Combobox options={locations.options} loading={locations.isLoading} value={field.value} onChange={field.onChange} placeholder="Choose a location" emptyText="No locations" />}
          />
        </FormField>
        {type === 'adjustment' && (
          <FormField label="Direction" asGroup required error={formState.errors.direction?.message}>
            <Controller
              control={control}
              name="direction"
              render={({ field }) => (
                <SegmentedControl
                  label="Direction"
                  value={field.value ?? 'increase'}
                  onChange={field.onChange}
                  options={ADJUSTMENT_DIRECTIONS.map((value) => ({ value, label: value === 'increase' ? 'Increase' : 'Decrease', tone: value === 'decrease' ? ('danger' as const) : undefined }))}
                />
              )}
            />
          </FormField>
        )}
        <FormField label="Quantity" required error={formState.errors.quantity?.message} hint={`In ${part.unit}. Available now: ${formatQuantity(part.totals.available)} ${part.unit}.`}>
          <Input {...register('quantity')} data-autofocus inputMode="decimal" placeholder="0" />
        </FormField>
        {type === 'receipt' && (
          <FormField label="Unit cost" optionalLabel error={formState.errors.unit_cost?.message} hint="What this delivery cost per unit. Updates the weighted average.">
            <Input {...register('unit_cost')} inputMode="decimal" placeholder="0.00" />
          </FormField>
        )}
        {linksWorkOrder && (
          <FormField label="Work order" optionalLabel error={formState.errors.work_order_id?.message} hint="Charges the parts cost to that work order.">
            <Controller
              control={control}
              name="work_order_id"
              render={({ field }) => (
                <Combobox
                  options={workOrderOptions}
                  loading={workOrders.isPending && workOrders.fetchStatus !== 'idle'}
                  value={field.value}
                  onChange={field.onChange}
                  onSearch={setWorkOrderQuery}
                  placeholder="No work order"
                  emptyText="No matching work orders"
                />
              )}
            />
          </FormField>
        )}
        <FormField label="Note" required={NOTE_REQUIRED_TYPES.includes(type)} optionalLabel={!NOTE_REQUIRED_TYPES.includes(type)} error={formState.errors.note?.message}>
          <Textarea {...register('note')} rows={3} placeholder={NOTE_REQUIRED_TYPES.includes(type) ? 'Why the quantity changed.' : 'Anything worth recording.'} />
        </FormField>
      </form>
    </Dialog>
  )
}

/* Transfer ---------------------------------------------------------------------- */

const TRANSFER_FIELDS = ['from_location_id', 'to_location_id', 'quantity', 'note'] as const

export interface TransferDialogProps {
  open: boolean
  part: PartDetail
  submitting: boolean
  error: unknown
  onSubmit: (payload: TransferPayload) => Promise<void>
  onClose: () => void
}

/** Move stock between two shelves (`POST /inventory/transfers`): two linked rows. */
export function TransferDialog({ open, part, submitting, error, onSubmit, onClose }: TransferDialogProps) {
  const form = useForm<TransferInput>({ resolver: zodResolver(TransferInput), defaultValues: { from_location_id: '', to_location_id: '', quantity: '', note: '' } })
  const { register, control, handleSubmit, reset, setError, formState } = form
  const locations = useLocationOptions(part.balances, part.unit)

  useEffect(() => {
    if (!open) return
    reset({ from_location_id: defaultLocationId(part) ?? '', to_location_id: '', quantity: '', note: '' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, part.id, reset])

  useEffect(() => {
    for (const [field, message] of fieldMessages(error, TRANSFER_FIELDS)) setError(field as keyof TransferInput, { type: 'server', message })
  }, [error, setError])

  const generalError = generalErrorOf(error)

  return (
    <Dialog
      open={open}
      onClose={onClose}
      size="sm"
      title={`Transfer ${part.name}`}
      description="Moves stock between locations. Nothing is consumed: the ledger records a matched pair of rows."
      preventClose={submitting}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="part-transfer-form" loading={submitting}>
            Transfer
          </Button>
        </>
      }
    >
      <form id="part-transfer-form" noValidate className={styles.form} onSubmit={handleSubmit((values) => onSubmit(toTransferPayload(part.id, values)))}>
        {generalError && <InlineAlert tone="danger">{generalError}</InlineAlert>}
        <FormField label="From" required error={formState.errors.from_location_id?.message}>
          <Controller
            control={control}
            name="from_location_id"
            render={({ field }) => (
              <Combobox options={locations.options} loading={locations.isLoading} value={field.value || null} onChange={(value) => field.onChange(value ?? '')} placeholder="Choose a location" emptyText="No locations" />
            )}
          />
        </FormField>
        <FormField label="To" required error={formState.errors.to_location_id?.message}>
          <Controller
            control={control}
            name="to_location_id"
            render={({ field }) => (
              <Combobox options={locations.options} loading={locations.isLoading} value={field.value || null} onChange={(value) => field.onChange(value ?? '')} placeholder="Choose a location" emptyText="No locations" />
            )}
          />
        </FormField>
        <FormField label="Quantity" required error={formState.errors.quantity?.message} hint={`In ${part.unit}.`}>
          <Input {...register('quantity')} data-autofocus inputMode="decimal" placeholder="0" />
        </FormField>
        <FormField label="Note" optionalLabel error={formState.errors.note?.message}>
          <Textarea {...register('note')} rows={2} placeholder="Why it moved." />
        </FormField>
      </form>
    </Dialog>
  )
}

/* Cycle count -------------------------------------------------------------------- */

const COUNT_FIELDS = ['location_id', 'counted_quantity', 'note'] as const

export interface CountDialogProps {
  open: boolean
  part: PartDetail
  submitting: boolean
  error: unknown
  onSubmit: (payload: CountPayload) => Promise<void>
  onClose: () => void
}

/** Count one part at one location (`POST /inventory/cycle-counts`). */
export function CountDialog({ open, part, submitting, error, onSubmit, onClose }: CountDialogProps) {
  const form = useForm<CountInput>({ resolver: zodResolver(CountInput), defaultValues: { location_id: '', counted_quantity: '', note: '' } })
  const { register, control, handleSubmit, reset, setError, watch, formState } = form
  const locations = useLocationOptions(part.balances, part.unit)
  const locationId = watch('location_id')
  const counted = watch('counted_quantity')

  const expected = useMemo(() => part.balances.find((balance) => balance.location?.id === locationId)?.on_hand ?? 0, [part.balances, locationId])
  const delta = counted.trim() === '' || Number.isNaN(Number(counted)) ? null : Number(counted) - expected

  useEffect(() => {
    if (!open) return
    reset({ location_id: defaultLocationId(part) ?? '', counted_quantity: '', note: '' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, part.id, reset])

  useEffect(() => {
    for (const [field, message] of fieldMessages(error, COUNT_FIELDS)) setError(field as keyof CountInput, { type: 'server', message })
  }, [error, setError])

  const generalError = generalErrorOf(error)

  return (
    <Dialog
      open={open}
      onClose={onClose}
      size="sm"
      title={`Count ${part.name}`}
      description="Records what is physically on the shelf. The difference is posted as a cycle-count row, even when it is zero."
      preventClose={submitting}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="part-count-form" loading={submitting}>
            Record count
          </Button>
        </>
      }
    >
      <form id="part-count-form" noValidate className={styles.form} onSubmit={handleSubmit((values) => onSubmit(toCountPayload(part.id, values)))}>
        {generalError && <InlineAlert tone="danger">{generalError}</InlineAlert>}
        <FormField label="Location" required error={formState.errors.location_id?.message}>
          <Controller
            control={control}
            name="location_id"
            render={({ field }) => (
              <Combobox options={locations.options} loading={locations.isLoading} value={field.value || null} onChange={(value) => field.onChange(value ?? '')} placeholder="Choose a location" emptyText="No locations" />
            )}
          />
        </FormField>
        <FormField
          label="Counted quantity"
          required
          error={formState.errors.counted_quantity?.message}
          hint={`System quantity there: ${formatQuantity(expected)} ${part.unit}.${delta === null ? '' : delta === 0 ? ' Your count matches.' : ` Difference: ${delta > 0 ? '+' : '−'}${formatQuantity(Math.abs(delta))} ${part.unit}.`}`}
        >
          <Input {...register('counted_quantity')} data-autofocus inputMode="decimal" placeholder="0" />
        </FormField>
        <FormField label="Note" optionalLabel error={formState.errors.note?.message}>
          <Textarea {...register('note')} rows={2} placeholder="Who counted, and anything odd about the shelf." />
        </FormField>
      </form>
    </Dialog>
  )
}
