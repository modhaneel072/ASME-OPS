import { AlertTriangle, ChevronRight, Flag, FolderKanban, Lock, Plus } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ApiError, errorMessage } from '@/api/client'
import { labelFor } from '@/api/contracts/common'
import { PROJECT_STATUSES, RISK_LABELS, RISK_LEVELS, toProjectPayload, type Project, type ProjectInput } from '@/api/contracts/projects'
import { useArchiveProject, useCreateProject, useProject, useProjects, useRestoreProject, useUpdateProject } from '@/api/queries/projects'
import { useTeamOptions } from '@/api/queries/teams'
import { usePeopleOptions } from '@/api/queries/users'
import { formatDate } from '@/lib/dates'
import { useCan } from '@/lib/permissions'
import { Avatar, Badge, Button, Dialog, EmptyState, FilterChip, InlineAlert, ListRow, ListToolbarSpacer, MasterDetailLayout, Page, PageHeader, SearchField, SkeletonBlock, SkeletonRows, SplitButton, StatusBadge, ViewSelector, useToast, type FilterOption } from '@/ui'
import { ProjectDetail } from './ProjectDetail'
import { ProjectForm } from './ProjectForm'
import { isProjectTab, newWorkOrderHref, workOrdersHref, type ProjectTab } from './shared'
import styles from './projects.module.css'

type View = 'active' | 'all' | 'archived'
type Sort = 'name' | '-updated_at' | 'target_date' | '-risk'
const SORTS: Array<{ value: Sort; label: string }> = [
  { value: 'name', label: 'Name A–Z' },
  { value: '-updated_at', label: 'Recently updated' },
  { value: 'target_date', label: 'Target date' },
  { value: '-risk', label: 'Highest risk' },
]
const FILTER_KEYS = ['lead', 'status', 'risk', 'team', 'academic_year', 'competition'] as const
type FilterKey = (typeof FILTER_KEYS)[number]

function isTyping(event: KeyboardEvent) {
  const target = event.target as HTMLElement | null
  return Boolean(target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable))
}

export default function ProjectsPage() {
  const { projectId, tab: tabParam } = useParams<{ projectId: string; tab: string }>()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const toast = useToast()
  const can = useCan()
  const canCreate = can('project.create')
  const canCreateWork = can('work_order.create')

  const view: View = params.get('view') === 'all' || params.get('view') === 'archived' ? (params.get('view') as View) : 'active'
  const sort: Sort = (SORTS.find((s) => s.value === params.get('sort'))?.value ?? 'name') as Sort
  const tab: ProjectTab = isProjectTab(tabParam) ? tabParam : 'overview'
  const filters = useMemo(() => {
    const out = {} as Record<FilterKey, string[]>
    for (const key of FILTER_KEYS) out[key] = (params.get(`filter[${key}]`) ?? '').split(',').filter(Boolean)
    return out
  }, [params])

  const [query, setQuery] = useState(params.get('q') ?? '')
  const [debounced, setDebounced] = useState(query)
  const searchRef = useRef<HTMLInputElement>(null)

  const updateParams = (mutate: (next: URLSearchParams) => void, replace = false) => {
    const next = new URLSearchParams(params)
    mutate(next)
    setParams(next, { replace })
  }
  useEffect(() => {
    if ((params.get('q') ?? '') === debounced) return
    updateParams((next) => (debounced ? next.set('q', debounced) : next.delete('q')), true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced])

  const setFilter = (key: FilterKey, values: string[]) => updateParams((next) => (values.length ? next.set(`filter[${key}]`, values.join(',')) : next.delete(`filter[${key}]`)))
  const clearFilters = () => {
    setQuery('')
    updateParams((next) => {
      for (const key of FILTER_KEYS) next.delete(`filter[${key}]`)
      next.delete('q')
    })
  }
  const activeFilterCount = FILTER_KEYS.reduce((count, key) => count + (filters[key].length ? 1 : 0), 0)

  const list = useProjects({
    view,
    q: debounced || undefined,
    lead: filters.lead,
    status: filters.status,
    risk: filters.risk,
    team: filters.team,
    academic_year: filters.academic_year,
    competition: filters.competition[0],
    sort,
  })
  const projects = useMemo(() => list.data?.items ?? [], [list.data])
  const selected = useProject(projectId)

  const people = usePeopleOptions()
  const teams = useTeamOptions()
  const leadOptions = useMemo<FilterOption[]>(() => people.options.map((o) => ({ value: String(o.value), label: o.label })), [people.options])
  const teamOptions = useMemo<FilterOption[]>(() => teams.options.map((o) => ({ value: o.value, label: o.label })), [teams.options])
  const distinct = (values: Array<string | null | undefined>, selectedValues: string[]) => {
    const set = new Set<string>(selectedValues)
    for (const value of values) if (value) set.add(value)
    return [...set].sort().map((value) => ({ value, label: value }))
  }
  const yearOptions = useMemo(() => distinct(projects.map((p) => p.academic_year), filters.academic_year), [projects, filters.academic_year])
  const competitionOptions = useMemo(() => distinct(projects.map((p) => p.competition), filters.competition), [projects, filters.competition])

  /* Create / edit pane ---------------------------------------------------- */
  const pane = params.get('pane')
  const paneOpen = pane === 'new' || (pane === 'edit' && Boolean(selected.data))
  const create = useCreateProject()
  const update = useUpdateProject(projectId ?? '')
  const archive = useArchiveProject()
  const restore = useRestoreProject()
  const [confirmArchive, setConfirmArchive] = useState(false)

  const openPane = (mode: 'new' | 'edit') => updateParams((next) => next.set('pane', mode))
  const closePane = () => {
    updateParams((next) => next.delete('pane'))
    create.reset()
    update.reset()
  }

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTyping(event) || event.metaKey || event.ctrlKey || event.altKey) return
      if (event.key === '/') {
        event.preventDefault()
        searchRef.current?.focus()
      } else if (event.key === 'n' && canCreate && !paneOpen) {
        event.preventDefault()
        openPane('new')
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canCreate, paneOpen, params])

  const search = params.toString() ? `?${params.toString()}` : ''
  const goToProject = (id: string, nextTab: ProjectTab = 'overview') => navigate(`/projects/${id}${nextTab === 'overview' ? '' : `/${nextTab}`}${search}`)

  const submitForm = async (values: ProjectInput) => {
    const payload = toProjectPayload(values)
    try {
      if (pane === 'edit' && projectId) {
        await update.mutateAsync(payload)
        toast.success('Project updated')
        closePane()
      } else {
        const created = await create.mutateAsync(payload)
        toast.success('Project created', `${created.name} (${created.code})`)
        const next = new URLSearchParams(params)
        next.delete('pane')
        navigate(`/projects/${created.id}${next.toString() ? `?${next.toString()}` : ''}`)
      }
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not save project', errorMessage(error))
    }
  }

  const onArchive = async () => {
    if (!projectId) return
    try {
      await archive.mutateAsync(projectId)
      toast.success('Project archived', 'Its work orders stay visible.')
      setConfirmArchive(false)
    } catch (error) {
      setConfirmArchive(false)
      toast.error('Could not archive project', errorMessage(error))
    }
  }
  const onRestore = async () => {
    if (!projectId) return
    try {
      await restore.mutateAsync(projectId)
      toast.success('Project restored')
    } catch (error) {
      toast.error('Could not restore project', errorMessage(error))
    }
  }

  /* List ------------------------------------------------------------------- */
  const hasNarrowing = Boolean(debounced) || activeFilterCount > 0
  const listContent = list.isPending ? (
    <SkeletonRows rows={8} avatar />
  ) : list.isError ? (
    <div className={styles.padded}>
      <InlineAlert
        tone="danger"
        title="Projects could not be loaded"
        actions={
          <Button size="sm" onClick={() => void list.refetch()}>
            Retry
          </Button>
        }
      >
        {errorMessage(list.error)}
      </InlineAlert>
    </div>
  ) : projects.length === 0 && hasNarrowing ? (
    <EmptyState compact illustration="search" title="No projects match" description={debounced ? `Nothing matches “${debounced}” with the current filters.` : 'Nothing matches the current filters.'} action={<Button size="sm" onClick={clearFilters}>Clear search and filters</Button>} />
  ) : projects.length === 0 ? (
    <EmptyState
      compact
      illustration="folder"
      title={view === 'archived' ? 'No archived projects' : 'No projects yet'}
      description={view === 'archived' ? 'Archived projects keep their work orders and history and show up here.' : 'Projects group the chapter’s work orders, milestones, teams and documents around one effort.'}
      action={canCreate && view !== 'archived' ? <Button variant="primary" size="sm" leadingIcon={<Plus size={16} />} onClick={() => openPane('new')}>Create the first project</Button> : undefined}
    />
  ) : (
    <ul aria-label="Projects">
      {projects.map((project) => (
        <li key={project.id}>
          <ProjectRow project={project} selected={project.id === projectId} to={`/projects/${project.id}${tab !== 'overview' && project.id === projectId ? `/${tab}` : ''}${search}`} />
        </li>
      ))}
    </ul>
  )

  /* Detail ----------------------------------------------------------------- */
  const detail = !projectId ? (
    <EmptyState illustration="folder" title="Select a project" description="Choose a project on the left to see its health, work, milestones, teams and documents." />
  ) : selected.isPending ? (
    <div className={styles.paddedLarge}>
      <SkeletonBlock lines={5} />
    </div>
  ) : selected.isError ? (
    <div className={styles.paddedLarge}>
      {selected.error instanceof ApiError && selected.error.isNotFound ? (
        <EmptyState illustration="search" title="Project not found" description="It may be private, deleted, or the link is out of date." action={<Button onClick={() => navigate('/projects')}>Back to projects</Button>} />
      ) : (
        <InlineAlert
          tone="danger"
          title="Could not load this project"
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
    <ProjectDetail detail={selected.data} tab={tab} onTabChange={(next) => goToProject(selected.data.project.id, next)} onEdit={() => openPane('edit')} onArchive={() => setConfirmArchive(true)} onRestore={() => void onRestore()} />
  )

  return (
    <Page>
      <PageHeader
        title="Projects"
        viewSelector={
          <ViewSelector<View>
            label="View"
            value={view}
            onChange={(next) => updateParams((p) => (next === 'active' ? p.delete('view') : p.set('view', next)))}
            options={[
              { value: 'active', label: 'Active', description: 'Projects that are not archived' },
              { value: 'all', label: 'All', description: 'Every project you can see' },
              { value: 'archived', label: 'Archived', description: 'Archived projects only' },
            ]}
          />
        }
        actions={
          <>
            <SearchField ref={searchRef} value={query} onChange={setQuery} onDebouncedChange={setDebounced} placeholder="Search projects" shortcutHint="/" />
            {canCreate && (
              <SplitButton
                label="New Project"
                menuLabel="More create options"
                leadingIcon={<Plus size={16} />}
                onClick={() => openPane('new')}
                items={[
                  { key: 'work', label: 'Go to Work Orders', onSelect: () => navigate(projectId ? workOrdersHref(projectId) : '/work-orders') },
                  ...(canCreateWork ? [{ key: 'new-work', label: 'New work order', onSelect: () => navigate(projectId ? newWorkOrderHref(projectId) : '/work-orders/new') }] : []),
                ]}
              />
            )}
          </>
        }
        filters={
          <>
            <FilterChip label="Lead" options={leadOptions} value={filters.lead} onChange={(v) => setFilter('lead', v)} searchable loading={people.isLoading} emptyText="No members" />
            <FilterChip label="Status" options={[...PROJECT_STATUSES, 'archived'].map((status) => ({ value: status, label: labelFor(status) }))} value={filters.status} onChange={(v) => setFilter('status', v)} />
            <FilterChip label="Risk" options={RISK_LEVELS.map((level) => ({ value: level, label: RISK_LABELS[level] }))} value={filters.risk} onChange={(v) => setFilter('risk', v)} />
            <FilterChip label="Team" options={teamOptions} value={filters.team} onChange={(v) => setFilter('team', v)} searchable loading={teams.isLoading} emptyText="No teams" />
            <FilterChip label="Academic year" options={yearOptions} value={filters.academic_year} onChange={(v) => setFilter('academic_year', v)} emptyText="No academic years recorded" />
            <FilterChip label="Competition" options={competitionOptions} value={filters.competition} onChange={(v) => setFilter('competition', v)} multiple={false} emptyText="No competitions recorded" />
            {activeFilterCount > 0 && (
              <Button variant="link" size="sm" onClick={clearFilters}>
                Clear filters
              </Button>
            )}
          </>
        }
      />
      <MasterDetailLayout
        detailOpen={Boolean(projectId)}
        backTo="/projects"
        backLabel="Back to projects"
        listToolbar={
          <>
            <span>{list.data ? `${list.data.total ?? projects.length} ${(list.data.total ?? projects.length) === 1 ? 'project' : 'projects'}` : ''}</span>
            <ListToolbarSpacer />
            {list.isFetching && !list.isPending && <span aria-live="polite">Updating…</span>}
            <ViewSelector<Sort> label="Sort" value={sort} onChange={(next) => updateParams((p) => (next === 'name' ? p.delete('sort') : p.set('sort', next)))} options={SORTS} />
          </>
        }
        list={listContent}
        detail={
          <>
            {detail}
            <ProjectForm open={paneOpen} mode={pane === 'edit' ? 'edit' : 'create'} initial={pane === 'edit' ? selected.data?.project : null} submitting={create.isPending || update.isPending} error={pane === 'edit' ? update.error : create.error} onSubmit={submitForm} onClose={closePane} />
          </>
        }
      />
      <Dialog
        open={confirmArchive}
        onClose={() => setConfirmArchive(false)}
        size="sm"
        title="Archive this project?"
        description="Archiving hides the project from the Active view and stops new milestones. Its work orders, documents and history stay visible, and you can restore it at any time."
        preventClose={archive.isPending}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmArchive(false)} disabled={archive.isPending}>
              Cancel
            </Button>
            <Button variant="primary" onClick={() => void onArchive()} loading={archive.isPending} data-autofocus>
              Archive project
            </Button>
          </>
        }
      />
    </Page>
  )
}

function ProjectRow({ project, selected, to }: { project: Project; selected: boolean; to: string }) {
  const stats = project.stats
  const completion = Math.max(0, Math.min(100, Math.round(stats?.completion_percent ?? 0)))
  const next = stats?.next_milestone
  const overdue = stats?.overdue_work_orders ?? 0
  return (
    <ListRow
      to={to}
      selected={selected}
      leading={<FolderKanban size={16} style={{ color: 'var(--color-text-muted)' }} aria-hidden="true" />}
      title={
        <span className={styles.rowTitle}>
          <span className={styles.rowName}>{project.name}</span>
          <Badge tone="outline" size="sm" className="mono">
            {project.code}
          </Badge>
          {project.visibility === 'private' && <Lock size={13} className={styles.rowLock} aria-label="Private project" role="img" />}
        </span>
      }
      meta={
        <span className={styles.rowMeta}>
          <StatusBadge status={project.status} size="sm" />
          {project.lead ? <Avatar name={project.lead.name} src={project.lead.avatar_url} /> : <span className={styles.muted}>No lead</span>}
          <span className={styles.rowProgress} title={`${completion}% complete`}>
            <span className={styles.rowProgressTrack} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={completion} aria-label={`${project.name} completion`}>
              <span className={styles.rowProgressBar} style={{ width: `${completion}%` }} />
            </span>
            <span className="mono">{completion}%</span>
          </span>
          {next && (
            <span className={styles.rowMilestone} title={`Next milestone: ${next.name}`}>
              <Flag size={12} aria-hidden="true" />
              {next.name}
              {next.due_date && <> · {formatDate(next.due_date, 'MMM d')}</>}
            </span>
          )}
          {overdue > 0 && (
            <Badge tone="danger" size="sm">
              <AlertTriangle size={12} aria-hidden="true" /> {overdue} overdue
            </Badge>
          )}
        </span>
      }
      trailing={<ChevronRight size={16} style={{ color: 'var(--color-text-disabled)' }} aria-hidden="true" />}
      data-testid="project-row"
    />
  )
}
