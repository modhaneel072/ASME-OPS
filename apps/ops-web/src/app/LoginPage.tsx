import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError, errorMessage } from '@/api/client'
import { useLogin, useSessionState } from '@/api/queries/session'
import { Button, FormField, InlineAlert, Input } from '@/ui'
import styles from './shell.module.css'

function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith('/') || raw.startsWith('//')) return '/'
  return raw
}

export function LoginPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const state = useSessionState()
  const login = useLogin()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [noMembership, setNoMembership] = useState(false)
  const identifierRef = useRef<HTMLInputElement>(null)
  const next = safeNext(params.get('next'))

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
    <div className={styles.shell}>
      <div className={styles.centered}>
        <div className={styles.authCard}>
          <div className={styles.authBrand}>
            <span className={styles.brandMark} aria-hidden="true">
              A
            </span>
            <div>
              <h1 className={styles.authTitle}>ASME Ops</h1>
              <p className={styles.authSubtitle}>ASME at the University of Iowa</p>
            </div>
          </div>
          <form className={styles.authForm} onSubmit={submit} noValidate>
            {generalError && <InlineAlert tone="danger">{generalError}</InlineAlert>}
            {noMembership && (
              <InlineAlert tone="warning" title="Signed in without a workspace membership">
                Ask a chapter administrator to add you to ASME Ops. You can still use the member portal.
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
          <div className={styles.authFooter}>
            <a href="/forgot-password">Forgot password?</a>
            <a href="/">Back to the website</a>
          </div>
        </div>
      </div>
    </div>
  )
}
