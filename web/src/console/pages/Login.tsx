import { ArrowRight, Info, LockKeyhole } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'

import { DEMO_ANALYST, SignInError, signInAnalyst, type AnalystState } from '@/console/auth'
import { useConsoleTitle } from '@/console/title'
import { ShieldMark } from '@/components/ShieldMark'
import { Input } from '@/components/ui/input'
import { BANK_NAME } from '@/lib/product'

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
    <div className="flex min-h-svh flex-col bg-background">
      <header className="flex items-center px-6 py-4">
        <Link to="/" className="rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring/50" aria-label="PauseGuard home">
          <ShieldMark />
        </Link>
      </header>
      <main className="flex flex-1 items-start justify-center px-4 pt-[8vh] pb-10">
        <div className="w-full max-w-sm">
          <div className="mb-6 flex flex-col items-center text-center">
            <span className="mb-3 inline-flex size-12 items-center justify-center rounded-2xl bg-primary-soft text-primary">
              <LockKeyhole aria-hidden="true" className="size-6" />
            </span>
            <h1 className="text-2xl font-semibold tracking-tight">Analyst console</h1>
            <p className="mt-1 text-sm text-muted-foreground">{BANK_NAME} fraud operations</p>
          </div>

          {analyst.status === 'local' ? (
            <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
              <p className="text-sm text-muted-foreground">
                Local development: Firebase sign-in is off and the API lets you in as a local
                analyst.
              </p>
              <Link
                to={from}
                className="mt-4 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-primary px-4 font-semibold text-primary-foreground outline-none hover:bg-brand-deep focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                Open the console
                <ArrowRight aria-hidden="true" className="size-4" />
              </Link>
            </div>
          ) : (
            <form
              onSubmit={(e) => void submit(e)}
              className="flex flex-col gap-4 rounded-2xl border border-border bg-card p-6 shadow-sm"
              aria-describedby={error ? `${id}-error` : undefined}
            >
              <p className="flex gap-2 rounded-lg bg-primary-soft px-3 py-2.5 text-sm text-secondary-foreground">
                <Info aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                <span>Demo login is filled in. All customers and cases are synthetic.</span>
              </p>
              <div className="flex flex-col gap-1.5">
                <label htmlFor={`${id}-email`} className="text-sm font-medium">
                  Work email
                </label>
                <Input
                  id={`${id}-email`}
                  type="email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor={`${id}-password`} className="text-sm font-medium">
                  Password
                </label>
                <Input
                  id={`${id}-password`}
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              {error && (
                <p id={`${id}-error`} role="alert" className="text-sm font-medium text-verdict-red-ink">
                  {error}
                </p>
              )}
              <button
                type="submit"
                disabled={busy || analyst.status === 'loading'}
                className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-primary px-4 font-semibold text-primary-foreground outline-none transition-colors hover:bg-brand-deep focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-60"
              >
                {busy ? 'Signing in…' : 'Sign in'}
                {!busy && <ArrowRight aria-hidden="true" className="size-4" />}
              </button>
            </form>
          )}
        </div>
      </main>
    </div>
  )
}
