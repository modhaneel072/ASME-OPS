import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../client'
import {
  ActivityList,
  Attachment,
  AttachmentList,
  Milestone,
  MilestoneList,
  Project,
  ProjectDetail,
  ProjectHealth,
  ProjectList,
  ProjectWorkOrderList,
  type MembersInput,
  type MilestonePayload,
  type ProjectListParams,
  type ProjectPayload,
} from '../contracts/projects'
import type { ComboOption } from '@/ui/Form'

export const projectKeys = {
  all: ['projects'] as const,
  list: (params: ProjectListParams) => ['projects', 'list', params] as const,
  detail: (id: string) => ['projects', 'detail', id] as const,
  health: (id: string) => ['projects', 'health', id] as const,
  activity: (id: string) => ['projects', 'activity', id] as const,
  milestones: (id: string) => ['projects', 'milestones', id] as const,
  attachments: (id: string) => ['projects', 'attachments', id] as const,
  workOrders: (id: string) => ['projects', 'work-orders', id] as const,
}

export function useProjects(params: ProjectListParams = {}) {
  return useQuery({
    queryKey: projectKeys.list(params),
    queryFn: async () =>
      ProjectList.parse(
        await api.get('/projects', {
          params: {
            view: params.view,
            q: params.q,
            'filter[lead]': params.lead,
            'filter[status]': params.status,
            'filter[risk]': params.risk,
            'filter[team]': params.team,
            'filter[academic_year]': params.academic_year,
            'filter[competition]': params.competition,
            sort: params.sort ?? 'name',
            limit: params.limit ?? 200,
            cursor: params.cursor,
          },
        }),
      ),
    placeholderData: keepPreviousData,
  })
}

export function useProjectOptions(): { options: ComboOption<string>[]; isLoading: boolean } {
  const query = useProjects({ view: 'active', limit: 200 })
  const options = (query.data?.items ?? []).map((project) => ({ value: project.id, label: project.name, meta: project.code }))
  return { options, isLoading: query.isPending }
}

/* Detail --------------------------------------------------------------------- */

/** `GET /projects/:id` → `{ project, members }`. */
export function useProject(id: string | undefined) {
  return useQuery({
    queryKey: projectKeys.detail(id ?? ''),
    queryFn: async () => ProjectDetail.parse(await api.get(`/projects/${id}`)),
    enabled: Boolean(id),
  })
}

export function useProjectHealth(id: string | undefined) {
  return useQuery({
    queryKey: projectKeys.health(id ?? ''),
    queryFn: async () => ProjectHealth.parse(await api.get(`/projects/${id}/health`)),
    enabled: Boolean(id),
  })
}

export function useProjectActivity(id: string | undefined, limit = 25) {
  return useInfiniteQuery({
    queryKey: [...projectKeys.activity(id ?? ''), limit],
    queryFn: async ({ pageParam }) => ActivityList.parse(await api.get(`/projects/${id}/activity`, { params: { limit, cursor: pageParam || undefined } })),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    enabled: Boolean(id),
  })
}

export function useProjectMilestones(id: string | undefined) {
  return useQuery({
    queryKey: projectKeys.milestones(id ?? ''),
    queryFn: async () => MilestoneList.parse(await api.get(`/projects/${id}/milestones`)),
    enabled: Boolean(id),
  })
}

export function useProjectAttachments(id: string | undefined) {
  return useQuery({
    queryKey: projectKeys.attachments(id ?? ''),
    queryFn: async () => AttachmentList.parse(await api.get(`/projects/${id}/attachments`)),
    enabled: Boolean(id),
  })
}

/** Work orders of one project for the Work tab (owned by the Work Orders slice; read-only here). */
export function useProjectWorkOrders(id: string | undefined, limit = 50) {
  return useQuery({
    queryKey: [...projectKeys.workOrders(id ?? ''), limit],
    queryFn: async () => ProjectWorkOrderList.parse(await api.get('/work-orders', { params: { 'filter[project]': id, tab: 'all', sort: '-updated_at', limit } })),
    enabled: Boolean(id),
  })
}

/* Mutations ------------------------------------------------------------------ */

function useInvalidateProjects() {
  const client = useQueryClient()
  return (id?: string) =>
    Promise.all([
      client.invalidateQueries({ queryKey: projectKeys.all }),
      client.invalidateQueries({ queryKey: ['setup'] }),
      id ? client.invalidateQueries({ queryKey: ['work-orders'] }) : Promise.resolve(),
    ])
}

export function useCreateProject() {
  const invalidate = useInvalidateProjects()
  return useMutation({
    mutationFn: async (input: ProjectPayload) => Project.parse((await api.post<{ project: unknown }>('/projects', input)).project),
    onSuccess: () => invalidate(),
  })
}

export function useUpdateProject(id: string) {
  const invalidate = useInvalidateProjects()
  return useMutation({
    mutationFn: async (input: Partial<ProjectPayload>) => Project.parse((await api.patch<{ project: unknown }>(`/projects/${id}`, input)).project),
    onSuccess: () => invalidate(),
  })
}

export function useArchiveProject() {
  const invalidate = useInvalidateProjects()
  return useMutation({
    mutationFn: async (id: string) => Project.parse((await api.post<{ project: unknown }>(`/projects/${id}/archive`, {})).project),
    onSuccess: () => invalidate(),
  })
}

export function useRestoreProject() {
  const invalidate = useInvalidateProjects()
  return useMutation({
    mutationFn: async (id: string) => Project.parse((await api.post<{ project: unknown }>(`/projects/${id}/restore`, {})).project),
    onSuccess: () => invalidate(),
  })
}

export function useReplaceMembers(id: string) {
  const invalidate = useInvalidateProjects()
  return useMutation({
    mutationFn: async (input: MembersInput) => ProjectDetail.parse(await api.put(`/projects/${id}/members`, input)),
    onSuccess: () => invalidate(),
  })
}

function useInvalidateMilestones(projectId: string) {
  const client = useQueryClient()
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: projectKeys.milestones(projectId) }),
      client.invalidateQueries({ queryKey: projectKeys.health(projectId) }),
      client.invalidateQueries({ queryKey: projectKeys.activity(projectId) }),
      client.invalidateQueries({ queryKey: projectKeys.detail(projectId) }),
      client.invalidateQueries({ queryKey: ['projects', 'list'] }),
    ])
}

export function useCreateMilestone(projectId: string) {
  const invalidate = useInvalidateMilestones(projectId)
  return useMutation({
    mutationFn: async (input: MilestonePayload) => Milestone.parse((await api.post<{ milestone: unknown }>(`/projects/${projectId}/milestones`, input)).milestone),
    onSuccess: () => invalidate(),
  })
}

export function useUpdateMilestone(projectId: string) {
  const invalidate = useInvalidateMilestones(projectId)
  return useMutation({
    mutationFn: async ({ id, ...input }: Partial<MilestonePayload> & { id: string }) =>
      Milestone.parse((await api.patch<{ milestone: unknown }>(`/projects/${projectId}/milestones/${id}`, input)).milestone),
    onSuccess: () => invalidate(),
  })
}

export function useDeleteMilestone(projectId: string) {
  const invalidate = useInvalidateMilestones(projectId)
  return useMutation({
    mutationFn: (id: string) => api.delete(`/projects/${projectId}/milestones/${id}`),
    onSuccess: () => invalidate(),
  })
}

export function useUploadProjectAttachment(projectId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return Attachment.parse((await api.upload<{ attachment: unknown }>(`/projects/${projectId}/attachments`, form)).attachment)
    },
    onSuccess: () => Promise.all([client.invalidateQueries({ queryKey: projectKeys.attachments(projectId) }), client.invalidateQueries({ queryKey: projectKeys.activity(projectId) })]),
  })
}

export function useDeleteAttachment(projectId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (attachmentId: string) => api.delete(`/attachments/${attachmentId}`),
    onSuccess: () => Promise.all([client.invalidateQueries({ queryKey: projectKeys.attachments(projectId) }), client.invalidateQueries({ queryKey: projectKeys.activity(projectId) })]),
  })
}
