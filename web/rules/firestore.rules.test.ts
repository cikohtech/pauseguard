/**
 * Firestore security rules (infra/firestore.rules, SECURITY_PRIVACY §3) against the emulator.
 *
 * Run with `make test-rules`: it starts a throwaway Firestore emulator on its own port and
 * project (infra/firebase.rules-test.json), so the dev emulator's data is never touched.
 * Clients only read; every write goes through the API's service account, which rules don't
 * apply to. These tests model the three kinds of browser client the app has: signed out,
 * the customer app's anonymous user, and an analyst (custom claim role=analyst).
 */
import { readFileSync } from 'node:fs'
import path from 'node:path'

import {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
  type RulesTestContext,
  type RulesTestEnvironment,
} from '@firebase/rules-unit-testing'
import {
  addDoc,
  collection,
  deleteDoc,
  doc,
  getDoc,
  getDocs,
  limit,
  orderBy,
  query,
  setDoc,
  updateDoc,
  where,
  type Firestore,
} from 'firebase/firestore'
import { afterAll, beforeAll, beforeEach, describe, it } from 'vitest'

const RULES = path.resolve(import.meta.dirname, '../../infra/firestore.rules')
const CHECK_ID = 'chk_4f9c2a7b1e0d3c5a8b6e'
const CASE_ID = 'case_7d1e9a0c2b4f6e8a1c3d'

let env: RulesTestEnvironment

// The test contexts hand out the compat Firestore; the modular API takes it at runtime.
const fs = (ctx: RulesTestContext) => ctx.firestore() as unknown as Firestore

beforeAll(async () => {
  env = await initializeTestEnvironment({
    projectId: 'demo-pauseguard-rules',
    firestore: { rules: readFileSync(RULES, 'utf8') },
  })
})

afterAll(async () => {
  await env?.cleanup()
})

beforeEach(async () => {
  await env.clearFirestore()
  await env.withSecurityRulesDisabled(async (ctx) => {
    const db = fs(ctx)
    await setDoc(doc(db, 'checks', CHECK_ID), { customer_id: 'cust_001', status: 'DONE' })
    await setDoc(doc(db, 'checks', 'chk_other'), { customer_id: 'cust_002', status: 'DONE' })
    await setDoc(doc(db, 'personas', 'cust_001'), { display_name: 'Mrs Tan' })
    await setDoc(doc(db, 'cases', CASE_ID), {
      status: 'OPEN',
      verdict: 'RED',
      created_at: new Date('2026-10-11T03:00:00Z'),
    })
    await setDoc(doc(db, 'audit', 'aud_1'), { case_id: CASE_ID, action: 'CASE_OPENED' })
    await setDoc(doc(db, 'watchlist', 'DOMAIN:mas-gov-verify.example'), { type: 'DOMAIN' })
    await setDoc(doc(db, 'feedback', 'fb_1'), { check_id: CHECK_ID, helpful: true })
    await setDoc(doc(db, 'checks_analytics', 'snap_1'), { check_id: CHECK_ID })
  })
})

const signedOut = (): Firestore => fs(env.unauthenticatedContext())
// Firebase anonymous auth: the customer app's user (no custom claims).
const customer = (): Firestore =>
  fs(env.authenticatedContext('anon_uid', { firebase: { sign_in_provider: 'anonymous' } }))
const analyst = (): Firestore =>
  fs(env.authenticatedContext('analyst_uid', { role: 'analyst', email: 'analyst@harbourbank.example' }))
// Signed in with email/password but without the analyst claim.
const plainUser = (): Firestore =>
  fs(env.authenticatedContext('user_uid', { email: 'someone@example.example' }))

// The console queue's live query (console/feed.ts).
const openCases = (db: Firestore) =>
  query(collection(db, 'cases'), where('status', '==', 'OPEN'), orderBy('created_at', 'desc'), limit(100))

const ANALYST_ONLY = ['cases', 'audit', 'watchlist', 'feedback'] as const
const SAMPLE_ID: Record<(typeof ANALYST_ONLY)[number], string> = {
  cases: CASE_ID,
  audit: 'aud_1',
  watchlist: 'DOMAIN:mas-gov-verify.example',
  feedback: 'fb_1',
}

describe('signed out', () => {
  it('reads nothing', async () => {
    const db = signedOut()
    await assertFails(getDoc(doc(db, 'checks', CHECK_ID)))
    await assertFails(getDoc(doc(db, 'personas', 'cust_001')))
    for (const c of ANALYST_ONLY) await assertFails(getDoc(doc(db, c, SAMPLE_ID[c])))
  })

  it('writes nothing', async () => {
    const db = signedOut()
    await assertFails(setDoc(doc(db, 'checks', 'chk_new'), { status: 'DONE' }))
    await assertFails(addDoc(collection(db, 'watchlist'), { type: 'PHONE' }))
  })
})

describe('customer (anonymous auth)', () => {
  it('gets one check by the ID the API returned', async () => {
    await assertSucceeds(getDoc(doc(customer(), 'checks', CHECK_ID)))
  })

  it('cannot list or query checks', async () => {
    const db = customer()
    await assertFails(getDocs(collection(db, 'checks')))
    await assertFails(getDocs(query(collection(db, 'checks'), where('customer_id', '==', 'cust_001'))))
  })

  it('reads the demo personas', async () => {
    const db = customer()
    await assertSucceeds(getDoc(doc(db, 'personas', 'cust_001')))
    await assertSucceeds(getDocs(collection(db, 'personas')))
  })

  it('cannot read cases, the audit log, the watchlist or feedback', async () => {
    const db = customer()
    for (const c of ANALYST_ONLY) {
      await assertFails(getDoc(doc(db, c, SAMPLE_ID[c])))
      await assertFails(getDocs(collection(db, c)))
    }
    await assertFails(getDocs(openCases(db)))
  })

  it('cannot write: a check cannot be turned GREEN from the browser', async () => {
    const db = customer()
    await assertFails(updateDoc(doc(db, 'checks', CHECK_ID), { verdict: 'GREEN' }))
    await assertFails(setDoc(doc(db, 'checks', 'chk_new'), { status: 'DONE', verdict: 'GREEN' }))
    await assertFails(deleteDoc(doc(db, 'checks', CHECK_ID)))
    await assertFails(setDoc(doc(db, 'personas', 'cust_001'), { display_name: 'x' }))
    await assertFails(addDoc(collection(db, 'feedback'), { check_id: CHECK_ID, helpful: false }))
  })
})

describe('analyst (role=analyst)', () => {
  it('runs the console queue query and opens a case', async () => {
    const db = analyst()
    await assertSucceeds(getDocs(openCases(db)))
    await assertSucceeds(getDoc(doc(db, 'cases', CASE_ID)))
  })

  it('reads the audit log, the watchlist and feedback', async () => {
    const db = analyst()
    for (const c of ANALYST_ONLY) {
      await assertSucceeds(getDoc(doc(db, c, SAMPLE_ID[c])))
      await assertSucceeds(getDocs(collection(db, c)))
    }
  })

  it('cannot write: decisions and watchlist entries go through the API (audited)', async () => {
    const db = analyst()
    await assertFails(updateDoc(doc(db, 'cases', CASE_ID), { status: 'CLOSED' }))
    await assertFails(setDoc(doc(db, 'watchlist', 'PHONE:+6580000147'), { type: 'PHONE' }))
    await assertFails(addDoc(collection(db, 'audit'), { action: 'RELEASE' }))
    await assertFails(deleteDoc(doc(db, 'audit', 'aud_1')))
  })
})

describe('signed in without the analyst claim', () => {
  it('is treated like a customer', async () => {
    const db = plainUser()
    await assertSucceeds(getDoc(doc(db, 'checks', CHECK_ID)))
    for (const c of ANALYST_ONLY) await assertFails(getDoc(doc(db, c, SAMPLE_ID[c])))
    await assertFails(getDocs(openCases(db)))
  })

  it('cannot fake the claim with a different role', async () => {
    const db = fs(env.authenticatedContext('u2', { role: 'customer' }))
    await assertFails(getDoc(doc(db, 'cases', CASE_ID)))
  })
})

describe('everything else is denied', () => {
  it('collections the rules do not name', async () => {
    for (const db of [customer(), analyst()]) {
      await assertFails(getDoc(doc(db, 'checks_analytics', 'snap_1')))
      await assertFails(getDocs(collection(db, 'admin')))
    }
  })

  it('subcollections under a readable document', async () => {
    for (const db of [customer(), analyst()]) {
      await assertFails(getDocs(collection(db, 'checks', CHECK_ID, 'events')))
      await assertFails(getDocs(collection(db, 'cases', CASE_ID, 'notes')))
    }
  })
})
