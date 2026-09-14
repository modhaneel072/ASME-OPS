import { BarChart3, CheckCircle2, ClipboardList, Users, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'
import { Badge, Button, Dialog } from '@/ui'
import type { TileTone } from './taskMeta'
import styles from './setup.module.css'

export interface OfficerGuideDialogProps {
  open: boolean
  onClose: () => void
  /** Holder of `chapter.setup.manage`. */
  canMark: boolean
  /** Whether the chapter already recorded the guide as read. */
  marked: boolean
  marking: boolean
  onMark: () => void
}

function GuideSection({ icon: Icon, tone, title, lead, children }: { icon: LucideIcon; tone: TileTone; title: string; lead: string; children: ReactNode }) {
  return (
    <section className={styles.guideSection} aria-label={title}>
      <span className={cn(styles.tile, styles[`tile_${tone}`])} aria-hidden="true">
        <Icon size={20} />
      </span>
      <div className={styles.guideText}>
        <h3 className={styles.guideTitle}>{title}</h3>
        <p className={styles.guideLead}>{lead}</p>
        <ul className={styles.guideList}>{children}</ul>
      </div>
    </section>
  )
}

/**
 * The officer guide is the one setup task whose "screen" is the Setup Center
 * itself, so it opens here. Reading is open to every member; recording it as
 * read is a chapter-wide setting reserved for setup managers.
 */
export function OfficerGuideDialog({ open, onClose, canMark, marked, marking, onMark }: OfficerGuideDialogProps) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      size="lg"
      title="Officer guide"
      description="A short tour of roles, work orders and reporting for chapter officers."
      preventClose={marking}
      footer={
        <>
          {marked && (
            <Badge tone="success" dot>
              Read
            </Badge>
          )}
          <Button variant="ghost" onClick={onClose} disabled={marking}>
            Close
          </Button>
          {canMark && !marked && (
            <Button variant="primary" leadingIcon={<CheckCircle2 size={16} />} onClick={onMark} loading={marking}>
              Mark as read
            </Button>
          )}
        </>
      }
    >
      <div className={styles.guide}>
        <GuideSection icon={Users} tone="gold" title="Roles" lead="Permissions come from the role on each member's chapter membership. The server enforces them on every request; controls appear only where a role allows them.">
          <li>
            <strong>Chapter Administrator</strong> manages everything, including roles and chapter settings.
          </li>
          <li>
            <strong>Executive Officer</strong> manages everything except roles and chapter settings.
          </li>
          <li>
            <strong>Project Lead</strong> creates projects and runs milestones, members and work inside their own projects.
          </li>
          <li>
            <strong>Team Lead</strong> assigns and progresses work for the teams they lead.
          </li>
          <li>
            <strong>Full Member</strong> creates work orders and works the ones assigned to them.
          </li>
          <li>
            <strong>Shop Operator</strong> and <strong>Requester</strong> see only assigned work or submit requests.
          </li>
        </GuideSection>
        <GuideSection icon={ClipboardList} tone="primary" title="Work orders" lead="Every job the chapter does, from a rover repair to an outreach event task, is a numbered work order.">
          <li>Status moves Open → In progress → On hold → Done, or Canceled; Draft holds plans that are not ready yet.</li>
          <li>Priority (None to Critical), work type, due date and assignees (people or teams) drive everyone's To Do list.</li>
          <li>Attach a project, location and asset so time, cost and history land in the right place.</li>
          <li>Break large jobs into sub-work orders and add dependencies to block work that cannot start yet.</li>
        </GuideSection>
        <GuideSection icon={BarChart3} tone="success" title="Reporting" lead="The Operations dashboard turns work-order history into a picture of how the chapter is running.">
          <li>Created vs completed per week, on-time completion rate and overdue open work.</li>
          <li>Workload by team and by member, hours logged, parts and other cost.</li>
          <li>Pick the last 7, 30 or 90 days, this semester or a custom range; every card drills into the filtered work-order list.</li>
        </GuideSection>
      </div>
    </Dialog>
  )
}
