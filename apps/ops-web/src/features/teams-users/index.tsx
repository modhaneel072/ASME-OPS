import { Plus, UserPlus } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { TEAM_SORTS, type TeamSort } from '@/api/contracts/teams'
import { USER_SORTS, type UserSort } from '@/api/contracts/users'
import { NotFoundPage } from '@/app/Pages'
import { useCan } from '@/lib/permissions'
import { Button, Page, PageHeader, SearchField, SplitButton, Tabs, ViewSelector } from '@/ui'
import { RolesTab } from './RolesTab'
import { TeamsTab } from './TeamsTab'
import { UsersTab } from './UsersTab'
import styles from './teams-users.module.css'
import { isTypingTarget, oneOf, parseTab, useUrlSearch, withParams, type Tab } from './urlState'

const TAB_ITEMS: Array<{ value: Tab; label: string }> = [
  { value: 'teams', label: 'Teams' },
  { value: 'users', label: 'Users' },
  { value: 'roles', label: 'Roles' },
]

const TEAM_SORT_OPTIONS: Array<{ value: TeamSort; label: string }> = [
  { value: 'name', label: 'Name A–Z' },
  { value: '-name', label: 'Name Z–A' },
  { value: '-created_at', label: 'Newest first' },
  { value: 'created_at', label: 'Oldest first' },
]

const USER_SORT_OPTIONS: Array<{ value: UserSort; label: string }> = [
  { value: 'name', label: 'Name A–Z' },
  { value: '-name', label: 'Name Z–A' },
  { value: '-joined_at', label: 'Recently joined' },
  { value: '-last_login_at', label: 'Recently active' },
]

const SEARCH_PLACEHOLDER: Record<Tab, string> = { teams: 'Search teams', users: 'Search members', roles: 'Filter permissions' }

/**
 * /teams-users/:tab/:itemId — Teams, Users and Roles share one header; the
 * tab, selection, search, filters and open pane all live in the URL.
 */
export default function TeamsUsersPage() {
  const { tab: rawTab, itemId } = useParams<{ tab?: string; itemId?: string }>()
  const tab = parseTab(rawTab)
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const can = useCan()
  const canManageTeams = can('team.manage')
  const canManageUsers = can('user.manage')
  const searchRef = useRef<HTMLInputElement>(null)
  const search = useUrlSearch(params, setParams)
  const pane = params.get('pane')

  const openPane = (mode: 'new' | 'invite') => setParams(withParams(params, { pane: mode }))

  useEffect(() => {
    if (!tab) return
    const onKey = (event: KeyboardEvent) => {
      if (isTypingTarget(event) || event.metaKey || event.ctrlKey || event.altKey) return
      if (document.querySelector('[role="dialog"][aria-modal="true"]')) return
      if (event.key === '/') {
        event.preventDefault()
        searchRef.current?.focus()
      } else if (event.key === 'n' && !pane) {
        if (tab === 'teams' && canManageTeams) {
          event.preventDefault()
          openPane('new')
        } else if (tab === 'users' && canManageUsers) {
          event.preventDefault()
          openPane('invite')
        }
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, pane, canManageTeams, canManageUsers, params])

  if (!tab) return <NotFoundPage />

  const primary =
    tab === 'teams' && canManageTeams ? (
      canManageUsers ? (
        <SplitButton
          label="New Team"
          leadingIcon={<Plus size={16} />}
          onClick={() => openPane('new')}
          items={[{ key: 'invite', label: 'Invite member', icon: <UserPlus size={16} />, onSelect: () => navigate('/teams-users/users?pane=invite') }]}
        />
      ) : (
        <Button variant="primary" leadingIcon={<Plus size={16} />} onClick={() => openPane('new')}>
          New Team
        </Button>
      )
    ) : tab === 'users' && canManageUsers ? (
      canManageTeams ? (
        <SplitButton
          label="Invite member"
          leadingIcon={<UserPlus size={16} />}
          onClick={() => openPane('invite')}
          items={[{ key: 'team', label: 'New Team', icon: <Plus size={16} />, onSelect: () => navigate('/teams-users/teams?pane=new') }]}
        />
      ) : (
        <Button variant="primary" leadingIcon={<UserPlus size={16} />} onClick={() => openPane('invite')}>
          Invite member
        </Button>
      )
    ) : null

  const viewSelector =
    tab === 'teams' ? (
      <ViewSelector<TeamSort> label="Sort" value={oneOf(params.get('sort'), TEAM_SORTS, 'name')} onChange={(value) => setParams(withParams(params, { sort: value === 'name' ? null : value }))} options={TEAM_SORT_OPTIONS} />
    ) : tab === 'users' ? (
      <ViewSelector<UserSort> label="Sort" value={oneOf(params.get('sort'), USER_SORTS, 'name')} onChange={(value) => setParams(withParams(params, { sort: value === 'name' ? null : value }))} options={USER_SORT_OPTIONS} />
    ) : undefined

  return (
    <Page>
      <PageHeader
        title="Teams / Users"
        viewSelector={viewSelector}
        actions={
          <>
            <SearchField ref={searchRef} value={search.query} onChange={search.setQuery} onDebouncedChange={search.commit} placeholder={SEARCH_PLACEHOLDER[tab]} label={SEARCH_PLACEHOLDER[tab]} shortcutHint="/" />
            {primary}
          </>
        }
      />
      <div className={styles.tabStrip}>
        <Tabs<Tab> label="Teams, users and roles" value={tab} onChange={(next) => navigate(`/teams-users/${next}`)} items={TAB_ITEMS} />
      </div>
      {tab === 'teams' && <TeamsTab teamId={itemId} />}
      {tab === 'users' && <UsersTab userId={itemId} />}
      {tab === 'roles' && <RolesTab />}
    </Page>
  )
}
