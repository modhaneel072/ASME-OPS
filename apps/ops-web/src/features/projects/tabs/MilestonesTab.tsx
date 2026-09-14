import { CheckCircle2, Pencil, Plus, RotateCcw, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { ApiError, errorMessage } from '@/api/client'
import { toMilestonePayload, type Milestone, type MilestoneInput, type Project } from '@/api/contracts/projects'
import { useCreateMilestone, useDeleteMilestone, useProjectMilestones, useUpdateMilestone } from '@/api/queries/projects'
import { formatDate } from '@/lib/dates'
import { canOn, useSession } from '@/lib/permissions'
import { Avatar, Badge, Button, Card, Dialog, EmptyState, IconButton, StatusBadge, useToast } from '@/ui'
import { MilestoneDialog } from '../MilestoneDialog'
import { QueryState } from '../shared'
import styles from '../projects.module.css'

export function MilestonesTab({ project }: { project: Project }) {
  const session = useSession()
  const canManage = canOn(session, 'milestone.manage', { project_id: project.id })
  const toast = useToast()
  const list = useProjectMilestones(project.id)
  const create = useCreateMilestone(project.id)
  const update = useUpdateMilestone(project.id)
  const remove = useDeleteMilestone(project.id)

  const [dialog, setDialog] = useState<{ open: boolean; milestone: Milestone | null }>({ open: false, milestone: null })
  const [pendingDelete, setPendingDelete] = useState<Milestone | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  const openDialog = (milestone: Milestone | null) => {
    create.reset()
    update.reset()
    setDialog({ open: true, milestone })
  }
  const closeDialog = () => setDialog((current) => ({ ...current, open: false }))

  const submit = async (values: MilestoneInput) => {
    const payload = toMilestonePayload(values)
    try {
      if (dialog.milestone) {
        await update.mutateAsync({ id: dialog.milestone.id, ...payload })
        toast.success('Milestone updated')
      } else {
        await create.mutateAsync(payload)
        toast.success('Milestone added', payload.name)
      }
      closeDialog()
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not save milestone', errorMessage(error))
    }
  }

  const setStatus = async (milestone: Milestone, status: 'done' | 'planned') => {
    setBusyId(milestone.id)
    try {
      await update.mutateAsync({ id: milestone.id, status })
      toast.success(status === 'done' ? 'Milestone marked done' : 'Milestone reopened', milestone.name)
    } catch (error) {
      toast.error('Could not update milestone', errorMessage(error))
    } finally {
      setBusyId(null)
    }
  }

  const confirmDelete = async () => {
    if (!pendingDelete) return
    try {
      await remove.mutateAsync(pendingDelete.id)
      toast.success('Milestone deleted', pendingDelete.name)
      setPendingDelete(null)
    } catch (error) {
      setPendingDelete(null)
      toast.error('Could not delete milestone', errorMessage(error))
    }
  }

  const items = list.data?.items ?? []

  return (
    <>
      <Card
        title={`Milestones${list.data ? ` (${items.length})` : ''}`}
        flush
        actions={
          canManage ? (
            <Button size="sm" variant="primary" leadingIcon={<Plus size={14} />} onClick={() => openDialog(null)}>
              Add milestone
            </Button>
          ) : undefined
        }
      >
        <QueryState isPending={list.isPending} isError={list.isError} error={list.error} onRetry={() => void list.refetch()} title="Milestones could not be loaded">
          {items.length === 0 ? (
            <EmptyState
              compact
              illustration="clipboard"
              title="No milestones yet"
              description="Break the project into checkpoints such as design review, build complete and competition day."
              action={
                canManage ? (
                  <Button size="sm" variant="primary" leadingIcon={<Plus size={14} />} onClick={() => openDialog(null)}>
                    Add the first milestone
                  </Button>
                ) : undefined
              }
            />
          ) : (
            <ul className={styles.milestoneList} aria-label="Milestones">
              {items.map((milestone) => {
                const done = milestone.status === 'done'
                const busy = busyId === milestone.id && update.isPending
                return (
                  <li key={milestone.id} className={styles.milestone}>
                    <div className={styles.milestoneMain}>
                      <span className={styles.milestoneName}>
                        <span className={styles.rowName}>{milestone.name}</span>
                        <StatusBadge status={milestone.status} size="sm" />
                      </span>
                      <span className={styles.milestoneMeta}>
                        <span style={milestone.status === 'missed' ? { color: 'var(--color-danger-text)' } : undefined}>{milestone.due_date ? `Due ${formatDate(milestone.due_date)}` : 'No due date'}</span>
                        {milestone.owner ? (
                          <span className={styles.owner}>
                            <Avatar name={milestone.owner.name} src={milestone.owner.avatar_url} />
                            {milestone.owner.name}
                          </span>
                        ) : (
                          <span>No owner</span>
                        )}
                        <Badge tone="outline" size="sm" title="Weight toward completion">
                          Weight {milestone.weight ?? 1}
                        </Badge>
                        {done && milestone.completed_at && <span>Completed {formatDate(milestone.completed_at)}</span>}
                        {milestone.description && <span className={styles.rowName}>{milestone.description}</span>}
                      </span>
                    </div>
                    {canManage && (
                      <div className={styles.milestoneActions}>
                        {done ? (
                          <Button size="sm" variant="ghost" leadingIcon={<RotateCcw size={14} />} onClick={() => void setStatus(milestone, 'planned')} loading={busy}>
                            Reopen
                          </Button>
                        ) : (
                          <Button size="sm" variant="ghost" leadingIcon={<CheckCircle2 size={14} />} onClick={() => void setStatus(milestone, 'done')} loading={busy}>
                            Mark done
                          </Button>
                        )}
                        <IconButton size="sm" variant="ghost" label={`Edit ${milestone.name}`} onClick={() => openDialog(milestone)}>
                          <Pencil size={14} />
                        </IconButton>
                        <IconButton size="sm" variant="ghost" label={`Delete ${milestone.name}`} onClick={() => setPendingDelete(milestone)}>
                          <Trash2 size={14} />
                        </IconButton>
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </QueryState>
      </Card>

      <MilestoneDialog open={dialog.open} milestone={dialog.milestone} submitting={create.isPending || update.isPending} error={dialog.milestone ? update.error : create.error} onSubmit={submit} onClose={closeDialog} />

      <Dialog
        open={Boolean(pendingDelete)}
        onClose={() => setPendingDelete(null)}
        size="sm"
        title="Delete this milestone?"
        description={pendingDelete ? `“${pendingDelete.name}” will be removed from ${project.name}. Work orders are not affected.` : undefined}
        preventClose={remove.isPending}
        footer={
          <>
            <Button variant="ghost" onClick={() => setPendingDelete(null)} disabled={remove.isPending}>
              Cancel
            </Button>
            <Button variant="danger" onClick={() => void confirmDelete()} loading={remove.isPending} data-autofocus>
              Delete milestone
            </Button>
          </>
        }
      />
    </>
  )
}
