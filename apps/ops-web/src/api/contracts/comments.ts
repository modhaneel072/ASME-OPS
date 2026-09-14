import { z } from 'zod'
import { listOf, UserRef } from './common'

/** Shape from asme/ops/serializers/comments.py. Soft-deleted comments keep their place with an empty body. */
export const Comment = z.looseObject({
  id: z.string(),
  entity_type: z.string(),
  entity_id: z.string(),
  author: UserRef.nullable(),
  body: z.string(),
  parent_comment_id: z.string().nullable().optional(),
  edited_at: z.string().nullable().optional(),
  created_at: z.string(),
  deleted: z.boolean().default(false),
  mentions: z.array(UserRef).default([]),
})
export type Comment = z.infer<typeof Comment>

export const CommentList = listOf(Comment)
export type CommentList = z.infer<typeof CommentList>

/** URL segment accepted by `/:entity/:id/comments`. */
export type CommentEntity = 'work-orders' | 'projects' | 'assets'

export const CommentInput = z.object({
  body: z.string().trim().min(1, 'Write something first.').max(8000, 'Keep comments under 8,000 characters.'),
  parent_comment_id: z.string().nullable().optional(),
})
export type CommentInput = z.infer<typeof CommentInput>
