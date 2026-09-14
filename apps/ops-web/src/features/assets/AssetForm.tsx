import { zodResolver } from '@hookform/resolvers/zod'
import { Plus } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { ApiError, errorMessage } from '@/api/client'
import {
  ASSET_CRITICALITIES,
  ASSET_CRITICALITY_LABELS,
  ASSET_STATUSES,
  ASSET_STATUS_LABELS,
  AssetInput,
  toAssetPayload,
  type Asset,
  type AssetPayload,
} from '@/api/contracts/assets'
import { useAssetParentOptions, useAssetTypeOptions } from '@/api/queries/assets'
import { useLocations } from '@/api/queries/locations'
import { useProjectOptions } from '@/api/queries/projects'
import { useTeamOptions } from '@/api/queries/teams'
import { usePeopleOptions } from '@/api/queries/users'
import { Button, Combobox, DateInput, FieldRow, FormField, FormSection, InlineAlert, Input, SegmentedControl, Select, SideSheet, Textarea } from '@/ui'
import styles from './assets.module.css'
import { AssetTypeDialog } from './AssetTypeDialog'

export interface AssetFormProps {
  open: boolean
  mode: 'create' | 'edit'
  /** Existing asset when editing; when creating, may carry a preselected parent (and its project/location). */
  initial?: Partial<Asset> | null
  canManageTypes: boolean
  submitting: boolean
  error: unknown
  onSubmit: (payload: AssetPayload) => Promise<void>
  onClose: () => void
}

const EMPTY: AssetInput = {
  name: '',
  code: '',
  description: '',
  type_ids: [],
  parent_id: null,
  project_id: null,
  location_id: null,
  responsible_team_id: null,
  owner_user_id: null,
  manufacturer: '',
  model: '',
  serial_number: '',
  purchase_date: '',
  purchase_cost: '',
  warranty_end: '',
  criticality: 'none',
  status: 'online',
}

function fromAsset(asset: Partial<Asset>): AssetInput {
  return {
    name: asset.name ?? '',
    code: asset.code ?? '',
    description: asset.description ?? '',
    type_ids: (asset.types ?? []).map((t) => t.id),
    parent_id: asset.parent_id ?? null,
    project_id: asset.project?.id ?? null,
    location_id: asset.location?.id ?? null,
    responsible_team_id: asset.team?.id ?? null,
    owner_user_id: asset.owner?.id ?? null,
    manufacturer: asset.manufacturer ?? '',
    model: asset.model ?? '',
    serial_number: asset.serial_number ?? '',
    purchase_date: asset.purchase_date ?? '',
    purchase_cost: asset.purchase_cost === null || asset.purchase_cost === undefined ? '' : String(asset.purchase_cost),
    warranty_end: asset.warranty_end ?? '',
    criticality: (asset.criticality as AssetInput['criticality']) ?? 'none',
    status: (asset.status as AssetInput['status']) ?? 'online',
  }
}

export function AssetForm({ open, mode, initial, canManageTypes, submitting, error, onSubmit, onClose }: AssetFormProps) {
  const form = useForm<AssetInput>({ resolver: zodResolver(AssetInput), defaultValues: EMPTY })
  const { register, control, handleSubmit, reset, setError, getValues, setValue, formState } = form
  const [typeDialog, setTypeDialog] = useState(false)

  const types = useAssetTypeOptions()
  const parents = useAssetParentOptions(mode === 'edit' ? initial?.id : undefined)
  const projects = useProjectOptions()
  const teams = useTeamOptions()
  const people = usePeopleOptions()
  const locations = useLocations({ limit: 200 })
  const locationOptions = useMemo(
    () => (locations.data?.items ?? []).map((location) => ({ value: location.id, label: location.name, meta: location.path.length > 1 ? location.path.slice(0, -1).join(' › ') : location.is_default ? 'Default' : undefined })),
    [locations.data],
  )
  const defaultLocationId = useMemo(() => locations.data?.items.find((location) => location.is_default)?.id ?? null, [locations.data])

  // Populate on open. In create mode a parent may be preselected (sub-asset); the
  // default location is applied once the location list is known.
  useEffect(() => {
    if (!open) return
    if (mode === 'edit' && initial) reset(fromAsset(initial))
    else
      reset({
        ...EMPTY,
        parent_id: initial?.parent_id ?? null,
        project_id: initial?.project?.id ?? null,
        location_id: initial?.location?.id ?? defaultLocationId,
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, mode, initial, reset])

  useEffect(() => {
    if (!open || mode !== 'create' || !defaultLocationId) return
    if (!getValues('location_id') && !formState.dirtyFields.location_id) setValue('location_id', defaultLocationId)
  }, [open, mode, defaultLocationId, getValues, setValue, formState.dirtyFields.location_id])

  // Map server-side field errors (validation map, or a single `field` such as asset_cycle) onto the form.
  useEffect(() => {
    if (!(error instanceof ApiError)) return
    if (error.isValidation) {
      for (const [field, message] of Object.entries(error.errors)) setError(field as keyof AssetInput, { type: 'server', message })
    } else if (typeof error.extra.field === 'string' && error.extra.field in EMPTY) {
      setError(error.extra.field as keyof AssetInput, { type: 'server', message: error.message })
    }
  }, [error, setError])

  const generalError = error && !(error instanceof ApiError && (error.isValidation || typeof error.extra.field === 'string')) ? errorMessage(error) : null
  const dirty = formState.isDirty

  return (
    <SideSheet
      open={open}
      onClose={onClose}
      title={mode === 'create' ? (initial?.parent_id ? 'New sub-asset' : 'New Asset') : `Edit ${initial?.name ?? 'asset'}`}
      subtitle={mode === 'create' ? 'Equipment, vehicles, tools and their sub-assemblies.' : undefined}
      onRequestClose={() => (dirty && !submitting ? window.confirm('Discard your changes?') : true)}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="asset-form" loading={submitting}>
            {mode === 'create' ? 'Create Asset' : 'Save changes'}
          </Button>
        </>
      }
    >
      <form id="asset-form" noValidate className={styles.form} onSubmit={handleSubmit((values) => onSubmit(toAssetPayload(values, mode)))}>
        {generalError && <InlineAlert tone="danger">{generalError}</InlineAlert>}

        <FormField label="Name" required error={formState.errors.name?.message}>
          <Input {...register('name')} data-autofocus placeholder="e.g. 3D Printer 01" maxLength={200} />
        </FormField>
        <FieldRow>
          <FormField label="Code" optionalLabel error={formState.errors.code?.message} hint="Short unique tag, e.g. PRN-01.">
            <Input {...register('code')} placeholder="PRN-01" maxLength={60} className="mono" />
          </FormField>
          <FormField label="Criticality" asGroup error={formState.errors.criticality?.message}>
            <Controller
              control={control}
              name="criticality"
              render={({ field }) => (
                <SegmentedControl label="Criticality" value={field.value} onChange={field.onChange} options={ASSET_CRITICALITIES.map((value) => ({ value, label: ASSET_CRITICALITY_LABELS[value], tone: value === 'high' ? ('danger' as const) : undefined }))} />
              )}
            />
          </FormField>
        </FieldRow>
        <FormField label="Description" optionalLabel error={formState.errors.description?.message}>
          <Textarea {...register('description')} rows={3} placeholder="What it is, where it lives, anything a new member should know." />
        </FormField>
        <FormField
          label="Types"
          optionalLabel
          error={formState.errors.type_ids?.message}
          hint={
            canManageTypes ? (
              <span className={styles.inlineActions}>
                <span>Group similar equipment.</span>
                <Button variant="link" size="sm" leadingIcon={<Plus size={14} />} onClick={() => setTypeDialog(true)}>
                  Create type
                </Button>
              </span>
            ) : (
              'Group similar equipment.'
            )
          }
        >
          <Controller control={control} name="type_ids" render={({ field }) => <Combobox multiple options={types.options} loading={types.isLoading} value={field.value} onChange={field.onChange} placeholder="Add types" emptyText="No asset types yet" />} />
        </FormField>
        {mode === 'create' && (
          <FormField label="Initial status" error={formState.errors.status?.message} hint="Change it later from the asset page; every change is recorded.">
            <Select {...register('status')}>
              {ASSET_STATUSES.map((value) => (
                <option key={value} value={value}>
                  {ASSET_STATUS_LABELS[value]}
                </option>
              ))}
            </Select>
          </FormField>
        )}

        <FormSection title="Where it belongs">
          <FormField label="Parent asset" optionalLabel error={formState.errors.parent_id?.message} hint="Nest sub-assemblies under the machine they belong to.">
            <Controller control={control} name="parent_id" render={({ field }) => <Combobox options={parents.options} loading={parents.isLoading} value={field.value} onChange={field.onChange} placeholder="No parent (top level)" emptyText="No matching assets" />} />
          </FormField>
          <FieldRow>
            <FormField label="Project" optionalLabel error={formState.errors.project_id?.message}>
              <Controller control={control} name="project_id" render={({ field }) => <Combobox options={projects.options} loading={projects.isLoading} value={field.value} onChange={field.onChange} placeholder="Chapter-wide" emptyText="No matching projects" />} />
            </FormField>
            <FormField label="Location" optionalLabel error={formState.errors.location_id?.message}>
              <Controller control={control} name="location_id" render={({ field }) => <Combobox options={locationOptions} loading={locations.isPending} value={field.value} onChange={field.onChange} placeholder="Choose a location" emptyText="No matching locations" />} />
            </FormField>
          </FieldRow>
          <FieldRow>
            <FormField label="Responsible team" optionalLabel error={formState.errors.responsible_team_id?.message}>
              <Controller control={control} name="responsible_team_id" render={({ field }) => <Combobox options={teams.options} loading={teams.isLoading} value={field.value} onChange={field.onChange} placeholder="No team" emptyText="No matching teams" />} />
            </FormField>
            <FormField label="Owner" optionalLabel error={formState.errors.owner_user_id?.message}>
              <Controller control={control} name="owner_user_id" render={({ field }) => <Combobox<number> options={people.options} loading={people.isLoading} value={field.value} onChange={field.onChange} placeholder="No owner" emptyText="No matching members" />} />
            </FormField>
          </FieldRow>
        </FormSection>

        <FormSection title="Make and purchase">
          <FieldRow>
            <FormField label="Manufacturer" optionalLabel error={formState.errors.manufacturer?.message}>
              <Input {...register('manufacturer')} placeholder="Prusa" maxLength={160} />
            </FormField>
            <FormField label="Model" optionalLabel error={formState.errors.model?.message}>
              <Input {...register('model')} placeholder="MK4" maxLength={160} />
            </FormField>
          </FieldRow>
          <FormField label="Serial number" optionalLabel error={formState.errors.serial_number?.message}>
            <Input {...register('serial_number')} placeholder="SN-123" maxLength={160} className="mono" />
          </FormField>
          <FieldRow>
            <FormField label="Purchase date" optionalLabel error={formState.errors.purchase_date?.message}>
              <DateInput {...register('purchase_date')} />
            </FormField>
            <FormField label="Purchase cost" optionalLabel error={formState.errors.purchase_cost?.message} hint="USD">
              <Input {...register('purchase_cost')} inputMode="decimal" placeholder="0.00" />
            </FormField>
          </FieldRow>
          <FormField label="Warranty end" optionalLabel error={formState.errors.warranty_end?.message}>
            <DateInput {...register('warranty_end')} />
          </FormField>
        </FormSection>
      </form>

      <AssetTypeDialog
        open={typeDialog}
        onClose={() => setTypeDialog(false)}
        onCreated={(type) => {
          const current = getValues('type_ids')
          if (!current.includes(type.id)) setValue('type_ids', [...current, type.id], { shouldDirty: true })
        }}
      />
    </SideSheet>
  )
}
