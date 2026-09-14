import { MoreHorizontal, Pencil, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { errorMessage } from '@/api/client'
import type { Comment } from '@/api/contracts/comments'
import type { WorkOrderDetail } from '@/api/contracts/work-orders'
import { useComments, useCreateComment, useDeleteComment, useUpdateComment } from '@/api/queries/comments'
import { usePeopleOptions } from '@/api/queries/users'
import { formatRelative } from '@/lib/dates'
import { canOn, useSession } from '@/lib/permissions'
import { Avatar, Button, Card, CommentComposer, Dialog, DropdownMenu, IconButton, InlineAlert, renderMentions, SkeletonRows, Textarea, useToast, type MentionCandidate } from '@/ui'
import styles from './work-orders.module.css'

export function CommentsCard({ workOrder }: { workOrder: WorkOrderDetail }) {
  const session = useSession()
  const toast = useToast()
  const comments = useComments('work-orders', workOrder.id)
  const create = useCreateComment('work-orders', workOrder.id)
  const update = useUpdateComment('work-orders', workOrder.id)
  const remove = useDeleteComment('work-orders', workOrder.id)
  const people = usePeopleOptions()
  const canComment = canOn(session, 'work_order.comment', workOrder)
  const canManage = canOn(session, 'work_order.edit', workOrder)
  const [editing, setEditing] = useState<{ id: string; body: string } | null>(null)
  const [deleting, setDeleting] = useState<Comment | null>(null)

  const candidates = useMemo<MentionCandidate[]>(() => people.options.map((o) => ({ id: o.value, name: o.label })), [people.options])
  const searchPeople = (query: string) => {
    const q = query.trim().toLowerCase()
    return q ? candidates.filter((c) => c.name.toLowerCase().includes(q)) : candidates
  }

  const items = comments.data?.items ?? []

  return (
    <Card title={`Comments${items.length ? ` (${items.length})` : ''}`}>
      <div className={styles.comments}>
        {comments.isPending ? (
          <SkeletonRows rows={2} avatar />
        ) : comments.isError ? (
          <InlineAlert
            tone="danger"
            title="Comments could not be loaded"
            actions={
              <Button size="sm" onClick={() => void comments.refetch()}>
                Retry
              </Button>
            }
          >
            {errorMessage(comments.error)}
          </InlineAlert>
        ) : items.length === 0 ? (
          <p className={styles.muted}>No comments yet. Mention a teammate with @ to pull them in.</p>
        ) : (
          <ol className={styles.comments} aria-label="Comments">
            {items.map((comment) => {
              const own = comment.author?.id === session.user.id
              const mayChange = !comment.deleted && (own || canManage)
              return (
                <li key={comment.id} className={styles.comment}>
                  <Avatar name={comment.author?.name ?? 'Unknown'} src={comment.author?.avatar_url} />
                  <div className={styles.commentBody}>
                    <div className={styles.commentHead}>
                      <span className={styles.commentAuthor}>{comment.author?.name ?? 'Unknown member'}</span>
                      <time dateTime={comment.created_at} title={comment.created_at}>
                        {formatRelative(comment.created_at)}
                      </time>
                      {comment.edited_at && !comment.deleted && <span>(edited)</span>}
                      <span style={{ flex: 1 }} />
                      {mayChange && (
                        <DropdownMenu
                          align="end"
                          label="Comment actions"
                          items={[
                            { key: 'edit', label: 'Edit', icon: <Pencil size={16} />, onSelect: () => setEditing({ id: comment.id, body: comment.body }) },
                            { key: 'delete', label: 'Delete', icon: <Trash2 size={16} />, destructive: true, onSelect: () => setDeleting(comment) },
                          ]}
                          trigger={(props) => (
                            <IconButton {...props} ref={props.ref} size="sm" variant="ghost" label="Comment actions">
                              <MoreHorizontal size={16} />
                            </IconButton>
                          )}
                        />
                      )}
                    </div>
                    {comment.deleted ? (
                      <p className={styles.commentDeleted}>This comment was deleted.</p>
                    ) : editing?.id === comment.id ? (
                      <form
                        className={styles.commentEdit}
                        onSubmit={async (event) => {
                          event.preventDefault()
                          const body = editing.body.trim()
                          if (!body) return
                          try {
                            await update.mutateAsync({ commentId: comment.id, body })
                            toast.success('Comment updated')
                            setEditing(null)
                          } catch (error) {
                            toast.error('Could not update the comment', errorMessage(error))
                          }
                        }}
                      >
                        <Textarea value={editing.body} onChange={(event) => setEditing({ id: comment.id, body: event.target.value })} rows={3} aria-label="Edit comment" />
                        <div className={styles.inlineActions}>
                          <Button size="sm" variant="ghost" onClick={() => setEditing(null)} disabled={update.isPending}>
                            Cancel
                          </Button>
                          <Button size="sm" variant="primary" type="submit" loading={update.isPending}>
                            Save
                          </Button>
                        </div>
                      </form>
                    ) : (
                      <p className={styles.commentText}>{renderMentions(comment.body)}</p>
                    )}
                  </div>
                </li>
              )
            })}
          </ol>
        )}
        {canComment && (
          <CommentComposer
            submitting={create.isPending}
            searchPeople={searchPeople}
            onSubmit={async (body) => {
              try {
                await create.mutateAsync({ body })
                toast.success('Comment posted')
              } catch (error) {
                toast.error('Could not post the comment', errorMessage(error))
                throw error
              }
            }}
          />
        )}
      </div>
      <Dialog
        open={Boolean(deleting)}
        onClose={() => setDeleting(null)}
        size="sm"
        title="Delete this comment?"
        description="The comment keeps its place in the thread but its text is removed."
        preventClose={remove.isPending}
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleting(null)} disabled={remove.isPending}>
              Cancel
            </Button>
            <Button
              variant="danger"
              data-autofocus
              loading={remove.isPending}
              onClick={async () => {
                if (!deleting) return
                try {
                  await remove.mutateAsync(deleting.id)
                  toast.success('Comment deleted')
                  setDeleting(null)
                } catch (error) {
                  toast.error('Could not delete the comment', errorMessage(error))
                }
              }}
            >
              Delete
            </Button>
          </>
        }
      />
    </Card>
  )
}
