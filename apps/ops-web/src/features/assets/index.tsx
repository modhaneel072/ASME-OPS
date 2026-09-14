import { Boxes, ChevronRight, Plus } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ApiError, errorMessage } from '@/api/client'
import { ASSET_CRITICALITIES, ASSET_CRITICALITY_LABELS, ASSET_STATUSES, ASSET_STATUS_LABELS, type Asset, type AssetHierarchyNode, type AssetPayload, type AssetSort, type AssetStatusPayload } from '@/api/contracts/assets'
import { useAsset, useAssetHierarchy, useAssetTypes, useAssets, useChangeAssetStatus, useCreateAsset, useUpdateAsset } from '@/api/queries/assets'
import { useLocations } from '@/api/queries/locations'
import { useProjectOptions } from '@/api/queries/projects'
import { useTeamOptions } from '@/api/queries/teams'
import { canOn, useCan, useSession } from '@/lib/permissions'
import { Button, EmptyState, FilterChip, InlineAlert, ListRow, ListToolbarSpacer, MasterDetailLayout, Page, PageHeader, SearchField, SkeletonBlock, SkeletonRows, SplitButton, StatusBadge, ViewSelector, useToast } from '@/ui'
import styles from './assets.module.css'
import { AssetDetail } from './AssetDetail'
import { AssetForm } from './AssetForm'
import { AssetStatusDialog } from './AssetStatusDialog'
import { AssetTable } from './AssetTable'
import { AssetTree } from './AssetTree'
import { AssetTypeDialog } from './AssetTypeDialog'
import { CriticalityBadge, TypeChips } from './bits'
import { clearFilters, hasActiveFilters, listSearch, matchesSearch, pruneTree, readFilters, readSort, readView, writeFilter, type AssetView, type FilterKey } from './params'

function isTyping(event: KeyboardEvent): boolean {
  const target = event.target as HTMLElement | null
  return Boolean(target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable))
}

export default function AssetsPage() {
  const { assetId } = useParams<{ assetId: string }>()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()
  const session = useSession()
  const can = useCan()
  const canManage = can('asset.manage')
  const canCreateWorkOrder = can('work_order.create')

  const view = readView(params)
  const sort = readSort(params)
  const filters = useMemo(() => readFilters(params), [params])
  const filtersActive = hasActiveFilters(filters)
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
      status: filters.status.length ? filters.status : undefined,
      criticality: filters.criticality.length ? filters.criticality : undefined,
      type: filters.type.length ? filters.type : undefined,
      project: filters.project.length ? filters.project : undefined,
      location: filters.location.length ? filters.location : undefined,
      team: filters.team.length ? filters.team : undefined,
      sort,
    }),
    [debounced, filters, sort],
  )
  const list = useAssets(listParams, { enabled: view !== 'hierarchy' })
  const hierarchy = useAssetHierarchy({ project: filters.project.length ? filters.project : undefined, location: filters.location.length ? filters.location : undefined }, { enabled: view === 'hierarchy' })
  const selected = useAsset(assetId)
  const rows = useMemo(() => list.data?.items ?? [], [list.data])

  // Filters the server ignores in hierarchy mode (status, criticality, type, team, search) are applied to the tree here.
  const tree = useMemo(() => {
    const roots = (hierarchy.data?.items ?? []) as AssetHierarchyNode[]
    const typeSet = new Set(filters.type)
    const predicate = (node: AssetHierarchyNode) =>
      (!filters.status.length || filters.status.includes(node.status)) &&
      (!filters.criticality.length || filters.criticality.includes(node.criticality ?? 'none')) &&
      (!typeSet.size || node.types.some((t) => typeSet.has(t.id))) &&
      (!filters.team.length || (node.team ? filters.team.includes(node.team.id) : false)) &&
      matchesSearch(node, debounced)
    return pruneTree(roots, predicate)
  }, [hierarchy.data, filters, debounced])

  const types = useAssetTypes()
  const projects = useProjectOptions()
  const teams = useTeamOptions()
  const locations = useLocations({ limit: 200 })

  const pane = params.get('pane') // 'new' | 'edit' | null
  const paneParent = params.get('parent')
  const paneOpen = pane === 'new' || (pane === 'edit' && Boolean(selected.data))
  const [statusOpen, setStatusOpen] = useState(false)
  const [typeDialog, setTypeDialog] = useState(false)

  const create = useCreateAsset()
  const update = useUpdateAsset(assetId ?? '')
  const changeStatus = useChangeAssetStatus(assetId ?? '')

  const setView = (next: AssetView) => {
    const copy = new URLSearchParams(params)
    if (next === 'panel') copy.delete('view')
    else copy.set('view', next)
    setParams(copy)
  }
  const setSort = (next: AssetSort) => {
    const copy = new URLSearchParams(params)
    if (next === 'name') copy.delete('sort')
    else copy.set('sort', next)
    setParams(copy)
  }
  const setFilter = (key: FilterKey, values: string[]) => setParams(writeFilter(params, key, values))

  const openPane = useCallback(
    (mode: 'new' | 'edit', parent?: string | null) => {
      const next = new URLSearchParams(params)
      next.set('pane', mode)
      if (parent) next.set('parent', parent)
      else next.delete('parent')
      setParams(next)
    },
    [params, setParams],
  )
  const closePane = () => {
    const next = new URLSearchParams(params)
    next.delete('pane')
    next.delete('parent')
    setParams(next)
    create.reset()
    update.reset()
  }

  const openAsset = (asset: { id: string }) => navigate(`/assets/${asset.id}${listSearch(params)}`)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event) || event.metaKey || event.ctrlKey || event.altKey) return
      if (event.key === '/') {
        event.preventDefault()
        searchRef.current?.focus()
      } else if (event.key === 'n' && canManage && !paneOpen && !statusOpen && !typeDialog) {
        event.preventDefault()
        openPane('new')
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [canManage, paneOpen, statusOpen, typeDialog, openPane])

  const submitForm = async (payload: AssetPayload) => {
    try {
      if (pane === 'edit' && assetId) {
        await update.mutateAsync(payload)
        toast.success('Asset updated')
        closePane()
      } else {
        const created = await create.mutateAsync(payload)
        toast.success('Asset created', created.name)
        closePane()
        navigate(`/assets/${created.id}${listSearch(params)}`)
      }
    } catch (error) {
      if (error instanceof ApiError && (error.isValidation || typeof error.extra.field === 'string')) return
      toast.error('Could not save asset', errorMessage(error))
    }
  }

  const submitStatus = async (payload: AssetStatusPayload) => {
    try {
      const result = await changeStatus.mutateAsync(payload)
      toast.success('Status updated', `${result.asset.name} is now ${ASSET_STATUS_LABELS[result.asset.status as keyof typeof ASSET_STATUS_LABELS] ?? result.asset.status}.`)
      setStatusOpen(false)
      changeStatus.reset()
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not change status', errorMessage(error))
    }
  }

  /* List region ------------------------------------------------------------- */

  const loadError = view === 'hierarchy' ? hierarchy.isError : list.isError
  const loading = view === 'hierarchy' ? hierarchy.isPending : list.isPending
  const retry = () => void (view === 'hierarchy' ? hierarchy.refetch() : list.refetch())
  const count = view === 'hierarchy' ? countTree(tree) : (list.data?.total ?? rows.length)
  const isEmpty = view === 'hierarchy' ? tree.length === 0 : rows.length === 0
  const noResults = isEmpty && (Boolean(debounced) || filtersActive)

  const noResultsState = (
    <EmptyState
      compact
      illustration="search"
      title="No assets match"
      description={debounced ? `Nothing matches “${debounced}” with the current filters.` : 'Nothing matches the current filters.'}
      action={
        <Button
          size="sm"
          onClick={() => {
            setQuery('')
            setDebounced('')
            setParams(clearFilters(params))
          }}
        >
          Clear search and filters
        </Button>
      }
    />
  )
  const emptyState = (
    <EmptyState
      compact
      illustration="box"
      title="No assets yet"
      description="Track the printers, rovers, tools and test rigs your chapter maintains."
      action={canManage ? <Button variant="primary" size="sm" leadingIcon={<Plus size={16} />} onClick={() => openPane('new')}>Add the first asset</Button> : undefined}
    />
  )

  const listContent = loading ? (
    <SkeletonRows rows={8} />
  ) : loadError ? (
    <div className={styles.padded}>
      <InlineAlert tone="danger" title="Assets could not be loaded" actions={<Button size="sm" onClick={retry}>Retry</Button>}>
        {errorMessage(view === 'hierarchy' ? hierarchy.error : list.error)}
      </InlineAlert>
    </div>
  ) : noResults ? (
    noResultsState
  ) : isEmpty ? (
    emptyState
  ) : view === 'table' ? (
    <AssetTable rows={rows} sort={sort} onSortChange={setSort} onOpen={openAsset} selectedId={assetId} />
  ) : view === 'hierarchy' ? (
    <AssetTree nodes={tree} selectedId={assetId} onOpen={openAsset} />
  ) : (
    <ul aria-label="Assets">
      {rows.map((asset) => (
        <li key={asset.id}>
          <AssetRow asset={asset} selected={asset.id === assetId} to={`/assets/${asset.id}${listSearch(params)}`} />
        </li>
      ))}
    </ul>
  )

  /* Detail region ---------------------------------------------------------- */

  const detail = !assetId ? (
    <EmptyState illustration="box" title="Select an asset" description="Choose an asset on the left to see its details, hierarchy, open work and history." />
  ) : selected.isPending ? (
    <div className={styles.detailPad}>
      <SkeletonBlock lines={5} />
    </div>
  ) : selected.isError ? (
    <div className={styles.detailPad}>
      {selected.error instanceof ApiError && selected.error.isNotFound ? (
        <EmptyState illustration="search" title="Asset not found" description="It may have been retired, moved to a private project, or the link is out of date." action={<Button onClick={() => navigate(`/assets${listSearch(params)}`)}>Back to assets</Button>} />
      ) : (
        <InlineAlert tone="danger" title="Could not load this asset" actions={<Button size="sm" onClick={() => void selected.refetch()}>Retry</Button>}>
          {errorMessage(selected.error)}
        </InlineAlert>
      )}
    </div>
  ) : (
    <AssetDetail
      asset={selected.data}
      canManage={canOn(session, 'asset.manage', selected.data)}
      canChangeStatus={canOn(session, 'asset.status.update', selected.data) || canOn(session, 'asset.manage', selected.data)}
      canCreateWorkOrder={canCreateWorkOrder}
      onEdit={() => openPane('edit')}
      onAddChild={() => openPane('new', selected.data.id)}
      onChangeStatus={() => setStatusOpen(true)}
    />
  )

  const parentForNew = paneParent ? (rows.find((a) => a.id === paneParent) ?? (selected.data?.id === paneParent ? selected.data : null)) : null
  const formInitial: Partial<Asset> | null = pane === 'edit' ? (selected.data ?? null) : paneParent ? { parent_id: paneParent, project: parentForNew?.project ?? null, location: parentForNew?.location ?? null } : null

  const chipOption = (value: string, label: string) => ({ value, label })

  return (
    <Page>
      <PageHeader
        title="Assets"
        viewSelector={
          <ViewSelector<AssetView>
            label="View"
            value={view}
            onChange={setView}
            options={[
              { value: 'panel', label: 'Panel', description: 'List with details alongside' },
              { value: 'table', label: 'Table', description: 'Sortable columns' },
              { value: 'hierarchy', label: 'Hierarchy', description: 'Assets nested under their parents' },
            ]}
          />
        }
        actions={
          <>
            <SearchField ref={searchRef} value={query} onChange={setQuery} onDebouncedChange={setDebounced} placeholder="Search assets" shortcutHint="/" />
            {canManage && (
              <SplitButton
                label="New Asset"
                menuLabel="More ways to add"
                leadingIcon={<Plus size={16} />}
                onClick={() => openPane('new')}
                items={[
                  { key: 'child', label: 'New sub-asset of selected', disabled: !assetId, onSelect: () => openPane('new', assetId) },
                  { key: 'type', label: 'New asset type', onSelect: () => setTypeDialog(true) },
                  { key: 'sep', type: 'separator' },
                  { key: 'locations', label: 'Go to Locations', onSelect: () => navigate('/locations') },
                ]}
              />
            )}
          </>
        }
        filters={
          <>
            <FilterChip label="Status" options={ASSET_STATUSES.map((value) => chipOption(value, ASSET_STATUS_LABELS[value]))} value={filters.status} onChange={(v) => setFilter('status', v)} />
            <FilterChip label="Criticality" options={ASSET_CRITICALITIES.map((value) => chipOption(value, ASSET_CRITICALITY_LABELS[value]))} value={filters.criticality} onChange={(v) => setFilter('criticality', v)} />
            <FilterChip label="Type" options={(types.data ?? []).map((type) => ({ value: type.id, label: type.name, color: type.color, count: type.asset_count }))} value={filters.type} onChange={(v) => setFilter('type', v)} loading={types.isPending} searchable emptyText="No asset types yet" />
            <FilterChip label="Project" options={projects.options.map((o) => chipOption(o.value, o.label))} value={filters.project} onChange={(v) => setFilter('project', v)} loading={projects.isLoading} searchable emptyText="No projects" />
            <FilterChip label="Location" options={(locations.data?.items ?? []).map((l) => chipOption(l.id, l.path.join(' › ')))} value={filters.location} onChange={(v) => setFilter('location', v)} loading={locations.isPending} searchable emptyText="No locations" />
            <FilterChip label="Team" options={teams.options.map((o) => chipOption(o.value, o.label))} value={filters.team} onChange={(v) => setFilter('team', v)} loading={teams.isLoading} searchable emptyText="No teams" />
            {(filtersActive || debounced) && (
              <Button
                variant="link"
                size="sm"
                onClick={() => {
                  setQuery('')
                  setDebounced('')
                  setParams(clearFilters(params))
                }}
              >
                Clear all
              </Button>
            )}
          </>
        }
      />
      <MasterDetailLayout
        detailOpen={Boolean(assetId)}
        backTo={`/assets${listSearch(params)}`}
        backLabel="Back to assets"
        listToolbar={
          <>
            <span>{loading ? '' : `${count} ${count === 1 ? 'asset' : 'assets'}`}</span>
            <ListToolbarSpacer />
            {(list.isFetching && !list.isPending) || (hierarchy.isFetching && !hierarchy.isPending) ? <span aria-live="polite">Updating…</span> : null}
          </>
        }
        list={listContent}
        detail={
          <>
            {detail}
            {paneOpen && (
              <AssetForm
                open
                mode={pane === 'edit' ? 'edit' : 'create'}
                initial={formInitial}
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
      {selected.data && (
        <AssetStatusDialog
          open={statusOpen}
          asset={selected.data}
          submitting={changeStatus.isPending}
          error={changeStatus.error}
          onSubmit={submitStatus}
          onClose={() => {
            setStatusOpen(false)
            changeStatus.reset()
          }}
        />
      )}
      <AssetTypeDialog open={typeDialog} onClose={() => setTypeDialog(false)} />
    </Page>
  )
}

function countTree(nodes: AssetHierarchyNode[]): number {
  return nodes.reduce((sum, node) => sum + 1 + countTree(node.children ?? []), 0)
}

function AssetRow({ asset, selected, to }: { asset: Asset; selected: boolean; to: string }) {
  return (
    <ListRow
      to={to}
      selected={selected}
      leading={<Boxes size={16} style={{ color: 'var(--color-text-muted)' }} aria-hidden="true" />}
      title={
        <span className={styles.rowTitle}>
          <span>{asset.name}</span>
          {asset.code && <span className={styles.code}>{asset.code}</span>}
        </span>
      }
      meta={
        <>
          <StatusBadge status={asset.status} size="sm" />
          <CriticalityBadge criticality={asset.criticality} size="sm" />
          {asset.location && <span>{asset.location.name}</span>}
          {asset.types.length > 0 && <TypeChips types={asset.types} max={2} />}
          <span>{asset.open_work_order_count ?? 0} open work</span>
        </>
      }
      trailing={<ChevronRight size={16} style={{ color: 'var(--color-text-disabled)' }} aria-hidden="true" />}
      data-testid="asset-row"
    />
  )
}
