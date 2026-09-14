import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ApiError, errorMessage } from '@/api/client'
import { PASSWORD_MIN_LENGTH, ResetPasswordForm, type ResetTokenInfo } from '@/api/contracts/session'
import { isInvalidTokenError, rateLimitMessage, useResetPassword, useResetToken } from '@/api/queries/session'
import { formatDateTime } from '@/lib/dates'
import { Button, FormField, InlineAlert, Input, LinkButton, SkeletonBlock } from '@/ui'
import { AuthLayout } from './AuthLayout'
import type { LoginLocationState } from './LoginPage'
import styles from './shell.module.css'

function InvalidLink() {
  return (
    <AuthLayout heading="This link is invalid or has expired" footer={<Link to="/auth/login">Back to sign in</Link>}>
      <div className={styles.authStatus}>
        <p className={styles.authText}>Password links work once and expire. Request a new link and use it from the most recent email you receive.</p>
        <LinkButton to="/auth/forgot-password" variant="primary">
          Request a new link
        </LinkButton>
      </div>
    </AuthLayout>
  )
}

/** Links carry the token in the fragment (`#token=...`), which browsers never send to a server. */
function tokenFromHash(hash: string): string {
  return (new URLSearchParams(hash.replace(/^#/, '')).get('token') ?? '').trim()
}

export function ResetPasswordPage() {
  const location = useLocation()
  const navigate = useNavigate()
  const [token] = useState(() => tokenFromHash(location.hash))

  // Drop the token from the address bar and history once it is held in memory.
  useEffect(() => {
    if (location.hash) navigate({ pathname: location.pathname, search: location.search }, { replace: true })
  }, [location.hash, location.pathname, location.search, navigate])

  const tokenQuery = useResetToken(token)
  const reset = useResetPassword()

  if (!token || isInvalidTokenError(tokenQuery.error) || isInvalidTokenError(reset.error)) return <InvalidLink />

  if (tokenQuery.isPending) {
    return (
      <AuthLayout busy>
        <div aria-label="Checking your link" role="status">
          <SkeletonBlock lines={5} />
        </div>
      </AuthLayout>
    )
  }

  if (tokenQuery.isError) {
    return (
      <AuthLayout heading="We couldn't check your link" footer={<Link to="/auth/login">Back to sign in</Link>}>
        <InlineAlert
          tone="danger"
          actions={
            <Button size="sm" onClick={() => void tokenQuery.refetch()} loading={tokenQuery.isFetching}>
              Retry
            </Button>
          }
        >
          {rateLimitMessage(tokenQuery.error) ?? errorMessage(tokenQuery.error)}
        </InlineAlert>
      </AuthLayout>
    )
  }

  return <ResetForm token={token} info={tokenQuery.data} mutation={reset} />
}

function ResetForm({ token, info, mutation }: { token: string; info: ResetTokenInfo; mutation: ReturnType<typeof useResetPassword> }) {
  const navigate = useNavigate()
  const invite = info.purpose === 'invite'
  const { register, handleSubmit, setError, setFocus, formState } = useForm<ResetPasswordForm>({
    resolver: zodResolver(ResetPasswordForm),
    defaultValues: { password: '', confirm_password: '' },
  })

  useEffect(() => {
    setFocus('password')
  }, [setFocus])

  const submit = handleSubmit(async (values) => {
    try {
      await mutation.mutateAsync({ token, password: values.password, confirm_password: values.confirm_password })
      const state: LoginLocationState = { notice: invite ? 'password_set' : 'password_reset' }
      navigate('/auth/login', { replace: true, state })
    } catch (error) {
      if (error instanceof ApiError && error.isValidation) {
        let mapped = false
        for (const field of ['password', 'confirm_password'] as const) {
          const message = error.errors[field]
          if (message) {
            setError(field, { type: 'server', message }, { shouldFocus: !mapped })
            mapped = true
          }
        }
        if (!mapped) setError('root.server', { type: 'server', message: error.message })
      }
    }
  })

  const error = mutation.error
  const limited = rateLimitMessage(error)
  const generalError = limited ? null : error && !(error instanceof ApiError && error.isValidation) ? errorMessage(error) : (formState.errors.root?.server?.message ?? null)

  return (
    <AuthLayout
      heading={invite ? 'Set your password' : 'Choose a new password'}
      description={
        <>
          {invite ? 'Finish setting up ' : 'Choose a new password for '}
          <span className={styles.authEmail}>{info.email}</span>
          {invite ? '. You will use this password to sign in to ASME Ops.' : '.'} This link expires {formatDateTime(info.expires_at)}.
        </>
      }
      footer={<Link to="/auth/login">Back to sign in</Link>}
    >
      <form className={styles.authForm} onSubmit={(event) => void submit(event)} noValidate aria-label={invite ? 'Set your password' : 'Choose a new password'}>
        {limited && (
          <InlineAlert tone="warning" title="Please wait before trying again">
            {limited}
          </InlineAlert>
        )}
        {generalError && <InlineAlert tone="danger">{generalError}</InlineAlert>}
        {/* Lets password managers save the new password against the right account. */}
        <input type="text" name="username" autoComplete="username" value={info.email} readOnly hidden />
        <FormField label={invite ? 'Password' : 'New password'} required hint={`At least ${PASSWORD_MIN_LENGTH} characters.`} error={formState.errors.password?.message}>
          <Input {...register('password')} type="password" autoComplete="new-password" />
        </FormField>
        <FormField label="Confirm password" required error={formState.errors.confirm_password?.message}>
          <Input {...register('confirm_password')} type="password" autoComplete="new-password" />
        </FormField>
        <Button type="submit" variant="primary" block loading={mutation.isPending}>
          {invite ? 'Set password' : 'Change password'}
        </Button>
      </form>
    </AuthLayout>
  )
}
