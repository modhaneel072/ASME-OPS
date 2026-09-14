import type { Project } from '@/api/contracts/projects'
import { useProjectActivity } from '@/api/queries/projects'
import { ActivityTimeline, Card, LoadMore } from '@/ui'
import { activityToTimeline, QueryState } from '../shared'

export function ActivityTab({ project }: { project: Project }) {
  const activity = useProjectActivity(project.id, 25)
  const events = activity.data?.pages.flatMap((page) => page.items) ?? []
  const total = activity.data?.pages[0]?.total
  return (
    <Card title="Activity">
      <QueryState isPending={activity.isPending} isError={activity.isError} error={activity.error} onRetry={() => void activity.refetch()} title="Activity could not be loaded">
        <ActivityTimeline items={activityToTimeline(events)} emptyText="Nothing has happened on this project yet." />
        {events.length > 0 && <LoadMore loaded={events.length} total={total} hasMore={Boolean(activity.hasNextPage)} onLoadMore={() => void activity.fetchNextPage()} loading={activity.isFetchingNextPage} />}
      </QueryState>
    </Card>
  )
}
