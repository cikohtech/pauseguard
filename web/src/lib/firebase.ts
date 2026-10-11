// Firebase Auth for the web app. In cloud the API needs a Firebase ID token on every customer
// call (anonymous sign-in is enough, API_SPEC "Auth"). Locally the API runs with
// AUTH_DISABLED=true and VITE_FIREBASE_CONFIG_JSON is "{}", so no token is sent.
// The SDK is imported lazily, so a local build never loads it.
import type { Auth } from 'firebase/auth'

export type FirebaseConfig = {
  apiKey: string
  authDomain?: string
  projectId?: string
  appId?: string
}

function readConfig(): FirebaseConfig | null {
  try {
    const raw: unknown = JSON.parse(import.meta.env.VITE_FIREBASE_CONFIG_JSON ?? '{}')
    if (raw && typeof raw === 'object' && 'apiKey' in raw && typeof raw.apiKey === 'string') {
      return raw as FirebaseConfig
    }
  } catch {
    // A malformed value behaves like no config: local dev without auth.
  }
  return null
}

const config = readConfig()
/** The web config, or null when Firebase is off (local dev with AUTH_DISABLED=true). */
export const firebaseConfig = config
let authPromise: Promise<Auth> | null = null

export const firebaseEnabled = config !== null

export function getFirebaseAuth(): Promise<Auth> | null {
  if (!config) return null
  authPromise ??= (async () => {
    const [{ initializeApp }, { getAuth }] = await Promise.all([
      import('firebase/app'),
      import('firebase/auth'),
    ])
    return getAuth(initializeApp(config))
  })()
  return authPromise
}

let anonymousSignIn: Promise<unknown> | null = null

/** The ID token for API calls: the signed-in user's, else an anonymous customer's. */
export async function getIdToken(): Promise<string | null> {
  const pending = getFirebaseAuth()
  if (!pending) return null
  const auth = await pending
  await auth.authStateReady()
  if (!auth.currentUser) {
    anonymousSignIn ??= import('firebase/auth').then(({ signInAnonymously }) =>
      signInAnonymously(auth),
    )
    try {
      await anonymousSignIn
    } catch (err) {
      anonymousSignIn = null // let the next call retry
      throw err
    }
  }
  return auth.currentUser ? auth.currentUser.getIdToken() : null
}
