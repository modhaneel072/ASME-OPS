import { zodResolver } from '@hookform/resolvers/zod'
import { Bookmark, MoreHorizontal, Pencil, Share2, Star, Trash2 } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { ApiError, errorMessage } from '@/api/client'
import {
  SAVED_FILTER_VISIBILITIES,
  SAVED_FILTER_VISIBILITY_LABELS,
  SavedFilterNameInput,
  SavedFilterShareInput,
  type SavedFilter,
  type SavedFilterVisibility,
} from '@/api/contracts/saved-filters'
import { useCreateSavedFilter, useDeleteSavedFilter, useSavedFilters, useUpdateSavedFilter } from '@/api/queries/saved-filters'
import { useTeamOptions } from '@/api/queries/teams'
import { useCan, useSession } from '@/lib/permissions'
import { Button, Combobox, Dialog, DropdownMenu, FormField, IconButton, InlineAlert, Input, Popover, Select, useAnchor, useToast } from '@/ui'
import styles from './work-orders.module.css'

export interface SavedFiltersMenuProps {
  current: { filter: Record<string, string>; sort: string; view_type: string }
  onApply: (saved: SavedFilter) => void
  /** Increment to open the "Save current filters" dialog from elsewhere (the split button). */
  saveRequest?: number
}

type DialogState = { kind: 'save' } | { kind: 'rename'; target: SavedFilter } | { kind: 'share'; target: SavedFilter } | { kind: 'delete'; target: SavedFilter } | null

export function SavedFiltersMenu({ current, onApply, saveRequest = 0 }: SavedFiltersMenuProps) {
  const [open, setOpen] = useState(false)
  const [dialog, setDialog] = useState<DialogState>(null)
  const [lastSaveRequest, setLastSaveRequest] = useState(saveRequest)
  if (saveRequest !== lastSaveRequest) {
    setLastSaveRequest(saveRequest)
    if (saveRequest > 0) setDialog({ kind: 'save' })
  }
  const { anchor, ref } = useAnchor<HTMLButtonElement>()
  const contentRef = useRef<HTMLDivElement>(null)
  const id = useId()
  const toast = useToast()
  const session = useSession()
  const can = useCan()
  const canShare = can('saved_filter.share')
  const isAdmin = session.membership.role.system_key === 'chapter_admin'

  const saved = useSavedFilters('work_order')
  const update = useUpdateSavedFilter()
  const remove = useDeleteSavedFilter()

  // Menus and dialogs opened from inside the popover live in other portals; the
  // default outside-click handler would treat them as "outside", so we own it.
  useEffect(() => {
    if (!open) return
    const onPointer = (event: PointerEvent) => {
      const target = event.target as HTMLElement | null
      if (!target) return
      if (contentRef.current?.contains(target) || anchor?.contains(target)) return
      if (target.closest('[role="menu"], [role="dialog"][aria-modal="true"], [role="listbox"]')) return
      setOpen(false)
    }
    document.addEventListener('pointerdown', onPointer, true)
    return () => document.removeEventListener('pointerdown', onPointer, true)
  }, [open, anchor])

  const apply = (filter: SavedFilter) => {
    setOpen(false)
    onApply(filter)
  }

  const setDefault = async (filter: SavedFilter) => {
    try {
      await update.mutateAsync({ id: filter.id, is_default: !filter.is_default })
      toast.success(filter.is_default ? 'Default filter cleared' : `“${filter.name}” is now your default filter`)
    } catch (error) {
      toast.error('Could not update the filter', errorMessage(error))
    }
  }

  const rowMenu = (filter: SavedFilter) => (
    <DropdownMenu
      align="end"
      label={`Actions for ${filter.name}`}
      items={[
        { key: 'default', label: filter.is_default ? 'Clear default' : 'Set as default', icon: <Star size={16} />, onSelect: () => void setDefault(filter) },
        { key: 'rename', label: 'Rename', icon: <Pencil size={16} />, onSelect: () => setDialog({ kind: 'rename', target: filter }) },
        ...(canShare ? [{ key: 'share', label: 'Share', icon: <Share2 size={16} />, onSelect: () => setDialog({ kind: 'share', target: filter }) }] : []),
        { key: 'sep', type: 'separator' as const },
        { key: 'delete', label: 'Delete', icon: <Trash2 size={16} />, destructive: true, onSelect: () => setDialog({ kind: 'delete', target: filter }) },
      ]}
      trigger={(props) => (
        <IconButton {...props} ref={props.ref} size="sm" variant="ghost" label={`Actions for ${filter.name}`}>
          <MoreHorizontal size={16} />
        </IconButton>
      )}
    />
  )

  const section = (title: string, items: SavedFilter[], own: boolean) => (
    <div className={styles.savedSection}>
      <p className={styles.sectionLabel} style={{ padding: '0 var(--space-4)' }}>
        {title}
      </p>
      {items.length === 0 ? (
        <p className={styles.savedEmpty}>{own ? 'No saved filters yet.' : 'Nothing shared with you yet.'}</p>
      ) : (
        <ul>
          {items.map((filter) => (
            <li key={filter.id} className={styles.savedRow}>
              <button type="button" className={styles.savedApply} onClick={() => apply(filter)}>
                <span className={styles.savedName}>{filter.name}</span>
                {filter.is_default && (
                  <span className={styles.savedStar} title="Default filter" role="img" aria-label="Default filter">
                    <Star size={14} fill="currentColor" aria-hidden="true" />
                  </span>
                )}
                {!own && filter.visibility === 'team' && filter.team && <span className={styles.personMeta}>{filter.team.name}</span>}
                {!own && filter.visibility === 'chapter' && <span className={styles.personMeta}>Chapter</span>}
              </button>
              {(own || isAdmin) && rowMenu(filter)}
            </li>
          ))}
        </ul>
      )}
    </div>
  )

  return (
    <>
      <Button ref={ref} size="sm" variant="ghost" leadingIcon={<Bookmark size={14} />} aria-haspopup="dialog" aria-expanded={open} aria-controls={open ? id : undefined} onClick={() => setOpen((o) => !o)}>
        My Filters
      </Button>
      <Popover open={open} onOpenChange={setOpen} anchor={anchor} id={id} role="dialog" label="My Filters" placement="bottom-start" closeOnOutsideClick={false} className={styles.savedPanel}>
        <div ref={contentRef} className={styles.savedPanel}>
          <div className={styles.savedScroll}>
            {saved.isPending ? (
              <p className={styles.savedEmpty}>Loading…</p>
            ) : saved.isError ? (
              <div style={{ padding: 'var(--space-3)' }}>
                <InlineAlert
                  tone="danger"
                  title="Saved filters could not be loaded"
                  actions={
                    <Button size="sm" onClick={() => void saved.refetch()}>
                      Retry
                    </Button>
                  }
                >
                  {errorMessage(saved.error)}
                </InlineAlert>
              </div>
            ) : (
              <>
                {section('Personal', saved.data.personal, true)}
                {section('Shared', saved.data.shared, false)}
              </>
            )}
          </div>
          <div className={styles.savedFooter}>
            <Button
              size="sm"
              variant="primary"
              onClick={() => {
                setOpen(false)
                setDialog({ kind: 'save' })
              }}
            >
              Save current filters
            </Button>
          </div>
        </div>
      </Popover>

      <SaveFilterDialog open={dialog?.kind === 'save'} current={current} canShare={canShare} onClose={() => setDialog(null)} />
      <RenameFilterDialog target={dialog?.kind === 'rename' ? dialog.target : null} onClose={() => setDialog(null)} />
      <ShareFilterDialog target={dialog?.kind === 'share' ? dialog.target : null} onClose={() => setDialog(null)} />
      <Dialog
        open={dialog?.kind === 'delete'}
        onClose={() => setDialog(null)}
        size="sm"
        title="Delete this saved filter?"
        description={dialog?.kind === 'delete' ? `“${dialog.target.name}” will be removed for everyone it is shared with.` : undefined}
        preventClose={remove.isPending}
        footer={
          <>
            <Button variant="ghost" onClick={() => setDialog(null)} disabled={remove.isPending}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={remove.isPending}
              data-autofocus
              onClick={async () => {
                if (dialog?.kind !== 'delete') return
                try {
                  await remove.mutateAsync(dialog.target.id)
                  toast.success('Saved filter deleted')
                  setDialog(null)
                } catch (error) {
                  toast.error('Could not delete the filter', errorMessage(error))
                }
              }}
            >
              Delete
            </Button>
          </>
        }
      />
    </>
  )
}

/* Save dialog ---------------------------------------------------------------- */

interface SaveValues {
  name: string
  visibility: SavedFilterVisibility
  team_id: string | null
}

function SaveFilterDialog({ open, current, canShare, onClose }: { open: boolean; current: SavedFiltersMenuProps['current']; canShare: boolean; onClose: () => void }) {
  const create = useCreateSavedFilter()
  const toast = useToast()
  const teams = useTeamOptions()
  const form = useForm<SaveValues>({
    resolver: zodResolver(SavedFilterNameInput.and(SavedFilterShareInput)),
    defaultValues: { name: '', visibility: 'private', team_id: null },
  })
  const { register, handleSubmit, reset, setError, control, formState } = form
  const visibility = useWatch({ control, name: 'visibility' })

  useEffect(() => {
    if (open) {
      reset({ name: '', visibility: 'private', team_id: null })
      create.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, reset])

  const submit = handleSubmit(async (values) => {
    try {
      const saved = await create.mutateAsync({
        entity_type: 'work_order',
        name: values.name,
        visibility: values.visibility,
        team_id: values.visibility === 'team' ? values.team_id : null,
        filter: current.filter,
        sort: current.sort,
        view_type: current.view_type,
      })
      toast.success('Filter saved', saved.name)
      onClose()
    } catch (error) {
      if (error instanceof ApiError && error.isValidation) {
        for (const [field, message] of Object.entries(error.errors)) setError(field as keyof SaveValues, { type: 'server', message })
      } else toast.error('Could not save the filter', errorMessage(error))
    }
  })

  const generalError = create.error && !(create.error instanceof ApiError && create.error.isValidation) ? errorMessage(create.error) : null
  const summary = Object.entries(current.filter)
    .map(([k, v]) => `${k}: ${v}`)
    .join(' · ')

  return (
    <Dialog
      open={open}
      onClose={onClose}
      size="sm"
      title="Save current filters"
      description={summary ? `Saves ${summary} and the current sort.` : 'Saves the current sort and view; no filters are active.'}
      preventClose={create.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={create.isPending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="save-filter-form" loading={create.isPending}>
            Save filter
          </Button>
        </>
      }
    >
      <form id="save-filter-form" noValidate onSubmit={submit} className={styles.form}>
        {generalError && <InlineAlert tone="danger">{generalError}</InlineAlert>}
        <FormField label="Name" required error={formState.errors.name?.message}>
          <Input {...register('name')} data-autofocus placeholder="e.g. My overdue work" maxLength={120} />
        </FormField>
        <FormField label="Visibility" error={formState.errors.visibility?.message}>
          <Select {...register('visibility')}>
            {SAVED_FILTER_VISIBILITIES.filter((v) => v === 'private' || canShare).map((v) => (
              <option key={v} value={v}>
                {SAVED_FILTER_VISIBILITY_LABELS[v]}
              </option>
            ))}
          </Select>
        </FormField>
        {visibility === 'team' && (
          <FormField label="Team" required error={formState.errors.team_id?.message}>
            <Controller control={control} name="team_id" render={({ field }) => <Combobox options={teams.options} loading={teams.isLoading} value={field.value} onChange={field.onChange} placeholder="Choose a team" />} />
          </FormField>
        )}
      </form>
    </Dialog>
  )
}

/* Rename dialog -------------------------------------------------------------- */

function RenameFilterDialog({ target, onClose }: { target: SavedFilter | null; onClose: () => void }) {
  const update = useUpdateSavedFilter()
  const toast = useToast()
  const { register, handleSubmit, reset, setError, formState } = useForm<{ name: string }>({ resolver: zodResolver(SavedFilterNameInput), defaultValues: { name: '' } })
  const targetId = target?.id
  const targetName = target?.name ?? ''
  useEffect(() => {
    if (targetId) reset({ name: targetName })
  }, [targetId, targetName, reset])

  return (
    <Dialog
      open={Boolean(target)}
      onClose={onClose}
      size="sm"
      title="Rename filter"
      preventClose={update.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={update.isPending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="rename-filter-form" loading={update.isPending}>
            Rename
          </Button>
        </>
      }
    >
      <form
        id="rename-filter-form"
        noValidate
        className={styles.form}
        onSubmit={handleSubmit(async (values) => {
          if (!target) return
          try {
            await update.mutateAsync({ id: target.id, name: values.name })
            toast.success('Filter renamed')
            onClose()
          } catch (error) {
            if (error instanceof ApiError && error.isValidation && error.errors.name) setError('name', { type: 'server', message: error.errors.name })
            else toast.error('Could not rename the filter', errorMessage(error))
          }
        })}
      >
        <FormField label="Name" required error={formState.errors.name?.message}>
          <Input {...register('name')} data-autofocus maxLength={120} />
        </FormField>
      </form>
    </Dialog>
  )
}

/* Share dialog --------------------------------------------------------------- */

function ShareFilterDialog({ target, onClose }: { target: SavedFilter | null; onClose: () => void }) {
  const update = useUpdateSavedFilter()
  const toast = useToast()
  const teams = useTeamOptions()
  const { register, handleSubmit, reset, setError, control, formState } = useForm<SavedFilterShareInput>({
    resolver: zodResolver(SavedFilterShareInput),
    defaultValues: { visibility: 'private', team_id: null },
  })
  const visibility = useWatch({ control, name: 'visibility' })
  const targetId = target?.id
  const targetVisibility = target?.visibility
  const targetTeam = target?.team?.id ?? null
  useEffect(() => {
    if (targetId) reset({ visibility: (SAVED_FILTER_VISIBILITIES as readonly string[]).includes(targetVisibility ?? '') ? (targetVisibility as SavedFilterVisibility) : 'private', team_id: targetTeam })
  }, [targetId, targetVisibility, targetTeam, reset])

  return (
    <Dialog
      open={Boolean(target)}
      onClose={onClose}
      size="sm"
      title="Share filter"
      description="Shared filters appear under “Shared” for the people you choose. They can apply it but not change it."
      preventClose={update.isPending}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={update.isPending}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="share-filter-form" loading={update.isPending}>
            Save sharing
          </Button>
        </>
      }
    >
      <form
        id="share-filter-form"
        noValidate
        className={styles.form}
        onSubmit={handleSubmit(async (values) => {
          if (!target) return
          try {
            await update.mutateAsync({ id: target.id, visibility: values.visibility, team_id: values.visibility === 'team' ? values.team_id : null })
            toast.success('Sharing updated')
            onClose()
          } catch (error) {
            if (error instanceof ApiError && error.isValidation) {
              for (const [field, message] of Object.entries(error.errors)) setError(field as keyof SavedFilterShareInput, { type: 'server', message })
            } else toast.error('Could not share the filter', errorMessage(error))
          }
        })}
      >
        <FormField label="Visibility" error={formState.errors.visibility?.message}>
          <Select {...register('visibility')} data-autofocus>
            {SAVED_FILTER_VISIBILITIES.map((v) => (
              <option key={v} value={v}>
                {SAVED_FILTER_VISIBILITY_LABELS[v]}
              </option>
            ))}
          </Select>
        </FormField>
        {visibility === 'team' && (
          <FormField label="Team" required error={formState.errors.team_id?.message}>
            <Controller control={control} name="team_id" render={({ field }) => <Combobox options={teams.options} loading={teams.isLoading} value={field.value} onChange={field.onChange} placeholder="Choose a team" />} />
          </FormField>
        )}
      </form>
    </Dialog>
  )
}
