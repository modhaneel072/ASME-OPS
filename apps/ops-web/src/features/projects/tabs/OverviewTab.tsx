import { Link, useNavigate } from 'react-router-dom'
import { labelFor } from '@/api/contracts/common'
import type { Project, ProjectHealth } from '@/api/contracts/projects'
import { useProjectActivity, useProjectHealth } from '@/api/queries/projects'
import { formatDate, formatMoney } from '@/lib/dates'
import { ActivityTimeline, Avatar, Badge, Button, Card, EmptyState, FieldList, Grid2, ProgressBar, ProgressRing, Stack, StatusBadge } from '@/ui'
import { cn } from '@/lib/cn'
import { activityToTimeline, QueryState, workOrdersHref } from '../shared'
import styles from '../projects.module.css'

function StatTile({ label, value, to, tone }: { label: string; value: number; to: string; tone?: 'danger' | 'warning' }) {
  return (
    <Link to={to} className={cn(styles.tile, tone === 'danger' && value > 0 && styles.tile_danger, tone === 'warning' && value > 0 && styles.tile_warning)} aria-label={`${label}: ${value} work orders`}>
      <span className={styles.tileValue}>{value}</span>
      <span className={styles.tileLabel}>{label}</span>
    </Link>
  )
}

export function BudgetSummary({ budget }: { budget: ProjectHealth['budget'] }) {
  const hasBudget = budget.amount !== null && budget.amount > 0
  const over = hasBudget && budget.used > (budget.amount ?? 0)
  const percent = hasBudget ? (budget.used / (budget.amount ?? 1)) * 100 : 0
  return (
    <div>
      <div className={styles.budgetFigures}>
        <div className={styles.figure}>
          <span className={styles.figureLabel}>Budget</span>
          <span className={styles.figureValue}>{budget.amount === null ? 'Not set' : formatMoney(budget.amount)}</span>
        </div>
        <div className={styles.figure}>
          <span className={styles.figureLabel}>Used</span>
          <span className={cn(styles.figureValue, over && styles.figureValue_danger)}>{formatMoney(budget.used)}</span>
        </div>
        <div className={styles.figure}>
          <span className={styles.figureLabel}>Remaining</span>
          <span className={cn(styles.figureValue, over && styles.figureValue_danger)}>{budget.remaining === null ? '—' : formatMoney(budget.remaining)}</span>
        </div>
      </div>
      {hasBudget ? <ProgressBar value={percent} label={over ? 'Over budget' : 'Spent'} tone={over ? 'danger' : percent > 85 ? 'gold' : undefined} /> : <p className={styles.helpText}>Set a budget amount on the project to track spending against it.</p>}
    </div>
  )
}

export function OverviewTab({ project, onOpenTab }: { project: Project; onOpenTab: (tab: 'milestones' | 'activity' | 'teams' | 'budget') => void }) {
  const health = useProjectHealth(project.id)
  const activity = useProjectActivity(project.id, 5)
  const navigate = useNavigate()
  const recent = activity.data?.pages[0]?.items.slice(0, 5) ?? []

  return (
    <QueryState isPending={health.isPending} isError={health.isError} error={health.error} onRetry={() => void health.refetch()} title="Project health could not be loaded">
      {health.data && (
        <Stack>
          <Card title="Health">
            <div className={styles.healthRow}>
              <ProgressRing value={health.data.completion_percent} size={88} stroke={8} label="Completion" />
              <div className={styles.healthSummary}>
                <span className={styles.healthHeadline}>{health.data.completion_percent}% of work complete</span>
                <span className={styles.healthCaption}>
                  {health.data.work.done} of {health.data.work.total - health.data.work.canceled} work orders done · {health.data.milestones.done}/{health.data.milestones.total} milestones reached
                  {health.data.milestones.missed > 0 ? ` · ${health.data.milestones.missed} missed` : ''} · {health.data.activity_7d} changes in the last 7 days
                </span>
              </div>
            </div>
            <div className={styles.tiles} style={{ marginTop: 'var(--space-4)' }}>
              <StatTile label="Open" value={health.data.work.open} to={workOrdersHref(project.id, { 'filter[status]': 'open' })} />
              <StatTile label="In progress" value={health.data.work.in_progress} to={workOrdersHref(project.id, { 'filter[status]': 'in_progress' })} />
              <StatTile label="On hold" value={health.data.work.on_hold} to={workOrdersHref(project.id, { 'filter[status]': 'on_hold' })} tone="warning" />
              <StatTile label="Overdue" value={health.data.work.overdue} to={workOrdersHref(project.id, { 'filter[due]': 'overdue' })} tone="danger" />
              <StatTile label="Blocked" value={health.data.work.blocked} to={workOrdersHref(project.id, { tab: 'todo' })} tone="danger" />
            </div>
          </Card>

          <Grid2>
            <Card
              title="Upcoming milestones"
              flush
              actions={
                <Button size="sm" variant="ghost" onClick={() => onOpenTab('milestones')}>
                  See all
                </Button>
              }
            >
              {health.data.milestones.upcoming.length === 0 ? (
                <EmptyState compact illustration="clipboard" title="No upcoming milestones" description="Milestones that are planned or in progress appear here." />
              ) : (
                <ul className={styles.milestoneList} aria-label="Upcoming milestones">
                  {health.data.milestones.upcoming.map((milestone) => (
                    <li key={milestone.id} className={styles.milestone}>
                      <div className={styles.milestoneMain}>
                        <span className={styles.milestoneName}>{milestone.name}</span>
                        <span className={styles.milestoneMeta}>
                          <span>{milestone.due_date ? `Due ${formatDate(milestone.due_date)}` : 'No due date'}</span>
                          {milestone.owner && (
                            <span className={styles.owner}>
                              <Avatar name={milestone.owner.name} src={milestone.owner.avatar_url} /> {milestone.owner.name}
                            </span>
                          )}
                        </span>
                      </div>
                      <StatusBadge status={milestone.status} size="sm" />
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card
              title="Budget"
              actions={
                <Button size="sm" variant="ghost" onClick={() => onOpenTab('budget')}>
                  Details
                </Button>
              }
            >
              <BudgetSummary budget={health.data.budget} />
            </Card>
          </Grid2>

          <Grid2>
            <Card title="Details">
              <FieldList
                items={[
                  { label: 'Status', value: <StatusBadge status={project.status} /> },
                  { label: 'Lead', value: project.lead ? <span className={styles.person}><Avatar name={project.lead.name} src={project.lead.avatar_url} />{project.lead.name}</span> : 'Not assigned' },
                  { label: 'Faculty advisor', value: project.faculty_advisor?.name ?? '—' },
                  { label: 'Dates', value: project.start_date || project.target_date ? `${formatDate(project.start_date)} → ${formatDate(project.target_date)}` : '—' },
                  { label: 'Academic year', value: project.academic_year ?? '—' },
                  { label: 'Visibility', value: labelFor(project.visibility) },
                  {
                    label: 'Links',
                    value:
                      project.repository_url || project.cad_url || project.requirements_url ? (
                        <span className={styles.inlineLinks}>
                          {project.repository_url && <a href={project.repository_url} target="_blank" rel="noreferrer">Repository</a>}
                          {project.cad_url && <a href={project.cad_url} target="_blank" rel="noreferrer">CAD</a>}
                          {project.requirements_url && <a href={project.requirements_url} target="_blank" rel="noreferrer">Requirements</a>}
                        </span>
                      ) : (
                        '—'
                      ),
                  },
                ]}
              />
            </Card>
            <Card
              title="Teams and members"
              actions={
                <Button size="sm" variant="ghost" onClick={() => onOpenTab('teams')}>
                  Manage
                </Button>
              }
            >
              <Stack>
                <div>
                  <p className={styles.figureLabel} style={{ marginBottom: 'var(--space-2)' }}>
                    Teams
                  </p>
                  {health.data.teams.length === 0 ? (
                    <p className={styles.muted}>No teams are linked to this project yet.</p>
                  ) : (
                    <div className={styles.chips}>
                      {health.data.teams.map((team) => (
                        <Link key={team.id} to={`/teams-users/teams/${team.id}`} className={styles.chipLink}>
                          {team.name}
                        </Link>
                      ))}
                    </div>
                  )}
                </div>
                <div>
                  <p className={styles.figureLabel} style={{ marginBottom: 'var(--space-2)' }}>
                    Members
                  </p>
                  <Badge tone="info">{health.data.members} {health.data.members === 1 ? 'member' : 'members'}</Badge>
                </div>
              </Stack>
            </Card>
          </Grid2>

          <Card
            title="Recent activity"
            actions={
              <Button size="sm" variant="ghost" onClick={() => onOpenTab('activity')}>
                Full history
              </Button>
            }
          >
            {activity.isError ? (
              <Button size="sm" onClick={() => void activity.refetch()}>
                Retry loading activity
              </Button>
            ) : (
              <ActivityTimeline items={activityToTimeline(recent)} emptyText={activity.isPending ? 'Loading…' : 'No activity yet'} />
            )}
          </Card>
          <div>
            <Button variant="link" onClick={() => navigate(workOrdersHref(project.id))}>
              Open all work orders for {project.code}
            </Button>
          </div>
        </Stack>
      )}
    </QueryState>
  )
}
