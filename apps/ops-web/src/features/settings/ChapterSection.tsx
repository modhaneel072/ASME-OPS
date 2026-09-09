import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { ApiError, errorMessage } from '@/api/client'
import {
  ChapterSettingsForm,
  COMMON_TIMEZONES,
  CUSTOM_TIMEZONE,
  MONTHS,
  monthLabel,
  ORGANIZATION_FIELD_MAP,
  organizationToForm,
  toOrganizationPatch,
  type Organization,
} from '@/api/contracts/organization'
import { useOrganization, useUpdateOrganization } from '@/api/queries/organization'
import { formatDateTime } from '@/lib/dates'
import { useCan, useSession } from '@/lib/permissions'
import { Badge, Button, Card, Checkbox, FieldList, FieldRow, FormField, FormSection, InlineAlert, Input, Select, SkeletonBlock, Stack, useToast } from '@/ui'
import styles from './settings.module.css'

export function ChapterSection() {
  const session = useSession()
  const can = useCan()
  const canManage = can('chapter.settings.manage')
  const organization = useOrganization()

  if (organization.isPending) {
    return (
      <Card title="Chapter profile">
        <SkeletonBlock lines={6} />
      </Card>
    )
  }
  if (organization.isError) {
    return (
      <InlineAlert
        tone="danger"
        title="Chapter settings could not be loaded"
        actions={
          <Button size="sm" onClick={() => void organization.refetch()}>
            Retry
          </Button>
        }
      >
        {errorMessage(organization.error)}
      </InlineAlert>
    )
  }

  const org = organization.data ?? session.organization
  return canManage ? <ChapterForm organization={org} /> : <ChapterReadOnly organization={org} />
}

function settingString(settings: Record<string, unknown>, key: string): string {
  const value = settings[key]
  return typeof value === 'string' && value ? value : typeof value === 'number' ? String(value) : '—'
}

export function ChapterReadOnly({ organization }: { organization: Organization }) {
  const settings = organization.settings as Record<string, unknown>
  const siteUrl = typeof settings.public_site_url === 'string' ? settings.public_site_url : null
  return (
    <Stack>
      <InlineAlert tone="info">Chapter settings are managed by chapter administrators. You can review them here.</InlineAlert>
      <Card title="Chapter profile">
        <FieldList
          items={[
            { label: 'Chapter name', value: organization.name },
            { label: 'Short name', value: settingString(settings, 'chapter_short_name') },
            { label: 'Time zone', value: organization.timezone },
            { label: 'Academic year starts', value: monthLabel(organization.academic_year_start_month) },
            { label: 'Primary contact', value: settingString(settings, 'primary_contact_email') },
            {
              label: 'Public website',
              value: siteUrl ? (
                <a href={siteUrl} target="_blank" rel="noreferrer">
                  {siteUrl}
                </a>
              ) : (
                '—'
              ),
            },
            { label: 'Default due window', value: settingString(settings, 'default_due_days') === '—' ? '—' : `${settingString(settings, 'default_due_days')} days` },
            {
              label: 'Profile status',
              value: settings.profile_completed === true ? (
                <Badge tone="success" dot>
                  Complete
                </Badge>
              ) : (
                <Badge tone="warning" dot>
                  In progress
                </Badge>
              ),
            },
            { label: 'Last updated', value: formatDateTime(organization.updated_at) },
          ]}
        />
      </Card>
    </Stack>
  )
}

export function ChapterForm({ organization }: { organization: Organization }) {
  const toast = useToast()
  const update = useUpdateOrganization()
  const form = useForm<ChapterSettingsForm>({
    resolver: zodResolver(ChapterSettingsForm),
    defaultValues: organizationToForm(organization),
  })
  const { register, control, handleSubmit, reset, setError, formState } = form
  const logoUrl = useWatch({ control, name: 'logo_url' })

  // Re-seed when the organization changes underneath us (another admin saved, session refreshed).
  useEffect(() => {
    if (!formState.isDirty) reset(organizationToForm(organization))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [organization.updated_at])

  useEffect(() => {
    const error = update.error
    if (!(error instanceof ApiError && error.isValidation)) return
    for (const [field, message] of Object.entries(error.errors)) {
      const target = ORGANIZATION_FIELD_MAP[field]
      if (target) setError(target, { type: 'server', message })
      else setError('root.server', { type: 'server', message: `${field}: ${message}` })
    }
  }, [update.error, setError])

  const submit = handleSubmit(async (values) => {
    try {
      const saved = await update.mutateAsync(toOrganizationPatch(values))
      reset(organizationToForm(saved))
      toast.success('Chapter settings saved')
    } catch (error) {
      if (!(error instanceof ApiError && error.isValidation)) toast.error('Could not save chapter settings', errorMessage(error))
    }
  })

  const discard = () => {
    if (!formState.isDirty || window.confirm('Discard your unsaved changes?')) {
      reset(organizationToForm(organization))
      update.reset()
    }
  }

  const generalError = update.error && !(update.error instanceof ApiError && update.error.isValidation) ? errorMessage(update.error) : formState.errors.root?.server?.message
  const submitting = update.isPending

  return (
    <form className={styles.form} noValidate onSubmit={(event) => void submit(event)} aria-label="Chapter settings">
      {generalError && (
        <InlineAlert tone="danger" title="Changes were not saved">
          {generalError}
        </InlineAlert>
      )}
      <Card title="Chapter profile">
        <Stack>
          <FormField label="Chapter name" required error={formState.errors.name?.message}>
            <Input {...register('name')} maxLength={200} placeholder="ASME at the University of Iowa" />
          </FormField>
          <FieldRow>
            <FormField label="Short name" optionalLabel hint="Used where space is tight, e.g. badges and exports." error={formState.errors.chapter_short_name?.message}>
              <Input {...register('chapter_short_name')} maxLength={40} placeholder="ASME Iowa" />
            </FormField>
            <FormField label="Academic year starts" required error={formState.errors.academic_year_start_month?.message}>
              <Select {...register('academic_year_start_month')}>
                {MONTHS.map((month) => (
                  <option key={month.value} value={month.value}>
                    {month.label}
                  </option>
                ))}
              </Select>
            </FormField>
          </FieldRow>
          <Controller
            control={control}
            name="timezone"
            render={({ field }) => {
              const isCommon = (COMMON_TIMEZONES as readonly string[]).includes(field.value)
              const selectValue = isCommon ? field.value : CUSTOM_TIMEZONE
              return (
                <FieldRow>
                  <FormField label="Time zone" required hint="IANA name, e.g. America/Chicago." error={isCommon ? formState.errors.timezone?.message : undefined}>
                    <Select
                      value={selectValue}
                      onChange={(event) => field.onChange(event.target.value === CUSTOM_TIMEZONE ? (isCommon ? '' : field.value) : event.target.value)}
                      onBlur={field.onBlur}
                      name={field.name}
                    >
                      {COMMON_TIMEZONES.map((zone) => (
                        <option key={zone} value={zone}>
                          {zone}
                        </option>
                      ))}
                      <option value={CUSTOM_TIMEZONE}>Other (type it in)…</option>
                    </Select>
                  </FormField>
                  {!isCommon && (
                    <FormField label="Custom time zone" required error={formState.errors.timezone?.message}>
                      <Input ref={field.ref} value={field.value} onChange={(event) => field.onChange(event.target.value)} onBlur={field.onBlur} placeholder="Region/City" maxLength={64} data-autofocus />
                    </FormField>
                  )}
                </FieldRow>
              )
            }}
          />
          <FormField label="Logo URL" optionalLabel hint="A square PNG or SVG works best." error={formState.errors.logo_url?.message}>
            <Input {...register('logo_url')} type="url" inputMode="url" placeholder="https://" maxLength={500} />
          </FormField>
          {logoUrl && !formState.errors.logo_url && (
            <div className={styles.logoPreview}>
              <img className={styles.logoImage} src={logoUrl} alt="" />
              <span style={{ fontSize: 'var(--text-caption)', color: 'var(--color-text-muted)' }}>Logo preview</span>
            </div>
          )}
          <Controller control={control} name="profile_completed" render={({ field }) => <Checkbox name={field.name} checked={field.value} onChange={field.onChange} label="Chapter profile is complete" hint="Marks the profile task done in the Setup Center." />} />
        </Stack>
      </Card>

      <Card title="Contact and defaults">
        <FormSection title="Contact">
          <FieldRow>
            <FormField label="Primary contact email" optionalLabel error={formState.errors.primary_contact_email?.message}>
              <Input {...register('primary_contact_email')} type="email" inputMode="email" placeholder="asme@uiowa.edu" maxLength={160} />
            </FormField>
            <FormField label="Public website" optionalLabel error={formState.errors.public_site_url?.message}>
              <Input {...register('public_site_url')} type="url" inputMode="url" placeholder="https://" maxLength={500} />
            </FormField>
          </FieldRow>
        </FormSection>
        <FormSection title="Work defaults">
          <FormField label="Default due window (days)" optionalLabel hint="Suggested due date offset for new work orders. Leave blank for none." error={formState.errors.default_due_days?.message}>
            <Input {...register('default_due_days')} inputMode="numeric" placeholder="7" maxLength={3} style={{ maxWidth: 160 }} />
          </FormField>
        </FormSection>
      </Card>

      <div className={styles.formFooter}>
        <span className={styles.formFooterNote}>{formState.isDirty ? 'Unsaved changes' : `Last updated ${formatDateTime(organization.updated_at)}`}</span>
        <Button variant="ghost" onClick={discard} disabled={!formState.isDirty || submitting}>
          Discard
        </Button>
        <Button type="submit" variant="primary" loading={submitting} disabled={submitting}>
          Save changes
        </Button>
      </div>
    </form>
  )
}
