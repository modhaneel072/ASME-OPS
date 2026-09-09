import { Bell, Building2, History, Plug, ShieldCheck, UserRound, type LucideIcon } from 'lucide-react'
import { NavLink, useNavigate, useParams } from 'react-router-dom'
import { ComingSoon } from '@/app/Pages'
import { EmptyState, LinkButton, Page, PageHeader, Tabs } from '@/ui'
import { ChapterSection } from './ChapterSection'
import { ProfileSection } from './ProfileSection'
import { RolesSection } from './RolesSection'
import styles from './settings.module.css'
import { useMediaQuery } from './useMediaQuery'

export type SettingsSection = 'profile' | 'chapter' | 'roles' | 'notifications' | 'integrations' | 'audit'

interface SectionDef {
  key: SettingsSection
  label: string
  description: string
  icon: LucideIcon
  /** Stage in which the section ships; undefined means built. */
  stage?: number
}

export const SETTINGS_SECTIONS: SectionDef[] = [
  { key: 'profile', label: 'Profile', description: 'Your account, role and permissions in this chapter.', icon: UserRound },
  { key: 'chapter', label: 'Chapter', description: 'Name, time zone, academic year and contact details.', icon: Building2 },
  { key: 'roles', label: 'Roles', description: 'What each role in the chapter can do.', icon: ShieldCheck },
  { key: 'notifications', label: 'Notifications', description: 'Which events reach you and how.', icon: Bell, stage: 7 },
  { key: 'integrations', label: 'Integrations', description: 'Calendar, storage and messaging connections.', icon: Plug, stage: 8 },
  { key: 'audit', label: 'Audit log', description: 'Who changed what, and when.', icon: History, stage: 8 },
]

function isSection(value: string | undefined): value is SettingsSection {
  return SETTINGS_SECTIONS.some((section) => section.key === value)
}

export default function SettingsPage() {
  const { section } = useParams<{ section: string }>()
  const navigate = useNavigate()
  const narrow = useMediaQuery('(max-width: 899px)')
  const current = isSection(section) ? section : null
  const def = current ? SETTINGS_SECTIONS.find((s) => s.key === current) : undefined

  return (
    <Page>
      <PageHeader title="Settings" subtitle="Your profile and how this ASME chapter runs." />
      <div className={styles.layout}>
        {narrow ? (
          <div className={styles.subnavTabs}>
            <Tabs<SettingsSection>
              label="Settings sections"
              value={current ?? 'profile'}
              onChange={(next) => navigate(`/settings/${next}`)}
              items={SETTINGS_SECTIONS.map((s) => ({ value: s.key, label: s.stage ? `${s.label} · S${s.stage}` : s.label }))}
            />
          </div>
        ) : (
          <nav className={styles.subnav} aria-label="Settings sections">
            <ul className={styles.subnavList}>
              {SETTINGS_SECTIONS.map((s) => {
                const Icon = s.icon
                return (
                  <li key={s.key}>
                    <NavLink to={`/settings/${s.key}`} className={styles.subnavLink} aria-current={s.key === current ? 'page' : undefined} end>
                      <span className={styles.subnavIcon}>
                        <Icon size={16} aria-hidden="true" />
                      </span>
                      <span>{s.label}</span>
                      {s.stage && (
                        <span className={styles.subnavTag} title={`Ships in stage ${s.stage}`}>
                          S{s.stage}
                        </span>
                      )}
                    </NavLink>
                  </li>
                )
              })}
            </ul>
          </nav>
        )}
        <div className={styles.content}>
          {!current || !def ? (
            <div className={styles.section}>
              <EmptyState illustration="search" title="Settings section not found" description="Pick a section from the navigation." action={<LinkButton to="/settings/profile">Go to Profile</LinkButton>} />
            </div>
          ) : current === 'notifications' ? (
            <ComingSoon title="Notification settings" stage={7} description="Choose which chapter events notify you in-app and by email." />
          ) : current === 'integrations' ? (
            <ComingSoon title="Integrations" stage={8} description="Connect calendars, cloud storage and messaging to ASME Ops." />
          ) : current === 'audit' ? (
            <ComingSoon title="Audit log" stage={8} description="Browse every change made in the chapter workspace." />
          ) : (
            <div className={styles.section}>
              <header className={styles.sectionHeader}>
                <h2 className={styles.sectionTitle}>{def.label}</h2>
                <p className={styles.sectionSubtitle}>{def.description}</p>
              </header>
              {current === 'profile' && <ProfileSection />}
              {current === 'chapter' && <ChapterSection />}
              {current === 'roles' && <RolesSection />}
            </div>
          )}
        </div>
      </div>
    </Page>
  )
}
