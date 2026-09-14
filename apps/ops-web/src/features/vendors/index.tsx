import { Archive, ArchiveRestore, ExternalLink, MoreHorizontal, Pencil, Plus, Store } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ApiError, errorMessage } from '@/api/client'
import type { Vendor, VendorPayload } from '@/api/contracts/vendors'
import { useCreateVendor, useUpdateVendor, useVendor, useVendors } from '@/api/queries/vendors'
import { formatDateTime } from '@/lib/dates'
import { useCan } from '@/lib/permissions'
import {
  Badge,
  Button,
  Card,
  DetailPanel,
  DropdownMenu,
  EmptyState,
  FieldList,
  FilterChip,
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
import { VendorForm } from './VendorForm'
import styles from './vendors.module.css'

type Sort = 'name' | '-name' | '-created_at'
const SORTS: readonly Sort[] = ['name', '-name', '-created_at']
const DEFAULT_SORT: Sort = 'name'

type ActiveFilter = 'true' | 'false' | 'all'
const ACTIVE_PARAM = 'filter[active]'

function parseSort(raw: string | null): Sort {
  return raw && (SORTS as readonly string[]).includes(raw) ? (raw as Sort) : DEFAULT_SORT
}

/** Absent = active vendors only (the screen default); `all` is explicit. */
function parseActive(raw: string | null): ActiveFilter {
  return raw === 'false' || raw === 'all' ? raw : 'true'
}

function isTypingTarget(event: KeyboardEvent): boolean {
  const target = event.target as HTMLElement | null
  return Boolean(target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable))
}

function ActiveBadge({ active, size }: { active: boolean; size?: 'sm' }) {
  return active ? (
    <Badge tone="success" dot size={size}>
      Active
    </Badge>
  ) : (
    <Badge tone="neutral" dot size={size}>
      Inactive
    </Badge>
  )
}

export default function VendorsPage() {
  const { vendorId } = useParams<{ vendorId: string }>()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()
  const can = useCan()
  const canManage = can('vendor.manage')

  const urlQuery = params.get('q') ?? ''
  const sort = parseSort(params.get('sort'))
  const active = parseActive(params.get(ACTIVE_PARAM))
  const [query, setQuery] = useState(urlQuery)
  const searchRef = useRef<HTMLInputElement>(null)

  const paramsRef = useRef(params)
  const setParamsRef = useRef(setParams)
  useEffect(() => {
    paramsRef.current = params
    setParamsRef.current = setParams
  }, [params, setParams])

  const syncSearchToUrl = useCallback((value: string) => {
    const current = paramsRef.current
    if ((current.get('q') ?? '') === value) return
    const next = new URLSearchParams(current)
    if (value) next.set('q', value)
    else next.delete('q')
    setParamsRef.current(next, { replace: true })
  }, [])

  const replaceParams = (mutate: (next: URLSearchParams) => void) => {
    const next = new URLSearchParams(params)
    mutate(next)
    setParams(next, { replace: true })
  }
  const setSort = (value: Sort) => replaceParams((next) => (value === DEFAULT_SORT ? next.delete('sort') : next.set('sort', value)))
  const setActive = (value: ActiveFilter) => replaceParams((next) => (value === 'true' ? next.delete(ACTIVE_PARAM) : next.set(ACTIVE_PARAM, value)))

  const list = useVendors({ q: urlQuery || undefined, active, sort })
  const selected = useVendor(vendorId)
  const items = useMemo(() => list.data?.items ?? [], [list.data])

  const pane = params.get('pane') // 'new' | 'edit' | null
  const paneOpen = (pane === 'new' && canManage) || (pane === 'edit' && canManage && Boolean(selected.data))

  const create = useCreateVendor()
  const update = useUpdateVendor(vendorId ?? '')
  const toggle = useUpdateVendor(vendorId ?? '')

  const listSearch = useMemo(() => {
    const next = new URLSearchParams(params)
    next.delete('pane')
    const text = next.toString()
    return text ? `?${text}` : ''
  }, [params])

  const openPane = useCallback(
    (mode: 'new' | 'edit') => {
      const next = new URLSearchParams(params)
      next.set('pane', mode)
      setParams(next)
    },
    [params, setParams],
  )
  const closePane = () => {
    const next = new URLSearchParams(params)
    next.delete('pane')
    setParams(next)
    create.reset()
    update.reset()
  }

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTypingTarget(event) || event.metaKey || event.ctrlKey || event.altKey) return
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
  }, [canManage, paneOpen, openPane])

  const submitForm = async (values: VendorPayload) => {
    try {
      if (pane === 'edit' && vendorId) {
        await update.mutateAsync(values)
        toast.success('Vendor updated')
        closePane()
      } else {
        const created = await create.mutateAsync(values)
        toast.success('Vendor created', created.name)
        create.reset()
        navigate(`/vendors/${created.id}${listSearch}`)
      }
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not save vendor', errorMessage(error))
    }
  }

  const onToggleActive = async () => {
    if (!selected.data) return
    const next = !(selected.data.is_active ?? true)
    try {
      await toggle.mutateAsync({ is_active: next })
      toast.success(next ? 'Vendor reactivated' : 'Vendor deactivated', next ? 'It is available in pickers again.' : 'It stays on past work orders and purchases.')
    } catch (error) {
      toast.error(next ? 'Could not reactivate vendor' : 'Could not deactivate vendor', errorMessage(error))
    }
  }

  const filtersActive = Boolean(urlQuery) || active !== 'true'

  const listContent = list.isPending ? (
    <SkeletonRows rows={8} />
  ) : list.isError ? (
    <div style={{ padding: 'var(--space-4)' }}>
      <InlineAlert
        tone="danger"
        title="Vendors could not be loaded"
        actions={
          <Button size="sm" onClick={() => void list.refetch()}>
            Retry
          </Button>
        }
      >
        {errorMessage(list.error)}
      </InlineAlert>
    </div>
  ) : items.length === 0 && filtersActive ? (
    <EmptyState
      compact
      illustration="search"
      title="No vendors match"
      description={urlQuery ? `Nothing matches “${urlQuery}” with the current filter.` : active === 'false' ? 'There are no inactive vendors.' : 'No vendors match the current filter.'}
      action={
        <Button
          size="sm"
          onClick={() => {
            setQuery('')
            replaceParams((next) => {
              next.delete('q')
              next.delete(ACTIVE_PARAM)
            })
          }}
        >
          Clear filters
        </Button>
      }
    />
  ) : items.length === 0 ? (
    <EmptyState
      compact
      illustration="box"
      title="No vendors yet"
      description="Add the suppliers and service providers the chapter orders parts from or sends work to."
      action={
        canManage ? (
          <Button variant="primary" size="sm" leadingIcon={<Plus size={16} />} onClick={() => openPane('new')}>
            Add the first vendor
          </Button>
        ) : undefined
      }
    />
  ) : (
    <ul aria-label="Vendors">
      {items.map((vendor) => (
        <li key={vendor.id}>
          <ListRow
            to={`/vendors/${vendor.id}${listSearch}`}
            selected={vendor.id === vendorId}
            leading={<Store size={16} className={styles.rowIcon} aria-hidden="true" />}
            title={vendor.name}
            meta={
              vendor.contact_name || vendor.email ? (
                <>
                  {vendor.contact_name && <span>{vendor.contact_name}</span>}
                  {vendor.email && <span>{vendor.email}</span>}
                </>
              ) : (
                <span>No contact on file</span>
              )
            }
            trailing={<ActiveBadge active={vendor.is_active ?? true} size="sm" />}
            data-testid="vendor-row"
          />
        </li>
      ))}
    </ul>
  )

  const detail = !vendorId ? (
    <EmptyState illustration="box" title="Select a vendor" description="Choose a vendor on the left to see contact details and notes." />
  ) : selected.isPending ? (
    <div style={{ padding: 'var(--space-6)' }}>
      <SkeletonBlock lines={5} />
    </div>
  ) : selected.isError ? (
    <div style={{ padding: 'var(--space-6)' }}>
      {selected.error instanceof ApiError && selected.error.isNotFound ? (
        <EmptyState illustration="search" title="Vendor not found" description="It may have been removed or the link is out of date." action={<Button onClick={() => navigate('/vendors')}>Back to vendors</Button>} />
      ) : (
        <InlineAlert
          tone="danger"
          title="Could not load this vendor"
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
    <VendorDetail vendor={selected.data} canManage={canManage} onEdit={() => openPane('edit')} onToggleActive={onToggleActive} busy={toggle.isPending} />
  )

  return (
    <Page>
      <PageHeader
        title="Vendors"
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
            <SearchField ref={searchRef} value={query} onChange={setQuery} onDebouncedChange={syncSearchToUrl} placeholder="Search vendors" shortcutHint="/" />
            {canManage && (
              <SplitButton
                label="New Vendor"
                leadingIcon={<Plus size={16} />}
                onClick={() => openPane('new')}
                menuLabel="More vendor actions"
                items={[
                  { key: 'inactive', label: 'Show inactive vendors', onSelect: () => setActive('false'), disabled: active === 'false' },
                  { key: 'all', label: 'Show all vendors', onSelect: () => setActive('all'), disabled: active === 'all' },
                  { key: 'sep', type: 'separator' },
                  { key: 'work-orders', label: 'Go to Work Orders', onSelect: () => navigate('/work-orders') },
                ]}
              />
            )}
          </>
        }
        filters={
          <FilterChip
            label="Active"
            multiple={false}
            value={active === 'all' ? [] : [active]}
            onChange={(value) => setActive(value[0] === 'false' ? 'false' : value[0] === 'true' ? 'true' : 'all')}
            options={[
              { value: 'true', label: 'Active' },
              { value: 'false', label: 'Inactive' },
            ]}
          />
        }
      />
      <MasterDetailLayout
        detailOpen={Boolean(vendorId)}
        backTo={`/vendors${listSearch}`}
        listToolbar={
          <>
            <span>{list.data ? `${list.data.total ?? items.length} ${(list.data.total ?? items.length) === 1 ? 'vendor' : 'vendors'}` : ''}</span>
            <ListToolbarSpacer />
            {list.isFetching && !list.isPending && <span aria-live="polite">Updating…</span>}
          </>
        }
        list={listContent}
        detail={
          <>
            {detail}
            <VendorForm
              open={paneOpen}
              mode={pane === 'edit' ? 'edit' : 'create'}
              initial={pane === 'edit' ? selected.data : null}
              submitting={create.isPending || update.isPending}
              error={pane === 'edit' ? update.error : create.error}
              onSubmit={submitForm}
              onClose={closePane}
            />
          </>
        }
      />
    </Page>
  )
}

function displayUrl(url: string): string {
  return url.replace(/^https?:\/\//i, '').replace(/\/$/, '')
}

function VendorDetail({ vendor, canManage, onEdit, onToggleActive, busy }: { vendor: Vendor; canManage: boolean; onEdit: () => void; onToggleActive: () => void; busy: boolean }) {
  const isActive = vendor.is_active ?? true
  return (
    <DetailPanel
      eyebrow={
        <>
          <Store size={12} aria-hidden="true" />
          Vendor
        </>
      }
      title={
        <span className={styles.titleRow}>
          {vendor.name}
          <ActiveBadge active={isActive} />
        </span>
      }
      subtitle={vendor.contact_name || undefined}
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
                isActive
                  ? { key: 'deactivate', label: 'Deactivate vendor', icon: <Archive size={16} />, onSelect: onToggleActive, disabled: busy }
                  : { key: 'reactivate', label: 'Reactivate vendor', icon: <ArchiveRestore size={16} />, onSelect: onToggleActive, disabled: busy },
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
        <Card title="Contact">
          <FieldList
            items={[
              { label: 'Contact name', value: vendor.contact_name || '—' },
              { label: 'Email', value: vendor.email ? <a href={`mailto:${vendor.email}`}>{vendor.email}</a> : '—' },
              { label: 'Phone', value: vendor.phone ? <a href={`tel:${vendor.phone.replace(/[^\d+]/g, '')}`}>{vendor.phone}</a> : '—' },
              {
                label: 'Website',
                value: vendor.website ? (
                  <a href={vendor.website} target="_blank" rel="noopener noreferrer" className={styles.externalLink}>
                    <span className={styles.externalLinkText}>{displayUrl(vendor.website)}</span>
                    <ExternalLink size={13} aria-hidden="true" />
                    <span className="sr-only">(opens in a new tab)</span>
                  </a>
                ) : (
                  '—'
                ),
              },
            ]}
          />
        </Card>
        <Card title="Notes">{vendor.notes ? <p className={styles.notes}>{vendor.notes}</p> : <span style={{ color: 'var(--color-text-muted)' }}>No notes yet.</span>}</Card>
        <Card title="Record">
          <FieldList
            items={[
              { label: 'Status', value: <ActiveBadge active={isActive} /> },
              { label: 'Created', value: formatDateTime(vendor.created_at) },
              { label: 'Updated', value: formatDateTime(vendor.updated_at) },
            ]}
          />
        </Card>
      </Stack>
    </DetailPanel>
  )
}
