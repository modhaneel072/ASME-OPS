import { z } from 'zod'
import { listOf, UserRef } from './common'

/** Shape from asme/ops/serializers/attachments.py; `download_url` carries a short-lived signed token. */
export const Attachment = z.looseObject({
  id: z.string(),
  entity_type: z.string(),
  entity_id: z.string(),
  original_name: z.string(),
  content_type: z.string().nullable().optional(),
  size_bytes: z.number().default(0),
  is_image: z.boolean().optional(),
  uploaded_by: UserRef.nullable(),
  download_url: z.string(),
  created_at: z.string(),
})
export type Attachment = z.infer<typeof Attachment>

export const AttachmentList = listOf(Attachment)
export type AttachmentList = z.infer<typeof AttachmentList>

/** URL segment accepted by `/:entity/:id/attachments`. */
export type AttachmentEntity = 'work-orders' | 'projects' | 'assets'

export function isImageAttachment(attachment: Pick<Attachment, 'is_image' | 'content_type'>): boolean {
  return attachment.is_image ?? Boolean(attachment.content_type?.startsWith('image/'))
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
