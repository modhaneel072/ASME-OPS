import { ArrowLeftRight, ClipboardCheck, ExternalLink, MinusCircle, MoreHorizontal, Package, Pencil, PlusCircle, SlidersHorizontal } from 'lucide-react'
import { Link } from 'react-router-dom'
import {
  formatQuantity,
  formatQuantityUnit,
  formatUnitCost,
  type MovementType,
  type PartDetail as PartDetailShape,
} from '@/api/contracts/parts'
import { formatDate, formatDateTime } from '@/lib/dates'
import { Badge, Button, Card, DetailPanel, DropdownMenu, EmptyState, FieldList, IconButton, Stack, StatusBadge } from '@/ui'
import { CriticalBadge, StockChip } from './bits'
import styles from './parts.module.css'
import { TransactionHistory } from './TransactionHistory'

export interface PartDetailProps {
  part: PartDetailShape
  canManage: boolean
  onEdit: () => void
  onMovement: (type: MovementType) => void
  onTransfer: () => void
  onCount: () => void
  onEditVendors: () => void
  onEditAssets: () => void
}

export function PartDetail({ part, canManage, onEdit, onMovement, onTransfer, onCount, onEditVendors, onEditAssets }: PartDetailProps) {
  const subtitle = [part.manufacturer, part.manufacturer_part_number].filter(Boolean).join(' · ')

  return (
    <DetailPanel
      eyebrow={
        <span className={styles.eyebrowRow}>
          <Package size={12} aria-hidden="true" />
          <span>{part.part_type?.name ?? 'Part'}</span>
          {part.sku && <span className={styles.code}>{part.sku}</span>}
        </span>
      }
      title={
        <span className={styles.titleRow}>
          {part.name}
          <StockChip state={part.stock_state} />
          {part.is_critical && <CriticalBadge />}
          {part.is_active === false && <Badge tone="neutral">Retired</Badge>}
        </span>
      }
      subtitle={subtitle || undefined}
      actions={
        canManage ? (
          <>
            <Button leadingIcon={<PlusCircle size={16} />} onClick={() => onMovement('receipt')}>
              Receive
            </Button>
            <Button leadingIcon={<MinusCircle size={16} />} onClick={() => onMovement('issue')}>
              Issue
            </Button>
            <Button leadingIcon={<SlidersHorizontal size={16} />} onClick={() => onMovement('adjustment')}>
              Adjust
            </Button>
            <Button leadingIcon={<ArrowLeftRight size={16} />} onClick={onTransfer}>
              Transfer
            </Button>
            <Button leadingIcon={<ClipboardCheck size={16} />} onClick={onCount}>
              Count
            </Button>
            <DropdownMenu
              align="end"
              label="More actions"
              items={[
                { key: 'edit', label: 'Edit part', icon: <Pencil size={16} />, onSelect: onEdit },
                { key: 'return', label: 'Return stock', onSelect: () => onMovement('return') },
                { key: 'scrap', label: 'Scrap stock', destructive: true, onSelect: () => onMovement('scrap') },
                { key: 'sep', type: 'separator' },
                { key: 'vendors', label: 'Edit vendors', onSelect: onEditVendors },
                { key: 'assets', label: 'Edit spare-for assets', onSelect: onEditAssets },
              ]}
              trigger={(props) => (
                <IconButton {...props} ref={props.ref} label="More actions">
                  <MoreHorizontal size={18} />
                </IconButton>
              )}
            />
          </>
        ) : undefined
      }
    >
      <Stack>
        <Card title="Stock">
          <div className={styles.totals}>
            <Total label="Available" value={formatQuantityUnit(part.totals.available, part.unit)} />
            <Total label="On hand" value={formatQuantity(part.totals.on_hand)} />
            <Total label="Reserved" value={formatQuantity(part.totals.reserved)} />
            <Total label="On order" value={formatQuantity(part.totals.ordered)} />
          </div>
          <FieldList
            items={[
              { label: 'Minimum stock', value: part.minimum_stock === null || part.minimum_stock === undefined ? 'Not tracked' : formatQuantityUnit(part.minimum_stock, part.unit) },
              { label: 'Maximum stock', value: part.maximum_stock === null || part.maximum_stock === undefined ? '—' : formatQuantityUnit(part.maximum_stock, part.unit) },
              { label: 'Reorder quantity', value: part.reorder_quantity === null || part.reorder_quantity === undefined ? '—' : formatQuantityUnit(part.reorder_quantity, part.unit) },
              { label: 'Unit cost', value: formatUnitCost(part.unit_cost) },
            ]}
          />
        </Card>

        <Card title="Stock by location" flush>
          {part.balances.length === 0 ? (
            <EmptyState
              compact
              illustration="pin"
              title="Nothing on the shelf"
              description="Receiving stock records where it is stored, and this list fills in."
              action={canManage ? <Button size="sm" onClick={() => onMovement('receipt')}>Receive stock</Button> : undefined}
            />
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <caption className="sr-only">On hand, reserved and available quantity for each location</caption>
                <thead>
                  <tr>
                    <th scope="col">Location</th>
                    <th scope="col" className={styles.numeric}>
                      On hand
                    </th>
                    <th scope="col" className={styles.numeric}>
                      Reserved
                    </th>
                    <th scope="col" className={styles.numeric}>
                      Available
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {part.balances.map((balance) => (
                    <tr key={balance.location?.id ?? 'unknown'} style={{ cursor: 'default' }}>
                      <td>{balance.location ? <Link to={`/locations/${balance.location.id}`}>{balance.location.name}</Link> : '—'}</td>
                      <td className={styles.numeric}>{formatQuantity(balance.on_hand)}</td>
                      <td className={styles.numeric}>{formatQuantity(balance.reserved)}</td>
                      <td className={styles.numeric}>{formatQuantity(balance.available)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="Details">
          <FieldList
            items={[
              { label: 'Part type', value: part.part_type?.name ?? '—' },
              { label: 'Unit', value: part.unit },
              { label: 'Default location', value: part.default_location ? <Link to={`/locations/${part.default_location.id}`}>{part.default_location.name}</Link> : '—' },
              { label: 'Manufacturer', value: part.manufacturer || '—' },
              { label: 'Manufacturer part number', value: part.manufacturer_part_number ? <span className="mono">{part.manufacturer_part_number}</span> : '—' },
              { label: 'QR or barcode', value: part.qr_code ? <span className="mono">{part.qr_code}</span> : '—' },
              ...(part.description ? [{ label: 'Description', value: part.description }] : []),
              { label: 'Created', value: formatDateTime(part.created_at) },
              { label: 'Updated', value: formatDateTime(part.updated_at) },
            ]}
          />
        </Card>

        <Card
          title={`Vendors${part.vendors.length ? ` (${part.vendors.length})` : ''}`}
          flush
          actions={
            canManage ? (
              <Button size="sm" variant="ghost" leadingIcon={<Pencil size={14} />} onClick={onEditVendors}>
                Edit vendors
              </Button>
            ) : undefined
          }
        >
          {part.vendors.length === 0 ? (
            <EmptyState
              compact
              illustration="tag"
              title="No vendors linked"
              description="Link who sells this part so a purchase request knows where to order it."
              action={canManage ? <Button size="sm" onClick={onEditVendors}>Link a vendor</Button> : undefined}
            />
          ) : (
            <ul aria-label="Vendors">
              {part.vendors.map((link) => (
                <li key={link.vendor.id} className={styles.linkRow}>
                  <Link to={`/vendors/${link.vendor.id}`} className={styles.linkName}>
                    {link.vendor.name}
                  </Link>
                  {link.preferred && (
                    <Badge tone="success" size="sm">
                      Preferred
                    </Badge>
                  )}
                  {link.vendor_part_number && <span className={styles.code}>{link.vendor_part_number}</span>}
                  <span className={styles.spacer} />
                  {link.last_price !== null && link.last_price !== undefined && <span className={styles.cellMuted}>Last {formatUnitCost(link.last_price)}</span>}
                  {link.last_ordered_at && <span className={styles.cellMuted}>Ordered {formatDate(link.last_ordered_at)}</span>}
                  {link.url && (
                    <a href={link.url} target="_blank" rel="noreferrer noopener" aria-label={`Open ${link.vendor.name} listing in a new tab`}>
                      <ExternalLink size={16} aria-hidden="true" />
                    </a>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          title={`Spare for${part.assets.length ? ` (${part.assets.length})` : ''}`}
          flush
          actions={
            canManage ? (
              <Button size="sm" variant="ghost" leadingIcon={<Pencil size={14} />} onClick={onEditAssets}>
                Edit assets
              </Button>
            ) : undefined
          }
        >
          {part.assets.length === 0 ? (
            <EmptyState
              compact
              illustration="box"
              title="Not linked to equipment"
              description="Say which machines this part fits and it shows up where the repair happens."
              action={canManage ? <Button size="sm" onClick={onEditAssets}>Link an asset</Button> : undefined}
            />
          ) : (
            <ul aria-label="Assets this part is a spare for">
              {part.assets.map((asset) => (
                <li key={asset.id} className={styles.linkRow}>
                  <Link to={`/assets/${asset.id}`} className={styles.linkName}>
                    {asset.name}
                  </Link>
                  {asset.code && <span className={styles.code}>{asset.code}</span>}
                  <span className={styles.spacer} />
                  {asset.status && <StatusBadge status={asset.status} size="sm" />}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title={`Open purchase requests${part.open_purchase_requests.length ? ` (${part.open_purchase_requests.length})` : ''}`} flush>
          {part.open_purchase_requests.length === 0 ? (
            <p className={styles.muted} style={{ padding: 'var(--space-3) var(--space-4)' }}>
              Nothing on order.
            </p>
          ) : (
            <ul aria-label="Open purchase requests">
              {part.open_purchase_requests.map((request) => (
                <li key={request.id} className={styles.linkRow}>
                  <Link to={`/purchase-requests/${request.id}`} className={styles.linkName}>
                    {request.display_number}
                  </Link>
                  <span>{request.title}</span>
                  <span className={styles.spacer} />
                  <span className={styles.cellMuted}>{formatQuantityUnit(request.outstanding_quantity, part.unit)} outstanding</span>
                  <StatusBadge status={request.status} size="sm" />
                </li>
              ))}
            </ul>
          )}
        </Card>

        <TransactionHistory partId={part.id} unit={part.unit} />
      </Stack>
    </DetailPanel>
  )
}

function Total({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.total}>
      <span className={styles.totalLabel}>{label}</span>
      <span className={styles.totalValue}>{value}</span>
    </div>
  )
}
