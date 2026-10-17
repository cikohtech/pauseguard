import { useId, useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'

import { DEMO_ANALYST, SignInError, signInAnalyst, type AnalystState } from '@/console/auth'
import { useConsoleTitle } from '@/console/title'
import { Icon, Sparkle } from '@/components/icons/Icon'
import { Field } from '@/components/m3/Field'
import { button, fieldBase } from '@/components/m3/styles'
import { PauseGuardLogo } from '@/components/ShieldMark'
import { cn } from '@/lib/utils'
import { BANK_NAME, PRODUCT_NAME } from '@/lib/product'

const ERRORS: Record<SignInError['reason'], string> = {
  credentials: 'That email and password don’t match. The demo login is filled in for you.',
  notAnalyst: 'This account isn’t an analyst account.',
  rateLimited: 'Too many attempts. Please wait a minute and try again.',
  network: 'We couldn’t reach the sign-in service. Check your connection and try again.',
  other: 'Sign-in failed. Please try again.',
}

// Analyst login (UI_SPEC Area 2). The public demo login is prefilled: judges open the console
// straight from the landing page, and every record behind it is synthetic.
export function Login({ analyst }: { analyst: AnalystState }) {
  useConsoleTitle('Sign in')
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from ?? '/console'
  const [email, setEmail] = useState(DEMO_ANALYST.email)
  const [password, setPassword] = useState(DEMO_ANALYST.password)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const id = useId()

  if (analyst.status === 'signedIn') return <Navigate to={from} replace />

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await signInAnalyst(email, password)
      // useAnalyst picks up the new session and the redirect above takes over.
    } catch (err) {
      setError(ERRORS[err instanceof SignInError ? err.reason : 'other'])
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-svh flex-col items-center justify-center bg-surface-container px-4 py-8">
      <main className="rise-in w-full max-w-[1040px] rounded-[28px] bg-surface-container-lowest p-6 sm:p-10">
        <div className="grid gap-8 md:grid-cols-2 md:gap-12">
          <div className="flex flex-col">
            <Link to="/" className="w-fit rounded-full" aria-label={`${PRODUCT_NAME} home`}>
              <PauseGuardLogo className="size-12" />
            </Link>
            <h1 className="mt-6 text-headline-l text-on-surface sm:text-[44px] sm:leading-[52px]">Analyst console</h1>
            <p className="mt-3 text-body-l text-on-surface-variant">
              Sign in to {BANK_NAME} fraud operations. RED and AMBER checks from the customer app arrive here in real time.
            </p>
            <ul className="mt-6 hidden flex-col gap-3 text-body-m text-on-surface-variant md:flex">
              <li className="flex items-center gap-3">
                <Sparkle />
                Case files and evidence boxes written by Gemini
              </li>
              <li className="flex items-center gap-3">
                <Icon name="database" className="size-5 text-primary" />
                A realtime queue on Firestore
              </li>
              <li className="flex items-center gap-3">
                <Icon name="lock" className="size-5 text-primary" />
                Firebase Authentication · all data synthetic
              </li>
            </ul>
          </div>

          {analyst.status === 'local' ? (
            <div className="flex flex-col justify-center gap-6">
              <p className="flex gap-3 rounded-lg bg-surface-container px-4 py-3 text-body-m text-on-surface-variant">
                <Icon name="info" className="size-5" />
                Local development: Firebase sign-in is off and the API lets you in as a local analyst.
              </p>
              <Link to={from} className={button('filled', 'md', 'self-end')}>
                Open the console
                <Icon name="arrow_forward" />
              </Link>
            </div>
          ) : (
            <form
              onSubmit={(e) => void submit(e)}
              className="flex flex-col justify-center gap-6 [--field-bg:var(--surface-container-lowest)]"
              aria-describedby={error ? `${id}-error` : undefined}
            >
              <p className="flex gap-3 rounded-lg bg-primary-container px-4 py-3 text-body-m text-on-primary-container">
                <Icon name="info" className="size-5" />
                <span>Demo login is filled in. All customers and cases are synthetic.</span>
              </p>
              <Field htmlFor={`${id}-email`} label="Work email">
                <input
                  id={`${id}-email`}
                  type="email"
                  autoComplete="username"
                  required
                  placeholder=" "
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className={cn(fieldBase, 'h-14')}
                />
              </Field>
              <Field htmlFor={`${id}-password`} label="Password">
                <input
                  id={`${id}-password`}
                  type="password"
                  autoComplete="current-password"
                  required
                  placeholder=" "
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className={cn(fieldBase, 'h-14')}
                />
              </Field>
              {error && (
                <p id={`${id}-error`} role="alert" className="flex items-start gap-2 text-body-m font-medium text-error">
                  <Icon name="error" className="size-5" />
                  {error}
                </p>
              )}
              <div className="flex items-center justify-end gap-2">
                <Link to="/" className={button('text', 'md')}>
                  Back to {PRODUCT_NAME}
                </Link>
                <button type="submit" disabled={busy || analyst.status === 'loading'} className={button('filled', 'md')}>
                  {busy ? 'Signing in…' : 'Sign in'}
                  {busy ? <Icon name="progress_activity" className="animate-spin" /> : <Icon name="login" />}
                </button>
              </div>
            </form>
          )}
        </div>
      </main>
      <p className="mt-4 flex w-full max-w-[1040px] flex-wrap justify-between gap-2 px-6 text-body-s text-on-surface-variant">
        <span>{PRODUCT_NAME} · Google Cloud AI Builder Cup 2026 prototype</span>
        <span>All people, banks and accounts are synthetic</span>
      </p>
    </div>
  )
}
