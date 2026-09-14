import { ArrowRight, Plus } from 'lucide-react'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ApiError, errorMessage } from '@/api/client'
import { PRIORITY_LABELS, WORK_TYPE_LABELS, labelFor, type Priority, type WorkType } from '@/api/contracts/common'
import { DEFAULT_RANGE, isRangeKey, type OperationsReport, type OperationsReportParams, type RangeKey, type WeekBucket } from '@/api/contracts/reports'
import { useProjectOptions } from '@/api/queries/projects'
import { useOperationsReport } from '@/api/queries/reports'
import { useTeamOptions } from '@/api/queries/teams'
import { cn } from '@/lib/cn'
import { formatMoney } from '@/lib/dates'
import { useCan } from '@/lib/permissions'
import { Avatar, Button, ChartFrame, EmptyState, FilterChip, InlineAlert, LinkButton, Page, PageHeader, PriorityBadge, ReportCard, ReportGrid, Skeleton, useToast, type FilterOption } from '@/ui'
import { BarRows, GroupedBars, Legend, SegmentBar } from './charts'
import { DOT, formatCount, formatHours, formatPercent, formatRangeLabel, formatWeek, joinList, pluralize, truncate } from './format'
import { RangeControl, type RangeSelection } from './RangeControl'
import styles from './reporting.module.css'

/* Colour assignments (tokens only) ------------------------------------------ */

const COLOR = {
  primary: 'var(--color-primary)',
  purple: 'var(--color-purple)',
  success: 'var(--color-success)',
  warning: 'var(--color-warning)',
  danger: 'var(--color-danger)',
  dangerStrong: 'var(--color-danger-text)',
  neutral: 'var(--color-neutral)',
  faint: 'var(--color-border-strong)',
  disabled: 'var(--color-text-disabled)',
}

const STATUS_COLORS: Record<string, string> = {
  draft: COLOR.faint,
  open: COLOR.primary,
  in_progress: COLOR.purple,
  on_hold: COLOR.warning,
  done: COLOR.success,
  canceled: COLOR.neutral,
  skipped: COLOR.disabled,
}

const PRIORITY_COLORS: Record<string, string> = {
  none: COLOR.neutral,
  low: COLOR.success,
  medium: COLOR.warning,
  high: COLOR.danger,
  critical: COLOR.dangerStrong,
}

const PROJECT_PARAM = 'filter[project]'
const TEAM_PARAM = 'filter[team]'
const TOP_USERS = 10

/* Page ------------------------------------------------------------------------ */

export function OperationsDashboard() {
  const [params, setParams] = useSearchParams()
  const toast = useToast()
  const can = useCan()
  const canView = can('report.view')
  const canCreateWork = can('work_order.create')

  // URL search params are the source of truth for range and filters.
  const rawRange = params.get('range')
  const range: RangeKey = isRangeKey(rawRange) ? rawRange : DEFAULT_RANGE
  const start = params.get('start') ?? undefined
  const end = params.get('end') ?? undefined
  const project = params.get(PROJECT_PARAM) ?? undefined
  const team = params.get(TEAM_PARAM) ?? undefined
  const customReady = range !== 'custom' || Boolean(start && end)
  const hasFilters = Boolean(project || team)

  const [customOpen, setCustomOpen] = useState(false)

  const query = useMemo<OperationsReportParams>(
    () => ({ range, start: range === 'custom' ? start : undefined, end: range === 'custom' ? end : undefined, project, team }),
    [range, start, end, project, team],
  )
  const report = useOperationsReport(query, { enabled: canView && customReady })
  const projects = useProjectOptions()
  const teams = useTeamOptions()

  // The server is the authority: a 403 is announced, never swallowed.
  const error = report.error
  useEffect(() => {
    if (error instanceof ApiError && error.isForbidden) toast.error('You do not have permission to view reports', error.message)
  }, [error, toast])

  const serverErrors = useMemo(() => (error instanceof ApiError && error.isValidation ? { start: error.errors.start, end: error.errors.end } : undefined), [error])

  const update = (mutate: (next: URLSearchParams) => void) => {
    const next = new URLSearchParams(params)
    mutate(next)
    setParams(next)
  }
  const onRangeChange = ({ range: nextRange, start: nextStart, end: nextEnd }: RangeSelection) =>
    update((next) => {
      next.set('range', nextRange)
      if (nextRange === 'custom' && nextStart && nextEnd) {
        next.set('start', nextStart)
        next.set('end', nextEnd)
      } else {
        next.delete('start')
        next.delete('end')
      }
    })
  const setFilter = (name: string, values: string[]) =>
    update((next) => {
      if (values[0]) next.set(name, values[0])
      else next.delete(name)
    })
  const clearFilters = () =>
    update((next) => {
      next.delete(PROJECT_PARAM)
      next.delete(TEAM_PARAM)
    })
  const resetRange = () =>
    update((next) => {
      next.delete('range')
      next.delete('start')
      next.delete('end')
    })

  let body: ReactNode
  if (!canView) {
    body = (
      <EmptyState
        illustration="chart"
        title="Reports are not available for your role"
        description="The Operations dashboard needs the report.view permission. Ask a chapter administrator if you need it."
      />
    )
  } else if (!customReady) {
    body = (
      <div className={styles.stateWrap}>
        <InlineAlert
          tone="warning"
          title="Choose a custom date range"
          actions={
            <>
              <Button size="sm" variant="primary" onClick={() => setCustomOpen(true)}>
                Choose dates
              </Button>
              <Button size="sm" variant="ghost" onClick={resetRange}>
                Use last 30 days
              </Button>
            </>
          }
        >
          Pick a start and end date to load the report, or switch back to a preset range.
        </InlineAlert>
      </div>
    )
  } else if (report.isPending) {
    body = <ReportSkeleton />
  } else if (report.isError) {
    body = (
      <div className={styles.stateWrap}>
        <ReportError error={report.error} hasFilters={hasFilters} onRetry={() => void report.refetch()} onEditDates={() => setCustomOpen(true)} onResetRange={resetRange} onClearFilters={clearFilters} />
      </div>
    )
  } else {
    body = <ReportBody data={report.data} updating={report.isFetching && report.isPlaceholderData} hasFilters={hasFilters} canCreateWork={canCreateWork} onClearFilters={clearFilters} />
  }

  return (
    <Page>
      <PageHeader
        title="Operations"
        subtitle="Work-order throughput, timeliness and workload"
        actions={canView ? <RangeControl value={range} start={start} end={end} open={customOpen} onOpenChange={setCustomOpen} serverErrors={serverErrors} onChange={onRangeChange} /> : undefined}
        filters={
          canView ? (
            <>
              <FilterChip
                label="Project"
                multiple={false}
                searchable
                options={toFilterOptions(projects.options)}
                value={project ? [project] : []}
                onChange={(values) => setFilter(PROJECT_PARAM, values)}
                loading={projects.isLoading}
                emptyText="No active projects"
              />
              <FilterChip
                label="Team"
                multiple={false}
                searchable
                options={toFilterOptions(teams.options)}
                value={team ? [team] : []}
                onChange={(values) => setFilter(TEAM_PARAM, values)}
                loading={teams.isLoading}
                emptyText="No teams yet"
              />
              {hasFilters && (
                <Button variant="link" size="sm" onClick={clearFilters}>
                  Clear filters
                </Button>
              )}
            </>
          ) : undefined
        }
      />
      <div className={cn(styles.scroll, 'scroll-y')}>
        <div className={styles.body}>{body}</div>
      </div>
    </Page>
  )
}

function toFilterOptions(options: Array<{ value: string; label: string; meta?: string }>): FilterOption[] {
  return options.map((option) => ({ value: option.value, label: option.label, description: option.meta }))
}

/* States ---------------------------------------------------------------------- */

function ReportError({
  error,
  hasFilters,
  onRetry,
  onEditDates,
  onResetRange,
  onClearFilters,
}: {
  error: unknown
  hasFilters: boolean
  onRetry: () => void
  onEditDates: () => void
  onResetRange: () => void
  onClearFilters: () => void
}) {
  if (error instanceof ApiError && error.isValidation) {
    const messages = Object.values(error.errors)
    const dateProblem = Boolean(error.errors.start || error.errors.end || error.errors.range)
    const filterProblem = Boolean(error.errors.project || error.errors.team)
    return (
      <InlineAlert
        tone="danger"
        title="The report request was not valid"
        actions={
          <>
            {dateProblem && (
              <Button size="sm" variant="primary" onClick={onEditDates}>
                Change dates
              </Button>
            )}
            {dateProblem && (
              <Button size="sm" onClick={onResetRange}>
                Reset to 30 days
              </Button>
            )}
            {filterProblem && (
              <Button size="sm" onClick={onClearFilters}>
                Clear filters
              </Button>
            )}
          </>
        }
      >
        {messages.length ? (
          <ul>
            {messages.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        ) : (
          error.message
        )}
      </InlineAlert>
    )
  }
  if (error instanceof ApiError && error.isNotFound) {
    return (
      <InlineAlert
        tone="danger"
        title="That project or team could not be found"
        actions={
          <>
            <Button size="sm" variant="primary" onClick={onClearFilters} disabled={!hasFilters}>
              Clear filters
            </Button>
            <Button size="sm" onClick={onRetry}>
              Retry
            </Button>
          </>
        }
      >
        The filter in this link points at a project or team that no longer exists or belongs to another chapter.
      </InlineAlert>
    )
  }
  if (error instanceof ApiError && error.isForbidden) {
    return (
      <InlineAlert
        tone="danger"
        title="You do not have permission to view this report"
        actions={
          <Button size="sm" onClick={onRetry}>
            Retry
          </Button>
        }
      >
        {error.message}
      </InlineAlert>
    )
  }
  return (
    <InlineAlert
      tone="danger"
      title="The report could not be loaded"
      actions={
        <Button size="sm" onClick={onRetry}>
          Retry
        </Button>
      }
    >
      {errorMessage(error)}
    </InlineAlert>
  )
}

function SkeletonCard({ wide, short }: { wide?: boolean; short?: boolean }) {
  return (
    <div className={cn(styles.skeletonCard, wide && styles.wide)}>
      <Skeleton width="40%" height={16} />
      <Skeleton width="25%" height={28} />
      {!short && <Skeleton height={200} />}
    </div>
  )
}

function ReportSkeleton() {
  return (
    <div role="status" aria-busy="true" aria-label="Loading report">
      <ReportGrid>
        <SkeletonCard wide />
        {Array.from({ length: 6 }, (_, index) => (
          <SkeletonCard key={index} />
        ))}
        <div className={styles.tiles}>
          <SkeletonCard short />
          <SkeletonCard short />
          <SkeletonCard short />
        </div>
      </ReportGrid>
    </div>
  )
}

/* Report body ------------------------------------------------------------------ */

interface NamedCount {
  key: string
  name: string
  count: number
  color: string
}

function percentOf(value: number, total: number): string {
  return total > 0 ? formatPercent(value / total) : '—'
}

function busiestWeek(weeks: WeekBucket[]): WeekBucket | undefined {
  return weeks.reduce<WeekBucket | undefined>((best, week) => (!best || week.created > best.created ? week : best), undefined)
}

function describeWeeks(weeks: WeekBucket[], totals: OperationsReport['totals'], rangeLabel: string): string {
  const busiest = busiestWeek(weeks)
  if (!busiest) return `No weekly data between ${rangeLabel}.`
  return `${pluralize(totals.created, 'work order')} created and ${formatCount(totals.completed)} completed between ${rangeLabel}, across ${pluralize(weeks.length, 'week')}. Most new work started the week of ${formatWeek(busiest.week_start)} with ${busiest.created} created and ${busiest.completed} completed.`
}

function describeDistribution(kind: string, rows: NamedCount[]): string {
  const total = rows.reduce((sum, row) => sum + row.count, 0)
  if (total === 0) return `No work orders to break down by ${kind}.`
  const present = rows.filter((row) => row.count > 0).map((row) => `${row.name} ${formatCount(row.count)}`)
  const absent = rows.filter((row) => row.count === 0).map((row) => row.name.toLowerCase())
  return `${pluralize(total, 'work order')} by ${kind}: ${joinList(present)}.${absent.length ? ` None are ${joinList(absent)}.` : ''}`
}

function Stat({ value, label, color }: { value: string; label: string; color: string }) {
  return (
    <div className={styles.stat}>
      <span className={styles.statValue}>{value}</span>
      <span className={styles.statLabel}>
        <span className={styles.swatch} style={{ background: color }} aria-hidden="true" />
        {label}
      </span>
    </div>
  )
}

function ReportBody({
  data,
  updating,
  hasFilters,
  canCreateWork,
  onClearFilters,
}: {
  data: OperationsReport
  updating: boolean
  hasFilters: boolean
  canCreateWork: boolean
  onClearFilters: () => void
}) {
  const [showAllUsers, setShowAllUsers] = useState(false)
  const { totals } = data
  const rangeLabel = formatRangeLabel(data.range.start, data.range.end)
  const isEmpty = totals.created === 0 && totals.completed === 0 && totals.open === 0
  const hasLogged = data.hours_logged > 0 || data.parts_cost > 0 || data.other_cost > 0

  const weeks = data.created_vs_completed
  const busiest = busiestWeek(weeks)
  const { repeating, non_repeating: nonRepeating } = data.repeating_vs_non
  const snapshotTotal = repeating + nonRepeating

  const typeRows: NamedCount[] = data.by_work_type.map((row) => ({
    key: row.work_type,
    name: WORK_TYPE_LABELS[row.work_type as WorkType] ?? labelFor(row.work_type),
    count: row.count,
    color: COLOR.primary,
  }))
  const topType = typeRows.reduce<NamedCount | undefined>((best, row) => (!best || row.count > best.count ? row : best), undefined)

  const statusRows: NamedCount[] = data.status_distribution.map((row) => ({
    key: row.status,
    name: labelFor(row.status),
    count: row.count,
    color: STATUS_COLORS[row.status] ?? COLOR.neutral,
  }))

  const priorityRows: NamedCount[] = data.priority_distribution.map((row) => ({
    key: row.priority,
    name: PRIORITY_LABELS[row.priority as Priority] ?? labelFor(row.priority),
    count: row.count,
    color: PRIORITY_COLORS[row.priority] ?? COLOR.neutral,
  }))
  const urgent = priorityRows.filter((row) => row.key === 'high' || row.key === 'critical').reduce((sum, row) => sum + row.count, 0)

  const teamRows = data.workload_by_team.map((row) => ({
    key: row.team?.id ?? 'none',
    id: row.team?.id ?? null,
    name: row.team?.name ?? 'No team',
    open: row.open,
    in_progress: row.in_progress,
  }))
  const teamTotal = teamRows.reduce((sum, row) => sum + row.open + row.in_progress, 0)

  const users = data.workload_by_user
  const userTotal = users.reduce((sum, row) => sum + row.open + row.in_progress, 0)
  const shownUsers = showAllUsers ? users : users.slice(0, TOP_USERS)

  return (
    <>
      <ul className={styles.summary} aria-label="Report summary">
        <li>
          <span className={styles.summaryStrong}>{rangeLabel}</span>
        </li>
        <li>{data.range.timezone}</li>
        <li>{formatCount(totals.created)} created</li>
        <li>{formatCount(totals.completed)} completed</li>
        <li>{formatCount(totals.open)} open now</li>
        {updating && (
          <li>
            <span className={styles.updating} aria-live="polite">
              Updating…
            </span>
          </li>
        )}
      </ul>

      <ReportGrid>
        {isEmpty ? (
          <div className={styles.emptyCard}>
            <EmptyState
              illustration="chart"
              title="No work in this range"
              description={hasFilters ? `No work orders match these filters between ${rangeLabel}.` : `No work orders were created, completed or left open between ${rangeLabel}.`}
              action={
                hasFilters ? (
                  <Button size="sm" onClick={onClearFilters}>
                    Clear filters
                  </Button>
                ) : canCreateWork ? (
                  <LinkButton to="/work-orders/new" variant="primary" size="sm" leadingIcon={<Plus size={16} />}>
                    New Work Order
                  </LinkButton>
                ) : undefined
              }
            />
          </div>
        ) : (
          <>
            <ReportCard wide title="Created vs Completed" subtitle="New work against finished work, per week (weeks start Monday)" value={`${formatCount(totals.created)} created ${DOT} ${formatCount(totals.completed)} completed`}>
              <Legend
                items={[
                  { key: 'created', label: 'Created', color: COLOR.primary },
                  { key: 'completed', label: 'Completed', color: COLOR.success },
                ]}
              />
              <ChartFrame summary={describeWeeks(weeks, totals, rangeLabel)} table={{ columns: ['Week of', 'Created', 'Completed'], rows: weeks.map((week) => [formatWeek(week.week_start), week.created, week.completed]) }}>
                {weeks.length ? (
                  <GroupedBars
                    categories={weeks.map((week) => ({ key: week.week_start, label: formatWeek(week.week_start), title: `Week of ${formatWeek(week.week_start)}` }))}
                    series={[
                      { key: 'created', label: 'Created', color: COLOR.primary, values: weeks.map((week) => week.created) },
                      { key: 'completed', label: 'Completed', color: COLOR.success, values: weeks.map((week) => week.completed) },
                    ]}
                  />
                ) : (
                  <p className={styles.chartEmpty}>No weeks in this range.</p>
                )}
              </ChartFrame>
              {busiest && (
                <p className={styles.caption}>
                  Most new work started the week of {formatWeek(busiest.week_start)} ({pluralize(busiest.created, 'work order')}).
                </p>
              )}
            </ReportCard>

            <ReportCard title="Work orders by type" subtitle="Open at the end of the range, plus anything created in it" value={formatCount(snapshotTotal)}>
              <ChartFrame summary={describeDistribution('work type', typeRows)} table={{ columns: ['Work type', 'Work orders'], rows: typeRows.map((row) => [row.name, row.count]) }}>
                <BarRows rows={typeRows.map((row) => ({ key: row.key, label: row.name, title: row.name, value: row.count, color: row.color }))} />
              </ChartFrame>
              {topType && topType.count > 0 && (
                <p className={styles.caption}>
                  Most common: {topType.name} ({formatCount(topType.count)}).
                </p>
              )}
            </ReportCard>

            <ReportCard title="Repeating vs non-repeating" subtitle="Scheduled work compared with one-off work" value={`${formatCount(repeating)} repeating`}>
              <ChartFrame
                summary={`${pluralize(snapshotTotal, 'work order')} in the snapshot: ${formatCount(repeating)} repeat on a schedule and ${formatCount(nonRepeating)} do not.`}
                table={{
                  columns: ['Kind', 'Work orders'],
                  rows: [
                    ['Repeating', repeating],
                    ['Non-repeating', nonRepeating],
                  ],
                }}
              >
                <div className={styles.stackWrap}>
                  <div className={styles.splitStat}>
                    <Stat value={formatCount(repeating)} label="Repeating" color={COLOR.purple} />
                    <Stat value={formatCount(nonRepeating)} label="Non-repeating" color={COLOR.primary} />
                  </div>
                  <SegmentBar
                    height={20}
                    segments={[
                      { key: 'repeating', label: 'Repeating', value: repeating, color: COLOR.purple },
                      { key: 'non_repeating', label: 'Non-repeating', value: nonRepeating, color: COLOR.primary },
                    ]}
                  />
                  <p className={styles.percentRow}>
                    <span>{percentOf(repeating, snapshotTotal)} repeating</span>
                    <span>{percentOf(nonRepeating, snapshotTotal)} non-repeating</span>
                  </p>
                </div>
              </ChartFrame>
            </ReportCard>

            <ReportCard title="Status distribution" subtitle="Where the snapshot stands today" value={formatCount(snapshotTotal)}>
              <ChartFrame summary={describeDistribution('status', statusRows)} table={{ columns: ['Status', 'Work orders'], rows: statusRows.map((row) => [row.name, row.count]) }}>
                <div className={styles.stackWrap}>
                  <p className={styles.stackTotal}>
                    {formatCount(snapshotTotal)} <span className={styles.muted}>work orders</span>
                  </p>
                  <SegmentBar height={28} segments={statusRows.map((row) => ({ key: row.key, label: row.name, value: row.count, color: row.color }))} />
                  <p className={styles.percentRow}>
                    {statusRows
                      .filter((row) => row.count > 0)
                      .map((row) => (
                        <span key={row.key}>
                          {row.name} {percentOf(row.count, snapshotTotal)}
                        </span>
                      ))}
                  </p>
                </div>
              </ChartFrame>
              <Legend label="Status legend" items={statusRows.map((row) => ({ key: row.key, label: row.name, color: row.color, value: formatCount(row.count), to: `/work-orders?filter[status]=${row.key}&tab=all` }))} />
            </ReportCard>

            <ReportCard title="Priority distribution" subtitle="Priority across the snapshot" value={`${formatCount(urgent)} high or critical`}>
              <ChartFrame summary={describeDistribution('priority', priorityRows)} table={{ columns: ['Priority', 'Work orders'], rows: priorityRows.map((row) => [row.name, row.count]) }}>
                <BarRows rows={priorityRows.map((row) => ({ key: row.key, label: <PriorityBadge priority={row.key} />, title: row.name, value: row.count, color: row.color }))} />
              </ChartFrame>
            </ReportCard>

            <ReportCard title="On-time completion" subtitle="Completed in this range" value={formatPercent(data.on_time_completion_rate)}>
              <p className={styles.explain}>
                {data.on_time_completion_rate === null
                  ? 'Nothing with a due date was completed in this range, so there is no rate to show.'
                  : 'Share of work orders completed in this range that had a due date and were finished on or before it.'}
              </p>
            </ReportCard>

            <ReportCard title="Overdue open" subtitle="Right now, regardless of range" value={formatCount(data.overdue_open)}>
              <p className={styles.explain}>Open work orders whose due date has passed. This is the current state, so it does not change with the date range.</p>
              <Link to="/work-orders?filter[due]=overdue" className={styles.cardLink}>
                View overdue work orders <ArrowRight size={14} aria-hidden="true" />
              </Link>
            </ReportCard>

            <ReportCard title="Average completion time" subtitle="Completed in this range" value={formatHours(data.avg_completion_hours)}>
              <p className={styles.explain}>
                {data.avg_completion_hours === null ? 'Nothing was completed in this range, so there is no average yet.' : 'Mean time from when a work order was created to when it was completed, in hours.'}
              </p>
            </ReportCard>

            <ReportCard title="Workload by team" subtitle="Open and in-progress work right now" value={formatCount(teamTotal)}>
              <Legend
                items={[
                  { key: 'open', label: 'Open', color: COLOR.primary },
                  { key: 'in_progress', label: 'In progress', color: COLOR.purple },
                ]}
              />
              <ChartFrame
                summary={teamRows.length ? `Open and in-progress work by team: ${joinList(teamRows.map((row) => `${row.name} ${row.open} open and ${row.in_progress} in progress`))}.` : 'No open or in-progress work is assigned right now.'}
                table={{ columns: ['Team', 'Open', 'In progress'], rows: teamRows.map((row) => [row.name, row.open, row.in_progress]) }}
              >
                {teamRows.length ? (
                  <GroupedBars
                    categories={teamRows.map((row) => ({ key: row.key, label: truncate(row.name, 14), title: row.name }))}
                    series={[
                      { key: 'open', label: 'Open', color: COLOR.primary, values: teamRows.map((row) => row.open) },
                      { key: 'in_progress', label: 'In progress', color: COLOR.purple, values: teamRows.map((row) => row.in_progress) },
                    ]}
                  />
                ) : (
                  <p className={styles.chartEmpty}>No open or in-progress work right now.</p>
                )}
              </ChartFrame>
              {teamRows.length > 0 && (
                <ul className={styles.teamList} aria-label="Teams">
                  {teamRows.map((row) => (
                    <li key={row.key}>
                      {row.id ? <Link to={`/work-orders?filter[team]=${row.id}`}>{row.name}</Link> : <span>{row.name}</span>}
                      <span className={styles.teamCounts}>
                        {formatCount(row.open)} open {DOT} {formatCount(row.in_progress)} in progress
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </ReportCard>

            <ReportCard title="Workload by user" subtitle={users.length > TOP_USERS && !showAllUsers ? `Direct assignees on open and in-progress work ${DOT} top ${TOP_USERS}` : 'Direct assignees on open and in-progress work'} value={formatCount(userTotal)}>
              {users.length === 0 ? (
                <EmptyState compact illustration="users" title="No one is assigned open work" description="Assign work orders to members and their load appears here." />
              ) : (
                <>
                  <div className={styles.tableWrap}>
                    <table className={styles.table}>
                      <thead>
                        <tr>
                          <th scope="col">Member</th>
                          <th scope="col" className={styles.numeric}>
                            Open
                          </th>
                          <th scope="col" className={styles.numeric}>
                            In progress
                          </th>
                          <th scope="col" className={styles.numeric}>
                            Total
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {shownUsers.map((row) => (
                          <tr key={row.user.id}>
                            <td>
                              <span className={styles.person}>
                                <span aria-hidden="true">
                                  <Avatar name={row.user.name} src={row.user.avatar_url} />
                                </span>
                                {row.user.name}
                              </span>
                            </td>
                            <td className={styles.numeric}>{row.open}</td>
                            <td className={styles.numeric}>{row.in_progress}</td>
                            <td className={styles.numeric}>{row.open + row.in_progress}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {users.length > TOP_USERS && (
                    <div className={styles.tableFooter}>
                      <Button variant="link" size="sm" onClick={() => setShowAllUsers((current) => !current)} aria-expanded={showAllUsers}>
                        {showAllUsers ? `Show top ${TOP_USERS}` : `Show all ${users.length}`}
                      </Button>
                    </div>
                  )}
                </>
              )}
            </ReportCard>
          </>
        )}

        {(!isEmpty || hasLogged) && (
          <div className={styles.tiles}>
            <ReportCard title="Hours logged" subtitle="Time entries in this range" value={formatHours(data.hours_logged)}>
              <p className={styles.explain}>Time recorded against work orders between {rangeLabel}.</p>
            </ReportCard>
            <ReportCard title="Parts cost" subtitle="Cost entries of type parts" value={formatMoney(data.parts_cost)}>
              <p className={styles.explain}>Parts charged to work orders between {rangeLabel}.</p>
            </ReportCard>
            <ReportCard title="Other cost" subtitle="Labor, vendor and other entries" value={formatMoney(data.other_cost)}>
              <p className={styles.explain}>Every other cost entry recorded between {rangeLabel}.</p>
            </ReportCard>
          </div>
        )}
      </ReportGrid>
    </>
  )
}
