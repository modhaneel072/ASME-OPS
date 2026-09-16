/**
 * The "Parts" section of a work order: which parts the job needs, where they are
 * drawn from, how far along each line is (assigned → reserved → kitted → staged
 * → issued) and the actions that move stock.
 *
 * Every route under `/work-orders/:id/parts` answers with the whole list, so one
 * query backs the section, the readiness badge in the header and every dialog.
 * Actions are hidden unless the session holds the key the API requires:
 * plan/edit/remove need `work_order.edit`, reserve and release need
 * `inventory.manage` or `work_order.edit`, kit and stage need `inventory.manage`,
 * issue and return need `inventory.manage` or `work_order.log_time`. The server
 * still decides at object level.
 */
import { zodResolver } from '@hookform/resolvers/zod'
import { AlertTriangle, MoreHorizontal, Package, Pencil, Plus, Trash2, Undo2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { ApiError, errorMessage } from '@/api/client'
import type { WorkOrderDetail } from '@/api/contracts/work-orders'
import {
  AddPartInput,
  PART_ACTION_LABELS,
  PartQuantityInput,
  READINESS_NONE,
  UpdatePartInput,
  canRemoveLine,
  formatQuantity,
  formatQuantityUnit,
  isQuantityAction,
  outstandingQuantity,
  readinessLabel,
  remainingNeed,
  reservableQuantity,
  returnableQuantity,
  stockShortfall,
  stockStateLabel,
  toAddPartPayload,
  toPartQuantityPayload,
  toUpdatePartPayload,
  type PartLineAction,
  type StockState,
  type WorkOrderPart,
  type WorkOrderPartReadiness,
} from '@/api/contracts/workOrderParts'
import {
  useAddWorkOrderPart,
  usePartInventory,
  usePartPickerOptions,
  useReleaseAllWorkOrderParts,
  useRemoveWorkOrderPart,
  useUpdateWorkOrderPart,
  useWorkOrderPartAction,
  useWorkOrderParts,
} from '@/api/queries/workOrderParts'
import { canOn, useCan, useSession } from '@/lib/permissions'
import {
  Badge,
  Button,
  Card,
  Combobox,
  Dialog,
  DropdownMenu,
  EmptyState,
  FormField,
  IconButton,
  InlineAlert,
  Input,
  Select,
  SkeletonRows,
  Textarea,
  useToast,
  type BadgeTone,
  type ComboOption,
  type MenuItem,
} from '@/ui'
import styles from './parts.module.css'

const READINESS_TONES: Record<WorkOrderPartReadiness, BadgeTone> = {
  assigned: 'outline',
  reserved: 'info',
  kitted: 'purple',
  staged: 'gold',
  issued: 'success',
}

const STOCK_TONES: Record<StockState, BadgeTone> = {
  ok: 'success',
  low: 'warning',
  out: 'danger',
  untracked: 'neutral',
}

function readinessTone(value: string): BadgeTone {
  return READINESS_TONES[value as WorkOrderPartReadiness] ?? 'neutral'
}

function serverErrors(error: unknown): Record<string, string> {
  return error instanceof ApiError && error.isValidation ? error.errors : {}
}

function generalMessage(error: unknown): string | null {
  return error && !(error instanceof ApiError && error.isValidation) ? errorMessage(error) : null
}

/* Permissions ------------------------------------------------------------------- */

interface PartPermissions {
  plan: boolean
  reserve: boolean
  kit: boolean
  issue: boolean
}

function usePartPermissions(workOrder: WorkOrderDetail): PartPermissions {
  const session = useSession()
  const can = useCan()
  const manage = can('inventory.manage')
  const plan = canOn(session, 'work_order.edit', workOrder)
  return {
    plan,
    reserve: manage || plan,
    kit: manage,
    issue: manage || canOn(session, 'work_order.log_time', workOrder),
  }
}

/* Readiness badge for the detail header ------------------------------------------ */

/** Least advanced readiness across the lines, shown next to the status badge. */
export function PartsReadinessBadge({ workOrderId }: { workOrderId: string }) {
  const parts = useWorkOrderParts(workOrderId)
  const summary = parts.data?.readiness_summary
  if (!summary || summary === READINESS_NONE || !parts.data || parts.data.items.length === 0) return null
  return (
    <Badge tone={readinessTone(summary)} title={`${parts.data.items.length} part ${parts.data.items.length === 1 ? 'line' : 'lines'}`}>
      Parts: {readinessLabel(summary)}
    </Badge>
  )
}

/* Section ------------------------------------------------------------------------- */

type DialogState =
  | { kind: 'add' }
  | { kind: 'edit'; line: WorkOrderPart }
  | { kind: 'remove'; line: WorkOrderPart }
  | { kind: 'quantity'; line: WorkOrderPart; action: PartLineAction }
  | null

export interface WorkOrderPartsSectionProps {
  workOrder: WorkOrderDetail
}

export function WorkOrderPartsSection({ workOrder }: WorkOrderPartsSectionProps) {
  const permissions = usePartPermissions(workOrder)
  const parts = useWorkOrderParts(workOrder.id)
  const toast = useToast()
  const releaseAll = useReleaseAllWorkOrderParts(workOrder.id)
  const action = useWorkOrderPartAction(workOrder.id)
  const [dialog, setDialog] = useState<DialogState>(null)

  const items = parts.data?.items ?? []
  const outstanding = parts.data?.parts_outstanding ?? 0
  const summary = parts.data?.readiness_summary ?? READINESS_NONE

  const runReadiness = async (line: WorkOrderPart, kind: 'kit' | 'stage') => {
    try {
      await action.mutateAsync({ lineId: line.id, action: kind })
      toast.success(`${line.part.name} ${kind === 'kit' ? 'kitted' : 'staged'}`)
    } catch (error) {
      toast.error(`Could not ${kind} ${line.part.name}`, errorMessage(error))
    }
  }

  const onReleaseAll = async () => {
    try {
      await releaseAll.mutateAsync()
      toast.success('Reservations released')
    } catch (error) {
      toast.error('Could not release the reservations', errorMessage(error))
    }
  }

  const headerActions = (
    <span className={styles.cardActions}>
      {items.length > 0 && (
        <span className={styles.summary}>
          <Badge tone={readinessTone(summary)} size="sm">
            {readinessLabel(summary)}
          </Badge>
          {outstanding > 0 && (
            <span className={styles.summaryNote}>
              {outstanding} {outstanding === 1 ? 'line' : 'lines'} still reserved
            </span>
          )}
        </span>
      )}
      {permissions.reserve && outstanding > 0 && (
        <Button size="sm" variant="ghost" leadingIcon={<Undo2 size={14} />} onClick={() => void onReleaseAll()} loading={releaseAll.isPending}>
          Release all
        </Button>
      )}
      {permissions.plan && (
        <Button size="sm" variant="ghost" leadingIcon={<Plus size={14} />} onClick={() => setDialog({ kind: 'add' })}>
          Add part
        </Button>
      )}
    </span>
  )

  return (
    <Card title="Parts" flush actions={headerActions}>
      {parts.isPending ? (
        <div className={styles.loading}>
          <SkeletonRows rows={3} />
        </div>
      ) : parts.isError ? (
        <div className={styles.loading}>
          <InlineAlert
            tone="danger"
            title="Could not load the parts"
            actions={
              <Button size="sm" onClick={() => void parts.refetch()}>
                Retry
              </Button>
            }
          >
            {errorMessage(parts.error)}
          </InlineAlert>
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          compact
          illustration="box"
          title="No parts planned"
          description="Add the parts this work order needs so stock can be reserved and issued against it."
          action={
            permissions.plan ? (
              <Button size="sm" leadingIcon={<Plus size={14} />} onClick={() => setDialog({ kind: 'add' })}>
                Add part
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table} aria-label="Parts">
            <thead>
              <tr>
                <th scope="col">Part</th>
                <th scope="col">Location</th>
                <th scope="col" className={styles.numeric}>
                  Planned
                </th>
                <th scope="col" className={styles.numeric}>
                  Reserved
                </th>
                <th scope="col" className={styles.numeric}>
                  Issued
                </th>
                <th scope="col" className={styles.numeric}>
                  Returned
                </th>
                <th scope="col">Readiness</th>
                <th scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((line) => (
                <PartRow
                  key={line.id}
                  line={line}
                  permissions={permissions}
                  busy={action.isPending}
                  onEdit={() => setDialog({ kind: 'edit', line })}
                  onRemove={() => setDialog({ kind: 'remove', line })}
                  onQuantity={(kind) => setDialog({ kind: 'quantity', line, action: kind })}
                  onReadiness={(kind) => void runReadiness(line, kind)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {dialog?.kind === 'add' && <AddPartDialog workOrder={workOrder} onClose={() => setDialog(null)} />}
      {dialog?.kind === 'edit' && <EditPartDialog workOrder={workOrder} line={dialog.line} onClose={() => setDialog(null)} />}
      {dialog?.kind === 'remove' && <RemovePartDialog workOrder={workOrder} line={dialog.line} onClose={() => setDialog(null)} />}
      {dialog?.kind === 'quantity' && <QuantityDialog workOrder={workOrder} line={dialog.line} action={dialog.action} onClose={() => setDialog(null)} />}
    </Card>
  )
}

/* One line ------------------------------------------------------------------------ */

interface PartRowProps {
  line: WorkOrderPart
  permissions: PartPermissions
  busy: boolean
  onEdit: () => void
  onRemove: () => void
  onQuantity: (action: PartLineAction) => void
  onReadiness: (action: 'kit' | 'stage') => void
}

function PartRow({ line, permissions, busy, onEdit, onRemove, onQuantity, onReadiness }: PartRowProps) {
  const shortfall = stockShortfall(line)
  const unit = line.part.unit
  const items: MenuItem[] = []
  if (permissions.reserve) {
    items.push({ key: 'reserve', label: 'Reserve…', onSelect: () => onQuantity('reserve'), disabled: reservableQuantity(line) <= 0 || !line.location })
    items.push({ key: 'release', label: 'Release…', onSelect: () => onQuantity('release'), disabled: line.quantity_reserved <= 0 })
  }
  if (permissions.kit) {
    items.push({ key: 'kit', label: 'Mark kitted', onSelect: () => onReadiness('kit'), disabled: busy || line.readiness === 'issued' })
    items.push({ key: 'stage', label: 'Mark staged', onSelect: () => onReadiness('stage'), disabled: busy || line.readiness === 'issued' })
  }
  if (permissions.issue) {
    items.push({ key: 'issue', label: 'Issue…', onSelect: () => onQuantity('issue'), disabled: !line.location })
    items.push({ key: 'return', label: 'Return…', onSelect: () => onQuantity('return'), disabled: returnableQuantity(line) <= 0 })
  }
  if (permissions.plan) {
    if (items.length) items.push({ type: 'separator', key: 'sep' })
    items.push({ key: 'edit', label: 'Edit planned quantity', icon: <Pencil size={14} />, onSelect: onEdit })
    items.push({
      key: 'remove',
      label: 'Remove part',
      icon: <Trash2 size={14} />,
      destructive: true,
      disabled: !canRemoveLine(line),
      onSelect: onRemove,
    })
  }

  return (
    <tr>
      <td>
        <span className={styles.partCell}>
          <span className={styles.partName}>{line.part.name}</span>
          <span className={styles.partMeta}>
            {line.part.sku && <span className="mono">{line.part.sku}</span>}
            <Badge tone={STOCK_TONES[(line.part.stock_state ?? 'untracked') as StockState] ?? 'neutral'} size="sm">
              {stockStateLabel(line.part.stock_state)}
            </Badge>
            <span>{formatQuantityUnit(line.part.totals.available, unit)} available</span>
          </span>
          {shortfall > 0 && (
            <span className={styles.warning}>
              <AlertTriangle size={13} aria-hidden="true" />
              Short by {formatQuantityUnit(shortfall, unit)} of the {formatQuantity(remainingNeed(line))} still needed.
            </span>
          )}
          {!line.location && <span className={styles.warning}>
            <AlertTriangle size={13} aria-hidden="true" />
            Choose a location before reserving or issuing.
          </span>}
        </span>
      </td>
      <td>{line.location?.name ?? '—'}</td>
      <td className={styles.numeric}>{formatQuantity(line.quantity_planned)}</td>
      <td className={styles.numeric}>{formatQuantity(line.quantity_reserved)}</td>
      <td className={styles.numeric}>{formatQuantity(line.quantity_issued)}</td>
      <td className={styles.numeric}>{formatQuantity(line.quantity_returned)}</td>
      <td>
        <Badge tone={readinessTone(line.readiness)} size="sm" dot>
          {readinessLabel(line.readiness)}
        </Badge>
      </td>
      <td>
        {items.length > 0 && (
          <DropdownMenu
            align="end"
            label={`Actions for ${line.part.name}`}
            items={items}
            trigger={(props) => (
              <IconButton {...props} ref={props.ref} size="sm" variant="ghost" label={`Actions for ${line.part.name}`}>
                <MoreHorizontal size={16} />
              </IconButton>
            )}
          />
        )}
      </td>
    </tr>
  )
}

/* Add part ------------------------------------------------------------------------ */

const NO_LOCATION = ''

function AddPartDialog({ workOrder, onClose }: { workOrder: WorkOrderDetail; onClose: () => void }) {
  const add = useAddWorkOrderPart(workOrder.id)
  const toast = useToast()
  const [search, setSearch] = useState('')
  const timer = useRef<number>(0)
  const picker = usePartPickerOptions(search)
  const form = useForm<AddPartInput>({
    resolver: zodResolver(AddPartInput),
    defaultValues: { part_id: '', location_id: null, quantity_planned: '1', note: '' },
  })
  const { handleSubmit, register, setValue, setError, watch, formState } = form
  const partId = watch('part_id')
  const locationId = watch('location_id')
  const selected = partId ? picker.byId.get(partId) : undefined
  const inventory = usePartInventory(partId || null)

  // Server field errors land on the matching control.
  useEffect(() => {
    for (const [field, message] of Object.entries(serverErrors(add.error))) {
      setError(field as keyof AddPartInput, { type: 'server', message })
    }
  }, [add.error, setError])

  // Default the location to where the part is actually stocked.
  useEffect(() => {
    if (!partId) return
    const balances = inventory.data?.balances ?? []
    const best = [...balances].sort((a, b) => b.available - a.available).find((balance) => balance.location)
    const fallback = selected?.default_location?.id ?? null
    setValue('location_id', best?.location?.id ?? fallback)
  }, [partId, inventory.data, selected, setValue])

  const options: ComboOption<string>[] = useMemo(
    () =>
      picker.items.map((part) => ({
        value: part.id,
        label: part.name,
        meta: [part.sku, `${formatQuantityUnit(part.totals.available, part.unit)} available`].filter(Boolean).join(' · '),
      })),
    [picker.items],
  )

  const locationOptions = useMemo(() => {
    const rows = (inventory.data?.balances ?? []).filter((balance) => balance.location)
    const seen = new Set(rows.map((balance) => balance.location!.id))
    const extra = selected?.default_location && !seen.has(selected.default_location.id) ? [{ id: selected.default_location.id, name: selected.default_location.name, available: 0 }] : []
    return [
      ...rows.map((balance) => ({ id: balance.location!.id, name: balance.location!.name, available: balance.available })),
      ...extra,
    ]
  }, [inventory.data, selected])

  const onSearch = (text: string) => {
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setSearch(text.trim()), 250)
  }

  const submit = handleSubmit(async (values) => {
    try {
      await add.mutateAsync(toAddPartPayload(values))
      toast.success(`${selected?.name ?? 'Part'} added to #${workOrder.number}`)
      onClose()
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not add the part', errorMessage(error))
    }
  })

  return (
    <Dialog
      open
      onClose={onClose}
      title={`Add a part to #${workOrder.number}`}
      description="Pick a part, say where it is drawn from and how many the job needs."
      preventClose={add.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={add.isPending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="add-part-form" loading={add.isPending}>
            Add part
          </Button>
        </>
      }
    >
      <form id="add-part-form" className={styles.form} noValidate onSubmit={(event) => void submit(event)}>
        {generalMessage(add.error) && <InlineAlert tone="danger">{generalMessage(add.error)}</InlineAlert>}
        {picker.error ? (
          <InlineAlert tone="warning" title="Parts are unavailable">
            {errorMessage(picker.error)}
          </InlineAlert>
        ) : null}
        <FormField label="Part" required error={formState.errors.part_id?.message} hint="Search by name or SKU.">
          <Combobox
            options={options}
            value={partId || null}
            onChange={(value) => setValue('part_id', value ?? '', { shouldValidate: Boolean(value) })}
            onSearch={onSearch}
            loading={picker.isLoading}
            placeholder="Search parts"
            emptyText="No matching parts"
            aria-label="Part"
          />
        </FormField>
        <FormField
          label="Location"
          optionalLabel
          error={formState.errors.location_id?.message}
          hint={selected ? 'Stock is reserved and issued from this location.' : 'Choose a part first.'}
        >
          <Select
            value={locationId ?? NO_LOCATION}
            onChange={(event) => setValue('location_id', event.target.value ? event.target.value : null)}
            disabled={!partId || inventory.isPending}
          >
            <option value={NO_LOCATION}>No location yet</option>
            {locationOptions.map((option) => (
              <option key={option.id} value={option.id}>
                {option.name} — {formatQuantity(option.available)} available
              </option>
            ))}
          </Select>
        </FormField>
        <FormField
          label={`Quantity planned${selected ? ` (${selected.unit})` : ''}`}
          required
          error={formState.errors.quantity_planned?.message}
        >
          <Input {...register('quantity_planned')} inputMode="decimal" placeholder="e.g. 2" data-autofocus />
        </FormField>
        <FormField label="Note" optionalLabel error={formState.errors.note?.message}>
          <Textarea {...register('note')} rows={2} placeholder="Anything the person picking this should know." />
        </FormField>
      </form>
    </Dialog>
  )
}

/* Edit planned quantity ------------------------------------------------------------ */

function EditPartDialog({ workOrder, line, onClose }: { workOrder: WorkOrderDetail; line: WorkOrderPart; onClose: () => void }) {
  const update = useUpdateWorkOrderPart(workOrder.id)
  const toast = useToast()
  const form = useForm<UpdatePartInput>({
    resolver: zodResolver(UpdatePartInput),
    defaultValues: { quantity_planned: formatQuantity(line.quantity_planned), note: line.note ?? '' },
  })
  const { handleSubmit, register, setError, formState } = form

  useEffect(() => {
    for (const [field, message] of Object.entries(serverErrors(update.error))) {
      setError(field as keyof UpdatePartInput, { type: 'server', message })
    }
  }, [update.error, setError])

  const submit = handleSubmit(async (values) => {
    try {
      await update.mutateAsync({ lineId: line.id, input: toUpdatePartPayload(values) })
      toast.success(`${line.part.name} updated`)
      onClose()
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not update the part', errorMessage(error))
    }
  })

  const outstanding = outstandingQuantity(line)

  return (
    <Dialog
      open
      onClose={onClose}
      size="sm"
      title={`Edit ${line.part.name}`}
      description={outstanding > 0 ? `${formatQuantityUnit(outstanding, line.part.unit)} has already been issued and cannot be planned away.` : undefined}
      preventClose={update.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={update.isPending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="edit-part-form" loading={update.isPending}>
            Save part
          </Button>
        </>
      }
    >
      <form id="edit-part-form" className={styles.form} noValidate onSubmit={(event) => void submit(event)}>
        {generalMessage(update.error) && <InlineAlert tone="danger">{generalMessage(update.error)}</InlineAlert>}
        <FormField label={`Quantity planned (${line.part.unit})`} required error={formState.errors.quantity_planned?.message}>
          <Input {...register('quantity_planned')} inputMode="decimal" data-autofocus />
        </FormField>
        <FormField label="Note" optionalLabel error={formState.errors.note?.message}>
          <Textarea {...register('note')} rows={2} />
        </FormField>
      </form>
    </Dialog>
  )
}

/* Remove ---------------------------------------------------------------------------- */

function RemovePartDialog({ workOrder, line, onClose }: { workOrder: WorkOrderDetail; line: WorkOrderPart; onClose: () => void }) {
  const remove = useRemoveWorkOrderPart(workOrder.id)
  const toast = useToast()

  const submit = async () => {
    try {
      await remove.mutateAsync(line.id)
      toast.success(`${line.part.name} removed`)
      onClose()
    } catch (error) {
      toast.error('Could not remove the part', errorMessage(error))
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      size="sm"
      title={`Remove ${line.part.name}?`}
      description="The planned line is deleted. Nothing is reserved or issued, so no stock moves."
      preventClose={remove.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={remove.isPending}>
            Keep it
          </Button>
          <Button variant="danger" onClick={() => void submit()} loading={remove.isPending} data-autofocus>
            Remove part
          </Button>
        </>
      }
    />
  )
}

/* Reserve / release / issue / return -------------------------------------------------- */

interface QuantityCopy {
  title: string
  description: string
  submit: string
  hint: string
  max: number
  done: string
}

function quantityCopy(line: WorkOrderPart, action: PartLineAction): QuantityCopy {
  const unit = line.part.unit
  const available = line.part.totals.available
  switch (action) {
    case 'reserve':
      return {
        title: `Reserve ${line.part.name}`,
        description: 'Reserved stock stays on the shelf but is held for this work order.',
        submit: 'Reserve',
        hint: `At most ${formatQuantityUnit(reservableQuantity(line), unit)} can still be reserved · ${formatQuantity(available)} available.`,
        max: reservableQuantity(line),
        done: 'reserved',
      }
    case 'release':
      return {
        title: `Release ${line.part.name}`,
        description: 'Releasing puts the held quantity back into general stock.',
        submit: 'Release',
        hint: `${formatQuantityUnit(line.quantity_reserved, unit)} is reserved.`,
        max: line.quantity_reserved,
        done: 'released',
      }
    case 'issue':
      return {
        title: `Issue ${line.part.name}`,
        description: 'Issuing takes the parts out of stock and charges them to this work order.',
        submit: 'Issue',
        hint: `${formatQuantityUnit(remainingNeed(line), unit)} still needed · ${formatQuantity(available)} available.`,
        max: remainingNeed(line),
        done: 'issued',
      }
    case 'return':
      return {
        title: `Return ${line.part.name}`,
        description: 'Returning puts unused parts back on the shelf and reverses their cost.',
        submit: 'Return',
        hint: `At most ${formatQuantityUnit(returnableQuantity(line), unit)} can be returned.`,
        max: returnableQuantity(line),
        done: 'returned',
      }
    default:
      return { title: PART_ACTION_LABELS[action], description: '', submit: PART_ACTION_LABELS[action], hint: '', max: 0, done: 'updated' }
  }
}

function QuantityDialog({ workOrder, line, action, onClose }: { workOrder: WorkOrderDetail; line: WorkOrderPart; action: PartLineAction; onClose: () => void }) {
  const run = useWorkOrderPartAction(workOrder.id)
  const toast = useToast()
  const copy = quantityCopy(line, action)
  const form = useForm<PartQuantityInput>({
    resolver: zodResolver(PartQuantityInput),
    defaultValues: { quantity: copy.max > 0 ? formatQuantity(copy.max) : '', note: '' },
  })
  const { handleSubmit, register, setError, formState } = form

  useEffect(() => {
    for (const [field, message] of Object.entries(serverErrors(run.error))) {
      setError(field as keyof PartQuantityInput, { type: 'server', message })
    }
  }, [run.error, setError])

  const submit = handleSubmit(async (values) => {
    try {
      await run.mutateAsync({ lineId: line.id, action, input: isQuantityAction(action) ? toPartQuantityPayload(values) : undefined })
      toast.success(`${line.part.name} ${copy.done}`)
      onClose()
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error(`Could not ${PART_ACTION_LABELS[action].toLowerCase()} ${line.part.name}`, errorMessage(error))
    }
  })

  return (
    <Dialog
      open
      onClose={onClose}
      size="sm"
      title={copy.title}
      description={copy.description}
      preventClose={run.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={run.isPending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="part-quantity-form" loading={run.isPending}>
            {copy.submit}
          </Button>
        </>
      }
    >
      <form id="part-quantity-form" className={styles.form} noValidate onSubmit={(event) => void submit(event)}>
        {generalMessage(run.error) && <InlineAlert tone="danger">{generalMessage(run.error)}</InlineAlert>}
        <p className={styles.dialogMeta}>
          <Package size={14} aria-hidden="true" />
          {line.location ? line.location.name : 'No location'} · planned {formatQuantityUnit(line.quantity_planned, line.part.unit)}
        </p>
        <FormField label={`Quantity (${line.part.unit})`} required hint={copy.hint} error={formState.errors.quantity?.message}>
          <Input {...register('quantity')} inputMode="decimal" data-autofocus />
        </FormField>
        <FormField label="Note" optionalLabel error={formState.errors.note?.message}>
          <Textarea {...register('note')} rows={2} />
        </FormField>
      </form>
    </Dialog>
  )
}

export default WorkOrderPartsSection
