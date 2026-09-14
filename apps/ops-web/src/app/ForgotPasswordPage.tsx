import { zodResolver } from '@hookform/resolvers/zod'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router-dom'
import { ApiError, errorMessage } from '@/api/client'
import { ForgotPasswordForm } from '@/api/contracts/session'
import { rateLimitMessage, useForgotPassword } from '@/api/queries/session'
import { Button, FormField, InlineAlert, Input } from '@/ui'
import { AuthLayout } from './AuthLayout'
import styles from './shell.module.css'

export const FORGOT_PASSWORD_CONFIRMATION = "If an account exists for that email, we've sent a link to reset the password."

export function ForgotPasswordPage() {
  const forgot = useForgotPassword()
  const [sentTo, setSentTo] = useState<string | null>(null)
  const { register, handleSubmit, setError, setFocus, formState } = useForm<ForgotPasswordForm>({
    resolver: zodResolver(ForgotPasswordForm),
    defaultValues: { email: '' },
  })

  useEffect(() => {
    if (sentTo === null) setFocus('email')
  }, [sentTo, setFocus])

  const submit = handleSubmit(async (values) => {
    try {
      await forgot.mutateAsync({ email: values.email })
      setSentTo(values.email)
    } catch (error) {
      if (error instanceof ApiError && error.isValidation) {
        const message = error.errors.email ?? error.message
        setError('email', { type: 'server', message }, { shouldFocus: true })
      }
    }
  })

  if (sentTo !== null) {
    return (
      <AuthLayout heading="Check your email" footer={<Link to="/auth/login">Back to sign in</Link>}>
        <div className={styles.authStatus}>
          <InlineAlert tone="success">{FORGOT_PASSWORD_CONFIRMATION}</InlineAlert>
          <p className={styles.authText}>The link works once and expires, so use it soon. If nothing arrives in a few minutes, check your spam folder or send another link.</p>
          <Button
            variant="secondary"
            block
            onClick={() => {
              forgot.reset()
              setSentTo(null)
            }}
          >
            Send another link
          </Button>
        </div>
      </AuthLayout>
    )
  }

  const limited = rateLimitMessage(forgot.error)
  const generalError = forgot.error && !limited && !(forgot.error instanceof ApiError && forgot.error.isValidation) ? errorMessage(forgot.error) : null

  return (
    <AuthLayout
      heading="Reset your password"
      description="Enter the email address on your ASME Ops account and we'll send you a link to choose a new password."
      footer={<Link to="/auth/login">Back to sign in</Link>}
    >
      <form className={styles.authForm} onSubmit={(event) => void submit(event)} noValidate aria-label="Request a password reset link">
        {limited && (
          <InlineAlert tone="warning" title="Please wait before trying again">
            {limited}
          </InlineAlert>
        )}
        {generalError && <InlineAlert tone="danger">{generalError}</InlineAlert>}
        <FormField label="Email" required error={formState.errors.email?.message}>
          <Input {...register('email')} type="email" inputMode="email" autoComplete="email" maxLength={160} />
        </FormField>
        <Button type="submit" variant="primary" block loading={forgot.isPending}>
          Send reset link
        </Button>
      </form>
    </AuthLayout>
  )
}
