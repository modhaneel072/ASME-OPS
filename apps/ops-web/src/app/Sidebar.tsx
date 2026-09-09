import { ChevronRight, ExternalLink, LifeBuoy, LogOut, PanelLeftClose, PanelLeftOpen, Settings2, UserRound } from 'lucide-react'
import { useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useLogout } from '@/api/queries/session'
import { cn } from '@/lib/cn'
import { hasPermission, useSession } from '@/lib/permissions'
import { DropdownMenu, IconButton, Tooltip } from '@/ui'
import { Avatar } from '@/ui/Form'
import { NAV_GROUPS, type NavItem } from './SidebarNav'
import styles from './shell.module.css'

interface SidebarProps {
  collapsed: boolean
  onToggleCollapsed: () => void
  mobileOpen: boolean
  onCloseMobile: () => void
}

function StageTag({ stage }: { stage?: number }) {
  if (!stage) return null
  return (
    <span className={styles.itemTag} title={`Ships in stage ${stage}`}>
      S{stage}
    </span>
  )
}

function NavEntry({ item, collapsed, onNavigate }: { item: NavItem; collapsed: boolean; onNavigate: () => void }) {
  const location = useLocation()
  const childActive = item.children?.some((child) => location.pathname.startsWith(child.to)) ?? false
  const [open, setOpen] = useState(childActive)
  const [wasChildActive, setWasChildActive] = useState(childActive)
  if (wasChildActive !== childActive) {
    setWasChildActive(childActive)
    if (childActive) setOpen(true)
  }
  const Icon = item.icon

  if (item.children && !collapsed) {
    return (
      <div>
        <button type="button" className={cn(styles.item, childActive && styles.item_active)} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          <span className={styles.itemIcon}>
            <Icon size={18} aria-hidden="true" />
          </span>
          <span className={styles.itemLabel}>{item.label}</span>
          <StageTag stage={item.stage} />
          <ChevronRight size={16} className={cn(styles.itemChevron, open && styles.itemChevron_open)} aria-hidden="true" />
        </button>
        {open && (
          <div className={styles.children}>
            {item.children.map((child) => (
              <NavLink key={child.key} to={child.to} className={({ isActive }) => cn(styles.child, isActive && styles.child_active)} onClick={onNavigate}>
                <span className={styles.itemLabel}>{child.label}</span>
                <StageTag stage={child.stage} />
              </NavLink>
            ))}
          </div>
        )}
      </div>
    )
  }

  const link = (
    <NavLink to={item.to} className={({ isActive }) => cn(styles.item, (isActive || childActive) && styles.item_active)} onClick={onNavigate} aria-label={collapsed ? item.label : undefined}>
      <span className={styles.itemIcon}>
        <Icon size={18} aria-hidden="true" />
      </span>
      <span className={styles.itemLabel}>{item.label}</span>
      <StageTag stage={item.stage} />
    </NavLink>
  )
  return collapsed ? (
    <Tooltip content={item.label} side="right">
      {link}
    </Tooltip>
  ) : (
    link
  )
}

export function Sidebar({ collapsed, onToggleCollapsed, mobileOpen, onCloseMobile }: SidebarProps) {
  const session = useSession()
  const navigate = useNavigate()
  const logout = useLogout()

  const visibleGroups = NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => !item.permissions || item.permissions.some((key) => hasPermission(session, key))),
  })).filter((group) => group.items.length > 0)

  return (
    <aside className={cn(styles.sidebar, collapsed && styles.sidebar_collapsed, mobileOpen && styles.sidebar_open)} aria-label="Primary navigation">
      <div className={styles.brand}>
        <span className={styles.brandMark} aria-hidden="true">
          A
        </span>
        <div className={styles.brandText}>
          <div className={styles.brandName}>ASME Ops</div>
          <div className={styles.brandChapter} title={session.organization.name}>
            {session.organization.name}
          </div>
        </div>
        <IconButton label={collapsed ? 'Expand navigation' : 'Collapse navigation'} variant="ghost" size="sm" className={styles.collapseButton} onClick={onToggleCollapsed}>
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </IconButton>
      </div>

      <nav className={styles.nav}>
        {visibleGroups.map((group) => (
          <div key={group.key} className={styles.group}>
            <div className={styles.groupLabel}>{group.label}</div>
            {group.items.map((item) => (
              <NavEntry key={item.key} item={item} collapsed={collapsed} onNavigate={onCloseMobile} />
            ))}
          </div>
        ))}
      </nav>

      <div className={styles.footer}>
        {collapsed ? (
          <Tooltip content="Help / Support" side="right">
            <a href="/portal/member/help" className={styles.item} aria-label="Help / Support">
              <span className={styles.itemIcon}>
                <LifeBuoy size={18} aria-hidden="true" />
              </span>
            </a>
          </Tooltip>
        ) : (
          <a href="/portal/member/help" className={styles.item}>
            <span className={styles.itemIcon}>
              <LifeBuoy size={18} aria-hidden="true" />
            </span>
            <span className={styles.itemLabel}>Help / Support</span>
          </a>
        )}
        <DropdownMenu
          align="start"
          placement="top-start"
          label="Account"
          items={[
            { key: 'profile', label: 'Profile', icon: <UserRound size={16} />, onSelect: () => navigate('/settings/profile') },
            { key: 'settings', label: 'Settings', icon: <Settings2 size={16} />, onSelect: () => navigate('/settings/chapter') },
            { key: 'sep', type: 'separator' },
            { key: 'portal', label: 'Open member portal', icon: <ExternalLink size={16} />, onSelect: () => window.location.assign('/portal') },
            { key: 'site', label: 'Public website', icon: <ExternalLink size={16} />, onSelect: () => window.location.assign('/') },
            { key: 'sep2', type: 'separator' },
            {
              key: 'logout',
              label: 'Log out',
              icon: <LogOut size={16} />,
              onSelect: () => logout.mutate(undefined, { onSettled: () => navigate('/auth/login', { replace: true }) }),
            },
          ]}
          trigger={(props, open) => (
            <button type="button" {...props} ref={props.ref} className={styles.userButton} aria-label={`Account menu for ${session.user.name}`} aria-expanded={open}>
              <Avatar name={session.user.name} src={session.user.avatar_url} size="lg" />
              <span className={cn(styles.userText)} style={{ minWidth: 0, flex: 1 }}>
                <span className={styles.userName} style={{ display: 'block' }}>
                  {session.user.name}
                </span>
                <span className={styles.userRole} style={{ display: 'block' }}>
                  {session.membership.role.name}
                </span>
              </span>
            </button>
          )}
        />
      </div>
    </aside>
  )
}
