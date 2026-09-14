import { Plus } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ApiError, errorMessage } from '@/api/client'
import type { SavedFilter } from '@/api/contracts/saved-filters'
import { WORK_ORDER_SORT_OPTIONS, type WorkOrder, type WorkOrderFilterName, type WorkOrderFormValues, type WorkOrderSort } from '@/api/contracts/work-orders'
import { uploadAttachment } from '@/api/queries/attachments'
import { useCreateWorkOrder, useDuplicateWorkOrder, useUpdateWorkOrder, useWorkOrder, useWorkOrders } from '@/api/queries/work-orders'
import { api } from '@/api/client'
import { useCan } from '@/lib/permissions'
import { Button, EmptyState, InlineAlert, ListToolbarSpacer, LoadMore, MasterDetailLayout, Page, PageHeader, SearchField, SkeletonBlock, SkeletonRows, SplitButton, Tabs, ViewSelector, useToast } from '@/ui'
import { prefillFromParams, toWorkOrderInput } from './formModel'
import { clearFilters, hasActiveFilters, listSearch, paramsFromSavedFilter, readListState, savedFilterFromParams, withFilter, withParam, type ListTab, type ListView } from './params'
import { SavedFiltersMenu } from './SavedFiltersMenu'
import { WorkOrderDetail } from './WorkOrderDetail'
import { WorkOrderFilterChips } from './WorkOrderFilters'
import { WorkOrderForm } from './WorkOrderForm'
import { WorkOrderPanelList, WorkOrderTable } from './WorkOrderList'
import styles from './work-orders.module.css'

function isTyping(event: KeyboardEvent): boolean {
  const target = event.target as HTMLElement | null
  return Boolean(target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable))
}

export default function WorkOrdersPage() {
  const { workOrderId } = useParams<{ workOrderId: string }>()
  const location = useLocation()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()
  const can = useCan()
  const canCreate = can('work_order.create')
  const searchRef = useRef<HTMLInputElement>(null)

  const state = useMemo(() => readListState(params), [params])
  const search = listSearch(params)
  const isNew = location.pathname.endsWith('/work-orders/new')
  const isEdit = Boolean(workOrderId) && location.pathname.endsWith('/edit')
  const paneParent = params.get('parent')

  // Local search text; re-synced when the URL's q changes from elsewhere (saved filter, clear).
  const [query, setQuery] = useState(state.q)
  const [lastQ, setLastQ] = useState(state.q)
  if (lastQ !== state.q) {
    setLastQ(state.q)
    setQuery(state.q)
  }
  const [revealed, setRevealed] = useState<Set<string>>(() => new Set())
  const [cursorId, setCursorId] = useState<string | null>(null)
  const [saveRequest, setSaveRequest] = useState(0)

  const listParams = useMemo(() => ({ q: state.q || undefined, tab: state.tab, sort: state.sort, filters: state.filters }), [state])
  const list = useWorkOrders(listParams)
  const items = useMemo(() => list.data?.pages.flatMap((page) => page.items) ?? [], [list.data])
  const total = list.data?.pages[0]?.total
  const tabs = list.data?.pages[0]?.tabs
  const filtersActive = hasActiveFilters(state)

  const selected = useWorkOrder(workOrderId)
  const parentForPane = useWorkOrder(isNew && paneParent ? paneParent : undefined)

  const create = useCreateWorkOrder()
  const update = useUpdateWorkOrder(workOrderId ?? '')
  const duplicate = useDuplicateWorkOrder()

  const setListParams = useCallback(
    (next: URLSearchParams, options: { replace?: boolean } = {}) => {
      setParams(next, { replace: options.replace ?? false })
    },
    [setParams],
  )

  const onFilterChange = (name: WorkOrderFilterName, values: string[]) => setListParams(withFilter(params, name, values))
  const onSearchDebounced = useCallback(
    (value: string) => {
      if ((params.get('q') ?? '') === value.trim()) return
      setListParams(withParam(params, 'q', value.trim()), { replace: true })
    },
    [params, setListParams],
  )
  const setTab = (tab: ListTab) => setListParams(withParam(params, 'tab', tab === 'todo' ? null : tab))
  const setSort = (sort: WorkOrderSort) => setListParams(withParam(params, 'sort', sort === '-updated_at' ? null : sort))
  const setView = (view: ListView) => setListParams(withParam(params, 'view', view === 'panel' ? null : view))
  const applySavedFilter = (saved: SavedFilter) => {
    setListParams(paramsFromSavedFilter(saved))
    toast.info(`Applied “${saved.name}”`)
  }

  const rowLink = useCallback((wo: WorkOrder) => `/work-orders/${wo.id}${search}`, [search])
  const openNew = useCallback((parent?: string) => navigate(`/work-orders/new${search}${parent ? `${search ? '&' : '?'}parent=${parent}` : ''}`), [navigate, search])
  const closePane = useCallback(() => {
    const target = isEdit && workOrderId ? `/work-orders/${workOrderId}${search}` : `/work-orders${search}`
    navigate(target)
    create.reset()
    update.reset()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isEdit, workOrderId, search, navigate])

  // Keyboard shortcuts: "/" search, "n" new, "j"/"k" move the cursor, Enter opens it.
  const keyState = useRef({ items, cursorId, canCreate, paneOpen: isNew || isEdit, openNew, rowLink })
  useEffect(() => {
    keyState.current = { items, cursorId, canCreate, paneOpen: isNew || isEdit, openNew, rowLink }
  })
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event) || event.metaKey || event.ctrlKey || event.altKey) return
      const current = keyState.current
      if (event.key === '/') {
        event.preventDefault()
        searchRef.current?.focus()
      } else if (event.key === 'n' && current.canCreate && !current.paneOpen) {
        event.preventDefault()
        current.openNew()
      } else if ((event.key === 'j' || event.key === 'k') && current.items.length && !current.paneOpen) {
        event.preventDefault()
        const index = current.items.findIndex((wo) => wo.id === current.cursorId)
        const next = event.key === 'j' ? Math.min(index + 1, current.items.length - 1) : Math.max(index <= 0 ? 0 : index - 1, 0)
        const target = current.items[next]
        setCursorId(target.id)
        document.querySelector(`[data-work-order-id="${target.id}"]`)?.scrollIntoView({ block: 'nearest' })
      } else if (event.key === 'Enter' && current.cursorId && !current.paneOpen) {
        const target = event.target as HTMLElement | null
        if (target && target !== document.body && target.closest('a, button, [role="button"], [role="menuitem"], [role="option"]')) return
        const wo = current.items.find((item) => item.id === current.cursorId)
        if (wo) {
          event.preventDefault()
          navigate(current.rowLink(wo))
        }
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [navigate])

  const uploadQueued = async (id: string, number: number, files: File[]) => {
    let failed = 0
    for (const file of files) {
      try {
        await uploadAttachment('work-orders', id, file)
      } catch {
        failed += 1
      }
    }
    if (failed) toast.error(`${failed} of ${files.length} files could not be uploaded`, `Open #${number} to try again from the Files card.`)
  }

  const createSubWorkOrders = async (id: string, titles: string[]) => {
    let failed = 0
    for (const title of titles) {
      try {
        await api.post(`/work-orders/${id}/sub-work-orders`, { title })
      } catch {
        failed += 1
      }
    }
    if (failed) toast.error(`${failed} sub-work ${failed === 1 ? 'order' : 'orders'} could not be created`)
  }

  const submitForm = async (values: WorkOrderFormValues, options: { draft?: boolean; publish?: boolean; files: File[] }) => {
    try {
      if (isEdit && workOrderId) {
        const updated = await update.mutateAsync(toWorkOrderInput(values, { publish: options.publish }))
        toast.success(options.publish ? `#${updated.number} published` : `#${updated.number} updated`)
        if (options.files.length) await uploadQueued(updated.id, updated.number, options.files)
        navigate(`/work-orders/${updated.id}${search}`)
      } else {
        const created = await create.mutateAsync(toWorkOrderInput(values, { draft: options.draft }))
        toast.success(`#${created.number} created`, options.draft ? 'Saved as a draft.' : created.title)
        if (options.files.length) await uploadQueued(created.id, created.number, options.files)
        const titles = values.sub_work_orders.map((s) => s.title.trim()).filter(Boolean)
        if (titles.length) await createSubWorkOrders(created.id, titles)
        navigate(`/work-orders/${created.id}${search}`)
      }
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not save the work order', errorMessage(error))
    }
  }

  const onDuplicateSelected = async () => {
    if (!workOrderId) return
    try {
      const copy = await duplicate.mutateAsync(workOrderId)
      toast.success(`#${copy.number} created`, `Duplicated from #${selected.data?.number ?? ''}`)
      navigate(`/work-orders/${copy.id}${search}`)
    } catch (error) {
      toast.error('Could not duplicate the work order', errorMessage(error))
    }
  }

  const prefill = useMemo(() => prefillFromParams(params), [params])
  const savedCurrent = useMemo(() => savedFilterFromParams(params), [params])

  /* List states ---------------------------------------------------------------- */

  const emptyState = list.isPending ? (
    <SkeletonRows rows={8} />
  ) : list.isError ? (
    <div style={{ padding: 'var(--space-4)' }}>
      <InlineAlert
        tone="danger"
        title="Work orders could not be loaded"
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
      title="No work orders match"
      description="Try fewer filters or a different search."
      action={
        <Button size="sm" onClick={() => setListParams(clearFilters(params))}>
          Clear filters
        </Button>
      }
    />
  ) : items.length === 0 && state.tab === 'done' && (tabs?.todo ?? 0) > 0 ? (
    <EmptyState compact illustration="clipboard" title="Nothing finished yet" description="Completed and canceled work orders will show up here." />
  ) : items.length === 0 ? (
    <EmptyState
      compact
      illustration="clipboard"
      title="You don't have any work orders"
      description="Work orders track repairs, builds, inspections and event tasks for the chapter."
      action={
        canCreate ? (
          <Button variant="primary" size="sm" leadingIcon={<Plus size={16} />} onClick={() => openNew()}>
            Create the first work order
          </Button>
        ) : undefined
      }
    />
  ) : null

  const loadMore = list.data && items.length > 0 && (
    <LoadMore loaded={items.length} total={total} hasMore={Boolean(list.hasNextPage)} loading={list.isFetchingNextPage} onLoadMore={() => void list.fetchNextPage()} />
  )

  const listContent =
    emptyState ??
    (state.view === 'table' ? (
      <>
        <WorkOrderTable items={items} selectedId={workOrderId} sort={state.sort} onSortChange={setSort} onOpen={(wo) => navigate(rowLink(wo))} />
        {loadMore}
      </>
    ) : (
      <>
        <WorkOrderPanelList items={items} selectedId={workOrderId} cursorId={cursorId} rowLink={rowLink} />
        {loadMore}
      </>
    ))

  const toolbar = (
    <div className={styles.listToolbar}>
      <Tabs<ListTab>
        label="Work order tabs"
        value={state.tab}
        onChange={setTab}
        items={[
          { value: 'todo', label: 'To Do', count: tabs?.todo ?? null },
          { value: 'done', label: 'Done', count: tabs?.done ?? null },
        ]}
      />
      <ListToolbarSpacer />
      {list.isFetching && !list.isPending && (
        <span className={styles.listCount} aria-live="polite">
          Updating…
        </span>
      )}
      <ViewSelector<WorkOrderSort> label="Sort" value={state.sort} onChange={setSort} options={WORK_ORDER_SORT_OPTIONS} />
    </div>
  )

  /* Detail states -------------------------------------------------------------- */

  const detail = !workOrderId ? (
    <EmptyState illustration="clipboard" title={isNew ? 'Creating a work order' : 'Select a work order'} description={isNew ? 'Fill in the pane to add it to the list.' : 'Choose a work order on the left to see its details, people, time and activity.'} />
  ) : selected.isPending ? (
    <div style={{ padding: 'var(--space-6)' }}>
      <SkeletonBlock lines={6} />
    </div>
  ) : selected.isError ? (
    <div style={{ padding: 'var(--space-6)' }}>
      {selected.error instanceof ApiError && selected.error.isNotFound ? (
        <EmptyState illustration="search" title="Work order not found" description="It may have been removed, or you may not have access to its project." action={<Button onClick={() => navigate(`/work-orders${search}`)}>Back to work orders</Button>} />
      ) : (
        <InlineAlert
          tone="danger"
          title="Could not load this work order"
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
    <WorkOrderDetail workOrder={selected.data} listSearch={search} />
  )

  const pane = (
    <WorkOrderForm
      open={isNew || (isEdit && Boolean(selected.data))}
      mode={isEdit ? 'edit' : 'create'}
      initial={isEdit ? selected.data : null}
      prefill={prefill}
      parentNumber={isNew && paneParent ? (parentForPane.data?.number ?? null) : null}
      submitting={create.isPending || update.isPending}
      error={isEdit ? update.error : create.error}
      onSubmit={submitForm}
      onClose={closePane}
    />
  )

  const header = (
    <PageHeader
      title="Work Orders"
      viewSelector={
        <ViewSelector<ListView>
          label="View"
          value={state.view}
          onChange={setView}
          options={[
            { value: 'panel', label: 'Panel' },
            { value: 'table', label: 'Table' },
          ]}
        />
      }
      actions={
        <>
          <SearchField ref={searchRef} value={query} onChange={setQuery} onDebouncedChange={onSearchDebounced} placeholder="Search work orders or #number" shortcutHint="/" />
          {canCreate && (
            <SplitButton
              label="New Work Order"
              menuLabel="New work order options"
              leadingIcon={<Plus size={16} />}
              onClick={() => openNew()}
              items={[
                { key: 'sub', label: 'New sub-work order of selected', disabled: !workOrderId, onSelect: () => openNew(workOrderId) },
                { key: 'dup', label: 'Duplicate selected', disabled: !workOrderId || duplicate.isPending, onSelect: () => void onDuplicateSelected() },
                { key: 'sep', type: 'separator' },
                { key: 'save', label: 'Save current view as filter', onSelect: () => setSaveRequest((n) => n + 1) },
              ]}
            />
          )}
        </>
      }
      filters={<WorkOrderFilterChips filters={state.filters} onChange={onFilterChange} revealed={revealed} onReveal={(name) => setRevealed((current) => new Set(current).add(name))} trailing={<SavedFiltersMenu current={savedCurrent} onApply={applySavedFilter} saveRequest={saveRequest} />} />}
    />
  )

  const fullTable = state.view === 'table' && !workOrderId && !isNew
  if (fullTable) {
    return (
      <Page>
        {header}
        <div className={styles.tablePage}>
          <div className={styles.tableToolbar}>
            {toolbar}
            <span className={styles.listCount}>{total !== undefined ? `${total} work orders` : ''}</span>
          </div>
          <div className={styles.tableScroll}>{listContent}</div>
        </div>
      </Page>
    )
  }

  return (
    <Page>
      {header}
      <MasterDetailLayout
        detailOpen={Boolean(workOrderId) || isNew}
        backTo={`/work-orders${search}`}
        backLabel="Back to work orders"
        listToolbar={toolbar}
        list={listContent}
        detail={
          <>
            {detail}
            {pane}
          </>
        }
      />
    </Page>
  )
}
