import { Download, FileText, Image as ImageIcon, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { errorMessage } from '@/api/client'
import { formatBytes, isImageAttachment, type Attachment } from '@/api/contracts/attachments'
import type { WorkOrderDetail } from '@/api/contracts/work-orders'
import { useAttachments, useDeleteAttachment, useUploadAttachment } from '@/api/queries/attachments'
import { formatDate } from '@/lib/dates'
import { canOn, useSession } from '@/lib/permissions'
import { AttachmentUploader, Button, Card, Dialog, IconButton, InlineAlert, SkeletonRows, useToast } from '@/ui'
import styles from './work-orders.module.css'

export function FilesCard({ workOrder }: { workOrder: WorkOrderDetail }) {
  const session = useSession()
  const toast = useToast()
  const attachments = useAttachments('work-orders', workOrder.id)
  const upload = useUploadAttachment('work-orders', workOrder.id)
  const remove = useDeleteAttachment('work-orders', workOrder.id)
  const canAttach = canOn(session, 'work_order.attach', workOrder)
  const canManage = canOn(session, 'work_order.edit', workOrder)
  const [deleting, setDeleting] = useState<Attachment | null>(null)
  const items = attachments.data?.items ?? []

  return (
    <Card title={`Files${items.length ? ` (${items.length})` : ''}`} flush>
      {canAttach && (
        <div style={{ padding: 'var(--space-3) var(--space-4)' }}>
          <AttachmentUploader
            compact
            onUpload={async (file) => {
              try {
                await upload.mutateAsync(file)
                toast.success('File uploaded', file.name)
              } catch (error) {
                toast.error('Upload failed', errorMessage(error))
                throw new Error(errorMessage(error))
              }
            }}
          />
        </div>
      )}
      {attachments.isPending ? (
        <SkeletonRows rows={2} />
      ) : attachments.isError ? (
        <div style={{ padding: 'var(--space-3) var(--space-4)' }}>
          <InlineAlert
            tone="danger"
            title="Files could not be loaded"
            actions={
              <Button size="sm" onClick={() => void attachments.refetch()}>
                Retry
              </Button>
            }
          >
            {errorMessage(attachments.error)}
          </InlineAlert>
        </div>
      ) : items.length === 0 ? (
        <p className={styles.muted} style={{ padding: 'var(--space-3) var(--space-4)' }}>
          No files yet.
        </p>
      ) : (
        <ul aria-label="Files">
          {items.map((file) => {
            const own = file.uploaded_by?.id === session.user.id
            return (
              <li key={file.id} className={styles.fileRow}>
                {isImageAttachment(file) ? <ImageIcon size={16} aria-hidden="true" style={{ color: 'var(--color-text-muted)' }} /> : <FileText size={16} aria-hidden="true" style={{ color: 'var(--color-text-muted)' }} />}
                <span className={styles.fileName} title={file.original_name}>
                  {file.original_name}
                </span>
                <span className={styles.fileMeta}>
                  {formatBytes(file.size_bytes)} · {file.uploaded_by?.name ?? 'Unknown'} · {formatDate(file.created_at)}
                </span>
                <a href={file.download_url} className={styles.fileMeta} aria-label={`Download ${file.original_name}`} title="Download">
                  <Download size={16} aria-hidden="true" />
                </a>
                {(own || canManage) && (
                  <IconButton size="sm" variant="ghost" label={`Delete ${file.original_name}`} onClick={() => setDeleting(file)}>
                    <Trash2 size={16} />
                  </IconButton>
                )}
              </li>
            )
          })}
        </ul>
      )}
      <Dialog
        open={Boolean(deleting)}
        onClose={() => setDeleting(null)}
        size="sm"
        title="Delete this file?"
        description={deleting ? `${deleting.original_name} will be removed permanently.` : undefined}
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
                  toast.success('File deleted')
                  setDeleting(null)
                } catch (error) {
                  toast.error('Could not delete the file', errorMessage(error))
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
