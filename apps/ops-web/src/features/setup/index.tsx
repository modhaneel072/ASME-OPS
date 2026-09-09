import type { UseMutationResult } from '@tanstack/react-query'
import { Rocket } from 'lucide-react'
import { useRef, useState } from 'react'
import { errorMessage } from '@/api/client'
import { findSetupTask, OFFICER_GUIDE_TASK_KEY, type SetupProgress } from '@/api/contracts/setup'
import { useCompleteSetup, useDismissSetupBanner, useMarkGuideRead, useReopenSetupBanner, useSetupProgress } from '@/api/queries/setup'
import { cn } from '@/lib/cn'
import { useCan } from '@/lib/permissions'
import { Button, Dialog, InlineAlert, Page, Skeleton, SkeletonBlock, SkeletonRows, useToast } from '@/ui'
import { OfficerGuideDialog } from './OfficerGuideDialog'
import { PhaseCard } from './PhaseCard'
import { ProgressPanel } from './ProgressPanel'
import styles from './setup.module.css'

type SetupMutation = UseMutationResult<SetupProgress, Error, void>

/**
 * Setup Center (`/setup`): a scrolling welcome page. Phase cards on the left
 * list every onboarding task with its live status; the sticky panel on the
 * right shows progress, the next task and the chapter-level actions.
 */
export default function SetupPage() {
  const toast = useToast()
  const can = useCan()
  const canManage = can('chapter.setup.manage')

  const progress = useSetupProgress()
  const dismiss = useDismissSetupBanner()
  const reopen = useReopenSetupBanner()
  const complete = useCompleteSetup()
  const markGuide = useMarkGuideRead()

  const [confirmOpen, setConfirmOpen] = useState(false)
  const [guideOpen, setGuideOpen] = useState(false)
  const panelRef = useRef<HTMLElement>(null)

  /** Runs a setup action; success and failure (including 403) both surface as toasts. */
  const run = async (mutation: SetupMutation, success: { title: string; description?: string }, failureTitle: string): Promise<boolean> => {
    try {
      await mutation.mutateAsync()
      toast.success(success.title, success.description)
      return true
    } catch (error) {
      toast.error(failureTitle, errorMessage(error))
      return false
    }
  }

  const onToggleBanner = () => {
    if (!progress.data) return
    if (progress.data.banner_dismissed) void run(reopen, { title: 'Setup banner restored' }, 'Could not show the setup banner')
    else void run(dismiss, { title: 'Setup banner hidden', description: 'You can bring it back from the Setup Center at any time.' }, 'Could not hide the setup banner')
  }

  const onMarkGuideRead = async () => {
    const ok = await run(markGuide, { title: 'Officer guide marked as read' }, 'Could not mark the officer guide as read')
    if (ok) setGuideOpen(false)
  }

  const onConfirmComplete = async () => {
    const ok = await run(complete, { title: 'Setup marked complete', description: 'The setup banner is now hidden for the whole chapter.' }, 'Could not mark setup complete')
    setConfirmOpen(false)
    if (ok) panelRef.current?.focus({ preventScroll: true })
  }

  const guideTask = progress.data ? findSetupTask(progress.data, OFFICER_GUIDE_TASK_KEY) : undefined

  return (
    <Page>
      <div className={cn(styles.scroll, 'scroll-y')}>
        <header className={styles.hero}>
          <div className={styles.heroInner}>
            <p className={styles.heroEyebrow}>
              <Rocket size={14} aria-hidden="true" />
              Setup Center
            </p>
            <h1 className={styles.heroTitle}>Welcome to ASME Ops Setup Center</h1>
            <p className={styles.heroSubtitle}>Build a reliable chapter operation, organize project work, and keep your teams ready.</p>
          </div>
        </header>
        <div className={styles.body}>
          {progress.isPending ? (
            <SetupSkeleton />
          ) : progress.isError ? (
            <InlineAlert
              tone="danger"
              title="Setup progress could not be loaded"
              actions={
                <Button size="sm" onClick={() => void progress.refetch()} loading={progress.isFetching}>
                  Retry
                </Button>
              }
            >
              {errorMessage(progress.error)}
            </InlineAlert>
          ) : (
            <div className={styles.columns}>
              <aside className={styles.side}>
                <ProgressPanel
                  ref={panelRef}
                  progress={progress.data}
                  canManage={canManage}
                  onOpenGuide={() => setGuideOpen(true)}
                  onToggleBanner={onToggleBanner}
                  bannerPending={dismiss.isPending || reopen.isPending}
                  onMarkGuideRead={() => void onMarkGuideRead()}
                  guidePending={markGuide.isPending}
                  onRequestComplete={() => setConfirmOpen(true)}
                />
              </aside>
              <div className={styles.main}>
                {progress.data.phases.map((phase, index) => (
                  <PhaseCard key={phase.key} phase={phase} index={index} onOpenGuide={() => setGuideOpen(true)} />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <Dialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        size="sm"
        title="Mark setup complete?"
        description="This records that the chapter finished setup and hides the setup banner for everyone. The Setup Center stays available for review."
        preventClose={complete.isPending}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmOpen(false)} disabled={complete.isPending}>
              Cancel
            </Button>
            <Button variant="primary" onClick={() => void onConfirmComplete()} loading={complete.isPending} data-autofocus>
              Mark complete
            </Button>
          </>
        }
      />

      <OfficerGuideDialog open={guideOpen} onClose={() => setGuideOpen(false)} canMark={canManage} marked={guideTask?.status === 'complete'} marking={markGuide.isPending} onMark={() => void onMarkGuideRead()} />
    </Page>
  )
}

/** Shaped like the loaded page: a progress panel and three phase cards with task rows. */
function SetupSkeleton() {
  return (
    <div className={styles.columns} aria-busy="true" aria-label="Loading setup progress">
      <aside className={styles.side}>
        <div className={styles.panel}>
          <div className={styles.panelHeader}>
            <Skeleton width={80} height={80} circle />
            <div className={styles.panelHeaderText}>
              <SkeletonBlock lines={2} />
            </div>
          </div>
          <SkeletonBlock lines={3} />
        </div>
      </aside>
      <div className={styles.main}>
        {[0, 1, 2].map((index) => (
          <section key={index} className={styles.phase}>
            <div className={styles.skeletonPhaseHeader}>
              <Skeleton width="38%" height={18} />
              <Skeleton width="64%" height={12} />
            </div>
            <SkeletonRows rows={4} avatar />
          </section>
        ))}
      </div>
    </div>
  )
}
