/**
 * Small dialogs opened from the work-order detail: cancel (note required),
 * assignees, watchers, add dependency, log time and add cost. Each is mounted
 * only while open so its local state starts fresh every time; each owns its
 * mutation, maps server field errors and reports 403/409 through toasts.
 */
import { useMemo, useRef, useState } from 'react'
import { ApiError, errorMessage } from '@/api/client'
import { COST_TYPES, COST_TYPE_LABELS, type WorkOrder, type WorkOrderDetail } from '@/api/contracts/work-orders'
import { useAddCostEntry, useAddDependency, useAddTimeEntry, useSetAssignees, useSetWatchers, useTransitionWorkOrder, searchWorkOrders } from '@/api/queries/work-orders'
import { useTeamOptions } from '@/api/queries/teams'
import { usePeopleOptions } from '@/api/queries/users'
import { useVendorOptions } from '@/api/queries/vendors'
import { fromDateTimeLocal } from '@/lib/dates'
import { Button, Combobox, DateTimeInput, Dialog, FieldRow, FormField, InlineAlert, Input, Select, Textarea, useToast, type ComboOption } from '@/ui'
import styles from './work-orders.module.css'

function serverErrors(error: unknown): Record<string, string> {
  return error instanceof ApiError && error.isValidation ? error.errors : {}
}

function generalMessage(error: unknown): string | null {
  return error && !(error instanceof ApiError && error.isValidation) ? errorMessage(error) : null
}

interface DialogProps<T> {
  workOrder: T
  open: boolean
  onClose: () => void
}

/* Cancel --------------------------------------------------------------------- */

export function CancelDialog(props: DialogProps<WorkOrder>) {
  return props.open ? <CancelDialogInner {...props} /> : null
}

function CancelDialogInner({ workOrder, onClose }: DialogProps<WorkOrder>) {
  const transition = useTransitionWorkOrder(workOrder.id)
  const toast = useToast()
  const [note, setNote] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)
  const errors = serverErrors(transition.error)

  const submit = async () => {
    if (!note.trim()) {
      setLocalError('A reason is required to cancel a work order.')
      return
    }
    setLocalError(null)
    try {
      await transition.mutateAsync({ action: 'cancel', note: note.trim() })
      toast.success(`#${workOrder.number} canceled`)
      onClose()
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not cancel the work order', errorMessage(error))
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      size="sm"
      title={`Cancel #${workOrder.number}?`}
      description="The work order moves to Canceled and everyone involved is notified. It can be reopened later."
      preventClose={transition.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={transition.isPending}>
            Keep it
          </Button>
          <Button variant="danger" onClick={() => void submit()} loading={transition.isPending}>
            Cancel work order
          </Button>
        </>
      }
    >
      <form
        className={styles.form}
        noValidate
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
      >
        <FormField label="Reason" required error={localError ?? errors.note}>
          <Textarea value={note} onChange={(event) => setNote(event.target.value)} rows={3} data-autofocus placeholder="Why is this being canceled?" />
        </FormField>
      </form>
    </Dialog>
  )
}

/* Assignees ------------------------------------------------------------------ */

export function AssigneesDialog(props: DialogProps<WorkOrderDetail>) {
  return props.open ? <AssigneesDialogInner {...props} /> : null
}

function AssigneesDialogInner({ workOrder, onClose }: DialogProps<WorkOrderDetail>) {
  const set = useSetAssignees(workOrder.id)
  const toast = useToast()
  const people = usePeopleOptions()
  const teams = useTeamOptions()
  const [userIds, setUserIds] = useState<number[]>(() => workOrder.assignees.map((u) => u.id))
  const [teamIds, setTeamIds] = useState<string[]>(() => workOrder.assignee_teams.map((t) => t.id))
  const errors = serverErrors(set.error)

  return (
    <Dialog
      open
      onClose={onClose}
      title="Edit assignees"
      description="Assigned people and teams are notified and can start, log time on and complete this work order."
      preventClose={set.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={set.isPending}>
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={set.isPending}
            onClick={async () => {
              try {
                await set.mutateAsync({ user_ids: userIds, team_ids: teamIds })
                toast.success('Assignees updated')
                onClose()
              } catch (error) {
                if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not update assignees', errorMessage(error))
              }
            }}
          >
            Save assignees
          </Button>
        </>
      }
    >
      <div className={styles.form}>
        {generalMessage(set.error) && <InlineAlert tone="danger">{generalMessage(set.error)}</InlineAlert>}
        <FormField label="People" error={errors.assignee_user_ids ?? errors.user_ids}>
          <Combobox<number> multiple options={people.options} loading={people.isLoading} value={userIds} onChange={setUserIds} placeholder="Add people" emptyText="No matching members" />
        </FormField>
        <FormField label="Teams" error={errors.assignee_team_ids ?? errors.team_ids}>
          <Combobox multiple options={teams.options} loading={teams.isLoading} value={teamIds} onChange={setTeamIds} placeholder="Add teams" emptyText="No matching teams" />
        </FormField>
      </div>
    </Dialog>
  )
}

/* Watchers ------------------------------------------------------------------- */

export function WatchersDialog(props: DialogProps<WorkOrderDetail>) {
  return props.open ? <WatchersDialogInner {...props} /> : null
}

function WatchersDialogInner({ workOrder, onClose }: DialogProps<WorkOrderDetail>) {
  const set = useSetWatchers(workOrder.id)
  const toast = useToast()
  const people = usePeopleOptions()
  const [userIds, setUserIds] = useState<number[]>(() => workOrder.watchers.map((u) => u.id))
  const errors = serverErrors(set.error)

  return (
    <Dialog
      open
      onClose={onClose}
      title="Edit watchers"
      description="Watchers receive updates without being responsible for the work."
      preventClose={set.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={set.isPending}>
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={set.isPending}
            onClick={async () => {
              try {
                await set.mutateAsync({ user_ids: userIds })
                toast.success('Watchers updated')
                onClose()
              } catch (error) {
                if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not update watchers', errorMessage(error))
              }
            }}
          >
            Save watchers
          </Button>
        </>
      }
    >
      <div className={styles.form}>
        {generalMessage(set.error) && <InlineAlert tone="danger">{generalMessage(set.error)}</InlineAlert>}
        <FormField label="People" error={errors.watcher_user_ids ?? errors.user_ids}>
          <Combobox<number> multiple options={people.options} loading={people.isLoading} value={userIds} onChange={setUserIds} placeholder="Add watchers" emptyText="No matching members" />
        </FormField>
      </div>
    </Dialog>
  )
}

/* Add dependency ------------------------------------------------------------- */

export function DependencyDialog(props: DialogProps<WorkOrderDetail>) {
  return props.open ? <DependencyDialogInner {...props} /> : null
}

function DependencyDialogInner({ workOrder, onClose }: DialogProps<WorkOrderDetail>) {
  const add = useAddDependency(workOrder.id)
  const toast = useToast()
  const [selected, setSelected] = useState<string | null>(null)
  const [results, setResults] = useState<WorkOrder[]>([])
  const [searching, setSearching] = useState(false)
  const timer = useRef<number>(0)
  const abort = useRef<AbortController | null>(null)

  const search = (query: string) => {
    window.clearTimeout(timer.current)
    abort.current?.abort()
    const text = query.trim()
    if (!text) {
      setResults([])
      setSearching(false)
      return
    }
    setSearching(true)
    timer.current = window.setTimeout(async () => {
      const controller = new AbortController()
      abort.current = controller
      try {
        const items = await searchWorkOrders(text, controller.signal)
        if (!controller.signal.aborted) setResults(items.filter((wo) => wo.id !== workOrder.id))
      } catch {
        if (!controller.signal.aborted) setResults([])
      } finally {
        if (!controller.signal.aborted) setSearching(false)
      }
    }, 250)
  }

  const options = useMemo<ComboOption<string>[]>(() => results.map((wo) => ({ value: wo.id, label: `#${wo.number} ${wo.title}`, meta: wo.status.replace(/_/g, ' ') })), [results])
  const errors = serverErrors(add.error)

  return (
    <Dialog
      open
      onClose={onClose}
      title="Add dependency"
      description={`#${workOrder.number} cannot start until the work order you pick is done or canceled.`}
      preventClose={add.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={add.isPending}>
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={add.isPending}
            disabled={!selected}
            onClick={async () => {
              if (!selected) return
              try {
                await add.mutateAsync(selected)
                toast.success('Dependency added')
                onClose()
              } catch (error) {
                if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not add the dependency', errorMessage(error))
              }
            }}
          >
            Add dependency
          </Button>
        </>
      }
    >
      <div className={styles.form}>
        {generalMessage(add.error) && <InlineAlert tone="danger">{generalMessage(add.error)}</InlineAlert>}
        <FormField label="Blocked by" required hint="Search by number or title." error={errors.blocking_work_order_id}>
          <Combobox options={options} value={selected} onChange={setSelected} onSearch={search} loading={searching} placeholder="Type a number or title" emptyText="Type to search work orders" aria-label="Blocked by" />
        </FormField>
      </div>
    </Dialog>
  )
}

/* Log time --------------------------------------------------------------------- */

export function LogTimeDialog(props: DialogProps<WorkOrderDetail>) {
  return props.open ? <LogTimeDialogInner {...props} /> : null
}

function LogTimeDialogInner({ workOrder, onClose }: DialogProps<WorkOrderDetail>) {
  const add = useAddTimeEntry(workOrder.id)
  const toast = useToast()
  const [minutes, setMinutes] = useState('')
  const [started, setStarted] = useState('')
  const [ended, setEnded] = useState('')
  const [note, setNote] = useState('')
  const errors = serverErrors(add.error)

  const submit = async () => {
    try {
      await add.mutateAsync({
        minutes: minutes.trim() ? Number(minutes) : null,
        started_at: fromDateTimeLocal(started),
        ended_at: fromDateTimeLocal(ended),
        note: note.trim() || null,
      })
      toast.success('Time logged')
      onClose()
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not log time', errorMessage(error))
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title={`Log time on #${workOrder.number}`}
      description="Enter minutes, or a start and end time and the minutes are worked out for you."
      preventClose={add.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={add.isPending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="log-time-form" loading={add.isPending}>
            Log time
          </Button>
        </>
      }
    >
      <form
        id="log-time-form"
        className={styles.form}
        noValidate
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
      >
        {generalMessage(add.error) && <InlineAlert tone="danger">{generalMessage(add.error)}</InlineAlert>}
        <FormField label="Minutes" error={errors.minutes}>
          <Input value={minutes} onChange={(event) => setMinutes(event.target.value)} inputMode="numeric" placeholder="e.g. 45" data-autofocus />
        </FormField>
        <FieldRow>
          <FormField label="Started" optionalLabel error={errors.started_at}>
            <DateTimeInput value={started} onChange={(event) => setStarted(event.target.value)} />
          </FormField>
          <FormField label="Ended" optionalLabel error={errors.ended_at}>
            <DateTimeInput value={ended} onChange={(event) => setEnded(event.target.value)} />
          </FormField>
        </FieldRow>
        <FormField label="Note" optionalLabel error={errors.note}>
          <Input value={note} onChange={(event) => setNote(event.target.value)} maxLength={400} placeholder="What was done" />
        </FormField>
      </form>
    </Dialog>
  )
}

/* Add cost ---------------------------------------------------------------------- */

export function AddCostDialog(props: DialogProps<WorkOrderDetail>) {
  return props.open ? <AddCostDialogInner {...props} /> : null
}

function AddCostDialogInner({ workOrder, onClose }: DialogProps<WorkOrderDetail>) {
  const add = useAddCostEntry(workOrder.id)
  const toast = useToast()
  const vendors = useVendorOptions()
  const [type, setType] = useState<string>('parts')
  const [amount, setAmount] = useState('')
  const [vendorId, setVendorId] = useState<string | null>(workOrder.vendor?.id ?? null)
  const [description, setDescription] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)
  const errors = serverErrors(add.error)

  const submit = async () => {
    const value = Number(amount)
    if (!amount.trim() || !Number.isFinite(value) || value < 0) {
      setLocalError('Enter an amount of 0 or more.')
      return
    }
    setLocalError(null)
    try {
      await add.mutateAsync({ type, amount: value, vendor_id: vendorId, description: description.trim() || null })
      toast.success('Cost added')
      onClose()
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not add the cost', errorMessage(error))
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title={`Add cost to #${workOrder.number}`}
      preventClose={add.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={add.isPending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="add-cost-form" loading={add.isPending}>
            Add cost
          </Button>
        </>
      }
    >
      <form
        id="add-cost-form"
        className={styles.form}
        noValidate
        onSubmit={(event) => {
          event.preventDefault()
          void submit()
        }}
      >
        {generalMessage(add.error) && <InlineAlert tone="danger">{generalMessage(add.error)}</InlineAlert>}
        <FieldRow>
          <FormField label="Type" required error={errors.type}>
            <Select value={type} onChange={(event) => setType(event.target.value)} data-autofocus>
              {COST_TYPES.map((t) => (
                <option key={t} value={t}>
                  {COST_TYPE_LABELS[t]}
                </option>
              ))}
            </Select>
          </FormField>
          <FormField label="Amount (USD)" required error={localError ?? errors.amount}>
            <Input value={amount} onChange={(event) => setAmount(event.target.value)} inputMode="decimal" placeholder="0.00" />
          </FormField>
        </FieldRow>
        <FormField label="Vendor" optionalLabel error={errors.vendor_id}>
          <Combobox options={vendors.options} loading={vendors.isLoading} value={vendorId} onChange={setVendorId} placeholder="No vendor" emptyText="No matching vendors" />
        </FormField>
        <FormField label="Description" optionalLabel error={errors.description}>
          <Input value={description} onChange={(event) => setDescription(event.target.value)} maxLength={400} placeholder="What was bought or paid for" />
        </FormField>
      </form>
    </Dialog>
  )
}
