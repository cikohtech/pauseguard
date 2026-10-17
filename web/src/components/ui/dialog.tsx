import * as React from "react"
import { cn } from "@/lib/utils"
import { Icon } from "@/components/icons/Icon"
import { Dialog as DialogPrimitive } from "radix-ui"

// shadcn/ui Dialog, with two additions for the phone mock: `container` portals the dialog into
// the phone screen instead of <body>, and `side="bottom"` makes it a bottom sheet.

function Dialog(props: React.ComponentProps<typeof DialogPrimitive.Root>) {
  return <DialogPrimitive.Root data-slot="dialog" {...props} />
}

function DialogTrigger(props: React.ComponentProps<typeof DialogPrimitive.Trigger>) {
  return <DialogPrimitive.Trigger data-slot="dialog-trigger" {...props} />
}

function DialogClose(props: React.ComponentProps<typeof DialogPrimitive.Close>) {
  return <DialogPrimitive.Close data-slot="dialog-close" {...props} />
}

function DialogContent({
  className,
  children,
  container,
  side = "center",
  closeLabel,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Content> & {
  container?: HTMLElement | null
  side?: "center" | "bottom"
  /** Shows an X button with this accessible name. */
  closeLabel?: string
}) {
  // Inside the phone the overlay is absolute (the phone screen is the positioned parent).
  const position = container ? "absolute" : "fixed"
  return (
    <DialogPrimitive.Portal container={container ?? undefined}>
      <DialogPrimitive.Overlay
        data-slot="dialog-overlay"
        className={cn(
          position,
          "inset-0 z-40 bg-scrim data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 motion-reduce:animate-none"
        )}
      />
      <DialogPrimitive.Content
        data-slot="dialog-content"
        className={cn(
          position,
          "z-50 flex flex-col text-on-surface outline-none motion-reduce:animate-none",
          // M3 bottom sheet (surface-container-low) and basic dialog (surface-container-high, 28px)
          side === "bottom"
            ? "inset-x-0 bottom-0 max-h-[92%] rounded-t-[28px] bg-surface-container-low shadow-e1 data-[state=open]:animate-in data-[state=open]:slide-in-from-bottom data-[state=open]:duration-500 data-[state=open]:ease-[cubic-bezier(0.05,0.7,0.1,1)] data-[state=closed]:animate-out data-[state=closed]:slide-out-to-bottom data-[state=closed]:duration-200"
            : "top-1/2 left-1/2 w-[calc(100%-3rem)] max-w-[400px] -translate-x-1/2 -translate-y-1/2 gap-4 rounded-[28px] bg-surface-container-high p-6 shadow-e3 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-90 data-[state=open]:duration-300 data-[state=open]:ease-[cubic-bezier(0.05,0.7,0.1,1)]",
          className
        )}
        {...props}
      >
        {children}
        {closeLabel && (
          <DialogPrimitive.Close
            aria-label={closeLabel}
            className="ripple absolute top-3 right-3 inline-flex size-12 items-center justify-center rounded-full text-on-surface-variant"
          >
            <Icon name="close" />
          </DialogPrimitive.Close>
        )}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  )
}

function DialogHeader({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="dialog-header" className={cn("flex flex-col gap-2", className)} {...props} />
}

function DialogFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div data-slot="dialog-footer" className={cn("flex flex-col gap-2", className)} {...props} />
  )
}

function DialogTitle({ className, ...props }: React.ComponentProps<typeof DialogPrimitive.Title>) {
  return (
    <DialogPrimitive.Title
      data-slot="dialog-title"
      className={cn("text-headline-s text-on-surface", className)}
      {...props}
    />
  )
}

function DialogDescription({
  className,
  ...props
}: React.ComponentProps<typeof DialogPrimitive.Description>) {
  return (
    <DialogPrimitive.Description
      data-slot="dialog-description"
      className={cn("text-body-m text-on-surface-variant", className)}
      {...props}
    />
  )
}

export {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
}
