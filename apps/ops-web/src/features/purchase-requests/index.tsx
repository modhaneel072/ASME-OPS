/**
 * Purchase Requests: a master-detail screen at `/purchase-requests` and
 * `/purchase-requests/:purchaseRequestId`.
 *
 * Tabs, search, filters and sort all live in the URL, and the detail pane is the
 * route itself, so any view can be linked to. The tab badges are the `tabs`
 * counts the list endpoint returns, and every action on the detail pane is
 * driven by that request's `available_actions` - the screen never re-implements
 * the approval rules.
 */

import { Plus, Settings2, ShoppingCart } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ApiError, errorMessage } from '@/api/client'
import {
  PURCHASE_REQUEST_SORT_OPTIONS,
  PURCHASE_REQUEST_STATUSES,
  purchaseRequestStatusLabel,
  type PurchaseRequest,
  type PurchaseRequestPayload,
  type PurchaseRequestSort,
  type PurchaseRequestTab,
} from '@/api/contracts/purchaseRequests'
import { useProjectOptions } from '@/api/queries/projects'
import { useCreatePurchaseRequest, usePurchaseRequest, usePurchaseRequests, useUpdatePurchaseRequest } from '@/api/queries/purchaseRequests'
import { useVendors } from '@/api/queries/vendors'
import { formatRelative } from '@/lib/dates'
import { useCan, useSession } from '@/lib/permissions'
import {
  Button,
  EmptyState,
  FilterChip,
  InlineAlert,
  ListRow,
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
import { Money, NeededBy, PurchaseRequestStatusBadge } from './bits'
import { clearFilters, hasActiveFilters, listSearch, readListState, withFilter, withParam, type FilterKey } from './params'
import { PurchaseRequestDetail } from './PurchaseRequestDetail'
import { PurchaseRequestForm } from './PurchaseRequestForm'
import { PurchasingSettingsDialog } from './PurchasingSettingsDialog'
import styles from './purchase-requests.module.css'

const TAB_LABELS: Record<PurchaseRequestTab, string> = {
  mine: 'Mine',
  review: 'Needs review',
  open: 'Open',
  closed: 'Closed',
}

const EMPTY_STATES: Record<PurchaseRequestTab, { title: string; description: string }> = {
  mine: { title: 'You have not asked for anything yet', description: 'Start a purchase request when the chapter needs parts, tools or materials.' },
  review: { title: 'Nothing needs your review', description: 'Requests waiting on your approval land here.' },
  open: { title: 'No open purchase requests', description: 'Everything the chapter asked for has been received, declined or canceled.' },
  closed: { title: 'Nothing has closed yet', description: 'Received, declined and canceled requests are kept here.' },
}

function isTyping(event: KeyboardEvent): boolean {
  const target = event.target as HTMLElement | null
  return Boolean(target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable))
}

export default function PurchaseRequestsPage() {
  const { purchaseRequestId } = useParams<{ purchaseRequestId: string }>()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()
  const session = useSession()
  const can = useCan()
  const canSubmit = can('purchase.submit')
  const canManageSettings = can('chapter.settings.manage')
  const canReview = can('purchase.review')

  const state = useMemo(() => readListState(params), [params])
  const search = listSearch(params)
  const filtersActive = hasActiveFilters(state)
  const searchRef = useRef<HTMLInputElement>(null)

  const [query, setQuery] = useState(state.q)
  const [lastQ, setLastQ] = useState(state.q)
  if (lastQ !== state.q) {
    setLastQ(state.q)
    setQuery(state.q)
  }

  const listParams = useMemo(
    () => ({
      q: state.q || undefined,
      tab: state.tab,
      sort: state.sort,
      status: state.filters.status.length ? state.filters.status : undefined,
      project: state.filters.project.length ? state.filters.project : undefined,
      vendor: state.filters.vendor.length ? state.filters.vendor : undefined,
    }),
    [state],
  )
  const list = usePurchaseRequests(listParams)
  const items = useMemo(() => list.data?.pages.flatMap((page) => page.items) ?? [], [list.data])
  const total = list.data?.pages[0]?.total
  const tabs = list.data?.pages[0]?.tabs
  const selected = usePurchaseRequest(purchaseRequestId)

  const projects = useProjectOptions()
  const vendors = useVendors({ active: 'true', limit: 200 })

  const pane = params.get('pane') // 'new' | 'edit' | null
  const [settingsOpen, setSettingsOpen] = useState(false)

  const create = useCreatePurchaseRequest()
  const update = useUpdatePurchaseRequest(purchaseRequestId ?? '')

  const paramsRef = useRef(params)
  const setParamsRef = useRef(setParams)
  useEffect(() => {
    paramsRef.current = params
    setParamsRef.current = setParams
  }, [params, setParams])

  const syncSearch = useCallback((value: string) => {
    const current = paramsRef.current
    if ((current.get('q') ?? '') === value.trim()) return
    setParamsRef.current(withParam(current, 'q', value.trim() || null), { replace: true })
  }, [])

  const setTab = (tab: PurchaseRequestTab) => setParams(withParam(params, 'tab', tab === 'mine' ? null : tab))
  const setSort = (sort: PurchaseRequestSort) => setParams(withParam(params, 'sort', sort === '-updated_at' ? null : sort))
  const setFilter = (key: FilterKey, values: string[]) => setParams(withFilter(params, key, values))

  const openPane = useCallback(
    (mode: 'new' | 'edit') => {
      setParamsRef.current(withParam(paramsRef.current, 'pane', mode))
    },
    [],
  )
  const closePane = () => {
    setParams(withParam(params, 'pane', null))
    create.reset()
    update.reset()
  }

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event) || event.metaKey || event.ctrlKey || event.altKey) return
      if (event.key === '/') {
        event.preventDefault()
        searchRef.current?.focus()
      } else if (event.key === 'n' && canSubmit && !pane) {
        event.preventDefault()
        openPane('new')
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [canSubmit, pane, openPane])

  const editing = pane === 'edit' && Boolean(selected.data)
  const canEditSelected = Boolean(selected.data && selected.data.status === 'draft' && (selected.data.requester?.id === session.user.id || canReview))
  const paneOpen = (pane === 'new' && canSubmit) || (editing && canEditSelected)

  const submitForm = async (payload: PurchaseRequestPayload) => {
    try {
      if (pane === 'edit' && purchaseRequestId) {
        await update.mutateAsync(payload)
        toast.success('Purchase request updated')
        closePane()
      } else {
        const created = await create.mutateAsync(payload)
        toast.success('Purchase request created', `${created.display_number} is a draft until you submit it.`)
        create.reset()
        navigate(`/purchase-requests/${created.id}${search}`)
      }
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not save the purchase request', errorMessage(error))
    }
  }

  const clearAll = () => {
    setQuery('')
    setParams(clearFilters(params))
  }

  /* List region -------------------------------------------------------------- */

  const listContent = list.isPending ? (
    <SkeletonRows rows={8} />
  ) : list.isError ? (
    <div className={styles.padded}>
      <InlineAlert
        tone="danger"
        title="Purchase requests could not be loaded"
        actions={
          <Button size="sm" onClick={() => void list.refetch()}>
            Retry
          </Button>
        }
      >
        {errorMessage(list.error)}
      </InlineAlert>
    </div>
  ) : items.length === 0 && (state.q || filtersActive) ? (
    <EmptyState
      compact
      illustration="search"
      title="No purchase requests match"
      description={state.q ? `Nothing matches “${state.q}” with the current filters.` : 'Nothing matches the current filters.'}
      action={
        <Button size="sm" onClick={clearAll}>
          Clear search and filters
        </Button>
      }
    />
  ) : items.length === 0 ? (
    <EmptyState
      compact
      illustration="box"
      title={EMPTY_STATES[state.tab].title}
      description={EMPTY_STATES[state.tab].description}
      action={
        canSubmit && state.tab !== 'review' ? (
          <Button variant="primary" size="sm" leadingIcon={<Plus size={16} />} onClick={() => openPane('new')}>
            New purchase request
          </Button>
        ) : undefined
      }
    />
  ) : (
    <>
      <ul aria-label="Purchase requests">
        {items.map((request) => (
          <li key={request.id}>
            <RequestRow request={request} selected={request.id === purchaseRequestId} to={`/purchase-requests/${request.id}${search}`} />
          </li>
        ))}
      </ul>
      <LoadMore loaded={items.length} total={total} hasMore={Boolean(list.hasNextPage)} loading={list.isFetchingNextPage} onLoadMore={() => void list.fetchNextPage()} />
    </>
  )

  /* Detail region ------------------------------------------------------------ */

  const detail = !purchaseRequestId ? (
    <EmptyState illustration="box" title="Select a purchase request" description="Choose a request on the left to see its line items, approvals and receipts." />
  ) : selected.isPending ? (
    <div className={styles.detailPad}>
      <SkeletonBlock lines={6} />
    </div>
  ) : selected.isError ? (
    <div className={styles.detailPad}>
      {selected.error instanceof ApiError && selected.error.isNotFound ? (
        <EmptyState
          illustration="search"
          title="Purchase request not found"
          description="It may have been removed, or you may not be able to see requests from other members."
          action={<Button onClick={() => navigate(`/purchase-requests${search}`)}>Back to purchase requests</Button>}
        />
      ) : (
        <InlineAlert
          tone="danger"
          title="Could not load this purchase request"
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
    <PurchaseRequestDetail request={selected.data} canEdit={canEditSelected} onEdit={() => openPane('edit')} />
  )

  const chipOption = (value: string, label: string) => ({ value, label })

  return (
    <Page>
      <PageHeader
        title="Purchase Requests"
        viewSelector={<ViewSelector<PurchaseRequestSort> label="Sort" value={state.sort} onChange={setSort} options={PURCHASE_REQUEST_SORT_OPTIONS} />}
        actions={
          <>
            <SearchField ref={searchRef} value={query} onChange={setQuery} onDebouncedChange={syncSearch} placeholder="Search requests" shortcutHint="/" />
            {canManageSettings && (
              <Button leadingIcon={<Settings2 size={16} />} onClick={() => setSettingsOpen(true)}>
                Purchasing settings
              </Button>
            )}
            {canSubmit && (
              <Button variant="primary" leadingIcon={<Plus size={16} />} onClick={() => openPane('new')}>
                New purchase request
              </Button>
            )}
          </>
        }
        filters={
          <>
            <FilterChip
              label="Status"
              options={PURCHASE_REQUEST_STATUSES.map((value) => chipOption(value, purchaseRequestStatusLabel(value)))}
              value={state.filters.status}
              onChange={(values) => setFilter('status', values)}
            />
            <FilterChip
              label="Project"
              options={projects.options.map((option) => chipOption(option.value, option.label))}
              value={state.filters.project}
              onChange={(values) => setFilter('project', values)}
              loading={projects.isLoading}
              searchable
              emptyText="No projects"
            />
            <FilterChip
              label="Vendor"
              options={(vendors.data?.items ?? []).map((vendor) => chipOption(vendor.id, vendor.name))}
              value={state.filters.vendor}
              onChange={(values) => setFilter('vendor', values)}
              loading={vendors.isPending}
              searchable
              emptyText="No vendors"
            />
            {(filtersActive || state.q) && (
              <Button variant="link" size="sm" onClick={clearAll}>
                Clear all
              </Button>
            )}
          </>
        }
      />
      <MasterDetailLayout
        detailOpen={Boolean(purchaseRequestId)}
        backTo={`/purchase-requests${search}`}
        backLabel="Back to purchase requests"
        listToolbar={
          <div className={styles.listToolbar}>
            <Tabs<PurchaseRequestTab>
              label="Purchase request tabs"
              value={state.tab}
              onChange={setTab}
              items={[
                { value: 'mine', label: TAB_LABELS.mine, count: tabs?.mine ?? null },
                { value: 'review', label: TAB_LABELS.review, count: tabs?.review ?? null },
                { value: 'open', label: TAB_LABELS.open, count: tabs?.open ?? null },
                { value: 'closed', label: TAB_LABELS.closed, count: tabs?.closed ?? null },
              ]}
            />
            <ListToolbarSpacer />
            {list.isFetching && !list.isPending && (
              <span className={styles.listCount} aria-live="polite">
                Updating…
              </span>
            )}
          </div>
        }
        list={listContent}
        detail={
          <>
            {detail}
            <PurchaseRequestForm
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
      <PurchasingSettingsDialog open={settingsOpen && canManageSettings} onClose={() => setSettingsOpen(false)} />
    </Page>
  )
}

function RequestRow({ request, selected, to }: { request: PurchaseRequest; selected: boolean; to: string }) {
  return (
    <ListRow
      to={to}
      selected={selected}
      leading={<ShoppingCart size={16} className={styles.muted} aria-hidden="true" />}
      title={
        <span className={styles.rowTitle}>
          <span className={styles.number}>{request.display_number}</span>
          <span className={styles.rowTitleText}>{request.title}</span>
        </span>
      }
      meta={
        <>
          <PurchaseRequestStatusBadge status={request.status} size="sm" />
          {request.requester?.name && <span>{request.requester.name}</span>}
          {request.project?.name && <span>{request.project.name}</span>}
          {request.vendor?.name && <span>{request.vendor.name}</span>}
          <NeededBy date={request.needed_by} overdue={request.is_overdue} />
        </>
      }
      trailing={
        <span className={styles.rowTrailing}>
          <Money value={request.estimated_total} />
          <span className={styles.listCount}>{request.updated_at ? formatRelative(request.updated_at) : ''}</span>
        </span>
      }
      data-testid="purchase-request-row"
    />
  )
}
