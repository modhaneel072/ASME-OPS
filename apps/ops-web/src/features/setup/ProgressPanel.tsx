import { BookOpen, Clock, Eye, EyeOff } from 'lucide-react'
import { forwardRef, useId } from 'react'
import { findSetupTask, nextSetupTask, OFFICER_GUIDE_TASK_KEY, type SetupProgress } from '@/api/contracts/setup'
import { formatDate } from '@/lib/dates'
import { Badge, Button, InlineAlert, ProgressRing } from '@/ui'
import { TaskAction, TaskTile } from './TaskCard'
import { formatEstimate } from './taskMeta'
import styles from './setup.module.css'

export interface ProgressPanelProps {
  progress: SetupProgress
  /** Holder of `chapter.setup.manage`; the server re-checks every action. */
  canManage: boolean
  onOpenGuide: () => void
  onToggleBanner: () => void
  bannerPending: boolean
  onMarkGuideRead: () => void
  guidePending: boolean
  onRequestComplete: () => void
}

export const ProgressPanel = forwardRef<HTMLElement, ProgressPanelProps>(function ProgressPanel(
  { progress, canManage, onOpenGuide, onToggleBanner, bannerPending, onMarkGuideRead, guidePending, onRequestComplete },
  ref,
) {
  const titleId = useId()
  const hintId = useId()
  const { completed, available, percent } = progress.progress
  const next = nextSetupTask(progress)
  const guide = findSetupTask(progress, OFFICER_GUIDE_TASK_KEY)
  const guideRead = guide?.status === 'complete'
  const completedAt = progress.completed_at
  const remaining = Math.max(0, available - completed)
  const canComplete = percent === 100

  const showComplete = canManage && !completedAt
  const showGuide = canManage && Boolean(guide) && !guideRead
  // The shell only shows the banner to setup managers and never after completion,
  // so the toggle is rendered only where it has a visible effect.
  const showBannerToggle = canManage && !completedAt
  const hasActions = showComplete || showGuide || showBannerToggle

  return (
    <section ref={ref} tabIndex={-1} className={styles.panel} aria-labelledby={titleId}>
      <div className={styles.panelHeader}>
        <ProgressRing value={percent} size={80} stroke={7} label="Setup progress" />
        <div className={styles.panelHeaderText}>
          <h2 id={titleId} className={styles.panelTitle}>
            Setup progress
          </h2>
          <p className={styles.panelSummary}>
            {completed} of {available} tasks done
          </p>
          {completedAt && (
            <div className={styles.panelCompleted}>
              <Badge tone="success" dot>
                Setup completed {formatDate(completedAt)}
              </Badge>
            </div>
          )}
        </div>
      </div>

      {next ? (
        <section className={styles.nextSection} aria-label="Up next">
          <p className={styles.nextEyebrow}>Up next</p>
          <div className={styles.nextCard}>
            <div className={styles.nextCardHead}>
              <TaskTile taskKey={next.key} size={18} />
              <div className={styles.nextCardText}>
                <h3 className={styles.nextTitle}>{next.title}</h3>
                <p className={styles.nextDescription}>{next.description}</p>
              </div>
            </div>
            <div className={styles.nextMeta}>
              <span className={styles.taskMetaItem}>
                <Clock size={12} aria-hidden="true" />
                <span className="sr-only">Estimated </span>
                {formatEstimate(next.estimated_minutes)}
              </span>
              {next.optional && (
                <Badge tone="outline" size="sm">
                  Optional
                </Badge>
              )}
            </div>
            <div>
              <TaskAction task={next} emphasis="primary" onOpen={next.key === OFFICER_GUIDE_TASK_KEY ? onOpenGuide : undefined} />
            </div>
          </div>
        </section>
      ) : (
        <InlineAlert tone="success" title="Every available task is done">
          {completedAt ? 'Setup is complete for this chapter.' : canManage ? 'Mark setup complete to close the setup banner for the whole chapter.' : 'A chapter officer can now mark setup complete.'}
        </InlineAlert>
      )}

      {hasActions && (
        <div className={styles.panelActions}>
          {showComplete && (
            <>
              <Button variant="primary" block disabled={!canComplete} aria-describedby={canComplete ? undefined : hintId} onClick={onRequestComplete}>
                Mark setup complete
              </Button>
              {!canComplete && (
                <p id={hintId} className={styles.panelHint}>
                  Finish the remaining {remaining} required {remaining === 1 ? 'task' : 'tasks'} to mark setup complete. Optional tasks do not count.
                </p>
              )}
            </>
          )}
          {showGuide && (
            <Button block leadingIcon={<BookOpen size={16} />} onClick={onMarkGuideRead} loading={guidePending}>
              Mark officer guide read
            </Button>
          )}
          {showBannerToggle && (
            <Button variant="ghost" block leadingIcon={progress.banner_dismissed ? <Eye size={16} /> : <EyeOff size={16} />} onClick={onToggleBanner} loading={bannerPending}>
              {progress.banner_dismissed ? 'Show setup banner' : 'Hide setup banner'}
            </Button>
          )}
        </div>
      )}
    </section>
  )
})
