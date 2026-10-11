import { useCallback, useMemo, useState, type ReactNode } from 'react'

import { findPersona } from '@/customer/demo'
import {
  SessionContext,
  type CheckState,
  type Outcome,
  type SentTransfer,
  type Session,
} from '@/customer/session'
import type { Transfer } from '@/lib/api'

const STORAGE_KEY = 'pauseguard.persona'

function storedPersona(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

export function SessionProvider({
  children,
  initial,
}: {
  children: ReactNode
  /** Start state (tests and deep links): a persona, and optionally a transfer and its check. */
  initial?: { personaId?: string; transfer?: Transfer; check?: CheckState }
}) {
  const [personaId, setPersonaId] = useState<string | null>(
    () => initial?.personaId ?? storedPersona(),
  )
  const [transfer, setTransfer] = useState<Transfer | null>(initial?.transfer ?? null)
  const [check, setCheckState] = useState<CheckState | null>(initial?.check ?? null)
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const [sentByPersona, setSent] = useState<Record<string, SentTransfer[]>>({})

  // Image previews are object URLs: free the ones the next check no longer shows.
  const setCheck = useCallback(
    (c: CheckState | null) =>
      setCheckState((prev) => {
        const keep = new Set(c?.evidence.map((ev) => (ev.kind === 'image' ? ev.url : '')))
        for (const ev of prev?.evidence ?? []) {
          if (ev.kind === 'image' && !keep.has(ev.url)) URL.revokeObjectURL(ev.url)
        }
        return c
      }),
    [],
  )

  const resetFlow = useCallback(() => {
    setTransfer(null)
    setCheck(null)
    setOutcome(null)
  }, [setCheck])

  const value = useMemo<Session>(
    () => ({
      persona: findPersona(personaId),
      choosePersona: (id) => {
        try {
          sessionStorage.setItem(STORAGE_KEY, id)
        } catch {
          // private mode: the persona just won't survive a reload
        }
        setPersonaId(id)
        resetFlow()
      },
      transfer,
      setTransfer,
      check,
      setCheck,
      updateCheck: (patch) => setCheckState((prev) => (prev ? { ...prev, ...patch } : prev)),
      outcome,
      setOutcome,
      sent: (personaId && sentByPersona[personaId]) || [],
      recordSent: (t) => {
        if (!personaId) return
        setSent((s) => ({ ...s, [personaId]: [{ transfer: t, at: new Date() }, ...(s[personaId] ?? [])] }))
      },
      resetFlow,
    }),
    [personaId, transfer, check, setCheck, outcome, sentByPersona, resetFlow],
  )

  return <SessionContext value={value}>{children}</SessionContext>
}
