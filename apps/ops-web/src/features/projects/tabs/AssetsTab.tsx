import { Box, ChevronRight } from 'lucide-react'
import type { Project } from '@/api/contracts/projects'
import { useAssets } from '@/api/queries/assets'
import { Card, EmptyState, LinkButton, ListRow, StatusBadge } from '@/ui'
import { QueryState } from '../shared'

export function AssetsTab({ project }: { project: Project }) {
  const assets = useAssets({ project: [project.id] })
  const items = assets.data?.items ?? []
  return (
    <Card
      title={`Assets${assets.data ? ` (${assets.data.total ?? items.length})` : ''}`}
      flush
      actions={
        <LinkButton size="sm" to={`/assets?filter[project]=${encodeURIComponent(project.id)}`}>
          Open in Assets
        </LinkButton>
      }
    >
      <QueryState isPending={assets.isPending} isError={assets.isError} error={assets.error} onRetry={() => void assets.refetch()} title="Assets could not be loaded">
        {items.length === 0 ? (
          <EmptyState compact illustration="box" title="No assets linked" description="Assign equipment and sub-assemblies to this project from the Assets screen." />
        ) : (
          <ul aria-label="Assets">
            {items.map((asset) => (
              <li key={asset.id}>
                <ListRow
                  compact
                  to={`/assets/${asset.id}`}
                  leading={<Box size={14} aria-hidden="true" style={{ color: 'var(--color-text-muted)' }} />}
                  title={asset.name}
                  meta={
                    <>
                      {asset.code && <span className="mono">{asset.code}</span>}
                      {asset.location && <span>{asset.location.name}</span>}
                      <span>{asset.open_work_order_count ?? 0} open work</span>
                    </>
                  }
                  trailing={
                    <>
                      <StatusBadge status={asset.status} size="sm" />
                      <ChevronRight size={14} aria-hidden="true" style={{ color: 'var(--color-text-disabled)' }} />
                    </>
                  }
                />
              </li>
            ))}
          </ul>
        )}
      </QueryState>
    </Card>
  )
}
