import { BatteryFull, SignalHigh, Wifi } from 'lucide-react'
import {
  useEffect,
  useState,
  useSyncExternalStore,
  type CSSProperties,
  type ReactNode,
} from 'react'

import { PortalContainer } from '@/customer/portal'

// UI_SPEC Area 1: on desktop the app renders inside a 390×844 phone, scaled down to fit short
// screens; on a phone it is the whole screen. Dialogs and the check-in sheet portal into the
// phone screen (PortalContainer), so they stay inside the frame.

const FRAME_W = 390
const FRAME_H = 844
const DESKTOP_QUERY = '(min-width: 768px)'

function subscribeMedia(cb: () => void) {
  const mq = window.matchMedia?.(DESKTOP_QUERY)
  mq?.addEventListener('change', cb)
  return () => mq?.removeEventListener('change', cb)
}
const isDesktop = () => window.matchMedia?.(DESKTOP_QUERY).matches ?? false

function useFrameScale(enabled: boolean) {
  const [scale, setScale] = useState(1)
  useEffect(() => {
    if (!enabled) return
    const update = () => setScale(Math.min(1, (window.innerHeight - 48) / FRAME_H))
    update()
    window.addEventListener('resize', update)
    return () => window.removeEventListener('resize', update)
  }, [enabled])
  return scale
}

export function PhoneFrame({ children, caption }: { children: ReactNode; caption: ReactNode }) {
  const desktop = useSyncExternalStore(subscribeMedia, isDesktop, () => false)
  const scale = useFrameScale(desktop)
  const [screen, setScreen] = useState<HTMLElement | null>(null)

  const body = (
    <PortalContainer value={screen}>
      <div
        ref={setScreen}
        data-phone=""
        data-testid="phone-screen"
        // --sat / --sab: the insets each screen pads for: the fake status bar and home
        // indicator in the frame, the notch and home bar on a real phone
        style={
          {
            '--sat': desktop ? '44px' : 'env(safe-area-inset-top, 0px)',
            '--sab': desktop ? '28px' : '0px',
          } as CSSProperties
        }
        className="relative flex h-full flex-col overflow-hidden bg-background"
      >
        {desktop && <StatusBar />}
        {children}
        {desktop && (
          <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 bottom-2 z-[60] flex justify-center">
            <div className="h-1.5 w-32 rounded-full bg-foreground/80" />
          </div>
        )}
      </div>
    </PortalContainer>
  )

  if (!desktop) return <div className="h-svh">{body}</div>

  return (
    <div className="flex min-h-svh items-center justify-center gap-12 bg-[radial-gradient(ellipse_at_top,#E3EEF1,transparent_60%),linear-gradient(#F2F6F8,#E9EFF2)] px-8 py-6">
      <aside className="hidden max-w-xs lg:block">{caption}</aside>
      <div style={{ width: FRAME_W * scale, height: FRAME_H * scale }} className="shrink-0">
        <div
          style={{
            width: FRAME_W,
            height: FRAME_H,
            transform: scale < 1 ? `scale(${scale})` : undefined,
            transformOrigin: 'top left',
          }}
          className="rounded-[56px] bg-[#0F1B24] p-3 shadow-[0_30px_80px_-20px_rgba(15,27,36,0.45),inset_0_0_0_2px_#2A3842]"
        >
          <div className="h-full overflow-hidden rounded-[44px]">{body}</div>
        </div>
      </div>
      <aside className="max-w-[16rem] lg:hidden">{caption}</aside>
    </div>
  )
}

function StatusBar() {
  return (
    <div
      aria-hidden="true"
      className="phone-statusbar pointer-events-none absolute inset-x-0 top-0 z-[60] flex h-11 items-center justify-between px-7 pt-1 text-[15px] font-semibold text-foreground"
    >
      <span>9:41</span>
      <div className="absolute top-2.5 left-1/2 h-7 w-28 -translate-x-1/2 rounded-full bg-[#0F1B24]" />
      <span className="flex items-center gap-1.5">
        <SignalHigh className="size-4" strokeWidth={2.5} />
        <Wifi className="size-4" strokeWidth={2.5} />
        <BatteryFull className="size-5" strokeWidth={2} />
      </span>
    </div>
  )
}
