import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/**
 * M3 outlined text field chrome: the floating label and the supporting / error text. The control
 * is the child: give it `fieldBase` (components/m3/styles) and `placeholder=" "` (the label floats
 * when the field has focus or a value). The label sits on `--field-bg` (the surface behind).
 */
export function Field({
  htmlFor,
  label,
  error,
  errorId,
  hint,
  hintId,
  float = false,
  children,
  className,
}: {
  htmlFor: string
  label: string
  error?: string | null
  errorId?: string
  hint?: string
  hintId?: string
  /** Keep the label floated (a <select>, or a field that always has content). */
  float?: boolean
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('relative', className)}>
      {children}
      <label
        htmlFor={htmlFor}
        className={cn(
          'pointer-events-none absolute top-4 left-3 max-w-[calc(100%-1.5rem)] truncate bg-[var(--field-bg,var(--surface))] px-1 text-body-l text-on-surface-variant transition-all duration-150 ease-standard',
          'peer-focus:-top-2 peer-focus:text-body-s peer-focus:text-primary peer-[:not(:placeholder-shown)]:-top-2 peer-[:not(:placeholder-shown)]:text-body-s peer-aria-invalid:text-error',
          float && '-top-2 text-body-s',
        )}
      >
        {label}
      </label>
      {error ? (
        <p id={errorId} className="mt-1 flex items-start gap-1 px-4 text-body-s font-medium text-error">
          {error}
        </p>
      ) : hint ? (
        <p id={hintId} className="mt-1 px-4 text-body-s text-on-surface-variant">
          {hint}
        </p>
      ) : null}
    </div>
  )
}
