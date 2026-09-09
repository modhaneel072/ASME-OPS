import { zodResolver } from '@hookform/resolvers/zod'
import { GitBranch, Paperclip, Plus, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Controller, useFieldArray, useForm, useWatch } from 'react-hook-form'
import { ApiError, errorMessage } from '@/api/client'
import { PRIORITIES, PRIORITY_LABELS, WORK_TYPES, WORK_TYPE_LABELS, type Priority } from '@/api/contracts/common'
import { EMPTY_WORK_ORDER_FORM, WorkOrderFormValues, type WorkOrderDetail } from '@/api/contracts/work-orders'
import { useAssetOptions } from '@/api/queries/assets'
import { useCategories } from '@/api/queries/categories'
import { useLocations } from '@/api/queries/locations'
import { useProjectOptions } from '@/api/queries/projects'
import { useTeamOptions } from '@/api/queries/teams'
import { usePeopleOptions } from '@/api/queries/users'
import { useVendorOptions } from '@/api/queries/vendors'
import { useCan } from '@/lib/permissions'
import { AttachmentUploader, Button, Combobox, DateTimeInput, FieldRow, FormField, IconButton, InlineAlert, Input, SegmentedControl, Select, SideSheet, Textarea } from '@/ui'
import { fromWorkOrderDetail, SERVER_FIELD_MAP } from './formModel'
import styles from './work-orders.module.css'

export interface SubmitOptions {
  draft?: boolean
  publish?: boolean
  /** Files queued in the pane; uploaded by the caller after the record exists. */
  files: File[]
}

export interface WorkOrderFormProps {
  open: boolean
  mode: 'create' | 'edit'
  /** Existing work order when editing. */
  initial?: WorkOrderDetail | null
  /** Prefill for the create pane (from search params). */
  prefill?: Partial<WorkOrderFormValues>
  /** Number of the parent when creating a sub-work order. */
  parentNumber?: number | null
  submitting: boolean
  error: unknown
  onSubmit: (values: WorkOrderFormValues, options: SubmitOptions) => Promise<void>
  onClose: () => void
}

const IMAGE_EXT = /\.(png|jpe?g|gif|webp)$/i

/** Mounted only while open so every opening starts from fresh values. */
export function WorkOrderForm(props: WorkOrderFormProps) {
  return props.open ? <WorkOrderFormInner {...props} /> : null
}

function WorkOrderFormInner({ mode, initial, prefill, parentNumber, submitting, error, onSubmit, onClose }: WorkOrderFormProps) {
  const can = useCan()
  const form = useForm<WorkOrderFormValues>({
    resolver: zodResolver(WorkOrderFormValues),
    defaultValues: mode === 'edit' && initial ? fromWorkOrderDetail(initial) : { ...EMPTY_WORK_ORDER_FORM, ...prefill },
  })
  const { register, control, handleSubmit, setError, formState } = form
  const subWorkOrders = useFieldArray({ control, name: 'sub_work_orders' })
  const [queued, setQueued] = useState<File[]>([])
  const [intent, setIntent] = useState<'create' | 'draft' | 'publish' | null>(null)

  useEffect(() => {
    if (error instanceof ApiError && error.isValidation) {
      for (const [field, message] of Object.entries(error.errors)) {
        const name = (SERVER_FIELD_MAP[field] ?? field) as keyof WorkOrderFormValues
        if (name in EMPTY_WORK_ORDER_FORM) setError(name, { type: 'server', message })
        else setError('root.server', { type: 'server', message: `${field}: ${message}` })
      }
    }
  }, [error, setError])

  const projectId = useWatch({ control, name: 'project_id' })
  const locationId = useWatch({ control, name: 'location_id' })
  const categoryIds = useWatch({ control, name: 'category_ids' })
  const priority = useWatch({ control, name: 'priority' })

  const people = usePeopleOptions()
  const projects = useProjectOptions()
  const locations = useLocations({})
  const teams = useTeamOptions()
  const assets = useAssetOptions({ project: projectId ? [projectId] : undefined, location: locationId ? [locationId] : undefined })
  const categories = useCategories({})
  const vendors = useVendorOptions()

  const locationOptions = useMemo(() => (locations.data?.items ?? []).map((l) => ({ value: l.id, label: l.name, meta: l.path.length > 1 ? l.path.slice(0, -1).join(' › ') : undefined })), [locations.data])
  const categoryOptions = useMemo(() => (categories.data?.items ?? []).map((c) => ({ value: c.id, label: c.name })), [categories.data])
  const safetySelected = useMemo(() => {
    const names = new Map((categories.data?.items ?? []).map((c) => [c.id, c.name.trim().toLowerCase()]))
    return categoryIds.some((id) => names.get(id) === 'safety')
  }, [categories.data, categoryIds])
  const allowCritical = can('work_order.cancel') || safetySelected || priority === 'critical'
  const priorityOptions = PRIORITIES.filter((p) => p !== 'critical' || allowCritical).map((p) => ({ value: p, label: PRIORITY_LABELS[p], tone: p === 'critical' ? ('danger' as const) : undefined }))

  const generalError = error && !(error instanceof ApiError && error.isValidation) ? errorMessage(error) : null
  const rootError = formState.errors.root?.server?.message
  const dirty = formState.isDirty || queued.length > 0

  const queue = async (file: File) => {
    setQueued((current) => [...current, file])
  }
  const queuePicture = async (file: File) => {
    if (!IMAGE_EXT.test(file.name)) throw new Error('Choose an image (PNG, JPG, GIF or WebP).')
    setQueued((current) => [...current, file])
  }

  const submitWith = (options: Omit<SubmitOptions, 'files'>, which: 'create' | 'draft' | 'publish') =>
    handleSubmit(async (values) => {
      setIntent(which)
      try {
        await onSubmit(values, { ...options, files: queued })
      } finally {
        setIntent(null)
      }
    })

  const isDraft = mode === 'edit' && initial?.status === 'draft'
  const formId = 'work-order-form'

  return (
    <SideSheet
      open
      onClose={onClose}
      title={mode === 'create' ? (parentNumber ? `New sub-work order of #${parentNumber}` : 'New Work Order') : `Edit #${initial?.number ?? ''}`}
      subtitle={mode === 'create' ? 'Work orders track what needs doing across the chapter.' : undefined}
      onRequestClose={() => (dirty && !submitting ? window.confirm('Discard your changes?') : true)}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          {mode === 'create' && (
            <Button variant="secondary" onClick={() => void submitWith({ draft: true }, 'draft')()} loading={submitting && intent === 'draft'} disabled={submitting && intent !== 'draft'}>
              Save as draft
            </Button>
          )}
          {isDraft && (
            <Button variant="secondary" onClick={() => void submitWith({ publish: true }, 'publish')()} loading={submitting && intent === 'publish'} disabled={submitting && intent !== 'publish'}>
              Publish
            </Button>
          )}
          <Button variant="primary" type="submit" form={formId} loading={submitting && (intent === 'create' || intent === null)} disabled={submitting && intent !== null && intent !== 'create'}>
            {mode === 'create' ? 'Create' : 'Save changes'}
          </Button>
        </>
      }
    >
      <form id={formId} noValidate onSubmit={(event) => void submitWith({}, 'create')(event)} className={styles.form}>
        {(generalError || rootError) && (
          <InlineAlert tone="danger" title={generalError ? 'Could not save the work order' : 'Please check the form'}>
            {generalError ?? rootError}
          </InlineAlert>
        )}

        <FormField label="Title" required error={formState.errors.title?.message}>
          <Input {...register('title')} data-autofocus placeholder="What needs to be done?" maxLength={240} />
        </FormField>

        <FormField label="Add pictures" optionalLabel hint="Pictures are uploaded as soon as the work order is created." asGroup>
          <AttachmentUploader compact onUpload={queuePicture} />
        </FormField>

        <FormField label="Description" optionalLabel error={formState.errors.description?.message}>
          <Textarea {...register('description')} rows={5} placeholder="Steps, symptoms, safety notes, links to CAD or documentation." />
        </FormField>

        {mode === 'create' && (
          <FormField label="Sub-work orders" optionalLabel hint="Each line becomes its own work order under this one after it is created." asGroup>
            <div className={styles.form}>
              {subWorkOrders.fields.map((field, index) => (
                <div key={field.id} className={styles.subRow}>
                  <Input {...register(`sub_work_orders.${index}.title` as const)} placeholder={`Sub-work order ${index + 1}`} aria-label={`Sub-work order ${index + 1} title`} maxLength={240} />
                  <IconButton label={`Remove sub-work order ${index + 1}`} variant="ghost" onClick={() => subWorkOrders.remove(index)}>
                    <X size={16} />
                  </IconButton>
                </div>
              ))}
              <div>
                <Button size="sm" variant="ghost" leadingIcon={<Plus size={14} />} onClick={() => subWorkOrders.append({ title: '' })}>
                  Add sub-work order
                </Button>
              </div>
            </div>
          </FormField>
        )}

        <FieldRow>
          <FormField label="Project" optionalLabel error={formState.errors.project_id?.message}>
            <Controller control={control} name="project_id" render={({ field }) => <Combobox options={projects.options} loading={projects.isLoading} value={field.value} onChange={field.onChange} placeholder="No project" emptyText="No matching projects" />} />
          </FormField>
          <FormField label="Location" optionalLabel error={formState.errors.location_id?.message}>
            <Controller control={control} name="location_id" render={({ field }) => <Combobox options={locationOptions} loading={locations.isPending} value={field.value} onChange={field.onChange} placeholder="Anywhere" emptyText="No matching locations" />} />
          </FormField>
        </FieldRow>

        <FormField label="Asset" optionalLabel error={formState.errors.primary_asset_id?.message} hint={projectId || locationId ? 'Showing assets in the selected project or location.' : undefined}>
          <Controller control={control} name="primary_asset_id" render={({ field }) => <Combobox options={assets.options} loading={assets.isLoading} value={field.value} onChange={field.onChange} placeholder="No asset" emptyText="No matching assets" />} />
        </FormField>

        <FieldRow>
          <FormField label="Assignees" optionalLabel error={formState.errors.assignee_user_ids?.message}>
            <Controller control={control} name="assignee_user_ids" render={({ field }) => <Combobox<number> multiple options={people.options} loading={people.isLoading} value={field.value} onChange={field.onChange} placeholder="Add people" emptyText="No matching members" />} />
          </FormField>
          <FormField label="Team" optionalLabel error={formState.errors.team_id?.message}>
            <Controller control={control} name="team_id" render={({ field }) => <Combobox options={teams.options} loading={teams.isLoading} value={field.value} onChange={field.onChange} placeholder="No team" emptyText="No matching teams" />} />
          </FormField>
        </FieldRow>

        <FormField label="Estimated duration" optionalLabel error={formState.errors.estimated_hours?.message ?? formState.errors.estimated_minutes?.message} asGroup>
          <div className={styles.duration}>
            <div className={styles.durationInput}>
              <Input {...register('estimated_hours')} inputMode="numeric" placeholder="0" aria-label="Estimated hours" />
              <span className={styles.durationUnit}>hours</span>
            </div>
            <div className={styles.durationInput}>
              <Input {...register('estimated_minutes')} inputMode="numeric" placeholder="0" aria-label="Estimated minutes" />
              <span className={styles.durationUnit}>minutes</span>
            </div>
          </div>
        </FormField>

        <FieldRow>
          <FormField label="Due date" optionalLabel error={formState.errors.due_at?.message}>
            <DateTimeInput {...register('due_at')} />
          </FormField>
          <FormField label="Start date" optionalLabel error={formState.errors.start_at?.message}>
            <DateTimeInput {...register('start_at')} />
          </FormField>
        </FieldRow>

        <FormField label="Work type" error={formState.errors.work_type?.message}>
          <Select {...register('work_type')}>
            {WORK_TYPES.map((t) => (
              <option key={t} value={t}>
                {WORK_TYPE_LABELS[t]}
              </option>
            ))}
          </Select>
        </FormField>

        <FormField label="Priority" error={formState.errors.priority?.message} hint={allowCritical ? undefined : 'Critical priority is available for Safety work or to leads and officers.'} asGroup>
          <Controller control={control} name="priority" render={({ field }) => <SegmentedControl<Priority> label="Priority" value={field.value} onChange={field.onChange} options={priorityOptions} />} />
        </FormField>

        <FormField label="Files" optionalLabel hint="Drawings, G-code, spreadsheets or PDFs; uploaded right after the work order is created." asGroup>
          <AttachmentUploader compact onUpload={queue} />
          {queued.length > 0 && (
            <ul className={styles.queue} aria-label="Files to upload">
              {queued.map((file, index) => (
                <li key={`${file.name}-${index}`} className={styles.queueItem}>
                  <Paperclip size={14} aria-hidden="true" />
                  <span className={styles.queueName}>{file.name}</span>
                  <IconButton size="sm" variant="ghost" label={`Remove ${file.name}`} onClick={() => setQueued((current) => current.filter((_, i) => i !== index))}>
                    <X size={14} />
                  </IconButton>
                </li>
              ))}
            </ul>
          )}
        </FormField>

        <FormField label="Categories" optionalLabel error={formState.errors.category_ids?.message}>
          <Controller control={control} name="category_ids" render={({ field }) => <Combobox multiple options={categoryOptions} loading={categories.isPending} value={field.value} onChange={field.onChange} placeholder="Add categories" emptyText="No matching categories" />} />
        </FormField>

        <FieldRow>
          <FormField label="Vendor" optionalLabel error={formState.errors.vendor_id?.message}>
            <Controller control={control} name="vendor_id" render={({ field }) => <Combobox options={vendors.options} loading={vendors.isLoading} value={field.value} onChange={field.onChange} placeholder="No vendor" emptyText="No matching vendors" />} />
          </FormField>
          <FormField label="Budget code" optionalLabel error={formState.errors.budget_code?.message}>
            <Input {...register('budget_code')} placeholder="e.g. ROVER-2026" maxLength={60} />
          </FormField>
        </FieldRow>

        <FormField label="Watchers" optionalLabel error={formState.errors.watcher_user_ids?.message} hint="Watchers are notified about status changes and comments.">
          <Controller control={control} name="watcher_user_ids" render={({ field }) => <Combobox<number> multiple options={people.options} loading={people.isLoading} value={field.value} onChange={field.onChange} placeholder="Add watchers" emptyText="No matching members" />} />
        </FormField>

        {(parentNumber || initial?.parent_number) && (
          <FormField label="Parent" error={formState.errors.parent_id?.message} asGroup>
            <span className={styles.parentChip}>
              <GitBranch size={14} aria-hidden="true" />
              Sub-work order of #{parentNumber ?? initial?.parent_number}
            </span>
          </FormField>
        )}
      </form>
    </SideSheet>
  )
}
