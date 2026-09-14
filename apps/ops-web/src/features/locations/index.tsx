import { Building2, ChevronRight, MapPin, MoreHorizontal, Pencil, Plus, Star, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ApiError, errorMessage } from '@/api/client'
import type { Location, LocationInput } from '@/api/contracts/locations'
import { useCreateLocation, useDeleteLocation, useLocation, useLocations, useMakeDefaultLocation, useUpdateLocation } from '@/api/queries/locations'
import { formatDateTime } from '@/lib/dates'
import { useCan } from '@/lib/permissions'
import {
  Badge,
  Button,
  Card,
  DetailPanel,
  Dialog,
  DropdownMenu,
  EmptyState,
  FieldList,
  IconButton,
  InlineAlert,
  ListRow,
  ListToolbarSpacer,
  MasterDetailLayout,
  Page,
  PageHeader,
  SearchField,
  SkeletonBlock,
  SkeletonRows,
  SplitButton,
  Stack,
  ViewSelector,
  useToast,
} from '@/ui'
import { LocationForm } from './LocationForm'

type Sort = 'name' | '-name' | '-created_at'

function useTypingGuard() {
  return (event: KeyboardEvent) => {
    const target = event.target as HTMLElement | null
    return Boolean(target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable))
  }
}

export default function LocationsPage() {
  const { locationId } = useParams<{ locationId: string }>()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()
  const can = useCan()
  const canManage = can('location.manage')

  const [query, setQuery] = useState(params.get('q') ?? '')
  const [debounced, setDebounced] = useState(query)
  const [sort, setSort] = useState<Sort>('name')
  const searchRef = useRef<HTMLInputElement>(null)

  const list = useLocations({ q: debounced || undefined, sort })
  const selected = useLocation(locationId)
  const allLocations = useMemo(() => list.data?.items ?? [], [list.data])

  const pane = params.get('pane') // 'new' | 'edit' | null
  const paneParent = params.get('parent')
  const paneOpen = pane === 'new' || (pane === 'edit' && Boolean(selected.data))

  const create = useCreateLocation()
  const update = useUpdateLocation(locationId ?? '')
  const remove = useDeleteLocation()
  const makeDefault = useMakeDefaultLocation()
  const [confirmDelete, setConfirmDelete] = useState(false)

  const openPane = (mode: 'new' | 'edit', parent?: string) => {
    const next = new URLSearchParams(params)
    next.set('pane', mode)
    if (parent) next.set('parent', parent)
    else next.delete('parent')
    setParams(next)
  }
  const closePane = () => {
    const next = new URLSearchParams(params)
    next.delete('pane')
    next.delete('parent')
    setParams(next)
    create.reset()
    update.reset()
  }

  const isTyping = useTypingGuard()
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event) || event.metaKey || event.ctrlKey || event.altKey) return
      if (event.key === '/') {
        event.preventDefault()
        searchRef.current?.focus()
      } else if (event.key === 'n' && canManage && !paneOpen) {
        event.preventDefault()
        openPane('new')
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canManage, paneOpen, params])

  const submitForm = async (values: LocationInput) => {
    try {
      if (pane === 'edit' && locationId) {
        await update.mutateAsync(values)
        toast.success('Location updated')
        closePane()
      } else {
        const created = await create.mutateAsync(values)
        toast.success('Location created', created.name)
        closePane()
        navigate(`/locations/${created.id}`)
      }
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not save location', errorMessage(error))
    }
  }

  const onDelete = async () => {
    if (!locationId) return
    try {
      await remove.mutateAsync(locationId)
      toast.success('Location deleted')
      setConfirmDelete(false)
      navigate('/locations')
    } catch (error) {
      setConfirmDelete(false)
      toast.error('Could not delete location', errorMessage(error))
    }
  }

  const onMakeDefault = async () => {
    if (!locationId) return
    try {
      await makeDefault.mutateAsync(locationId)
      toast.success('Default location updated')
    } catch (error) {
      toast.error('Could not change the default location', errorMessage(error))
    }
  }

  const children = useMemo(() => allLocations.filter((l) => l.parent_id === locationId), [allLocations, locationId])

  const listContent = list.isPending ? (
    <SkeletonRows rows={8} />
  ) : list.isError ? (
    <div style={{ padding: 'var(--space-4)' }}>
      <InlineAlert
        tone="danger"
        title="Locations could not be loaded"
        actions={
          <Button size="sm" onClick={() => void list.refetch()}>
            Retry
          </Button>
        }
      >
        {errorMessage(list.error)}
      </InlineAlert>
    </div>
  ) : allLocations.length === 0 && debounced ? (
    <EmptyState compact illustration="search" title="No locations match" description={`Nothing matches “${debounced}”.`} action={<Button size="sm" onClick={() => setQuery('')}>Clear search</Button>} />
  ) : allLocations.length === 0 ? (
    <EmptyState
      compact
      illustration="pin"
      title="No locations yet"
      description="Add the rooms, benches and storage areas where your chapter keeps equipment."
      action={canManage ? <Button variant="primary" size="sm" leadingIcon={<Plus size={16} />} onClick={() => openPane('new')}>Add the first location</Button> : undefined}
    />
  ) : (
    <ul aria-label="Locations">
      {allLocations.map((location) => (
        <li key={location.id}>
          <ListRow
            to={`/locations/${location.id}${params.toString() ? `?${params.toString()}` : ''}`}
            selected={location.id === locationId}
            leading={<MapPin size={16} style={{ color: 'var(--color-text-muted)' }} aria-hidden="true" />}
            title={
              <>
                {location.name}
                {location.is_default && (
                  <Badge tone="gold" size="sm" className="mono" title="Default location">
                    Default
                  </Badge>
                )}
              </>
            }
            meta={
              <>
                {location.path.length > 1 && <span>{location.path.slice(0, -1).join(' › ')}</span>}
                <span>{location.asset_count} assets</span>
                <span>{location.open_work_order_count} open work</span>
              </>
            }
            trailing={<ChevronRight size={16} style={{ color: 'var(--color-text-disabled)' }} aria-hidden="true" />}
            data-testid="location-row"
          />
        </li>
      ))}
    </ul>
  )

  const detail = !locationId ? (
    <EmptyState illustration="pin" title="Select a location" description="Choose a location on the left to see its details, sub-locations and activity." />
  ) : selected.isPending ? (
    <div style={{ padding: 'var(--space-6)' }}>
      <SkeletonBlock lines={5} />
    </div>
  ) : selected.isError ? (
    <div style={{ padding: 'var(--space-6)' }}>
      {selected.error instanceof ApiError && selected.error.isNotFound ? (
        <EmptyState illustration="search" title="Location not found" description="It may have been deleted or the link is out of date." action={<Button onClick={() => navigate('/locations')}>Back to locations</Button>} />
      ) : (
        <InlineAlert
          tone="danger"
          title="Could not load this location"
          actions={
            <Button size="sm" onClick={() => void selected.refetch()}>
              Retry
            </Button>
          }
        >
          {errorMessage(selected.error)}
        </InlineAlert>
      )}
    </div>
  ) : (
    <LocationDetail
      location={selected.data}
      childLocations={children}
      canManage={canManage}
      onEdit={() => openPane('edit')}
      onAddChild={() => openPane('new', selected.data.id)}
      onMakeDefault={onMakeDefault}
      onDelete={() => setConfirmDelete(true)}
      busy={makeDefault.isPending}
    />
  )

  return (
    <Page>
      <PageHeader
        title="Locations"
        viewSelector={
          <ViewSelector<Sort>
            label="Sort"
            value={sort}
            onChange={setSort}
            options={[
              { value: 'name', label: 'Name A–Z' },
              { value: '-name', label: 'Name Z–A' },
              { value: '-created_at', label: 'Newest first' },
            ]}
          />
        }
        actions={
          <>
            <SearchField ref={searchRef} value={query} onChange={setQuery} onDebouncedChange={setDebounced} placeholder="Search locations" shortcutHint="/" />
            {canManage && (
              <SplitButton
                label="New Location"
                leadingIcon={<Plus size={16} />}
                onClick={() => openPane('new')}
                items={[
                  { key: 'child', label: 'New sub-location of selected', disabled: !locationId, onSelect: () => openPane('new', locationId) },
                  { key: 'sep', type: 'separator' },
                  { key: 'assets', label: 'Go to Assets', onSelect: () => navigate('/assets') },
                ]}
              />
            )}
          </>
        }
      />
      <MasterDetailLayout
        detailOpen={Boolean(locationId)}
        backTo="/locations"
        listToolbar={
          <>
            <span>{list.data ? `${list.data.total ?? allLocations.length} locations` : ''}</span>
            <ListToolbarSpacer />
            {list.isFetching && !list.isPending && <span aria-live="polite">Updating…</span>}
          </>
        }
        list={listContent}
        detail={
          <>
            {detail}
            <LocationForm
              open={paneOpen}
              mode={pane === 'edit' ? 'edit' : 'create'}
              initial={pane === 'edit' ? selected.data : paneParent ? { parent_id: paneParent } : null}
              locations={allLocations}
              submitting={create.isPending || update.isPending}
              error={pane === 'edit' ? update.error : create.error}
              onSubmit={submitForm}
              onClose={closePane}
            />
          </>
        }
      />
      <Dialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        size="sm"
        title="Delete this location?"
        description="Locations with assets, work orders or sub-locations cannot be deleted; move them first."
        preventClose={remove.isPending}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmDelete(false)} disabled={remove.isPending}>
              Cancel
            </Button>
            <Button variant="danger" onClick={() => void onDelete()} loading={remove.isPending} data-autofocus>
              Delete
            </Button>
          </>
        }
      />
    </Page>
  )
}

function LocationDetail({
  location,
  childLocations,
  canManage,
  onEdit,
  onAddChild,
  onMakeDefault,
  onDelete,
  busy,
}: {
  location: Location
  childLocations: Location[]
  canManage: boolean
  onEdit: () => void
  onAddChild: () => void
  onMakeDefault: () => void
  onDelete: () => void
  busy: boolean
}) {
  const navigate = useNavigate()
  return (
    <DetailPanel
      eyebrow={
        <>
          <MapPin size={12} aria-hidden="true" />
          {location.path.length > 1 ? location.path.slice(0, -1).join(' › ') : 'Top-level location'}
        </>
      }
      title={
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
          {location.name}
          {location.is_default && <Badge tone="gold">Default</Badge>}
        </span>
      }
      subtitle={location.description || undefined}
      actions={
        canManage ? (
          <>
            <Button leadingIcon={<Pencil size={16} />} onClick={onEdit}>
              Edit
            </Button>
            <DropdownMenu
              align="end"
              label="More actions"
              items={[
                { key: 'child', label: 'Add sub-location', icon: <Plus size={16} />, onSelect: onAddChild },
                { key: 'default', label: 'Make default location', icon: <Star size={16} />, onSelect: onMakeDefault, disabled: location.is_default || busy },
                { key: 'sep', type: 'separator' },
                { key: 'delete', label: 'Delete location', icon: <Trash2 size={16} />, destructive: true, disabled: location.is_default, onSelect: onDelete },
              ]}
              trigger={(props) => (
                <IconButton {...props} ref={props.ref} label="More actions">
                  <MoreHorizontal size={18} />
                </IconButton>
              )}
            />
          </>
        ) : undefined
      }
    >
      <Stack>
        <Card title="Details">
          <FieldList
            items={[
              { label: 'Building', value: location.building || '—' },
              { label: 'Room', value: location.room || '—' },
              { label: 'Assets here', value: <Button variant="link" onClick={() => navigate(`/assets?filter[location]=${location.id}`)}>{location.asset_count} assets</Button> },
              { label: 'Open work', value: <Button variant="link" onClick={() => navigate(`/work-orders?filter[location]=${location.id}`)}>{location.open_work_order_count} work orders</Button> },
              { label: 'Created', value: formatDateTime(location.created_at) },
              { label: 'Updated', value: formatDateTime(location.updated_at) },
            ]}
          />
        </Card>
        <Card
          title={`Sub-locations (${childLocations.length})`}
          flush
          actions={
            canManage ? (
              <Button size="sm" variant="ghost" leadingIcon={<Plus size={14} />} onClick={onAddChild}>
                Add
              </Button>
            ) : undefined
          }
        >
          {childLocations.length === 0 ? (
            <EmptyState compact illustration="pin" title="No sub-locations" description="Benches, shelves and bins can live under this location." />
          ) : (
            <ul>
              {childLocations.map((child) => (
                <li key={child.id}>
                  <ListRow compact to={`/locations/${child.id}`} leading={<Building2 size={14} aria-hidden="true" style={{ color: 'var(--color-text-muted)' }} />} title={child.name} meta={<span>{child.asset_count} assets</span>} />
                </li>
              ))}
            </ul>
          )}
        </Card>
      </Stack>
    </DetailPanel>
  )
}
