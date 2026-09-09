import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { errorMessage } from '@/api/client'
import { useRoles } from '@/api/queries/users'
import { cn } from '@/lib/cn'
import { Button, EmptyState, InlineAlert, SkeletonRows } from '@/ui'
import { SCOPES, SCOPE_ABBR, SCOPE_LABELS, SCOPE_TITLES, buildScopeMatrix, groupPermissionKeys } from './permissionGroups'
import styles from './teams-users.module.css'
import { withParams } from './urlState'

/**
 * Read-only permissions matrix from `GET /roles`: one column per role, one
 * row per permission key, each cell the scope the role holds it at.
 */
export function RolesTab() {
  const [params, setParams] = useSearchParams()
  const query = (params.get('q') ?? '').trim().toLowerCase()
  const roles = useRoles()
  const data = roles.data

  const { matrix, groups } = useMemo(() => {
    const built = buildScopeMatrix(data ?? [])
    const keys = query ? built.keys.filter((key) => key.toLowerCase().includes(query)) : built.keys
    return { matrix: built.matrix, groups: groupPermissionKeys(keys) }
  }, [data, query])

  const clearSearch = () => setParams(withParams(params, { q: null }), { replace: true })

  return (
    <div className={cn(styles.rolesPane, 'scroll-y')}>
      <div className={styles.rolesIntro}>
        <p>Every member holds one role. A role grants each permission at a scope: the letter in a cell says where the permission applies. Roles are fixed in this stage; the server enforces them on every request.</p>
        <dl className={styles.legend} aria-label="Scope legend">
          {SCOPES.map((scope) => (
            <div key={scope}>
              <dt>
                <span className={styles.scope} aria-hidden="true">
                  {SCOPE_ABBR[scope]}
                </span>
              </dt>
              <dd>
                <strong>{SCOPE_LABELS[scope]}</strong> · {SCOPE_TITLES[scope].slice(SCOPE_LABELS[scope].length + 2)}
              </dd>
            </div>
          ))}
        </dl>
      </div>
      {roles.isPending ? (
        <SkeletonRows rows={10} />
      ) : roles.isError ? (
        <InlineAlert
          tone="danger"
          title="Roles could not be loaded"
          actions={
            <Button size="sm" onClick={() => void roles.refetch()}>
              Retry
            </Button>
          }
        >
          {errorMessage(roles.error)}
        </InlineAlert>
      ) : !data || data.length === 0 ? (
        <EmptyState illustration="clipboard" title="No roles yet" description="Roles are created when the chapter is set up." />
      ) : groups.length === 0 ? (
        <EmptyState
          compact
          illustration="search"
          title="No permissions match"
          description={`No permission key contains “${query}”.`}
          action={
            <Button size="sm" onClick={clearSearch}>
              Clear search
            </Button>
          }
        />
      ) : (
        <div className={cn(styles.matrixWrap, 'scroll-x')}>
          <table className={styles.matrix}>
            <caption className="sr-only">Permissions by role. Each cell shows the scope at which the role holds the permission; a dash means no access.</caption>
            <thead>
              <tr>
                <th scope="col" className={styles.stickyCol}>
                  Permission
                </th>
                {data.map((role) => (
                  <th key={role.id} scope="col" className={styles.roleHead}>
                    <span className={styles.roleName}>{role.name}</span>
                    <span className={styles.roleCount}>
                      {role.member_count ?? 0} {role.member_count === 1 ? 'member' : 'members'}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            {groups.map((group) => (
              <tbody key={group.label}>
                <tr className={styles.groupRow}>
                  <th scope="rowgroup" className={styles.stickyCol}>
                    {group.label}
                  </th>
                  <td colSpan={data.length} aria-hidden="true" />
                </tr>
                {group.keys.map((key) => (
                  <tr key={key}>
                    <th scope="row" className={cn(styles.stickyCol, styles.permKey)}>
                      <code>{key}</code>
                    </th>
                    {data.map((role) => {
                      const scope = matrix.get(role.id)?.get(key)
                      return (
                        <td key={role.id}>
                          {scope ? (
                            <abbr className={styles.scope} title={SCOPE_TITLES[scope]}>
                              {SCOPE_ABBR[scope]}
                            </abbr>
                          ) : (
                            <>
                              <span className={styles.noAccess} aria-hidden="true">
                                —
                              </span>
                              <span className="sr-only">no access</span>
                            </>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            ))}
          </table>
        </div>
      )}
    </div>
  )
}
