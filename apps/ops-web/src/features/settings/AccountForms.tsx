import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect } from 'react'
import { useForm, type FieldPath, type FieldValues, type UseFormSetError } from 'react-hook-form'
import { ApiError, errorMessage } from '@/api/client'
import { ChangePasswordForm, PASSWORD_MIN_LENGTH, ProfileForm, profileToForm, toProfilePatch } from '@/api/contracts/session'
import { useChangePassword, useUpdateProfile } from '@/api/queries/session'
import { useSession } from '@/lib/permissions'
import { Button, Card, FieldRow, FormField, InlineAlert, Input, Stack, useToast } from '@/ui'
import styles from './settings.module.css'

/** Puts server field errors on known fields; anything else becomes a form-level message. */
function applyServerErrors<T extends FieldValues>(error: ApiError, fields: ReadonlyArray<FieldPath<T>>, setError: UseFormSetError<T>) {
  let focused = false
  const unknown: string[] = []
  for (const [field, message] of Object.entries(error.errors)) {
    if ((fields as readonly string[]).includes(field)) {
      setError(field as FieldPath<T>, { type: 'server', message }, { shouldFocus: !focused })
      focused = true
    } else {
      unknown.push(message)
    }
  }
  if (!focused || unknown.length) setError('root.server' as FieldPath<T>, { type: 'server', message: unknown.join(' ') || error.message })
}

const PROFILE_FIELDS = ['name', 'major', 'graduation_year', 'phone'] as const

export function EditProfileForm() {
  const session = useSession()
  const toast = useToast()
  const update = useUpdateProfile()
  const form = useForm<ProfileForm>({ resolver: zodResolver(ProfileForm), defaultValues: profileToForm(session.user) })
  const { register, handleSubmit, reset, setError, formState } = form
  const { dirtyFields, isDirty } = formState

  // Re-seed from the session when it changes underneath an untouched form.
  const { user } = session
  useEffect(() => {
    if (!isDirty) reset(profileToForm(user))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user.name, user.major, user.graduation_year, user.phone])

  const submit = handleSubmit(async (values) => {
    const patch = toProfilePatch(values, dirtyFields)
    if (Object.keys(patch).length === 0) return
    try {
      const saved = await update.mutateAsync(patch)
      reset(profileToForm(saved.user))
      toast.success('Profile saved')
    } catch (error) {
      if (error instanceof ApiError && error.isValidation) applyServerErrors<ProfileForm>(error, PROFILE_FIELDS, setError)
      else toast.error('Could not save your profile', errorMessage(error))
    }
  })

  const generalError = update.error && !(update.error instanceof ApiError && update.error.isValidation) ? errorMessage(update.error) : formState.errors.root?.server?.message

  return (
    <Card title="Edit profile">
      <form className={styles.form} noValidate onSubmit={(event) => void submit(event)} aria-label="Edit profile">
        {generalError && (
          <InlineAlert tone="danger" title="Your profile was not saved">
            {generalError}
          </InlineAlert>
        )}
        <Stack>
          <FormField label="Name" required error={formState.errors.name?.message}>
            <Input {...register('name')} autoComplete="name" maxLength={160} />
          </FormField>
          <FieldRow>
            <FormField label="Major" optionalLabel error={formState.errors.major?.message}>
              <Input {...register('major')} maxLength={120} placeholder="Mechanical Engineering" />
            </FormField>
            <FormField label="Graduation year" optionalLabel error={formState.errors.graduation_year?.message}>
              <Input {...register('graduation_year')} inputMode="numeric" maxLength={4} placeholder="2027" />
            </FormField>
          </FieldRow>
          <FormField label="Phone" optionalLabel error={formState.errors.phone?.message}>
            <Input {...register('phone')} type="tel" autoComplete="tel" maxLength={40} />
          </FormField>
        </Stack>
        <div className={styles.formFooter}>
          <Button variant="ghost" disabled={!isDirty || update.isPending}
            onClick={() => {
              reset()
              update.reset()
            }}
          >
            Discard
          </Button>
          <Button type="submit" variant="primary" loading={update.isPending} disabled={!isDirty}>
            Save profile
          </Button>
        </div>
      </form>
    </Card>
  )
}

const PASSWORD_FIELDS = ['current_password', 'new_password', 'confirm_password'] as const
const EMPTY_PASSWORDS: ChangePasswordForm = { current_password: '', new_password: '', confirm_password: '' }

export function ChangePasswordCard() {
  const session = useSession()
  const toast = useToast()
  const change = useChangePassword()
  const { register, handleSubmit, reset, setError, formState } = useForm<ChangePasswordForm>({ resolver: zodResolver(ChangePasswordForm), defaultValues: EMPTY_PASSWORDS })

  const submit = handleSubmit(async (values) => {
    try {
      await change.mutateAsync(values)
      reset(EMPTY_PASSWORDS)
      toast.success('Password changed', 'Use your new password the next time you sign in.')
    } catch (error) {
      if (error instanceof ApiError && error.isValidation) applyServerErrors<ChangePasswordForm>(error, PASSWORD_FIELDS, setError)
      else toast.error('Could not change your password', errorMessage(error))
    }
  })

  const generalError = change.error && !(change.error instanceof ApiError && change.error.isValidation) ? errorMessage(change.error) : formState.errors.root?.server?.message

  return (
    <Card title="Change password">
      <form className={styles.form} noValidate onSubmit={(event) => void submit(event)} aria-label="Change password">
        {generalError && (
          <InlineAlert tone="danger" title="Your password was not changed">
            {generalError}
          </InlineAlert>
        )}
        {/* Lets password managers update the saved password for this account. */}
        <input type="text" name="username" autoComplete="username" value={session.user.email} readOnly hidden />
        <Stack>
          <FormField label="Current password" required error={formState.errors.current_password?.message}>
            <Input {...register('current_password')} type="password" autoComplete="current-password" />
          </FormField>
          <FieldRow>
            <FormField label="New password" required hint={`At least ${PASSWORD_MIN_LENGTH} characters.`} error={formState.errors.new_password?.message}>
              <Input {...register('new_password')} type="password" autoComplete="new-password" />
            </FormField>
            <FormField label="Confirm new password" required error={formState.errors.confirm_password?.message}>
              <Input {...register('confirm_password')} type="password" autoComplete="new-password" />
            </FormField>
          </FieldRow>
        </Stack>
        <div className={styles.formFooter}>
          <Button type="submit" variant="primary" loading={change.isPending}>
            Change password
          </Button>
        </div>
      </form>
    </Card>
  )
}
