import { Download, FileText, Image, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { errorMessage } from '@/api/client'
import type { Attachment, Project } from '@/api/contracts/projects'
import { useDeleteAttachment, useProjectAttachments, useUploadProjectAttachment } from '@/api/queries/projects'
import { formatDateTime } from '@/lib/dates'
import { canOn, useSession } from '@/lib/permissions'
import { AttachmentUploader, Button, Card, Dialog, EmptyState, IconButton, Stack, useToast } from '@/ui'
import { formatBytes, QueryState } from '../shared'
import styles from '../projects.module.css'

export function DocumentsTab({ project }: { project: Project }) {
  const session = useSession()
  const canAttach = canOn(session, 'work_order.attach', { project_id: project.id })
  const canManage = canOn(session, 'project.manage', { project_id: project.id })
  const toast = useToast()
  const list = useProjectAttachments(project.id)
  const upload = useUploadProjectAttachment(project.id)
  const remove = useDeleteAttachment(project.id)
  const [pendingDelete, setPendingDelete] = useState<Attachment | null>(null)

  const onUpload = async (file: File) => {
    try {
      const saved = await upload.mutateAsync(file)
      toast.success('File uploaded', saved.original_name)
    } catch (error) {
      toast.error('Upload failed', errorMessage(error))
      throw error
    }
  }

  const confirmDelete = async () => {
    if (!pendingDelete) return
    try {
      await remove.mutateAsync(pendingDelete.id)
      toast.success('File removed', pendingDelete.original_name)
      setPendingDelete(null)
    } catch (error) {
      setPendingDelete(null)
      toast.error('Could not remove file', errorMessage(error))
    }
  }

  const items = list.data?.items ?? []

  return (
    <Stack>
      {canAttach && (
        <Card title="Upload">
          <AttachmentUploader onUpload={onUpload} />
        </Card>
      )}
      <Card title={`Documents${list.data ? ` (${items.length})` : ''}`} flush>
        <QueryState isPending={list.isPending} isError={list.isError} error={list.error} onRetry={() => void list.refetch()} title="Documents could not be loaded">
          {items.length === 0 ? (
            <EmptyState compact illustration="folder" title="No documents yet" description={canAttach ? 'Drop drawings, reports and CAD exports above to keep them with the project.' : 'Files uploaded to this project appear here.'} />
          ) : (
            <ul aria-label="Documents">
              {items.map((file) => {
                const canDelete = canAttach && (file.uploaded_by?.id === session.user.id || canManage)
                return (
                  <li key={file.id} className={styles.fileRow}>
                    <span className={styles.fileIcon} aria-hidden="true">
                      {file.is_image ? <Image size={18} /> : <FileText size={18} />}
                    </span>
                    <span style={{ minWidth: 0 }}>
                      <span className={styles.fileName}>{file.original_name}</span>
                      <span className={styles.fileMeta}>
                        {formatBytes(file.size_bytes)} · {file.uploaded_by?.name ?? 'Unknown'} · {formatDateTime(file.created_at)}
                      </span>
                    </span>
                    <span className={styles.milestoneActions}>
                      <a href={file.download_url} className={styles.chipLink} download={file.original_name} aria-label={`Download ${file.original_name}`}>
                        <Download size={14} aria-hidden="true" /> Download
                      </a>
                      {canDelete && (
                        <IconButton size="sm" variant="ghost" label={`Delete ${file.original_name}`} onClick={() => setPendingDelete(file)}>
                          <Trash2 size={14} />
                        </IconButton>
                      )}
                    </span>
                  </li>
                )
              })}
            </ul>
          )}
        </QueryState>
      </Card>
      <Dialog
        open={Boolean(pendingDelete)}
        onClose={() => setPendingDelete(null)}
        size="sm"
        title="Remove this file?"
        description={pendingDelete ? `“${pendingDelete.original_name}” will be deleted permanently.` : undefined}
        preventClose={remove.isPending}
        footer={
          <>
            <Button variant="ghost" onClick={() => setPendingDelete(null)} disabled={remove.isPending}>
              Cancel
            </Button>
            <Button variant="danger" onClick={() => void confirmDelete()} loading={remove.isPending} data-autofocus>
              Remove file
            </Button>
          </>
        }
      />
    </Stack>
  )
}
