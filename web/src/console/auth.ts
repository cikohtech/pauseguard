// Analyst sign-in for /console: Firebase email/password, and the API needs the custom claim
// role=analyst (SECURITY_PRIVACY §3). The console runs its own named Firebase app, so the analyst
// session never replaces the customer app's anonymous user (both live in one browser during the
// demo). Locally (no Firebase config, the API on AUTH_DISABLED=true) there is nothing to sign in to.
import type { FirebaseApp } from 'firebase/app'
import type { Auth, User } from 'firebase/auth'
import { useEffect, useState } from 'react'

import { firebaseConfig } from '@/lib/firebase'

/** The public demo analyst (infra/set_analyst_claim.py). All data behind it is synthetic. */
export const DEMO_ANALYST = { email: 'analyst@harbourbank.example', password: 'HarbourDemo2026' }

interface ConsoleFirebase {
  app: FirebaseApp
  auth: Auth
}

let consolePromise: Promise<ConsoleFirebase> | null = null

/** The console's Firebase app and auth, or null when Firebase is off (local dev). */
export function consoleFirebase(): Promise<ConsoleFirebase> | null {
  const config = firebaseConfig
  if (!config) return null
  consolePromise ??= (async () => {
    const [{ initializeApp }, { getAuth }] = await Promise.all([
      import('firebase/app'),
      import('firebase/auth'),
    ])
    const app = initializeApp(config, 'console')
    return { app, auth: getAuth(app) }
  })()
  return consolePromise
}

export async function getAnalystToken(): Promise<string | null> {
  const pending = consoleFirebase()
  if (!pending) return null
  const { auth } = await pending
  await auth.authStateReady()
  return auth.currentUser ? auth.currentUser.getIdToken() : null
}

export class SignInError extends Error {
  readonly reason: 'credentials' | 'notAnalyst' | 'rateLimited' | 'network' | 'other'

  constructor(reason: SignInError['reason']) {
    super(reason)
    this.name = 'SignInError'
    this.reason = reason
  }
}

const isAnalyst = async (user: User) => (await user.getIdTokenResult()).claims.role === 'analyst'

export async function signInAnalyst(email: string, password: string): Promise<void> {
  const pending = consoleFirebase()
  if (!pending) return // local dev: the API lets everyone in as a local analyst
  const { auth } = await pending
  const { signInWithEmailAndPassword, signOut } = await import('firebase/auth')
  let user: User
  try {
    user = (await signInWithEmailAndPassword(auth, email.trim(), password)).user
  } catch (err) {
    const code = (err as { code?: string }).code ?? ''
    if (/invalid-credential|wrong-password|user-not-found|invalid-email/.test(code)) {
      throw new SignInError('credentials')
    }
    if (code.includes('too-many-requests')) throw new SignInError('rateLimited')
    if (code.includes('network')) throw new SignInError('network')
    throw new SignInError('other')
  }
  if (!(await isAnalyst(user))) {
    await signOut(auth)
    throw new SignInError('notAnalyst')
  }
}

export async function signOutAnalyst(): Promise<void> {
  const pending = consoleFirebase()
  if (!pending) return
  const { auth } = await pending
  const { signOut } = await import('firebase/auth')
  await signOut(auth)
}

export type AnalystState =
  | { status: 'loading' }
  | { status: 'local' } // no Firebase config: local dev, auth disabled
  | { status: 'signedOut' }
  | { status: 'signedIn'; email: string }

/** The signed-in analyst, kept current with Firebase (a non-analyst user counts as signed out). */
export function useAnalyst(): AnalystState {
  const [state, setState] = useState<AnalystState>(() =>
    firebaseConfig ? { status: 'loading' } : { status: 'local' },
  )
  useEffect(() => {
    const pending = consoleFirebase()
    if (!pending) return
    let unsubscribe = () => {}
    let cancelled = false
    void (async () => {
      const { auth } = await pending
      const { onIdTokenChanged } = await import('firebase/auth')
      if (cancelled) return
      unsubscribe = onIdTokenChanged(auth, (user) => {
        if (!user) {
          setState({ status: 'signedOut' })
          return
        }
        void isAnalyst(user)
          .then((ok) =>
            setState(ok ? { status: 'signedIn', email: user.email ?? 'analyst' } : { status: 'signedOut' }),
          )
          .catch(() => setState({ status: 'signedOut' }))
      })
    })()
    return () => {
      cancelled = true
      unsubscribe()
    }
  }, [])
  return state
}
