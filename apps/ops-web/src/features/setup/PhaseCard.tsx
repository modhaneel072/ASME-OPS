import { useId } from 'react'
import { OFFICER_GUIDE_TASK_KEY, summarizeSetupPhase, type SetupPhase } from '@/api/contracts/setup'
import { Badge } from '@/ui'
import { TaskCard } from './TaskCard'
import styles from './setup.module.css'

export function PhaseCard({ phase, index, onOpenGuide }: { phase: SetupPhase; index: number; onOpenGuide: () => void }) {
  const titleId = useId()
  const summary = summarizeSetupPhase(phase)
  const allDone = summary.available > 0 && summary.completed === summary.available
  return (
    <section className={styles.phase} aria-labelledby={titleId}>
      <header className={styles.phaseHeader}>
        <div className={styles.phaseHeaderMain}>
          <p className={styles.phaseEyebrow}>Phase {index + 1}</p>
          <h2 id={titleId} className={styles.phaseTitle}>
            {phase.title}
          </h2>
          <p className={styles.phaseDescription}>{phase.description}</p>
        </div>
        <div className={styles.phaseSummary}>
          {summary.deferred ? (
            <Badge tone="outline">Later stages</Badge>
          ) : allDone ? (
            <Badge tone="success" dot>
              Complete
            </Badge>
          ) : summary.available > 0 ? (
            <Badge tone="neutral">
              {summary.completed} of {summary.available} done
            </Badge>
          ) : null}
        </div>
      </header>
      <ol className={styles.taskList} aria-label={`${phase.title} tasks`}>
        {phase.tasks.map((task) => (
          <li key={task.key}>
            <TaskCard task={task} onOpen={task.key === OFFICER_GUIDE_TASK_KEY ? onOpenGuide : undefined} />
          </li>
        ))}
      </ol>
    </section>
  )
}
