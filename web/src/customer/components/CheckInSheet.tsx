import { useEffect, useId, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import { Icon, Sparkle } from '@/components/icons/Icon'
import { LoadingIndicator, Shape } from '@/components/m3/Expressive'
import { Field } from '@/components/m3/Field'
import { button, chip, fieldBase, iconButton } from '@/components/m3/styles'
import { PauseGuardLogo } from '@/components/ShieldMark'
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
  const { t } = useTranslation()
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
    setText(sc.answer)
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
  const textArea = cn(fieldBase, 'resize-none py-4 placeholder:opacity-0 focus:placeholder:opacity-100')

  return (
    <Dialog open={open} onOpenChange={(o) => !analysing && onOpenChange(o)}>
      <DialogContent
        container={container}
        side="bottom"
        closeLabel={analysing ? undefined : t('customer.checkin.close')}
        onEscapeKeyDown={(e) => analysing && e.preventDefault()}
        onInteractOutside={(e) => analysing && e.preventDefault()}
        data-testid="checkin-sheet"
        className="[--field-bg:var(--surface-container-low)]"
      >
        <div aria-hidden="true" className="mx-auto mt-4 h-1 w-8 shrink-0 rounded-full bg-on-surface-variant/40" />
        <div className="flex shrink-0 items-center gap-3.5 px-5 pt-4 pb-3 pr-16">
          <Shape shape="cookie9" className="size-12 text-primary-container">
            <PauseGuardLogo className="size-7" />
          </Shape>
          <div className="flex flex-col">
            <DialogTitle className="text-title-l font-normal">{t('customer.checkin.title')}</DialogTitle>
            <DialogDescription className="flex items-center gap-1 text-body-m text-on-surface-variant">
              <Icon name="timer" className="size-4" />
              {t('customer.checkin.duration')}
            </DialogDescription>
          </div>
        </div>

        {analysing ? (
          <div className="fade-in flex flex-col gap-5 px-5 pt-3 pb-safe" data-testid="analysing">
            <div className="flex items-center gap-4">
              <LoadingIndicator className="size-14" />
              <h3 ref={analysingTitle} tabIndex={-1} className="text-headline-s outline-none">
                {t('customer.analysing.title')}
              </h3>
            </div>
            <StepTicks progress={progress} />
            <p className="flex items-center gap-3 rounded-xl bg-surface-container-highest/70 px-4 py-3 text-body-l text-on-surface">
              <Icon name="lock" fill className="size-5 text-primary" />
              {t('customer.analysing.note')}
            </p>
            <p className="-mt-1 mb-1 flex items-center justify-center gap-1.5 text-body-s text-on-surface-variant">
              <Sparkle className="size-4" />
              {t('customer.analysing.poweredBy')}
            </p>
          </div>
        ) : (
          <>
            <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-4">
              <p className="flex items-start gap-2 text-body-m text-on-surface-variant">
                <Icon name="lock" className="mt-0.5 size-4" />
                {t('customer.checkin.why')}
              </p>

              <button
                type="button"
                onClick={() => void fillDemo()}
                className={chip(false, 'mt-3 min-h-11 rounded-md border-0 bg-tertiary-container px-4 text-on-tertiary-container')}
                aria-describedby={`${id}-demo-hint`}
              >
                <Icon name="wand_stars" />
                {t('customer.checkin.demo')}
              </button>
              <span id={`${id}-demo-hint`} className="sr-only">
                {t('customer.checkin.demoHint')}
              </span>

              <fieldset className="mt-5 min-w-0">
                <legend className="text-headline-s text-on-surface">{question.text}</legend>
                <div className="mt-4 flex flex-wrap gap-2">
                  {question.quick_replies.map((q) => {
                    const on = reply === q
                    return (
                      <label
                        key={q}
                        className={chip(
                          on,
                          'min-h-11 cursor-pointer has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-[var(--focus)] has-[:focus-visible]:outline-solid',
                          // padding shrinks on the left to make room for the check (M3 filter chip)
                        )}
                        style={on ? { paddingLeft: 10 } : undefined}
                      >
                        <input
                          type="radio"
                          name={`${id}-reply`}
                          value={q}
                          checked={on}
                          onChange={() => setReply(q)}
                          className="sr-only"
                        />
                        {on && <Icon name="check" className="!size-[18px]" />}
                        <span className="text-[15px]">{q}</span>
                      </label>
                    )
                  })}
                </div>
              </fieldset>

              <Field htmlFor={`${id}-text`} label={t('customer.checkin.textLabel')} className="mt-6">
                <textarea
                  id={`${id}-text`}
                  rows={2}
                  maxLength={4000}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder={t('customer.checkin.textPlaceholder')}
                  className={textArea}
                />
              </Field>

              {items.length > 0 && (
                <ul className="mt-5 flex flex-wrap gap-3" aria-label={t('customer.checkin.add')}>
                  {items.map((it, i) => (
                    <li key={`${it.file.name}-${i}`} className="pop-in relative">
                      {it.preview ? (
                        <img
                          src={it.preview}
                          alt={it.file.name}
                          className="size-24 rounded-lg border border-outline-variant object-cover object-top"
                        />
                      ) : (
                        <span className="flex size-24 flex-col items-center justify-center gap-1.5 rounded-lg bg-surface-container-highest px-2 text-center">
                          <Icon name="picture_as_pdf" className="size-7 text-error" />
                          <span className="line-clamp-2 text-label-s break-all text-on-surface-variant">{it.file.name}</span>
                        </span>
                      )}
                      <button
                        type="button"
                        onClick={() => removeItem(i)}
                        aria-label={t('customer.checkin.remove', { name: it.file.name })}
                        className="absolute -top-2 -right-2 inline-flex size-7 items-center justify-center rounded-full bg-inverse-surface text-inverse-on-surface shadow-e1 before:absolute before:-inset-2 before:content-['']"
                      >
                        <Icon name="close" className="size-4" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              {pasted !== null && (
                <div className="rise-in mt-6">
                  <Field htmlFor={`${id}-paste`} label={t('customer.checkin.pasteLabel')}>
                    <textarea
                      id={`${id}-paste`}
                      rows={4}
                      maxLength={4000}
                      value={pasted}
                      onChange={(e) => setPasted(e.target.value)}
                      placeholder={t('customer.checkin.pastePlaceholder')}
                      className={cn(textArea, 'pr-12 text-body-m')}
                    />
                    <button
                      type="button"
                      onClick={() => setPasted(null)}
                      aria-label={t('customer.checkin.remove', { name: t('customer.checkin.pastedItem') })}
                      className={iconButton('standard', 'absolute top-1 right-1 size-11')}
                    >
                      <Icon name="close" className="!size-5" />
                    </button>
                  </Field>
                </div>
              )}

              <div className="mt-5 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => fileInput.current?.click()}
                  disabled={full}
                  aria-describedby={`${id}-add-hint`}
                  className={button('outlined', 'md', 'min-h-12 px-5')}
                >
                  <Icon name="add_photo_alternate" />
                  {t('customer.checkin.add')}
                </button>
                {pasted === null && (
                  <button
                    type="button"
                    onClick={() => setPasted('')}
                    disabled={full}
                    className={button('outlined', 'md', 'min-h-12 px-5')}
                  >
                    <Icon name="content_paste" />
                    {t('customer.checkin.paste')}
                  </button>
                )}
              </div>
              <p id={`${id}-add-hint`} className="mt-2 px-1 text-body-s text-on-surface-variant">
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
                <p
                  ref={errorLine}
                  role="alert"
                  className="mt-4 flex items-start gap-2 rounded-lg bg-error-container px-4 py-3 text-body-m font-medium text-on-error-container"
                >
                  <Icon name="error" className="size-5" />
                  {error}
                </p>
              )}
            </div>
            <div className="shrink-0 border-t border-outline-variant/60 px-5 pt-3 pb-safe">
              <p
                id={`${id}-consent`}
                data-testid="checkin-consent"
                className="mb-3 flex items-start gap-2 text-body-s text-on-surface-variant"
              >
                <Icon name="encrypted" className="size-4" />
                {t('customer.checkin.consent')}
              </p>
              <button
                type="button"
                onClick={() => void submit()}
                aria-describedby={`${id}-consent`}
                className={bigButton()}
              >
                <Icon name="verified_user" />
                {t('customer.checkin.submit')}
              </button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
