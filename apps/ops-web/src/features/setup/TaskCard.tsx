import { BookOpen, CheckCircle2, Circle, Clock, Lock } from 'lucide-react'
import { useId } from 'react'
import { Link, useLocation } from 'react-router-dom'
import type { SetupTask } from '@/api/contracts/setup'
import { cn } from '@/lib/cn'
import { Badge, Button, LinkButton } from '@/ui'
import { appPath } from './paths'
import { countLabel, formatEstimate, taskMeta } from './taskMeta'
import styles from './setup.module.css'

/** Coloured icon tile keyed by task; decorative (the title carries the meaning). */
export function TaskTile({ taskKey, size = 20 }: { taskKey: string; size?: number }) {
  const { icon: Icon, tone } = taskMeta(taskKey)
  return (
    <span className={cn(styles.tile, styles[`tile_${tone}`])} aria-hidden="true">
      <Icon size={size} />
    </span>
  )
}

/** Completion indicator. Text accompanies every icon so colour is never the only signal. */
export function TaskStatus({ task }: { task: SetupTask }) {
  if (task.status === 'complete') {
    return (
      <span className={styles.doneLabel}>
        <CheckCircle2 size={18} aria-hidden="true" />
        Done
      </span>
    )
  }
  if (task.status === 'unavailable') {
    return (
      <>
        <span className={cn(styles.indicator, styles.indicator_unavailable)} role="img" aria-label="Not available yet">
          <Lock size={18} aria-hidden="true" />
        </span>
        {task.stage !== null && (
          <Badge tone="neutral" size="sm">
            Stage {task.stage}
          </Badge>
        )}
      </>
    )
  }
  return (
    <span className={cn(styles.indicator, styles.indicator_incomplete)} role="img" aria-label="Not done yet">
      <Circle size={18} aria-hidden="true" />
    </span>
  )
}

export interface TaskActionProps {
  task: SetupTask
  /** Replaces the href navigation (the officer guide opens in place because its href is this page). */
  onOpen?: () => void
  emphasis?: 'default' | 'primary'
}

/**
 * The single control a task offers: "Set up" (incomplete), "Review" (complete)
 * or nothing (unavailable, or a link that would only reload this page).
 */
export function TaskAction({ task, onOpen, emphasis = 'default' }: TaskActionProps) {
  const location = useLocation()
  const to = appPath(task.href)
  const selfLink = to === location.pathname
  const variant = emphasis === 'primary' ? 'primary' : 'secondary'

  if (task.status === 'unavailable') return null

  if (task.status === 'complete') {
    if (onOpen) {
      return (
        <button type="button" className={styles.reviewLink} onClick={onOpen}>
          Review{' '}
          <span className="sr-only">{task.title}</span>
        </button>
      )
    }
    if (selfLink) return null
    return (
      <Link to={to} className={styles.reviewLink}>
        Review{' '}
        <span className="sr-only">{task.title}</span>
      </Link>
    )
  }

  if (onOpen) {
    return (
      <Button size="sm" variant={variant} leadingIcon={<BookOpen size={14} />} onClick={onOpen}>
        Read guide
      </Button>
    )
  }
  if (selfLink) return null
  return (
    <LinkButton size="sm" variant={variant} to={to}>
      Set up{' '}
      <span className="sr-only">{task.title}</span>
    </LinkButton>
  )
}

export function TaskCard({ task, onOpen }: { task: SetupTask; onOpen?: () => void }) {
  const titleId = useId()
  const count = countLabel(task)
  return (
    <article className={cn(styles.task, styles[`task_${task.status}`])} aria-labelledby={titleId} data-testid="setup-task" data-task-key={task.key} data-status={task.status}>
      <TaskTile taskKey={task.key} />
      <div className={styles.taskBody}>
        <div className={styles.taskTitleRow}>
          <h3 id={titleId} className={styles.taskTitle}>
            {task.title}
          </h3>
          {task.optional && (
            <Badge tone="outline" size="sm">
              Optional
            </Badge>
          )}
        </div>
        <p className={styles.taskDescription}>{task.description}</p>
        <div className={styles.taskMeta}>
          <span className={styles.taskMetaItem}>
            <Clock size={12} aria-hidden="true" />
            <span className="sr-only">Estimated </span>
            {formatEstimate(task.estimated_minutes)}
          </span>
          {count && <span className={styles.taskMetaItem}>{count}</span>}
        </div>
      </div>
      <div className={styles.taskActions}>
        <TaskStatus task={task} />
        <TaskAction task={task} onOpen={onOpen} />
      </div>
    </article>
  )
}
