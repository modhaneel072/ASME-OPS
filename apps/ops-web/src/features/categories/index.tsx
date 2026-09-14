import { ClipboardPlus, MoreHorizontal, Pencil, Plus, Tag, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ApiError, errorMessage } from '@/api/client'
import type { Category, CategoryPayload } from '@/api/contracts/categories'
import { useCategories, useCategory, useCreateCategory, useDeleteCategory, useUpdateCategory } from '@/api/queries/categories'
import { formatDateTime } from '@/lib/dates'
import { useCan } from '@/lib/permissions'
import {
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
import { CategoryForm } from './CategoryForm'
import { CategoryIconTile, iconLabel } from './icons'
import styles from './categories.module.css'

type Sort = 'name' | '-usage' | '-created_at'
const SORTS: readonly Sort[] = ['name', '-usage', '-created_at']
const DEFAULT_SORT: Sort = 'name'

function parseSort(raw: string | null): Sort {
  return raw && (SORTS as readonly string[]).includes(raw) ? (raw as Sort) : DEFAULT_SORT
}

function isTypingTarget(event: KeyboardEvent): boolean {
  const target = event.target as HTMLElement | null
  return Boolean(target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable))
}

function workOrdersLabel(count: number): string {
  return `${count} ${count === 1 ? 'work order' : 'work orders'}`
}

export default function CategoriesPage() {
  const { categoryId } = useParams<{ categoryId: string }>()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()
  const can = useCan()
  const canManage = can('category.manage')
  const canCreateWorkOrder = can('work_order.create')

  // The URL is the source of truth for search and sort; the input keeps what is being typed.
  const urlQuery = params.get('q') ?? ''
  const sort = parseSort(params.get('sort'))
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

  const setSort = (value: Sort) => {
    const next = new URLSearchParams(params)
    if (value === DEFAULT_SORT) next.delete('sort')
    else next.set('sort', value)
    setParams(next, { replace: true })
  }

  const list = useCategories({ q: urlQuery || undefined, sort })
  const selected = useCategory(categoryId)
  const items = useMemo(() => list.data?.items ?? [], [list.data])

  const pane = params.get('pane') // 'new' | 'edit' | null
  const paneOpen = (pane === 'new' && canManage) || (pane === 'edit' && canManage && Boolean(selected.data))

  const create = useCreateCategory()
  const update = useUpdateCategory(categoryId ?? '')
  const remove = useDeleteCategory()
  const [confirmDelete, setConfirmDelete] = useState(false)

  /** Current search/sort without the pane, for row links and post-create navigation. */
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

  const submitForm = async (values: CategoryPayload) => {
    try {
      if (pane === 'edit' && categoryId) {
        await update.mutateAsync(values)
        toast.success('Category updated')
        closePane()
      } else {
        const created = await create.mutateAsync(values)
        toast.success('Category created', created.name)
        create.reset()
        navigate(`/categories/${created.id}${listSearch}`)
      }
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not save category', errorMessage(error))
    }
  }

  const onDelete = async () => {
    if (!categoryId) return
    try {
      await remove.mutateAsync(categoryId)
      toast.success('Category deleted')
      setConfirmDelete(false)
      navigate(`/categories${listSearch}`)
    } catch (error) {
      setConfirmDelete(false)
      if (error instanceof ApiError && error.code === 'category_in_use') {
        const used = (error.extra.usage as { work_orders?: number } | undefined)?.work_orders
        toast.error('Category is in use', used ? `${workOrdersLabel(used)} still use it. Re-categorise them first.` : error.message)
      } else {
        toast.error('Could not delete category', errorMessage(error))
      }
    }
  }

  const listContent = list.isPending ? (
    <SkeletonRows rows={8} />
  ) : list.isError ? (
    <div style={{ padding: 'var(--space-4)' }}>
      <InlineAlert
        tone="danger"
        title="Categories could not be loaded"
        actions={
          <Button size="sm" onClick={() => void list.refetch()}>
            Retry
          </Button>
        }
      >
        {errorMessage(list.error)}
      </InlineAlert>
    </div>
  ) : items.length === 0 && urlQuery ? (
    <EmptyState
      compact
      illustration="search"
      title="No categories match"
      description={`Nothing matches “${urlQuery}”.`}
      action={
        <Button size="sm" onClick={() => setQuery('')}>
          Clear search
        </Button>
      }
    />
  ) : items.length === 0 ? (
    <EmptyState
      compact
      illustration="tag"
      title="No categories yet"
      description="Categories tag work orders so the chapter can see what kind of work is happening."
      action={
        canManage ? (
          <Button variant="primary" size="sm" leadingIcon={<Plus size={16} />} onClick={() => openPane('new')}>
            Add the first category
          </Button>
        ) : undefined
      }
    />
  ) : (
    <ul aria-label="Categories">
      {items.map((category) => {
        const used = category.usage?.work_orders ?? 0
        return (
          <li key={category.id}>
            <ListRow
              to={`/categories/${category.id}${listSearch}`}
              selected={category.id === categoryId}
              leading={<CategoryIconTile color={category.color} icon={category.icon} />}
              title={category.name}
              meta={category.description ? <span>{category.description}</span> : undefined}
              trailing={<span className={styles.rowUsage}>{workOrdersLabel(used)}</span>}
              data-testid="category-row"
            />
          </li>
        )
      })}
    </ul>
  )

  const detail = !categoryId ? (
    <EmptyState illustration="tag" title="Select a category" description="Choose a category on the left to see its colour, icon and how much work uses it." />
  ) : selected.isPending ? (
    <div style={{ padding: 'var(--space-6)' }}>
      <SkeletonBlock lines={5} />
    </div>
  ) : selected.isError ? (
    <div style={{ padding: 'var(--space-6)' }}>
      {selected.error instanceof ApiError && selected.error.isNotFound ? (
        <EmptyState illustration="search" title="Category not found" description="It may have been deleted or the link is out of date." action={<Button onClick={() => navigate('/categories')}>Back to categories</Button>} />
      ) : (
        <InlineAlert
          tone="danger"
          title="Could not load this category"
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
    <CategoryDetail category={selected.data} canManage={canManage} canCreateWorkOrder={canCreateWorkOrder} onEdit={() => openPane('edit')} onDelete={() => setConfirmDelete(true)} />
  )

  return (
    <Page>
      <PageHeader
        title="Categories"
        viewSelector={
          <ViewSelector<Sort>
            label="Sort"
            value={sort}
            onChange={setSort}
            options={[
              { value: 'name', label: 'Name A–Z' },
              { value: '-usage', label: 'Most used' },
              { value: '-created_at', label: 'Newest' },
            ]}
          />
        }
        actions={
          <>
            <SearchField ref={searchRef} value={query} onChange={setQuery} onDebouncedChange={syncSearchToUrl} placeholder="Search categories" shortcutHint="/" />
            {canManage && (
              <SplitButton
                label="New Category"
                leadingIcon={<Plus size={16} />}
                onClick={() => openPane('new')}
                menuLabel="More category actions"
                items={[
                  { key: 'work-orders', label: 'Go to Work Orders', onSelect: () => navigate('/work-orders') },
                  { key: 'setup', label: 'Back to Setup Center', onSelect: () => navigate('/setup') },
                ]}
              />
            )}
          </>
        }
      />
      <MasterDetailLayout
        detailOpen={Boolean(categoryId)}
        backTo={`/categories${listSearch}`}
        listToolbar={
          <>
            <span>{list.data ? `${list.data.total ?? items.length} ${(list.data.total ?? items.length) === 1 ? 'category' : 'categories'}` : ''}</span>
            <ListToolbarSpacer />
            {list.isFetching && !list.isPending && <span aria-live="polite">Updating…</span>}
          </>
        }
        list={listContent}
        detail={
          <>
            {detail}
            <CategoryForm
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
      <Dialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        size="sm"
        title="Delete this category?"
        description="Categories still used by work orders cannot be deleted; re-categorise that work first."
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

function CategoryDetail({
  category,
  canManage,
  canCreateWorkOrder,
  onEdit,
  onDelete,
}: {
  category: Category
  canManage: boolean
  canCreateWorkOrder: boolean
  onEdit: () => void
  onDelete: () => void
}) {
  const navigate = useNavigate()
  const used = category.usage?.work_orders ?? 0
  const created = category.created_at ? `${formatDateTime(category.created_at)}${category.created_by ? ` by ${category.created_by.name}` : ''}` : '—'
  const hasActions = canCreateWorkOrder || canManage

  return (
    <DetailPanel
      eyebrow={
        <>
          <Tag size={12} aria-hidden="true" />
          Category
        </>
      }
      title={
        <span className={styles.titleRow}>
          <CategoryIconTile color={category.color} icon={category.icon} size="lg" />
          {category.name}
        </span>
      }
      subtitle={category.description || undefined}
      actions={
        hasActions ? (
          <>
            {canCreateWorkOrder && (
              <Button variant="primary" leadingIcon={<ClipboardPlus size={16} />} onClick={() => navigate(`/work-orders/new?category=${category.id}`)}>
                Use in New Work Order
              </Button>
            )}
            {canManage && (
              <>
                <Button leadingIcon={<Pencil size={16} />} onClick={onEdit}>
                  Edit
                </Button>
                <DropdownMenu
                  align="end"
                  label="More actions"
                  items={[{ key: 'delete', label: 'Delete category', icon: <Trash2 size={16} />, destructive: true, onSelect: onDelete }]}
                  trigger={(props) => (
                    <IconButton {...props} ref={props.ref} label="More actions">
                      <MoreHorizontal size={18} />
                    </IconButton>
                  )}
                />
              </>
            )}
          </>
        ) : undefined
      }
    >
      <Stack>
        <Card title="Details">
          <FieldList
            items={[
              {
                label: 'Colour',
                value: (
                  <span className={styles.inlineValue}>
                    <span className={styles.swatchDot} style={{ background: category.color }} aria-hidden="true" />
                    <span className="mono">{category.color}</span>
                  </span>
                ),
              },
              {
                label: 'Icon',
                value: (
                  <span className={styles.inlineValue}>
                    <CategoryIconTile color={category.color} icon={category.icon} size="sm" />
                    {iconLabel(category.icon)}
                  </span>
                ),
              },
              { label: 'Created', value: created },
              { label: 'Updated', value: formatDateTime(category.updated_at) },
            ]}
          />
        </Card>
        <Card title="Usage">
          <div className={styles.usage}>
            <span className={styles.usageNumber}>{used}</span>
            <Link to={`/work-orders?filter[category]=${category.id}`}>Used by {workOrdersLabel(used)}</Link>
          </div>
          <p className={styles.usageHint}>{used === 0 ? 'No work order carries this category yet.' : 'Opens the work order list filtered to this category.'}</p>
        </Card>
      </Stack>
    </DetailPanel>
  )
}
