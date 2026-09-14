import { Plus } from 'lucide-react'
import { useMemo } from 'react'
import { PRIORITIES, PRIORITY_LABELS, STATUS_LABELS, WORK_ORDER_STATUSES, WORK_TYPES, WORK_TYPE_LABELS } from '@/api/contracts/common'
import { DUE_FILTER_OPTIONS, type WorkOrderFilterName, type WorkOrderFilters } from '@/api/contracts/work-orders'
import { useAssetOptions } from '@/api/queries/assets'
import { useCategories } from '@/api/queries/categories'
import { useLocations } from '@/api/queries/locations'
import { useProjectOptions } from '@/api/queries/projects'
import { useTeamOptions } from '@/api/queries/teams'
import { usePeopleOptions } from '@/api/queries/users'
import { useVendorOptions } from '@/api/queries/vendors'
import { Button, DropdownMenu, FilterChip, type FilterOption } from '@/ui'

export const HIDDEN_FILTERS: Array<{ name: WorkOrderFilterName; label: string }> = [
  { name: 'vendor', label: 'Vendor' },
  { name: 'created_by', label: 'Created by' },
  { name: 'parent', label: 'Parent' },
]

export interface WorkOrderFiltersProps {
  filters: WorkOrderFilters
  onChange: (name: WorkOrderFilterName, values: string[]) => void
  /** Hidden chips the user revealed through "Add Filter". */
  revealed: ReadonlySet<string>
  onReveal: (name: WorkOrderFilterName) => void
  /** Rendered after the chips (e.g. the My Filters button). */
  trailing?: React.ReactNode
}

export function WorkOrderFilterChips({ filters, onChange, revealed, onReveal, trailing }: WorkOrderFiltersProps) {
  const people = usePeopleOptions()
  const projects = useProjectOptions()
  const locations = useLocations({})
  const teams = useTeamOptions()
  const assets = useAssetOptions()
  const categories = useCategories({})
  const vendors = useVendorOptions()

  const peopleOptions = useMemo<FilterOption[]>(() => people.options.map((o) => ({ value: String(o.value), label: o.label, description: o.meta })), [people.options])
  const assigneeOptions = useMemo<FilterOption[]>(() => [{ value: 'me', label: 'Me' }, ...peopleOptions], [peopleOptions])
  const projectOptions = useMemo<FilterOption[]>(() => projects.options.map((o) => ({ value: o.value, label: o.label })), [projects.options])
  const locationOptions = useMemo<FilterOption[]>(() => (locations.data?.items ?? []).map((l) => ({ value: l.id, label: l.path.length > 1 ? l.path.join(' › ') : l.name })), [locations.data])
  const teamOptions = useMemo<FilterOption[]>(() => teams.options.map((o) => ({ value: o.value, label: o.label })), [teams.options])
  const assetOptions = useMemo<FilterOption[]>(() => assets.options.map((o) => ({ value: o.value, label: o.label })), [assets.options])
  const categoryOptions = useMemo<FilterOption[]>(() => (categories.data?.items ?? []).map((c) => ({ value: c.id, label: c.name, color: c.color })), [categories.data])
  const vendorOptions = useMemo<FilterOption[]>(() => vendors.options.map((o) => ({ value: o.value, label: o.label })), [vendors.options])
  const priorityOptions = useMemo<FilterOption[]>(() => PRIORITIES.map((p) => ({ value: p, label: PRIORITY_LABELS[p] })), [])
  const workTypeOptions = useMemo<FilterOption[]>(() => WORK_TYPES.map((t) => ({ value: t, label: WORK_TYPE_LABELS[t] })), [])
  const statusOptions = useMemo<FilterOption[]>(() => WORK_ORDER_STATUSES.map((s) => ({ value: s, label: STATUS_LABELS[s] ?? s })), [])

  const value = (name: WorkOrderFilterName) => filters[name] ?? []
  const shown = (name: WorkOrderFilterName) => revealed.has(name) || value(name).length > 0
  const addable = HIDDEN_FILTERS.filter((f) => !shown(f.name))

  return (
    <>
      <FilterChip label="Assigned To" options={assigneeOptions} value={value('assignee')} onChange={(v) => onChange('assignee', v)} searchable loading={people.isLoading} />
      <FilterChip label="Due Date" options={DUE_FILTER_OPTIONS} value={value('due')} onChange={(v) => onChange('due', v)} multiple={false} />
      <FilterChip label="Project" options={projectOptions} value={value('project')} onChange={(v) => onChange('project', v)} searchable loading={projects.isLoading} />
      <FilterChip label="Location" options={locationOptions} value={value('location')} onChange={(v) => onChange('location', v)} searchable loading={locations.isPending} />
      <FilterChip label="Priority" options={priorityOptions} value={value('priority')} onChange={(v) => onChange('priority', v)} />
      <FilterChip label="Team" options={teamOptions} value={value('team')} onChange={(v) => onChange('team', v)} searchable loading={teams.isLoading} />
      <FilterChip label="Asset" options={assetOptions} value={value('asset')} onChange={(v) => onChange('asset', v)} searchable loading={assets.isLoading} />
      <FilterChip label="Work Type" options={workTypeOptions} value={value('work_type')} onChange={(v) => onChange('work_type', v)} />
      <FilterChip label="Status" options={statusOptions} value={value('status')} onChange={(v) => onChange('status', v)} />
      <FilterChip label="Category" options={categoryOptions} value={value('category')} onChange={(v) => onChange('category', v)} searchable loading={categories.isPending} />
      {shown('vendor') && <FilterChip label="Vendor" options={vendorOptions} value={value('vendor')} onChange={(v) => onChange('vendor', v)} searchable loading={vendors.isLoading} />}
      {shown('created_by') && <FilterChip label="Created by" options={assigneeOptions} value={value('created_by')} onChange={(v) => onChange('created_by', v)} searchable loading={people.isLoading} />}
      {shown('parent') && <FilterChip label="Parent" options={[{ value: 'none', label: 'Top-level only (no parent)' }]} value={value('parent')} onChange={(v) => onChange('parent', v)} multiple={false} />}
      {addable.length > 0 && (
        <DropdownMenu
          label="Add filter"
          items={addable.map((f) => ({ key: f.name, label: f.label, onSelect: () => onReveal(f.name) }))}
          trigger={(props) => (
            <Button {...props} ref={props.ref} size="sm" variant="ghost" leadingIcon={<Plus size={14} />}>
              Add Filter
            </Button>
          )}
        />
      )}
      {trailing}
    </>
  )
}
