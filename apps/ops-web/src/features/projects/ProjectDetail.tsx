import { Archive, ArchiveRestore, ExternalLink, Lock, MoreHorizontal, Pencil, Plus, Users } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, errorMessage } from '@/api/client'
import { RISK_LABELS, type MemberInput, type ProjectDetail as ProjectDetailPayload, type RiskLevel } from '@/api/contracts/projects'
import { useReplaceMembers } from '@/api/queries/projects'
import { canOn, hasPermission, useSession } from '@/lib/permissions'
import { Badge, Button, DetailPanel, DropdownMenu, IconButton, Tabs, useToast, type BadgeTone, type MenuItem } from '@/ui'
import { MembersDialog } from './MembersDialog'
import { newWorkOrderHref, PROJECT_TABS, TAB_LABELS, workOrdersHref, type ProjectTab } from './shared'
import { ActivityTab } from './tabs/ActivityTab'
import { AssetsTab } from './tabs/AssetsTab'
import { BudgetTab } from './tabs/BudgetTab'
import { DocumentsTab } from './tabs/DocumentsTab'
import { MilestonesTab } from './tabs/MilestonesTab'
import { OverviewTab } from './tabs/OverviewTab'
import { TeamsTab } from './tabs/TeamsTab'
import { WorkTab } from './tabs/WorkTab'
import styles from './projects.module.css'

const RISK_TONES: Record<RiskLevel, BadgeTone> = { low: 'success', medium: 'warning', high: 'danger', critical: 'danger' }

export function riskBadge(level: string | undefined, size?: 'sm') {
  const key = (level ?? 'low') as RiskLevel
  return (
    <Badge tone={RISK_TONES[key] ?? 'neutral'} size={size} dot>
      {RISK_LABELS[key] ?? level}
    </Badge>
  )
}

export interface ProjectDetailProps {
  detail: ProjectDetailPayload
  tab: ProjectTab
  onTabChange: (tab: ProjectTab) => void
  onEdit: () => void
  onArchive: () => void
  onRestore: () => void
}

export function ProjectDetail({ detail, tab, onTabChange, onEdit, onArchive, onRestore }: ProjectDetailProps) {
  const { project, members } = detail
  const session = useSession()
  const navigate = useNavigate()
  const toast = useToast()
  const scoped = { project_id: project.id }
  const canManage = canOn(session, 'project.manage', scoped)
  const canArchive = canOn(session, 'project.archive', scoped)
  const canCreateWork = hasPermission(session, 'work_order.create')
  const archived = Boolean(project.archived_at)

  const [membersOpen, setMembersOpen] = useState(false)
  const replaceMembers = useReplaceMembers(project.id)

  const openMembers = () => {
    replaceMembers.reset()
    setMembersOpen(true)
  }
  const saveMembers = async (rows: MemberInput[]) => {
    try {
      await replaceMembers.mutateAsync({ members: rows })
      toast.success('Members updated', `${rows.length} ${rows.length === 1 ? 'member' : 'members'} on ${project.name}`)
      setMembersOpen(false)
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not save members', errorMessage(error))
    }
  }

  const menuItems: MenuItem[] = []
  if (canArchive) {
    menuItems.push(archived ? { key: 'restore', label: 'Restore project', icon: <ArchiveRestore size={16} />, onSelect: onRestore } : { key: 'archive', label: 'Archive project', icon: <Archive size={16} />, onSelect: onArchive })
  }
  if (canManage) menuItems.push({ key: 'members', label: 'Manage members', icon: <Users size={16} />, onSelect: openMembers })
  if (menuItems.length) menuItems.push({ key: 'sep', type: 'separator' })
  menuItems.push({ key: 'work', label: 'Open work orders', icon: <ExternalLink size={16} />, onSelect: () => navigate(workOrdersHref(project.id)) })
  if (canCreateWork) menuItems.push({ key: 'new-work', label: 'New work order', icon: <Plus size={16} />, onSelect: () => navigate(newWorkOrderHref(project.id)) })

  return (
    <DetailPanel
      eyebrow={
        <span className={styles.eyebrow}>
          <span className="mono">{project.code}</span>
          {project.competition && (
            <>
              <span className={styles.eyebrowSep} aria-hidden="true">
                ·
              </span>
              <span>{project.competition}</span>
            </>
          )}
          <span className={styles.eyebrowSep} aria-hidden="true">
            ·
          </span>
          {riskBadge(project.risk_level, 'sm')}
        </span>
      }
      title={
        <span className={styles.titleRow}>
          {project.name}
          {project.visibility === 'private' && (
            <Badge tone="outline" size="sm" title="Private project">
              <Lock size={12} aria-hidden="true" /> Private
            </Badge>
          )}
          {archived && (
            <Badge tone="neutral" size="sm">
              Archived
            </Badge>
          )}
        </span>
      }
      subtitle={project.description || undefined}
      actions={
        <>
          {canManage && !archived && (
            <Button leadingIcon={<Pencil size={16} />} onClick={onEdit}>
              Edit
            </Button>
          )}
          <DropdownMenu
            align="end"
            label="Project actions"
            items={menuItems}
            trigger={(props) => (
              <IconButton {...props} ref={props.ref} label="Project actions">
                <MoreHorizontal size={18} />
              </IconButton>
            )}
          />
        </>
      }
    >
      <div style={{ display: 'grid', gap: 'var(--space-4)' }}>
        <Tabs<ProjectTab> label="Project sections" value={tab} onChange={onTabChange} items={PROJECT_TABS.map((value) => ({ value, label: TAB_LABELS[value], count: value === 'teams' ? members.length : undefined }))} />
        <div role="tabpanel" aria-label={TAB_LABELS[tab]}>
          {tab === 'overview' && <OverviewTab project={project} onOpenTab={onTabChange} />}
          {tab === 'work' && <WorkTab project={project} />}
          {tab === 'milestones' && <MilestonesTab project={project} />}
          {tab === 'teams' && <TeamsTab project={project} members={members} canManage={canManage} onManageMembers={openMembers} />}
          {tab === 'assets' && <AssetsTab project={project} />}
          {tab === 'documents' && <DocumentsTab project={project} />}
          {tab === 'budget' && <BudgetTab project={project} />}
          {tab === 'activity' && <ActivityTab project={project} />}
        </div>
      </div>
      {canManage && <MembersDialog open={membersOpen} project={project} members={members} submitting={replaceMembers.isPending} error={replaceMembers.error} onSubmit={saveMembers} onClose={() => setMembersOpen(false)} />}
    </DetailPanel>
  )
}
