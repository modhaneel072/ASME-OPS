import { Activity, Boxes, ClipboardList, ExternalLink, History, MoreHorizontal, Pencil, Plus } from 'lucide-react'
import { useMemo, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { errorMessage } from '@/api/client'
import { ASSET_CRITICALITY_LABELS, DOWNTIME_TYPE_LABELS, type Asset, type AssetCriticality, type AssetTimelineEntry, type DowntimeType } from '@/api/contracts/assets'
import { labelFor } from '@/api/contracts/common'
import { useAsset, useAssetHistory, useAssetOpenWork, useAssets } from '@/api/queries/assets'
import { formatDate, formatDateTime, formatDue, formatMoney } from '@/lib/dates'
import { ActivityTimeline, Button, Card, DetailPanel, DropdownMenu, EmptyState, FieldList, IconButton, InlineAlert, ListRow, SkeletonBlock, SkeletonRows, Stack, StatusBadge, type TimelineItem } from '@/ui'
import styles from './assets.module.css'
import { CriticalityBadge, TypeChips } from './bits'

export interface AssetDetailProps {
  asset: Asset
  canManage: boolean
  canChangeStatus: boolean
  canCreateWorkOrder: boolean
  onEdit: () => void
  onAddChild: () => void
  onChangeStatus: () => void
}

export function AssetDetail({ asset, canManage, canChangeStatus, canCreateWorkOrder, onEdit, onAddChild, onChangeStatus }: AssetDetailProps) {
  const navigate = useNavigate()
  const parent = useAsset(asset.parent_id ?? undefined)
  const children = useAssets({ parent: asset.id, limit: 200 })
  const openWork = useAssetOpenWork(asset.id)
  const history = useAssetHistory(asset.id)

  const subtitle = [asset.manufacturer, asset.model, asset.serial_number ? `S/N ${asset.serial_number}` : null].filter(Boolean).join(' · ')
  const criticality = (asset.criticality ?? 'none') as AssetCriticality
  const customFields = Object.entries(asset.custom_fields ?? {})

  const menuItems = [
    ...(canManage ? [{ key: 'child', label: 'Add sub-asset', icon: <Plus size={16} />, onSelect: onAddChild }] : []),
    { key: 'work', label: 'Go to work orders', icon: <ClipboardList size={16} />, onSelect: () => navigate(`/work-orders?filter[asset]=${asset.id}`) },
    ...(canCreateWorkOrder ? [{ key: 'new-work', label: 'New work order for this asset', icon: <ExternalLink size={16} />, onSelect: () => navigate(`/work-orders/new?asset=${asset.id}`) }] : []),
  ]

  const timeline = useMemo<TimelineItem[]>(() => (history.data ?? []).map(toTimelineItem), [history.data])

  return (
    <DetailPanel
      eyebrow={
        <span className={styles.eyebrowRow}>
          <Boxes size={12} aria-hidden="true" />
          {asset.types.length ? <TypeChips types={asset.types} /> : <span>Asset</span>}
          {asset.code && <span className={styles.code}>{asset.code}</span>}
        </span>
      }
      title={
        <span className={styles.titleRow}>
          {asset.name}
          <StatusBadge status={asset.status} />
          <CriticalityBadge criticality={asset.criticality} />
        </span>
      }
      subtitle={subtitle || undefined}
      actions={
        <>
          {canChangeStatus && (
            <Button leadingIcon={<Activity size={16} />} onClick={onChangeStatus}>
              Change status
            </Button>
          )}
          {canManage && (
            <Button leadingIcon={<Pencil size={16} />} onClick={onEdit}>
              Edit
            </Button>
          )}
          <DropdownMenu
            align="end"
            label="More actions"
            items={menuItems}
            trigger={(props) => (
              <IconButton {...props} ref={props.ref} label="More actions">
                <MoreHorizontal size={18} />
              </IconButton>
            )}
          />
        </>
      }
    >
      <Stack>
        <Card title="Details">
          <FieldList
            items={[
              { label: 'Location', value: asset.location ? <Link to={`/locations/${asset.location.id}`}>{asset.location.name}</Link> : '—' },
              { label: 'Project', value: asset.project ? <Link to={`/projects/${asset.project.id}`}>{asset.project.name}</Link> : 'Chapter-wide' },
              { label: 'Responsible team', value: asset.team?.name ?? '—' },
              { label: 'Owner', value: asset.owner?.name ?? '—' },
              { label: 'Manufacturer', value: asset.manufacturer || '—' },
              { label: 'Model', value: asset.model || '—' },
              { label: 'Serial number', value: asset.serial_number ? <span className="mono">{asset.serial_number}</span> : '—' },
              { label: 'Purchased', value: asset.purchase_date || asset.purchase_cost !== null ? `${formatDate(asset.purchase_date)}${asset.purchase_cost !== null && asset.purchase_cost !== undefined ? ` · ${formatMoney(asset.purchase_cost)}` : ''}` : '—' },
              { label: 'Warranty ends', value: formatDate(asset.warranty_end) },
              { label: 'Criticality', value: ASSET_CRITICALITY_LABELS[criticality] ?? labelFor(criticality) },
              ...(asset.description ? [{ label: 'Description', value: asset.description }] : []),
              ...(customFields.length
                ? [
                    {
                      label: 'Custom fields',
                      value: (
                        <dl className={styles.customFields}>
                          {customFields.map(([key, value]) => (
                            <div key={key}>
                              <dt>{key}</dt>
                              <dd>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd>
                            </div>
                          ))}
                        </dl>
                      ),
                    },
                  ]
                : []),
              { label: 'Created', value: formatDateTime(asset.created_at) },
              { label: 'Updated', value: formatDateTime(asset.updated_at) },
            ]}
          />
        </Card>

        <Card
          title={`Hierarchy${children.data ? ` (${children.data.items.length} sub-assets)` : ''}`}
          flush
          actions={
            canManage ? (
              <Button size="sm" variant="ghost" leadingIcon={<Plus size={14} />} onClick={onAddChild}>
                Add sub-asset
              </Button>
            ) : undefined
          }
        >
          <div className={styles.parentRow}>
            <FieldList
              items={[
                {
                  label: 'Parent',
                  value: asset.parent_id ? parent.data ? <Link to={`/assets/${parent.data.id}`}>{parent.data.name}</Link> : parent.isError ? 'Not visible' : 'Loading…' : 'Top-level asset',
                },
              ]}
            />
          </div>
          {children.isPending ? (
            <SkeletonRows rows={2} />
          ) : children.isError ? (
            <div className={styles.padded}>
              <InlineAlert tone="danger" title="Sub-assets could not be loaded" actions={<Button size="sm" onClick={() => void children.refetch()}>Retry</Button>}>
                {errorMessage(children.error)}
              </InlineAlert>
            </div>
          ) : children.data.items.length === 0 ? (
            <EmptyState compact illustration="box" title="No sub-assets" description="Sub-assemblies and modules can live under this asset." />
          ) : (
            <ul aria-label="Sub-assets">
              {children.data.items.map((child) => (
                <li key={child.id}>
                  <ListRow compact to={`/assets/${child.id}`} title={child.name} meta={<>{child.code && <span className={styles.code}>{child.code}</span>}<StatusBadge status={child.status} size="sm" /></>} />
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          title={`Open work${openWork.data?.total !== undefined ? ` (${openWork.data.total})` : ''}`}
          flush
          actions={
            <Button size="sm" variant="ghost" onClick={() => navigate(`/work-orders?filter[asset]=${asset.id}`)}>
              View all
            </Button>
          }
        >
          {openWork.isPending ? (
            <SkeletonRows rows={3} />
          ) : openWork.isError ? (
            <div className={styles.padded}>
              <InlineAlert tone="danger" title="Open work could not be loaded" actions={<Button size="sm" onClick={() => void openWork.refetch()}>Retry</Button>}>
                {errorMessage(openWork.error)}
              </InlineAlert>
            </div>
          ) : openWork.data.items.length === 0 ? (
            <EmptyState
              compact
              illustration="clipboard"
              title="No open work"
              description="Nothing is scheduled against this asset right now."
              action={canCreateWorkOrder ? <Button size="sm" onClick={() => navigate(`/work-orders/new?asset=${asset.id}`)}>New work order</Button> : undefined}
            />
          ) : (
            <ul aria-label="Open work orders">
              {openWork.data.items.map((wo) => (
                <li key={wo.id}>
                  <Link to={`/work-orders/${wo.id}`} className={styles.workRow}>
                    <span className={styles.workNumber}>#{wo.number}</span>
                    <span className={styles.workTitle}>{wo.title}</span>
                    <StatusBadge status={wo.status} size="sm" />
                    {wo.due_at && (
                      <span className={styles.workDue} data-overdue={wo.is_overdue ? 'true' : undefined}>
                        {formatDue(wo.due_at)}
                      </span>
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="History">
          {history.isPending ? (
            <SkeletonBlock lines={4} />
          ) : history.isError ? (
            <InlineAlert tone="danger" title="History could not be loaded" actions={<Button size="sm" onClick={() => void history.refetch()}>Retry</Button>}>
              {errorMessage(history.error)}
            </InlineAlert>
          ) : (
            <ActivityTimeline items={timeline} emptyText="No history yet. Status changes, edits and work orders will show up here." />
          )}
        </Card>
      </Stack>
    </DetailPanel>
  )
}

function toTimelineItem(entry: AssetTimelineEntry): TimelineItem {
  if (entry.kind === 'status') {
    const details: ReactNode[] = []
    if (entry.downtime_type) details.push(<span key="type">Downtime: {DOWNTIME_TYPE_LABELS[entry.downtime_type as DowntimeType] ?? entry.downtime_type}{entry.downtime_reason ? ` — ${entry.downtime_reason}` : ''}</span>)
    else if (entry.downtime_reason) details.push(<span key="reason">Reason: {entry.downtime_reason}</span>)
    if (entry.note) details.push(<span key="note">{entry.note}</span>)
    return {
      id: `status-${entry.id}`,
      icon: <Activity size={14} aria-hidden="true" />,
      title: (
        <span className={styles.timelineStatus}>
          <span>Status changed</span>
          <StatusBadge status={entry.from_status ?? undefined} size="sm" />
          <span aria-hidden="true">→</span>
          <span className="sr-only">to</span>
          <StatusBadge status={entry.to_status} size="sm" />
        </span>
      ),
      actor: entry.changed_by?.name ?? null,
      at: entry.at,
      content: details.length ? <div className={styles.timelineDetail}>{details}</div> : undefined,
    }
  }
  if (entry.kind === 'work_order') {
    return {
      id: `wo-${entry.id}`,
      icon: <ClipboardList size={14} aria-hidden="true" />,
      title: (
        <span className={styles.timelineStatus}>
          <Link to={`/work-orders/${entry.id}`}>
            #{entry.number} {entry.title}
          </Link>
          <StatusBadge status={entry.status} size="sm" />
        </span>
      ),
      at: entry.at,
    }
  }
  return {
    id: `audit-${entry.id}`,
    icon: <History size={14} aria-hidden="true" />,
    title: entry.summary ?? labelFor(entry.event_type.split('.').pop()),
    actor: entry.actor?.name ?? null,
    at: entry.at,
  }
}
