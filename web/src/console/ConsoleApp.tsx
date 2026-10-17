import { DropdownMenu } from 'radix-ui'
import { useEffect, useId, useState, type FormEvent, type ReactNode } from 'react'
import { Navigate, NavLink, Outlet, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { Toaster } from 'sonner'

import { useAnalyst, signOutAnalyst, type AnalystState } from '@/console/auth'
import { Dashboard } from '@/console/pages/Dashboard'
import { Login } from '@/console/pages/Login'
import { QueuePage } from '@/console/pages/QueuePage'
import { Watchlist } from '@/console/pages/Watchlist'
import { IconSetContext } from '@/components/icons/context'
import { Icon, Sparkle, type IconName } from '@/components/icons/Icon'
import { OUTLINED } from '@/components/icons/outlined'
import { iconButton } from '@/components/m3/styles'
import { PauseGuardLogo } from '@/components/ShieldMark'
import { Skeleton } from '@/components/ui/skeleton'
import { BANK_NAME, PRODUCT_NAME } from '@/lib/product'
import { cn } from '@/lib/utils'

// /console: the bank side (UI_SPEC Area 2), in the Google Cloud console's design language (GM3):
// a top app bar with search, a navigation drawer, and the work on a white rounded panel. Desktop
// first; below 1024 px the queue and the case are shown one at a time, and below 768 px the
// drawer becomes a row of tabs under the bar, so the demo login still works on a phone.

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
    <IconSetContext value={OUTLINED}>
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
      {/* M3 snackbars: inverse surface, bottom left (where Google products put them) */}
      <Toaster
        position="bottom-left"
        closeButton
        toastOptions={{
          unstyled: true,
          classNames: {
            toast:
              'font-sans flex w-[min(100vw-2rem,420px)] items-center gap-3 rounded-xs bg-inverse-surface py-3 pr-10 pl-4 text-inverse-on-surface shadow-e3',
            title: 'text-body-m font-medium',
            description: 'text-body-s opacity-80',
            actionButton: 'ml-auto shrink-0 rounded-full px-3 py-2 text-label-l font-medium text-inverse-primary hover:bg-white/10',
            closeButton:
              '!absolute !top-1/2 !right-2 !left-auto !size-8 !-translate-y-1/2 !transform-none !rounded-full !border-0 !bg-transparent !text-inverse-on-surface hover:!bg-white/10',
            icon: 'shrink-0',
          },
        }}
        icons={{
          success: <Icon name="check_circle" fill className="size-5 text-[#81C995]" />,
          error: <Icon name="error" fill className="size-5 text-[#F28B82]" />,
        }}
      />
    </IconSetContext>
  )
}

function RequireAnalyst({ analyst }: { analyst: AnalystState }) {
  const location = useLocation()
  if (analyst.status === 'loading') {
    return (
      <div className="flex min-h-svh flex-col bg-surface" aria-busy="true">
        <div className="h-16" />
        <div className="grid flex-1 gap-4 p-4 lg:grid-cols-[256px_360px_1fr]">
          <Skeleton className="hidden h-64 lg:block" />
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

const NAV: { to: string; label: string; icon: IconName; end: boolean }[] = [
  { to: '/console', label: 'Queue', icon: 'inbox', end: false },
  { to: '/console/dashboard', label: 'Dashboard', icon: 'dashboard', end: true },
  { to: '/console/watchlist', label: 'Watchlist', icon: 'policy', end: true },
]

// What the console runs on (the contest's required services first). Shown, not linked.
const STACK: { label: string; detail: string; icon: IconName | 'gemini' }[] = [
  { label: 'Gemini', detail: 'Vertex AI · evidence, explanations', icon: 'gemini' },
  { label: 'Firestore', detail: 'Realtime queue, cases', icon: 'database' },
  { label: 'Cloud Run', detail: 'API + ADK agents', icon: 'deployed_code' },
  { label: 'Firebase', detail: 'Hosting, Auth', icon: 'bolt' },
  { label: 'BigQuery', detail: 'Transaction features', icon: 'query_stats' },
]

const DRAWER_KEY = 'pauseguard.console.drawer'
// Open on wide screens; on a laptop the rail leaves the case its room. The analyst's choice wins.
function initialDrawer() {
  try {
    const saved = localStorage.getItem(DRAWER_KEY)
    if (saved) return saved === 'open'
  } catch {
    // storage blocked: fall through to the default
  }
  return typeof window !== 'undefined' && window.innerWidth >= 1400
}

function ConsoleLayout({ analyst }: { analyst: AnalystState }) {
  const { pathname } = useLocation()
  const [open, setOpen] = useState(initialDrawer)
  const queueActive = pathname === '/console' || pathname.startsWith('/console/cases')
  const toggle = () => {
    setOpen(!open)
    try {
      localStorage.setItem(DRAWER_KEY, open ? 'closed' : 'open')
    } catch {
      // storage blocked: the drawer just won't remember
    }
  }
  const isActive = (to: string, active: boolean) => (to === '/console' ? queueActive : active)

  return (
    <div className="flex h-svh flex-col bg-surface text-on-surface">
      <a
        href="#console-main"
        className="sr-only z-50 rounded-full bg-primary px-4 py-2 text-on-primary focus:not-sr-only focus:absolute focus:top-2 focus:left-2"
      >
        Skip to content
      </a>
      <header className="flex h-16 shrink-0 items-center gap-1 pr-2 pl-1 sm:pr-4 sm:pl-2">
        <button
          type="button"
          onClick={toggle}
          aria-expanded={open}
          aria-controls="console-drawer"
          className={iconButton('standard', 'hidden md:inline-flex')}
        >
          <Icon name="menu" />
          <span className="sr-only">Main menu</span>
        </button>
        <NavLink to="/" className="ripple flex h-12 items-center gap-2 rounded-full px-3" aria-label={`${PRODUCT_NAME} home`}>
          <PauseGuardLogo />
          <span className="text-[22px] leading-none tracking-[-0.01em] text-on-surface-variant">
            <span className="font-medium text-on-surface">{PRODUCT_NAME}</span>
          </span>
        </NavLink>
        <span className="mr-2 hidden items-center gap-2 rounded-full border border-outline-variant py-1.5 pr-3 pl-2 text-label-l text-on-surface-variant xl:inline-flex">
          <Icon name="account_balance" className="size-[18px]" />
          {BANK_NAME} · Fraud operations
        </span>
        <HeaderSearch />
        <span className="ml-auto flex items-center gap-1">
          <span className="mr-1 hidden items-center gap-1.5 rounded-full bg-surface-container-high px-3 py-1.5 text-label-l text-on-surface-variant lg:inline-flex">
            <Sparkle className="size-4" />
            Gemini on Vertex AI
          </span>
          <AccountMenu analyst={analyst} />
        </span>
      </header>

      {/* below md: the drawer's destinations as a row of tabs */}
      <nav aria-label="Console" className="flex shrink-0 gap-1 overflow-x-auto px-2 pb-2 md:hidden">
        {NAV.map(({ to, label, icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            aria-current={to === '/console' && queueActive ? 'page' : undefined}
            className={({ isActive: a }) =>
              cn(
                'ripple inline-flex min-h-10 items-center gap-2 rounded-full px-4 text-label-l font-medium',
                isActive(to, a) ? 'bg-secondary-container text-on-secondary-container' : 'text-on-surface-variant',
              )
            }
          >
            <Icon name={icon} className="size-5" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="flex min-h-0 flex-1">
        <nav
          id="console-drawer"
          aria-label="Console"
          className={cn(
            'hidden shrink-0 flex-col overflow-y-auto pb-3 transition-[width] duration-300 ease-emphasized md:flex',
            open ? 'w-64 px-3' : 'w-[72px] px-3',
          )}
        >
          <ul className="flex flex-col gap-0.5">
            {NAV.map(({ to, label, icon, end }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={end}
                  title={open ? undefined : label}
                  aria-current={to === '/console' && queueActive ? 'page' : undefined}
                  className={({ isActive: a }) =>
                    cn(
                      'ripple flex h-12 items-center gap-3 rounded-full text-label-l font-medium',
                      open ? 'px-4' : 'justify-center px-0',
                      isActive(to, a) ? 'bg-secondary-container text-on-secondary-container' : 'text-on-surface-variant',
                    )
                  }
                >
                  {({ isActive: a }) => (
                    <>
                      <Icon name={icon} fill={isActive(to, a)} />
                      <span className={cn(!open && 'sr-only')}>{label}</span>
                    </>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
          {open && <StackCard />}
        </nav>

        <main id="console-main" className="min-h-0 min-w-0 flex-1 overflow-hidden bg-surface-container-lowest md:mr-3 md:mb-3 md:rounded-2xl md:shadow-[0_0_0_1px_var(--outline-variant)]">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

/** "Built on Google Cloud": what each part of the console runs on. */
function StackCard() {
  return (
    <section aria-labelledby="stack-title" className="mt-auto rounded-xl bg-surface-container p-3">
      <h2 id="stack-title" className="flex items-center gap-2 px-1 text-label-m font-medium tracking-wide text-on-surface-variant uppercase">
        <Icon name="cloud" className="size-4" />
        Built on Google Cloud
      </h2>
      <ul className="mt-2 flex flex-col gap-1">
        {STACK.map((s) => (
          <li key={s.label} className="flex items-center gap-2.5 rounded-lg px-1 py-1">
            <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-container-lowest text-primary">
              {s.icon === 'gemini' ? <Sparkle className="size-[18px]" /> : <Icon name={s.icon} className="size-[18px]" />}
            </span>
            <span className="flex min-w-0 flex-col">
              <span className="text-label-l font-medium text-on-surface">{s.label}</span>
              <span className="truncate text-body-s text-on-surface-variant">{s.detail}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** The Google-style search bar: looks up phones, links and accounts on the watchlist. */
function HeaderSearch() {
  const navigate = useNavigate()
  const id = useId()
  const [q, setQ] = useState('')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    navigate(`/console/watchlist${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ''}`)
  }
  return (
    <form role="search" onSubmit={submit} className="mx-2 hidden max-w-[720px] flex-1 md:block">
      <label htmlFor={`${id}-q`} className="sr-only">
        Search phones, links and accounts
      </label>
      <div className="flex h-12 items-center gap-2 rounded-full bg-surface-container-high px-2 transition-colors focus-within:bg-surface-container-lowest focus-within:shadow-e2">
        <button type="submit" className={iconButton('standard', 'size-10')} aria-label="Search">
          <Icon name="search" />
        </button>
        <input
          id={`${id}-q`}
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search phones, links, accounts"
          className="h-full min-w-0 flex-1 bg-transparent text-body-l text-on-surface placeholder:text-on-surface-variant focus-visible:outline-none"
        />
      </div>
    </form>
  )
}

function AccountMenu({ analyst }: { analyst: AnalystState }) {
  if (analyst.status !== 'signedIn') {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-surface-container-high px-3 py-1.5 text-label-l text-on-surface-variant">
        <Icon name="keyboard" className="size-4" />
        Local dev · sign-in off
      </span>
    )
  }
  const letter = analyst.email.charAt(0).toUpperCase()
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger className="ripple inline-flex size-12 items-center justify-center rounded-full" aria-label={`Account: ${analyst.email}`}>
        <span className="inline-flex size-8 items-center justify-center rounded-full bg-[#0B57D0] text-[15px] font-medium text-white">
          {letter}
        </span>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={4}
          className="z-50 w-[320px] rounded-2xl bg-surface-container-high p-3 text-on-surface shadow-e2 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95"
        >
          <MenuHeader email={analyst.email} letter={letter} />
          <DropdownMenu.Item
            onSelect={() => void signOutAnalyst()}
            className="ripple mt-2 flex h-12 cursor-pointer items-center gap-3 rounded-full bg-surface-container-lowest px-5 text-label-l font-medium outline-none data-[highlighted]:bg-surface-container-highest"
          >
            <Icon name="logout" className="size-5" />
            Sign out
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}

function MenuHeader({ email, letter }: { email: string; letter: string }): ReactNode {
  return (
    <div className="flex flex-col items-center gap-1 px-2 pt-3 pb-2 text-center">
      <span className="inline-flex size-16 items-center justify-center rounded-full bg-[#0B57D0] text-[28px] text-white">{letter}</span>
      <p className="mt-2 text-title-m">Hi, analyst</p>
      <p className="text-body-m text-on-surface-variant">{email}</p>
      <p className="text-body-s text-on-surface-variant">{BANK_NAME} · Fraud operations</p>
    </div>
  )
}
