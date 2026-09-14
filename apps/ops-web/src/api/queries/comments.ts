import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import { Comment, CommentList, type CommentEntity, type CommentInput } from '../contracts/comments'

export const commentKeys = {
  all: ['comments'] as const,
  list: (entity: CommentEntity, id: string) => ['comments', 'list', entity, id] as const,
}

/** Comments for a work order, project or asset, oldest first. */
export function useComments(entity: CommentEntity, id: string | undefined) {
  return useQuery({
    queryKey: commentKeys.list(entity, id ?? ''),
    queryFn: async () => CommentList.parse(await api.get(`/${entity}/${id}/comments`)),
    enabled: Boolean(id),
  })
}

function useInvalidateComments(entity: CommentEntity, id: string) {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: commentKeys.list(entity, id) })
}

export function useCreateComment(entity: CommentEntity, id: string) {
  const invalidate = useInvalidateComments(entity, id)
  return useMutation({
    mutationFn: async (input: CommentInput) => Comment.parse((await api.post<{ comment: unknown }>(`/${entity}/${id}/comments`, input)).comment),
    onSuccess: () => invalidate(),
  })
}

export function useUpdateComment(entity: CommentEntity, id: string) {
  const invalidate = useInvalidateComments(entity, id)
  return useMutation({
    mutationFn: async ({ commentId, body }: { commentId: string; body: string }) => Comment.parse((await api.patch<{ comment: unknown }>(`/comments/${commentId}`, { body })).comment),
    onSuccess: () => invalidate(),
  })
}

export function useDeleteComment(entity: CommentEntity, id: string) {
  const invalidate = useInvalidateComments(entity, id)
  return useMutation({
    mutationFn: async (commentId: string) => Comment.parse((await api.delete<{ comment: unknown }>(`/comments/${commentId}`)).comment),
    onSuccess: () => invalidate(),
  })
}
