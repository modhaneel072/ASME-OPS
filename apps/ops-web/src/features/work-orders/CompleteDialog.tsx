import { Plus, X } from 'lucide-react'
import { useState } from 'react'
import { ApiError, errorMessage } from '@/api/client'
import { PRIORITIES, PRIORITY_LABELS, STATUS_LABELS, WORK_TYPES, WORK_TYPE_LABELS } from '@/api/contracts/common'
import { ASSET_STATUSES, COST_TYPES, COST_TYPE_LABELS, DOWNTIME_TYPES, type CompleteInput, type CompleteResponse, type WorkOrderDetail } from '@/api/contracts/work-orders'
import { useCompleteWorkOrder } from '@/api/queries/work-orders'
import { usePeopleOptions } from '@/api/queries/users'
import { useVendorOptions } from '@/api/queries/vendors'
import { fromDateTimeLocal } from '@/lib/dates'
import { canOn, useSession } from '@/lib/permissions'
import { Button, Checkbox, Combobox, DateTimeInput, Dialog, FieldRow, FormField, FormSection, IconButton, InlineAlert, Input, Select, Textarea, useToast } from '@/ui'
import styles from './work-orders.module.css'

interface TimeRow {
  key: number
  user_id: number
  minutes: string
  note: string
}

interface CostRow {
  key: number
  type: string
  amount: string
  vendor_id: string | null
  description: string
}

export interface CompleteDialogProps {
  workOrder: WorkOrderDetail
  open: boolean
  onClose: () => void
  onCompleted?: (result: CompleteResponse) => void
}

let rowCounter = 0
const nextKey = () => ++rowCounter

export function CompleteDialog(props: CompleteDialogProps) {
  return props.open ? <CompleteDialogInner {...props} /> : null
}

function CompleteDialogInner({ workOrder, onClose, onCompleted }: CompleteDialogProps) {
  const session = useSession()
  const toast = useToast()
  const complete = useCompleteWorkOrder(workOrder.id)
  const people = usePeopleOptions()
  const vendors = useVendorOptions()
  const canAssign = canOn(session, 'work_order.assign', workOrder)

  const [note, setNote] = useState('')
  const [timeRows, setTimeRows] = useState<TimeRow[]>(() => [{ key: nextKey(), user_id: session.user.id, minutes: '', note: '' }])
  const [costRows, setCostRows] = useState<CostRow[]>([])
  const [assetStatus, setAssetStatus] = useState('')
  const [downtimeType, setDowntimeType] = useState('')
  const [downtimeReason, setDowntimeReason] = useState('')
  const [followUp, setFollowUp] = useState(false)
  const [followTitle, setFollowTitle] = useState('')
  const [followPriority, setFollowPriority] = useState(workOrder.priority)
  const [followWorkType, setFollowWorkType] = useState(workOrder.work_type)
  const [followDue, setFollowDue] = useState('')

  const errors = complete.error instanceof ApiError && complete.error.isValidation ? complete.error.errors : {}
  const generalError = complete.error && !(complete.error instanceof ApiError && complete.error.isValidation) ? errorMessage(complete.error) : null
  const offline = assetStatus === 'offline_planned' || assetStatus === 'offline_unplanned'

  const buildBody = (): CompleteInput => {
    const time_entries = timeRows
      .filter((row) => row.minutes.trim() !== '')
      .map((row) => ({ user_id: row.user_id, minutes: Number(row.minutes), note: row.note.trim() || null }))
    const cost_entries = costRows
      .filter((row) => row.amount.trim() !== '')
      .map((row) => ({ type: row.type, amount: Number(row.amount), vendor_id: row.vendor_id, description: row.description.trim() || null }))
    const body: CompleteInput = { note: note.trim() || null, time_entries, cost_entries }
    if (workOrder.asset && assetStatus) {
      body.asset_status = { status: assetStatus, downtime_type: offline ? downtimeType || null : null, downtime_reason: offline ? downtimeReason.trim() || null : null }
    }
    if (followUp) {
      body.follow_up = { title: followTitle.trim(), priority: followPriority, work_type: followWorkType, due_at: fromDateTimeLocal(followDue) }
    }
    return body
  }

  const submit = async () => {
    try {
      const result = await complete.mutateAsync(buildBody())
      if (result.follow_up) {
        const follow = result.follow_up
        toast.push({ tone: 'success', title: `#${workOrder.number} completed`, description: `Follow-up #${follow.number} created.`, action: { label: `Open #${follow.number}`, onClick: () => onCompleted?.(result) } })
      } else {
        toast.success(`#${workOrder.number} completed`)
      }
      onClose()
      if (result.follow_up) onCompleted?.(result)
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not complete the work order', errorMessage(error))
    }
  }

  const rowError = (prefix: string, index: number, field: string) => errors[`${prefix}[${index}].${field}`]

  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={`Complete #${workOrder.number}`}
      description={workOrder.title}
      preventClose={complete.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={complete.isPending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="complete-form" loading={complete.isPending}>
            Mark as done
          </Button>
        </>
      }
    >
      <form
        id="complete-form"
        className={styles.dialogStack}
        noValidate
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
      >
        {generalError && <InlineAlert tone="danger">{generalError}</InlineAlert>}
        {Object.keys(errors).length > 0 && !generalError && <InlineAlert tone="danger">Some entries need attention; see the messages below.</InlineAlert>}

        <FormField label="Completion note" optionalLabel error={errors.note}>
          <Textarea value={note} onChange={(event) => setNote(event.target.value)} rows={3} data-autofocus placeholder="What was done, what to watch for next time." />
        </FormField>

        <FormSection title="Time spent">
          <div className={styles.entryRows}>
            {timeRows.map((row, index) => (
              <div key={row.key} className={styles.entryRow}>
                <div>
                  {canAssign ? (
                    <Combobox<number>
                      options={people.options}
                      loading={people.isLoading}
                      value={row.user_id}
                      clearable={false}
                      onChange={(value) => setTimeRows((rows) => rows.map((r) => (r.key === row.key ? { ...r, user_id: value ?? session.user.id } : r)))}
                      aria-label={`Time entry ${index + 1} person`}
                      compact
                    />
                  ) : (
                    <Input value={session.user.name} readOnly aria-label={`Time entry ${index + 1} person`} compact />
                  )}
                  {rowError('time_entries', index, 'user_id') && <span className={styles.fieldError}>{rowError('time_entries', index, 'user_id')}</span>}
                </div>
                <div>
                  <Input value={row.minutes} inputMode="numeric" placeholder="Minutes" aria-label={`Time entry ${index + 1} minutes`} compact onChange={(event) => setTimeRows((rows) => rows.map((r) => (r.key === row.key ? { ...r, minutes: event.target.value } : r)))} />
                  {rowError('time_entries', index, 'minutes') && <span className={styles.fieldError}>{rowError('time_entries', index, 'minutes')}</span>}
                </div>
                <div>
                  <Input value={row.note} placeholder="Note" maxLength={400} aria-label={`Time entry ${index + 1} note`} compact onChange={(event) => setTimeRows((rows) => rows.map((r) => (r.key === row.key ? { ...r, note: event.target.value } : r)))} />
                  {rowError('time_entries', index, 'note') && <span className={styles.fieldError}>{rowError('time_entries', index, 'note')}</span>}
                </div>
                <IconButton size="sm" variant="ghost" label={`Remove time entry ${index + 1}`} onClick={() => setTimeRows((rows) => rows.filter((r) => r.key !== row.key))}>
                  <X size={14} />
                </IconButton>
              </div>
            ))}
          </div>
          <div>
            <Button size="sm" variant="ghost" leadingIcon={<Plus size={14} />} onClick={() => setTimeRows((rows) => [...rows, { key: nextKey(), user_id: session.user.id, minutes: '', note: '' }])}>
              Add time entry
            </Button>
          </div>
        </FormSection>

        <FormSection title="Costs">
          <div className={styles.entryRows}>
            {costRows.map((row, index) => (
              <div key={row.key} className={`${styles.entryRow} ${styles.costRow}`}>
                <div>
                  <Select value={row.type} compact aria-label={`Cost ${index + 1} type`} onChange={(event) => setCostRows((rows) => rows.map((r) => (r.key === row.key ? { ...r, type: event.target.value } : r)))}>
                    {COST_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {COST_TYPE_LABELS[t]}
                      </option>
                    ))}
                  </Select>
                  {rowError('cost_entries', index, 'type') && <span className={styles.fieldError}>{rowError('cost_entries', index, 'type')}</span>}
                </div>
                <div>
                  <Input value={row.amount} inputMode="decimal" placeholder="Amount" aria-label={`Cost ${index + 1} amount`} compact onChange={(event) => setCostRows((rows) => rows.map((r) => (r.key === row.key ? { ...r, amount: event.target.value } : r)))} />
                  {rowError('cost_entries', index, 'amount') && <span className={styles.fieldError}>{rowError('cost_entries', index, 'amount')}</span>}
                </div>
                <div>
                  <Combobox options={vendors.options} loading={vendors.isLoading} value={row.vendor_id} placeholder="Vendor" compact aria-label={`Cost ${index + 1} vendor`} onChange={(value) => setCostRows((rows) => rows.map((r) => (r.key === row.key ? { ...r, vendor_id: value } : r)))} />
                  {rowError('cost_entries', index, 'vendor_id') && <span className={styles.fieldError}>{rowError('cost_entries', index, 'vendor_id')}</span>}
                </div>
                <div>
                  <Input value={row.description} placeholder="Description" maxLength={400} aria-label={`Cost ${index + 1} description`} compact onChange={(event) => setCostRows((rows) => rows.map((r) => (r.key === row.key ? { ...r, description: event.target.value } : r)))} />
                  {rowError('cost_entries', index, 'description') && <span className={styles.fieldError}>{rowError('cost_entries', index, 'description')}</span>}
                </div>
                <IconButton size="sm" variant="ghost" label={`Remove cost ${index + 1}`} onClick={() => setCostRows((rows) => rows.filter((r) => r.key !== row.key))}>
                  <X size={14} />
                </IconButton>
              </div>
            ))}
          </div>
          <div>
            <Button size="sm" variant="ghost" leadingIcon={<Plus size={14} />} onClick={() => setCostRows((rows) => [...rows, { key: nextKey(), type: 'parts', amount: '', vendor_id: workOrder.vendor?.id ?? null, description: '' }])}>
              Add cost
            </Button>
          </div>
        </FormSection>

        {workOrder.asset && (
          <FormSection title={`Asset status: ${workOrder.asset.name}`}>
            <FormField label="New status" optionalLabel hint="Leave unchanged to keep the asset as it is." error={errors['asset_status.status'] ?? errors.asset_status}>
              <Select value={assetStatus} onChange={(event) => setAssetStatus(event.target.value)} placeholder="Keep current status">
                {ASSET_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {STATUS_LABELS[s] ?? s}
                  </option>
                ))}
              </Select>
            </FormField>
            {offline && (
              <FieldRow>
                <FormField label="Downtime type" error={errors['asset_status.downtime_type']}>
                  <Select value={downtimeType} onChange={(event) => setDowntimeType(event.target.value)} placeholder={assetStatus === 'offline_planned' ? 'Planned (default)' : 'Unplanned (default)'}>
                    {DOWNTIME_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {t === 'planned' ? 'Planned' : 'Unplanned'}
                      </option>
                    ))}
                  </Select>
                </FormField>
                <FormField label="Downtime reason" optionalLabel error={errors['asset_status.downtime_reason']}>
                  <Input value={downtimeReason} onChange={(event) => setDowntimeReason(event.target.value)} maxLength={160} placeholder="e.g. Awaiting calibration" />
                </FormField>
              </FieldRow>
            )}
          </FormSection>
        )}

        <FormSection title="Follow-up">
          <Checkbox label="Create a follow-up work order" hint="Opens a new work order linked to this one with the same project, location and asset." checked={followUp} onChange={setFollowUp} />
          {followUp && (
            <>
              <FormField label="Follow-up title" required error={errors['follow_up.title'] ?? errors.follow_up}>
                <Input value={followTitle} onChange={(event) => setFollowTitle(event.target.value)} maxLength={240} placeholder="What needs to happen next" />
              </FormField>
              <FieldRow>
                <FormField label="Priority" error={errors['follow_up.priority']}>
                  <Select value={followPriority} onChange={(event) => setFollowPriority(event.target.value)}>
                    {PRIORITIES.map((p) => (
                      <option key={p} value={p}>
                        {PRIORITY_LABELS[p]}
                      </option>
                    ))}
                  </Select>
                </FormField>
                <FormField label="Work type" error={errors['follow_up.work_type']}>
                  <Select value={followWorkType} onChange={(event) => setFollowWorkType(event.target.value)}>
                    {WORK_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {WORK_TYPE_LABELS[t]}
                      </option>
                    ))}
                  </Select>
                </FormField>
              </FieldRow>
              <FormField label="Due" optionalLabel error={errors['follow_up.due_at']}>
                <DateTimeInput value={followDue} onChange={(event) => setFollowDue(event.target.value)} />
              </FormField>
            </>
          )}
        </FormSection>
      </form>
    </Dialog>
  )
}
