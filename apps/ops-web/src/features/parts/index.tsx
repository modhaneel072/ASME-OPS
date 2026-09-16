import { Plus, ShoppingCart } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ApiError, errorMessage } from '@/api/client'
import type { CountPayload, MovementPayload, MovementType, Part, PartPayload, PartSort, TransferPayload, VendorLinkPayload } from '@/api/contracts/parts'
import { useLocations } from '@/api/queries/locations'
import {
  useCreatePart,
  useCreatePurchaseRequestsFromLowStock,
  useCycleCount,
  usePart,
  usePartTypes,
  useParts,
  useRecordMovement,
  useSetPartAssets,
  useSetPartVendors,
  useTransferStock,
  useUpdatePart,
} from '@/api/queries/parts'
import { useVendorOptions } from '@/api/queries/vendors'
import { useCan } from '@/lib/permissions'
import {
  Button,
  EmptyState,
  FilterChip,
  InlineAlert,
  ListToolbarSpacer,
  LoadMore,
  MasterDetailLayout,
  Page,
  PageHeader,
  SearchField,
  SkeletonBlock,
  SkeletonRows,
  Tabs,
  ViewSelector,
  useToast,
} from '@/ui'
import { AssetsDialog, VendorsDialog } from './LinkDialogs'
import { clearFilters, hasActiveFilters, listSearch, PART_TABS, readCritical, readFilters, readSort, readTab, stockFilterFor, TAB_LABELS, writeCritical, writeFilter, writeSort, writeTab, type FilterKey, type PartTab } from './params'
import { PartDetail } from './PartDetail'
import { PartForm } from './PartForm'
import styles from './parts.module.css'
import { PartsTable } from './PartsTable'
import { CountDialog, MovementDialog, TransferDialog } from './StockDialogs'

const SORT_OPTIONS: Array<{ value: PartSort; label: string; description?: string }> = [
  { value: 'name', label: 'Name A–Z' },
  { value: '-name', label: 'Name Z–A' },
  { value: 'sku', label: 'SKU A–Z' },
  { value: 'available', label: 'Least available first' },
  { value: '-available', label: 'Most available first' },
  { value: '-updated_at', label: 'Recently updated' },
]

type OpenDialog = { kind: 'movement'; type: MovementType } | { kind: 'transfer' } | { kind: 'count' } | { kind: 'vendors' } | { kind: 'assets' } | null

function isTyping(event: KeyboardEvent): boolean {
  const target = event.target as HTMLElement | null
  return Boolean(target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable))
}

export default function PartsPage() {
  const { partId } = useParams<{ partId: string }>()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()
  const can = useCan()
  const canManage = can('inventory.manage')
  const canSubmitPurchase = can('purchase.submit')

  const tab = readTab(params)
  const sort = readSort(params)
  const filters = useMemo(() => readFilters(params), [params])
  const critical = readCritical(params)
  const filtersActive = hasActiveFilters(filters, critical)
  const [query, setQuery] = useState(params.get('q') ?? '')
  const [debounced, setDebounced] = useState(query)
  const searchRef = useRef<HTMLInputElement>(null)

  // Keep ?q= in the URL so links and refreshes restore the search.
  useEffect(() => {
    if ((params.get('q') ?? '') === debounced) return
    const next = new URLSearchParams(params)
    if (debounced) next.set('q', debounced)
    else next.delete('q')
    setParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced])

  const listParams = useMemo(
    () => ({
      q: debounced || undefined,
      type: filters.type.length ? filters.type : undefined,
      location: filters.location.length ? filters.location : undefined,
      vendor: filters.vendor.length ? filters.vendor : undefined,
      stock: stockFilterFor(tab),
      critical,
      active: 'true' as const,
      sort,
    }),
    [debounced, filters, critical, tab, sort],
  )

  const list = useParts(listParams)
  const rows = useMemo(() => (list.data?.pages ?? []).flatMap((page) => page.items), [list.data])
  const total = list.data?.pages[0]?.total
  const counts = list.data?.pages[0]?.stock_counts

  const selected = usePart(partId)
  const types = usePartTypes()
  const vendors = useVendorOptions()
  const locations = useLocations({ limit: 200 })

  const pane = params.get('pane') // 'new' | 'edit' | null
  const paneOpen = pane === 'new' || (pane === 'edit' && Boolean(selected.data))
  const [dialog, setDialog] = useState<OpenDialog>(null)
  const [checked, setChecked] = useState<Set<string>>(new Set())

  const create = useCreatePart()
  const update = useUpdatePart(partId ?? '')
  const movement = useRecordMovement(partId ?? '')
  const transfer = useTransferStock()
  const count = useCycleCount()
  const setVendors = useSetPartVendors(partId ?? '')
  const setAssets = useSetPartAssets(partId ?? '')
  const createRequests = useCreatePurchaseRequestsFromLowStock()

  const setTab = (next: PartTab) => {
    setChecked(new Set())
    setParams(writeTab(params, next))
  }
  const setSort = (next: PartSort) => setParams(writeSort(params, next))
  const setFilter = (key: FilterKey, values: string[]) => setParams(writeFilter(params, key, values))

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

  const closeDialog = () => {
    setDialog(null)
    movement.reset()
    transfer.reset()
    count.reset()
    setVendors.reset()
    setAssets.reset()
  }

  const openPart = (part: Part) => navigate(`/parts/${part.id}${listSearch(params)}`)

  const resetSearch = () => {
    setQuery('')
    setDebounced('')
    setParams(clearFilters(params))
  }

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event) || event.metaKey || event.ctrlKey || event.altKey) return
      if (event.key === '/') {
        event.preventDefault()
        searchRef.current?.focus()
      } else if (event.key === 'n' && canManage && !paneOpen && !dialog) {
        event.preventDefault()
        openPane('new')
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [canManage, paneOpen, dialog, openPane])

  /* Mutations ---------------------------------------------------------------- */

  const submitForm = async (payload: PartPayload) => {
    try {
      if (pane === 'edit' && partId) {
        await update.mutateAsync(payload)
        toast.success('Part updated')
        closePane()
      } else {
        const created = await create.mutateAsync(payload)
        toast.success('Part created', created.name)
        closePane()
        navigate(`/parts/${created.id}${listSearch(params)}`)
      }
    } catch (error) {
      if (error instanceof ApiError && error.isValidation) return
      toast.error('Could not save part', errorMessage(error))
    }
  }

  const submitMovement = async (payload: MovementPayload) => {
    try {
      const part = await movement.mutateAsync(payload)
      toast.success('Stock updated', `${part.name}: ${part.totals.available} ${part.unit} available`)
      closeDialog()
    } catch (error) {
      if (error instanceof ApiError && error.isValidation) return
      toast.error('Could not record the movement', errorMessage(error))
    }
  }

  const submitTransfer = async (payload: TransferPayload) => {
    try {
      await transfer.mutateAsync(payload)
      toast.success('Stock transferred')
      closeDialog()
    } catch (error) {
      if (error instanceof ApiError && error.isValidation) return
      toast.error('Could not transfer the stock', errorMessage(error))
    }
  }

  const submitCount = async (payload: CountPayload) => {
    try {
      const result = await count.mutateAsync(payload)
      const delta = result.lines[0]?.delta ?? 0
      toast.success('Count recorded', delta === 0 ? 'The shelf matched the system quantity.' : `The system quantity moved by ${delta > 0 ? '+' : '−'}${Math.abs(delta)}.`)
      closeDialog()
    } catch (error) {
      if (error instanceof ApiError && error.isValidation) return
      toast.error('Could not record the count', errorMessage(error))
    }
  }

  const submitVendors = async (payload: VendorLinkPayload[]) => {
    try {
      await setVendors.mutateAsync(payload)
      toast.success('Vendors updated')
      closeDialog()
    } catch (error) {
      if (error instanceof ApiError && error.isValidation) return
      toast.error('Could not update the vendors', errorMessage(error))
    }
  }

  const submitAssets = async (assetIds: string[]) => {
    try {
      await setAssets.mutateAsync(assetIds)
      toast.success('Assets updated')
      closeDialog()
    } catch (error) {
      if (error instanceof ApiError && error.isValidation) return
      toast.error('Could not update the assets', errorMessage(error))
    }
  }

  const createPurchaseRequests = async () => {
    const ids = [...checked]
    if (ids.length === 0) return
    try {
      const created = await createRequests.mutateAsync(ids)
      setChecked(new Set())
      toast.success(created.length === 1 ? 'Draft purchase request created' : `${created.length} draft purchase requests created`, 'Review the quantities and submit them.')
      navigate('/purchase-requests')
    } catch (error) {
      toast.error('Could not create the purchase requests', errorMessage(error))
    }
  }

  /* List region -------------------------------------------------------------- */

  const isEmpty = rows.length === 0
  const noResults = isEmpty && (Boolean(debounced) || filtersActive || tab !== 'all')

  const listContent = list.isPending ? (
    <SkeletonRows rows={8} />
  ) : list.isError ? (
    <div className={styles.padded}>
      <InlineAlert tone="danger" title="Parts could not be loaded" actions={<Button size="sm" onClick={() => void list.refetch()}>Retry</Button>}>
        {errorMessage(list.error)}
      </InlineAlert>
    </div>
  ) : noResults ? (
    <EmptyState
      compact
      illustration="search"
      title={tab === 'low' ? 'Nothing is low' : tab === 'out' ? 'Nothing is out of stock' : 'No parts match'}
      description={
        tab === 'low'
          ? 'Every tracked part is above its minimum.'
          : tab === 'out'
            ? 'Every tracked part has something available.'
            : debounced
              ? `Nothing matches “${debounced}” with the current filters.`
              : 'Nothing matches the current filters.'
      }
      action={
        tab === 'all' ? (
          <Button size="sm" onClick={resetSearch}>
            Clear search and filters
          </Button>
        ) : (
          <Button size="sm" onClick={() => setTab('all')}>
            Show all parts
          </Button>
        )
      }
    />
  ) : isEmpty ? (
    <EmptyState
      compact
      illustration="box"
      title="No parts yet"
      description="Fasteners, filament, bearings and boards: everything the chapter keeps on a shelf lives here."
      action={canManage ? <Button variant="primary" size="sm" leadingIcon={<Plus size={16} />} onClick={() => openPane('new')}>Add the first part</Button> : undefined}
    />
  ) : (
    <>
      {tab === 'low' && canSubmitPurchase && checked.size > 0 && (
        <div className={styles.selectionBar}>
          <span>{checked.size === 1 ? '1 part selected' : `${checked.size} parts selected`}</span>
          <ListToolbarSpacer />
          <Button size="sm" variant="ghost" onClick={() => setChecked(new Set())}>
            Clear selection
          </Button>
          <Button size="sm" variant="primary" leadingIcon={<ShoppingCart size={14} />} loading={createRequests.isPending} onClick={createPurchaseRequests}>
            Create purchase requests
          </Button>
        </div>
      )}
      <PartsTable
        rows={rows}
        sort={sort}
        onSortChange={setSort}
        onOpen={openPart}
        selectedId={partId}
        selectable={tab === 'low' && canSubmitPurchase}
        checked={checked}
        onToggle={(id, on) =>
          setChecked((current) => {
            const next = new Set(current)
            if (on) next.add(id)
            else next.delete(id)
            return next
          })
        }
        onToggleAll={(on) => setChecked(on ? new Set(rows.map((row) => row.id)) : new Set())}
      />
      <LoadMore loaded={rows.length} total={total} hasMore={Boolean(list.hasNextPage)} loading={list.isFetchingNextPage} onLoadMore={() => void list.fetchNextPage()} />
    </>
  )

  /* Detail region ------------------------------------------------------------ */

  const detail = !partId ? (
    <EmptyState illustration="box" title="Select a part" description="Choose a part on the left to see its stock, vendors, open orders and full movement history." />
  ) : selected.isPending ? (
    <div className={styles.detailPad}>
      <SkeletonBlock lines={6} />
    </div>
  ) : selected.isError ? (
    <div className={styles.detailPad}>
      {selected.error instanceof ApiError && selected.error.isNotFound ? (
        <EmptyState illustration="search" title="Part not found" description="It may have been removed, or the link may be out of date." action={<Button onClick={() => navigate(`/parts${listSearch(params)}`)}>Back to parts</Button>} />
      ) : (
        <InlineAlert tone="danger" title="Could not load this part" actions={<Button size="sm" onClick={() => void selected.refetch()}>Retry</Button>}>
          {errorMessage(selected.error)}
        </InlineAlert>
      )}
    </div>
  ) : (
    <PartDetail
      part={selected.data}
      canManage={canManage}
      onEdit={() => openPane('edit')}
      onMovement={(type) => setDialog({ kind: 'movement', type })}
      onTransfer={() => setDialog({ kind: 'transfer' })}
      onCount={() => setDialog({ kind: 'count' })}
      onEditVendors={() => setDialog({ kind: 'vendors' })}
      onEditAssets={() => setDialog({ kind: 'assets' })}
    />
  )

  const part = selected.data

  return (
    <Page>
      <PageHeader
        title="Parts Inventory"
        actions={
          <>
            <SearchField ref={searchRef} value={query} onChange={setQuery} onDebouncedChange={setDebounced} placeholder="Search parts" shortcutHint="/" />
            {canManage && (
              <Button variant="primary" leadingIcon={<Plus size={16} />} onClick={() => openPane('new')}>
                New Part
              </Button>
            )}
          </>
        }
        filters={
          <>
            <FilterChip
              label="Type"
              options={(types.data ?? []).map((type) => ({ value: type.id, label: type.name, color: type.color, count: type.part_count }))}
              value={filters.type}
              onChange={(value) => setFilter('type', value)}
              loading={types.isPending}
              searchable
              emptyText="No part types yet"
            />
            <FilterChip
              label="Location"
              options={(locations.data?.items ?? []).map((location) => ({ value: location.id, label: location.path.join(' › ') }))}
              value={filters.location}
              onChange={(value) => setFilter('location', value)}
              loading={locations.isPending}
              searchable
              emptyText="No locations"
            />
            <FilterChip
              label="Vendor"
              options={vendors.options.map((option) => ({ value: option.value, label: option.label }))}
              value={filters.vendor}
              onChange={(value) => setFilter('vendor', value)}
              loading={vendors.isLoading}
              searchable
              emptyText="No vendors"
            />
            <FilterChip
              label="Critical"
              multiple={false}
              options={[{ value: 'true', label: 'Critical parts only' }]}
              value={critical ? ['true'] : []}
              onChange={(value) => setParams(writeCritical(params, value.includes('true')))}
            />
            {(filtersActive || debounced) && (
              <Button variant="link" size="sm" onClick={resetSearch}>
                Clear all
              </Button>
            )}
          </>
        }
      />
      <MasterDetailLayout
        detailOpen={Boolean(partId)}
        backTo={`/parts${listSearch(params)}`}
        backLabel="Back to parts"
        listToolbar={
          <div className={styles.listToolbar}>
            <Tabs<PartTab>
              label="Stock tabs"
              value={tab}
              onChange={setTab}
              items={PART_TABS.map((value) => ({
                value,
                label: TAB_LABELS[value],
                count: value === 'all' ? (total ?? null) : value === 'low' ? (counts?.low ?? null) : (counts?.out ?? null),
              }))}
            />
            <ListToolbarSpacer />
            {list.isFetching && !list.isPending && <span aria-live="polite">Updating…</span>}
            <ViewSelector<PartSort> label="Sort" value={sort} onChange={setSort} options={SORT_OPTIONS} />
          </div>
        }
        list={listContent}
        detail={
          <>
            {detail}
            {paneOpen && (
              <PartForm
                open
                mode={pane === 'edit' ? 'edit' : 'create'}
                initial={pane === 'edit' ? (part ?? null) : null}
                unitCostLocked={pane === 'edit' && Boolean(part && part.recent_transactions.length > 0)}
                canManageTypes={canManage}
                submitting={create.isPending || update.isPending}
                error={pane === 'edit' ? update.error : create.error}
                onSubmit={submitForm}
                onClose={closePane}
              />
            )}
          </>
        }
      />
      {part && dialog?.kind === 'movement' && (
        <MovementDialog open type={dialog.type} part={part} submitting={movement.isPending} error={movement.error} onSubmit={submitMovement} onClose={closeDialog} />
      )}
      {part && dialog?.kind === 'transfer' && <TransferDialog open part={part} submitting={transfer.isPending} error={transfer.error} onSubmit={submitTransfer} onClose={closeDialog} />}
      {part && dialog?.kind === 'count' && <CountDialog open part={part} submitting={count.isPending} error={count.error} onSubmit={submitCount} onClose={closeDialog} />}
      {part && dialog?.kind === 'vendors' && <VendorsDialog open part={part} submitting={setVendors.isPending} error={setVendors.error} onSubmit={submitVendors} onClose={closeDialog} />}
      {part && dialog?.kind === 'assets' && <AssetsDialog open part={part} submitting={setAssets.isPending} error={setAssets.error} onSubmit={submitAssets} onClose={closeDialog} />}
    </Page>
  )
}
