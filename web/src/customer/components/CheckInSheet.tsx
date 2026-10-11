import {
  ClipboardPaste,
  FileText,
  ImagePlus,
  Lock,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import { usePortalContainer } from '@/customer/portal'
import { StepTicks } from '@/customer/components/StepTicks'
import type { DemoPersona } from '@/customer/demo'
import { loadDemoFile, loadDemoText } from '@/customer/demo'
import { errorKey } from '@/customer/errors'
import type { EvidenceSource } from '@/customer/evidence'
import { advanceByTime, allDone, applyEvent, initialProgress } from '@/customer/progress'
import { useSession } from '@/customer/session'
import { bigButton } from '@/customer/styles'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import {
  api,
  ApiError,
  MAX_EVIDENCE_ITEMS,
  MAX_UPLOAD_BYTES,
  pollResult,
  UPLOAD_TYPES,
  uploadEvidence,
  watchCheckEvents,
  type CheckResult,
  type UploadContentType,
} from '@/lib/api'
import { cn } from '@/lib/utils'

interface Item {
  file: File
  preview: string | null // object URL for images
  uri: string | null // gcs_uri once uploaded (reused if the customer has to retry)
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

/**
 * Screen 5 + 6: the check-in bottom sheet ("Quick safety check"): the question, quick replies,
 * free text, uploads and pasted text; then the analysing step ticks until the verdict.
 */
export function CheckInSheet({
  open,
  onOpenChange,
  onError,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onError: (key: string) => void
}) {
  const { t, i18n } = useTranslation()
  const id = useId()
  const navigate = useNavigate()
  const container = usePortalContainer()
  const { check, updateCheck, persona } = useSession()
  const fileInput = useRef<HTMLInputElement>(null)
  const analysingTitle = useRef<HTMLHeadingElement>(null)
  const errorLine = useRef<HTMLParagraphElement>(null)

  const [phase, setPhase] = useState<'answer' | 'analysing'>('answer')
  const [reply, setReply] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [items, setItems] = useState<Item[]>([])
  const [pasted, setPasted] = useState<string | null>(null) // null: the paste box is closed
  const [error, setError] = useState<string | null>(null)
  const [progress, setProgress] = useState(initialProgress)

  useEffect(() => {
    if (phase === 'analysing') analysingTitle.current?.focus()
  }, [phase])

  // On a phone the message sits below the fold of the sheet: bring it into view.
  useEffect(() => {
    if (error) errorLine.current?.scrollIntoView?.({ block: 'nearest' })
  }, [error])

  if (!check?.question) return null
  const question = check.question
  const p = persona as DemoPersona
  const hasPaste = !!pasted?.trim()
  const count = items.length + (hasPaste ? 1 : 0)
  // an open paste box takes one of the 3 evidence slots
  const full = items.length + (pasted !== null ? 1 : 0) >= MAX_EVIDENCE_ITEMS

  const addFiles = (files: Iterable<File>) => {
    setError(null)
    const next: Item[] = []
    for (const file of files) {
      if (!UPLOAD_TYPES.includes(file.type as UploadContentType)) {
        setError(t('customer.checkin.errors.type'))
        continue
      }
      if (file.size > MAX_UPLOAD_BYTES) {
        setError(t('customer.checkin.errors.size'))
        continue
      }
      if (items.length + next.length + (pasted !== null ? 1 : 0) >= MAX_EVIDENCE_ITEMS) {
        setError(t('customer.checkin.errors.max'))
        break
      }
      next.push({ file, preview: file.type.startsWith('image/') ? URL.createObjectURL(file) : null, uri: null })
    }
    if (next.length) setItems((cur) => [...cur, ...next])
  }

  const removeItem = (i: number) =>
    setItems((cur) => {
      const gone = cur[i]
      if (gone?.preview) URL.revokeObjectURL(gone.preview)
      return cur.filter((_, j) => j !== i)
    })

  const fillDemo = async () => {
    const sc = p.scenario
    setError(null)
    setReply(question.quick_replies[sc.quickReplyIndex] ?? null)
    setText(sc.answer[i18n.language === 'zh' ? 'zh' : 'en'])
    try {
      if (sc.evidence && !items.some((it) => it.file.name === sc.evidence!.name)) {
        addFiles([await loadDemoFile(sc.evidence)])
      }
      if (sc.pastedFile) setPasted(await loadDemoText(sc.pastedFile))
    } catch {
      setError(t('customer.errors.generic'))
    }
  }

  const submit = async () => {
    if (!reply && !text.trim() && count === 0) {
      setError(t('customer.checkin.errors.needAnswer'))
      return
    }
    setError(null)
    setProgress(initialProgress())
    setPhase('analysing')
    const started = Date.now()
    let stopEvents = () => {}
    let timer: ReturnType<typeof setInterval> | undefined

    try {
      // 1. Uploads: sign, then PUT the bytes (API_SPEC "POST /uploads/sign").
      const uploaded = [...items]
      for (const [i, it] of uploaded.entries()) {
        if (it.uri) continue
        try {
          const uri = await uploadEvidence(check.id, it.file, it.file.name, it.file.type as UploadContentType)
          uploaded[i] = { ...it, uri }
        } catch (err) {
          setItems(uploaded)
          throw Object.assign(new Error('upload failed', { cause: err }), { key: 'upload', file: it.file.name })
        }
      }
      setItems(uploaded)

      // 2. Progress: SSE step ticks, or a timer if the stream can't be opened.
      stopEvents = await watchCheckEvents(
        check.id,
        (ev) => setProgress((cur) => applyEvent(cur, ev)),
        () => {
          timer ??= setInterval(
            () => setProgress((cur) => advanceByTime(cur, Date.now() - started)),
            300,
          )
        },
      )

      // 3. The answer. The response arrives at the orchestrator's `done` event.
      const msg = {
        text: text.trim() || undefined,
        quick_reply: reply ?? undefined,
        evidence_uris: uploaded.map((it) => it.uri!),
        pasted_text: hasPaste ? pasted!.trim() : undefined,
      }
      let result: CheckResult | null
      try {
        result = await api.sendMessage(check.id, msg)
      } catch (err) {
        // The request may have been lost while the analysis goes on: read the check instead.
        if (!(err instanceof ApiError) || err.status === 0 || err.status >= 500 || err.status === 409) {
          result = await pollResult(check.id)
          if (!result) throw err
        } else {
          throw err
        }
      }

      setProgress(allDone())
      await sleep(500)
      const evidence: EvidenceSource[] = [
        ...uploaded.map((it): EvidenceSource =>
          it.preview
            ? { kind: 'image', name: it.file.name, url: it.preview }
            : { kind: 'pdf', name: it.file.name },
        ),
        ...(hasPaste ? [{ kind: 'text' as const, text: pasted!.trim() }] : []),
      ]
      updateCheck({ result, evidence })
      navigate('/app/verdict')
    } catch (err) {
      setPhase('answer')
      const upload = err as { key?: string; file?: string }
      if (upload.key === 'upload') {
        setError(t('customer.checkin.errors.upload', { name: upload.file }))
      } else {
        onError(errorKey(err))
        onOpenChange(false)
      }
    } finally {
      stopEvents()
      if (timer) clearInterval(timer)
    }
  }

  const analysing = phase === 'analysing'
  const chip = (checked: boolean) =>
    cn(
      'inline-flex min-h-11 cursor-pointer items-center rounded-full border px-4 text-[15px] font-medium transition-colors has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/50',
      checked ? 'border-primary bg-primary text-primary-foreground' : 'border-input bg-card hover:bg-muted',
    )

  return (
    <Dialog open={open} onOpenChange={(o) => !analysing && onOpenChange(o)}>
      <DialogContent
        container={container}
        side="bottom"
        closeLabel={analysing ? undefined : t('customer.checkin.close')}
        onEscapeKeyDown={(e) => analysing && e.preventDefault()}
        onInteractOutside={(e) => analysing && e.preventDefault()}
        data-testid="checkin-sheet"
      >
        <div aria-hidden="true" className="mx-auto mt-2.5 h-1.5 w-10 shrink-0 rounded-full bg-border" />
        <div className="flex shrink-0 items-center gap-3 px-5 pt-3 pb-3">
          <span className="inline-flex size-11 items-center justify-center rounded-full bg-primary-soft text-primary">
            <ShieldCheck aria-hidden="true" className="size-6" />
          </span>
          <div className="flex flex-col">
            <DialogTitle>{t('customer.checkin.title')}</DialogTitle>
            <DialogDescription>{t('customer.checkin.duration')}</DialogDescription>
          </div>
        </div>

        {analysing ? (
          <div className="flex flex-col gap-4 px-5 pt-2 pb-safe" data-testid="analysing">
            <h3 ref={analysingTitle} tabIndex={-1} className="text-[19px] font-semibold outline-none">
              {t('customer.analysing.title')}
            </h3>
            <StepTicks progress={progress} />
            <p className="flex items-center gap-2 rounded-xl bg-muted px-3.5 py-3 text-[15px] text-muted-foreground">
              <Lock aria-hidden="true" className="size-4 shrink-0" />
              {t('customer.analysing.note')}
            </p>
          </div>
        ) : (
          <>
            <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-4">
              <p className="text-sm text-muted-foreground">{t('customer.checkin.why')}</p>

              <button
                type="button"
                onClick={() => void fillDemo()}
                className="mt-3 inline-flex min-h-11 items-center gap-2 rounded-full border border-dashed border-primary/50 px-4 text-sm font-semibold text-primary outline-none hover:bg-primary-soft focus-visible:ring-3 focus-visible:ring-ring/50"
                aria-describedby={`${id}-demo-hint`}
              >
                <Sparkles aria-hidden="true" className="size-4" />
                {t('customer.checkin.demo')}
              </button>
              <span id={`${id}-demo-hint`} className="sr-only">
                {t('customer.checkin.demoHint')}
              </span>

              <fieldset className="mt-4 min-w-0">
                <legend className="text-[18px] leading-snug font-semibold">{question.text}</legend>
                <div className="mt-3 flex flex-wrap gap-2">
                  {question.quick_replies.map((q) => (
                    <label key={q} className={chip(reply === q)}>
                      <input
                        type="radio"
                        name={`${id}-reply`}
                        value={q}
                        checked={reply === q}
                        onChange={() => setReply(q)}
                        className="sr-only"
                      />
                      {q}
                    </label>
                  ))}
                </div>
              </fieldset>

              <label htmlFor={`${id}-text`} className="mt-5 mb-1.5 block text-[15px] font-medium">
                {t('customer.checkin.textLabel')}
              </label>
              <textarea
                id={`${id}-text`}
                rows={2}
                maxLength={4000}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder={t('customer.checkin.textPlaceholder')}
                className="block w-full resize-none rounded-xl border border-input bg-card px-3.5 py-3 text-[16px] outline-none placeholder:text-muted-foreground/80 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30"
              />

              {items.length > 0 && (
                <ul className="mt-4 flex flex-wrap gap-3" aria-label={t('customer.checkin.add')}>
                  {items.map((it, i) => (
                    <li key={`${it.file.name}-${i}`} className="relative">
                      {it.preview ? (
                        <img
                          src={it.preview}
                          alt={it.file.name}
                          className="size-20 rounded-xl border border-border object-cover object-top"
                        />
                      ) : (
                        <span className="flex size-20 flex-col items-center justify-center gap-1 rounded-xl border border-border bg-muted px-1.5 text-center">
                          <FileText aria-hidden="true" className="size-6 text-muted-foreground" />
                          <span className="line-clamp-2 text-[11px] leading-tight break-all">{it.file.name}</span>
                        </span>
                      )}
                      <button
                        type="button"
                        onClick={() => removeItem(i)}
                        aria-label={t('customer.checkin.remove', { name: it.file.name })}
                        className="absolute -top-2 -right-2 inline-flex size-7 items-center justify-center rounded-full bg-foreground text-background shadow outline-none before:absolute before:-inset-2 before:content-[''] focus-visible:ring-3 focus-visible:ring-ring/50"
                      >
                        <X aria-hidden="true" className="size-4" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              {pasted !== null && (
                <div className="mt-4">
                  <div className="mb-1.5 flex items-center justify-between">
                    <label htmlFor={`${id}-paste`} className="text-[15px] font-medium">
                      {t('customer.checkin.pasteLabel')}
                    </label>
                    <button
                      type="button"
                      onClick={() => setPasted(null)}
                      aria-label={t('customer.checkin.remove', { name: t('customer.checkin.pastedItem') })}
                      className="inline-flex size-11 items-center justify-center rounded-full text-muted-foreground outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
                    >
                      <X aria-hidden="true" className="size-5" />
                    </button>
                  </div>
                  <textarea
                    id={`${id}-paste`}
                    rows={4}
                    maxLength={4000}
                    value={pasted}
                    onChange={(e) => setPasted(e.target.value)}
                    placeholder={t('customer.checkin.pastePlaceholder')}
                    className="block w-full rounded-xl border border-input bg-card px-3.5 py-3 text-[15px] outline-none placeholder:text-muted-foreground/80 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30"
                  />
                </div>
              )}

              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => fileInput.current?.click()}
                  disabled={full}
                  aria-describedby={`${id}-add-hint`}
                  className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-input bg-card px-3.5 text-[15px] font-medium outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50"
                >
                  <ImagePlus aria-hidden="true" className="size-5 text-primary" />
                  {t('customer.checkin.add')}
                </button>
                {pasted === null && (
                  <button
                    type="button"
                    onClick={() => setPasted('')}
                    disabled={full}
                    className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-input bg-card px-3.5 text-[15px] font-medium outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50"
                  >
                    <ClipboardPaste aria-hidden="true" className="size-5 text-primary" />
                    {t('customer.checkin.paste')}
                  </button>
                )}
              </div>
              <p id={`${id}-add-hint`} className="mt-1.5 text-[13px] text-muted-foreground">
                {t('customer.checkin.addHint')}
              </p>
              <input
                ref={fileInput}
                type="file"
                accept={UPLOAD_TYPES.join(',')}
                multiple
                tabIndex={-1}
                aria-hidden="true"
                className="hidden"
                onChange={(e) => {
                  addFiles(e.target.files ?? [])
                  e.target.value = '' // allow picking the same file again
                }}
              />
              {error && (
                <p ref={errorLine} role="alert" className="mt-3 text-[15px] font-medium text-destructive">
                  {error}
                </p>
              )}
            </div>
            <div className="shrink-0 border-t border-border px-5 pt-3 pb-safe">
              <p
                id={`${id}-consent`}
                data-testid="checkin-consent"
                className="mb-2.5 flex items-start gap-2 text-[13px] leading-snug text-muted-foreground"
              >
                <Lock aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
                {t('customer.checkin.consent')}
              </p>
              <button
                type="button"
                onClick={() => void submit()}
                aria-describedby={`${id}-consent`}
                className={bigButton()}
              >
                {t('customer.checkin.submit')}
              </button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
