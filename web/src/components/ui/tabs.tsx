import * as React from "react"
import { cn } from "@/lib/utils"
import { Tabs as TabsPrimitive } from "radix-ui"

// shadcn/ui Tabs, styled as M3 primary tabs (the console's case view). Radix gives the arrow-key
// navigation and the tab/tabpanel roles. On a narrow screen the tabs wrap onto a second row
// instead of scrolling sideways (every tab stays visible and tappable).

function Tabs({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Root>) {
  return <TabsPrimitive.Root data-slot="tabs" className={cn("flex flex-col", className)} {...props} />
}

function TabsList({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      className={cn("flex flex-wrap gap-x-1 border-b border-outline-variant", className)}
      {...props}
    />
  )
}

function TabsTrigger({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(
        "ripple relative -mb-px inline-flex min-h-12 shrink-0 items-center gap-2 rounded-t-sm px-4 text-title-s text-on-surface-variant transition-colors focus-visible:outline-offset-[-3px] data-[state=active]:text-primary [&_svg]:size-5 [&_svg]:shrink-0",
        // the active indicator: 3px, rounded on top, the width of the label
        "before:absolute before:inset-x-3 before:bottom-0 before:h-[3px] before:rounded-t-[3px] before:bg-primary before:opacity-0 before:transition-opacity data-[state=active]:before:opacity-100",
        className
      )}
      {...props}
    />
  )
}

function TabsContent({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      data-slot="tabs-content"
      className={cn("rounded-lg", className)}
      {...props}
    />
  )
}

export { Tabs, TabsContent, TabsList, TabsTrigger }
