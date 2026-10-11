import { LayoutDashboard, ListChecks, LogOut, ShieldBan } from 'lucide-react'
import { useEffect } from 'react'
import { Navigate, NavLink, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { Toaster } from 'sonner'

import { useAnalyst, signOutAnalyst, type AnalystState } from '@/console/auth'
import { Dashboard } from '@/console/pages/Dashboard'
import { Login } from '@/console/pages/Login'
import { QueuePage } from '@/console/pages/QueuePage'
import { Watchlist } from '@/console/pages/Watchlist'
import { ShieldMark } from '@/components/ShieldMark'
import { Skeleton } from '@/components/ui/skeleton'
import { BANK_NAME } from '@/lib/product'
import { cn } from '@/lib/utils'

// /console: the bank side (UI_SPEC Area 2). Desktop first; below 1024 px the queue and the case
// are shown one at a time so the demo login still works on a phone.

export function ConsoleApp() {
  const analyst = useAnalyst()
  useEffect(() => {
    const previous = document.documentElement.lang
    document.documentElement.lang = 'en' // the console is English only
    return () => {
      document.documentElement.lang = previous
    }
  }, [])
  return (
    <>
      <Routes>
        <Route path="login" element={<Login analyst={analyst} />} />
        <Route element={<RequireAnalyst analyst={analyst} />}>
          <Route index element={<QueuePage />} />
          <Route path="cases/:caseId" element={<QueuePage />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="watchlist" element={<Watchlist />} />
          <Route path="*" element={<Navigate to="/console" replace />} />
        </Route>
      </Routes>
      <Toaster position="top-right" closeButton toastOptions={{ className: 'font-sans' }} />
    </>
  )
}

function RequireAnalyst({ analyst }: { analyst: AnalystState }) {
  const location = useLocation()
  if (analyst.status === 'loading') {
    return (
      <div className="flex min-h-svh flex-col" aria-busy="true">
        <div className="h-14 border-b border-border bg-card" />
        <div className="grid flex-1 gap-4 p-6 lg:grid-cols-[360px_1fr]">
          <Skeleton className="h-64" />
          <Skeleton className="h-96" />
        </div>
      </div>
    )
  }
  if (analyst.status === 'signedOut') {
    return <Navigate to="/console/login" replace state={{ from: location.pathname }} />
  }
  return <ConsoleLayout analyst={analyst} />
}

const NAV = [
  { to: '/console', label: 'Queue', icon: ListChecks, end: false },
  { to: '/console/dashboard', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/console/watchlist', label: 'Watchlist', icon: ShieldBan, end: true },
] as const

function ConsoleLayout({ analyst }: { analyst: AnalystState }) {
  const { pathname } = useLocation()
  const queueActive = pathname === '/console' || pathname.startsWith('/console/cases')
  return (
    <div className="flex h-svh flex-col bg-background">
      <a
        href="#console-main"
        className="sr-only z-50 rounded-md bg-card px-3 py-2 focus:not-sr-only focus:absolute focus:top-2 focus:left-2"
      >
        Skip to content
      </a>
      <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-card px-3 sm:px-5">
        <NavLink to="/" className="rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring/50" aria-label="PauseGuard home">
          <ShieldMark />
        </NavLink>
        <span className="hidden text-sm text-muted-foreground md:inline">
          {BANK_NAME} · Fraud operations
        </span>
        <nav aria-label="Console" className="ml-auto flex items-center gap-0.5 sm:ml-6 md:ml-8">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              aria-current={to === '/console' && queueActive ? 'page' : undefined}
              className={({ isActive }) =>
                cn(
                  'inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 sm:px-3',
                  (to === '/console' ? queueActive : isActive)
                    ? 'bg-primary-soft text-primary'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                )
              }
            >
              <Icon aria-hidden="true" className="size-4" />
              <span className="hidden sm:inline">{label}</span>
              <span className="sr-only sm:hidden">{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="ml-auto hidden items-center gap-2 text-sm lg:flex">
          {analyst.status === 'signedIn' ? (
            <span className="text-muted-foreground">{analyst.email}</span>
          ) : (
            <span className="rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground">
              Local dev · sign-in off
            </span>
          )}
        </div>
        {analyst.status === 'signedIn' && (
          <button
            type="button"
            onClick={() => void signOutAnalyst()}
            className="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium text-muted-foreground outline-none hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 lg:ml-0"
          >
            <LogOut aria-hidden="true" className="size-4" />
            <span className="hidden sm:inline">Sign out</span>
            <span className="sr-only sm:hidden">Sign out</span>
          </button>
        )}
      </header>
      <main id="console-main" className="min-h-0 flex-1">
        <Outlet />
      </main>
    </div>
  )
}
