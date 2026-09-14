import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError, errorMessage } from '@/api/client'
import { useLogin, useSessionState } from '@/api/queries/session'
import { Button, FormField, InlineAlert, Input } from '@/ui'
import { AuthLayout } from './AuthLayout'
import styles from './shell.module.css'

/** Router state other account pages hand to the sign-in page. */
export type LoginNotice = 'password_set' | 'password_reset'

export interface LoginLocationState {
  notice?: LoginNotice
}

const NOTICES: Record<LoginNotice, { title: string; body: string }> = {
  password_set: { title: 'Your password is set', body: 'Sign in with your email and the password you just chose.' },
  password_reset: { title: 'Your password has been changed', body: 'Sign in with your new password.' },
}

function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith('/') || raw.startsWith('//')) return '/'
  return raw
}

function readNotice(state: unknown): LoginNotice | null {
  const notice = (state as LoginLocationState | null)?.notice
  return notice && notice in NOTICES ? notice : null
}

export function LoginPage() {
  const [params] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const state = useSessionState()
  const login = useLogin()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [noMembership, setNoMembership] = useState(false)
  const identifierRef = useRef<HTMLInputElement>(null)
  const next = safeNext(params.get('next'))
  const notice = readNotice(location.state)

  useEffect(() => {
    if (state.status === 'anonymous') identifierRef.current?.focus()
  }, [state.status])

  if (state.status === 'ready') return <Navigate to={next} replace />

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setFieldErrors({})
    setNoMembership(false)
    login.mutate(
      { identifier: identifier.trim(), password },
      {
        onSuccess: (data) => {
          if (data.session) navigate(next, { replace: true })
          else setNoMembership(true)
        },
        onError: (error) => {
          if (error instanceof ApiError && error.isValidation) setFieldErrors(error.errors)
        },
      },
    )
  }

  const generalError = login.error && !(login.error instanceof ApiError && login.error.isValidation) ? errorMessage(login.error) : null

  return (
    <AuthLayout footer={<Link to="/auth/forgot-password">Forgot password?</Link>}>
      <form className={styles.authForm} onSubmit={submit} noValidate>
        {notice && !generalError && !noMembership && (
          <InlineAlert tone="success" title={NOTICES[notice].title}>
            {NOTICES[notice].body}
          </InlineAlert>
        )}
        {generalError && <InlineAlert tone="danger">{generalError}</InlineAlert>}
        {noMembership && (
          <InlineAlert tone="warning" title="Signed in without a workspace membership">
            Ask a chapter administrator to add you to ASME Ops.
          </InlineAlert>
        )}
        <FormField label="Email or username" required error={fieldErrors.identifier}>
          <Input ref={identifierRef} name="identifier" autoComplete="username" value={identifier} onChange={(e) => setIdentifier(e.target.value)} />
        </FormField>
        <FormField label="Password" required error={fieldErrors.password}>
          <Input name="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </FormField>
        <Button type="submit" variant="primary" block loading={login.isPending}>
          Sign in
        </Button>
      </form>
    </AuthLayout>
  )
}
