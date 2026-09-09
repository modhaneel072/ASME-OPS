import { zodResolver } from '@hookform/resolvers/zod'
import { Check, Copy } from 'lucide-react'
import { useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { ApiError, errorMessage } from '@/api/client'
import { InviteInput, type InviteResult, type Member, type Role } from '@/api/contracts/users'
import { useInviteUser } from '@/api/queries/users'
import { Button, Dialog, FieldRow, FormField, InlineAlert, Input, Select, useToast } from '@/ui'
import styles from './teams-users.module.css'

export const INVITE_LINK_WARNING = 'This link is shown once. Send it to the member yourself.'

const FIELDS: ReadonlyArray<keyof InviteInput> = ['email', 'name', 'role_key', 'title']

export interface InviteDialogProps {
  /** Roles from `GET /roles`; only system roles can be chosen (`POST /users/invite` takes `role_key`). */
  roles: Role[]
  onClose: () => void
  /** Called when the admin is finished with the invite link. */
  onDone: (member: Member) => void
}

/**
 * Invite a member. Once the invitation exists the form is replaced by the
 * one-time link; the API never returns that link again.
 */
export function InviteDialog({ roles, onClose, onDone }: InviteDialogProps) {
  const invite = useInviteUser()
  const toast = useToast()
  const [result, setResult] = useState<InviteResult | null>(null)
  const [copied, setCopied] = useState(false)
  const [generalError, setGeneralError] = useState<string | null>(null)
  const systemRoles = roles.filter((role) => role.system_key)

  const form = useForm<InviteInput>({
    resolver: zodResolver(InviteInput),
    defaultValues: { email: '', name: '', role_key: 'full_member', title: '' },
  })
  const { register, control, handleSubmit, setError, formState } = form

  const submit = handleSubmit(async (values) => {
    setGeneralError(null)
    try {
      const outcome = await invite.mutateAsync({
        email: values.email.trim().toLowerCase(),
        name: values.name.trim(),
        role_key: values.role_key,
        title: values.title?.trim() || undefined,
      })
      setResult(outcome)
      toast.success('Invitation created', `${outcome.member.user.name} is listed as an invited member.`)
    } catch (error) {
      if (error instanceof ApiError && error.isValidation) {
        for (const [field, message] of Object.entries(error.errors)) {
          if ((FIELDS as readonly string[]).includes(field)) setError(field as keyof InviteInput, { type: 'server', message })
          else setGeneralError(message)
        }
      } else if (error instanceof ApiError && error.code === 'already_member') {
        setError('email', { type: 'server', message: error.message })
      } else if (error instanceof ApiError && error.isForbidden) {
        toast.error('You cannot invite members', error.message)
      } else {
        setGeneralError(errorMessage(error))
      }
    }
  })

  const copy = async () => {
    if (!result) return
    try {
      await navigator.clipboard.writeText(result.invite_url)
      setCopied(true)
    } catch {
      toast.error('Could not copy the link', 'Select the link and copy it manually.')
    }
  }

  const requestClose = () => {
    if (invite.isPending) return
    if (!result && formState.isDirty && !window.confirm('Discard this invitation?')) return
    if (result && !copied && !window.confirm('Close without copying the link? It will not be shown again.')) return
    onClose()
  }

  return (
    <Dialog
      open
      onClose={requestClose}
      title={result ? 'Invitation ready' : 'Invite a member'}
      description={result ? undefined : 'They get a one-time link to set a password and join the chapter.'}
      preventClose={invite.isPending}
      footer={
        result ? (
          <Button variant="primary" onClick={() => onDone(result.member)}>
            Done
          </Button>
        ) : (
          <>
            <Button variant="ghost" onClick={requestClose} disabled={invite.isPending}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" form="invite-form" loading={invite.isPending}>
              Create invitation
            </Button>
          </>
        )
      }
    >
      {result ? (
        <div className={styles.formGrid}>
          <InlineAlert tone="success" title={`${result.member.user.name} has been invited`}>
            They appear in the directory as an invited member until they sign in with this link.
          </InlineAlert>
          <FormField label="Invite link">
            <div className={styles.inviteUrlRow}>
              <Input readOnly value={result.invite_url} onFocus={(event) => event.currentTarget.select()} data-autofocus />
              <Button leadingIcon={copied ? <Check size={16} /> : <Copy size={16} />} onClick={() => void copy()}>
                {copied ? 'Copied' : 'Copy link'}
              </Button>
            </div>
          </FormField>
          <InlineAlert tone="warning">{INVITE_LINK_WARNING}</InlineAlert>
        </div>
      ) : (
        <form id="invite-form" noValidate onSubmit={submit} className={styles.formGrid}>
          {generalError && <InlineAlert tone="danger">{generalError}</InlineAlert>}
          <FormField label="Email" required error={formState.errors.email?.message}>
            <Input type="email" autoComplete="off" {...register('email', { setValueAs: (value: string) => value.trim() })} data-autofocus placeholder="hawkid@uiowa.edu" maxLength={160} />
          </FormField>
          <FormField label="Name" required error={formState.errors.name?.message}>
            <Input {...register('name')} placeholder="First and last name" maxLength={160} />
          </FormField>
          <FieldRow>
            <FormField label="Role" required error={formState.errors.role_key?.message}>
              <Controller
                control={control}
                name="role_key"
                render={({ field }) => (
                  <Select value={field.value} onChange={field.onChange} onBlur={field.onBlur} name={field.name} ref={field.ref}>
                    {systemRoles.length === 0 && <option value="full_member">Full Member</option>}
                    {systemRoles.map((role) => (
                      <option key={role.id} value={role.system_key ?? ''}>
                        {role.name}
                      </option>
                    ))}
                  </Select>
                )}
              />
            </FormField>
            <FormField label="Title" optionalLabel error={formState.errors.title?.message}>
              <Input {...register('title')} placeholder="e.g. Wheels lead" maxLength={120} />
            </FormField>
          </FieldRow>
        </form>
      )}
    </Dialog>
  )
}
