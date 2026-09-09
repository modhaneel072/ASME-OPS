import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import { Attachment, AttachmentList, type AttachmentEntity } from '../contracts/attachments'

export const attachmentKeys = {
  all: ['attachments'] as const,
  list: (entity: AttachmentEntity, id: string) => ['attachments', 'list', entity, id] as const,
}

export function useAttachments(entity: AttachmentEntity, id: string | undefined) {
  return useQuery({
    queryKey: attachmentKeys.list(entity, id ?? ''),
    queryFn: async () => AttachmentList.parse(await api.get(`/${entity}/${id}/attachments`)),
    enabled: Boolean(id),
  })
}

/** Multipart upload; the field name is `file` and the client adds the `X-Requested-With` header. */
export async function uploadAttachment(entity: AttachmentEntity, id: string, file: File) {
  const form = new FormData()
  form.append('file', file, file.name)
  return Attachment.parse((await api.upload<{ attachment: unknown }>(`/${entity}/${id}/attachments`, form)).attachment)
}

function useInvalidateAttachments(entity: AttachmentEntity, id: string) {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: attachmentKeys.list(entity, id) })
}

export function useUploadAttachment(entity: AttachmentEntity, id: string) {
  const invalidate = useInvalidateAttachments(entity, id)
  return useMutation({
    mutationFn: (file: File) => uploadAttachment(entity, id, file),
    onSuccess: () => invalidate(),
  })
}

export function useDeleteAttachment(entity: AttachmentEntity, id: string) {
  const invalidate = useInvalidateAttachments(entity, id)
  return useMutation({
    mutationFn: (attachmentId: string) => api.delete(`/attachments/${attachmentId}`),
    onSuccess: () => invalidate(),
  })
}
