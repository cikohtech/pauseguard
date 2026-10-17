import {
  useEffect,
  useState,
  useSyncExternalStore,
  type CSSProperties,
  type ReactNode,
} from 'react'

import { Icon } from '@/components/icons/Icon'
import { PortalContainer } from '@/customer/portal'

// UI_SPEC Area 1: on desktop the app renders inside a 390×844 phone (an Android device in the
// Pixel style: punch-hole camera, Android status bar, gesture bar), scaled down to fit short
// screens; on a phone it is the whole screen. Dialogs and the check-in sheet portal into the phone
// screen (PortalContainer), so they stay inside the frame. [data-phone] switches the colour roles
// to Harbour Bank's Material You scheme (index.css); the stage around it keeps Google's.

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
        // --sat / --sab: the insets each screen pads for: the status bar and gesture bar in the
        // frame, the notch and home bar on a real phone
        style={
          {
            '--sat': desktop ? '40px' : 'env(safe-area-inset-top, 0px)',
            '--sab': desktop ? '24px' : '0px',
          } as CSSProperties
        }
        className="relative flex h-full flex-col overflow-hidden bg-surface text-on-surface"
      >
        {desktop && <StatusBar />}
        {children}
        {desktop && (
          <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 bottom-2 z-[60] flex justify-center">
            <div className="h-1 w-[108px] rounded-full bg-on-surface/55" />
          </div>
        )}
      </div>
    </PortalContainer>
  )

  if (!desktop) return <div className="h-svh">{body}</div>

  return (
    <div className="relative flex min-h-svh items-center justify-center gap-14 overflow-hidden bg-surface px-8 py-6">
      <Backdrop />
      <aside className="relative hidden w-[22rem] shrink-0 lg:block">{caption}</aside>
      <div style={{ width: FRAME_W * scale, height: FRAME_H * scale }} className="relative shrink-0">
        <div
          style={{
            width: FRAME_W,
            height: FRAME_H,
            transform: scale < 1 ? `scale(${scale})` : undefined,
            transformOrigin: 'top left',
          }}
          className="relative rounded-[54px] bg-[#1B1B1F] p-[11px] shadow-[0_40px_80px_-24px_rgb(31_31_31/0.45),0_0_0_1px_rgb(0_0_0/0.08),inset_0_0_0_1.5px_#3C3C43]"
        >
          {/* side keys: power, then volume */}
          <span aria-hidden="true" className="absolute top-[150px] -right-[3px] h-[60px] w-[4px] rounded-r-[3px] bg-[#2A2A30]" />
          <span aria-hidden="true" className="absolute top-[240px] -right-[3px] h-[104px] w-[4px] rounded-r-[3px] bg-[#2A2A30]" />
          <div className="h-full overflow-hidden rounded-[43px]">{body}</div>
        </div>
      </div>
      <aside className="relative max-w-[17rem] lg:hidden">{caption}</aside>
    </div>
  )
}

/** Soft colour fields behind the phone, in Google's four colours at low strength. */
function Backdrop() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0">
      <div className="absolute -top-40 -left-32 size-[560px] rounded-full bg-[radial-gradient(circle,rgb(66_133_244/0.16),transparent_65%)]" />
      <div className="absolute top-1/3 -right-40 size-[620px] rounded-full bg-[radial-gradient(circle,rgb(52_168_83/0.10),transparent_65%)]" />
      <div className="absolute -bottom-48 left-1/4 size-[520px] rounded-full bg-[radial-gradient(circle,rgb(251_188_4/0.10),transparent_65%)]" />
      <div className="absolute inset-0 bg-[radial-gradient(rgb(31_31_31/0.06)_1px,transparent_1px)] [background-size:22px_22px] [mask-image:radial-gradient(ellipse_at_center,#000_20%,transparent_75%)]" />
    </div>
  )
}

/** Android status bar: time on the left, the punch-hole camera, then signal, Wi-Fi and battery. */
function StatusBar() {
  return (
    <div
      aria-hidden="true"
      className="phone-statusbar pointer-events-none absolute inset-x-0 top-0 z-[60] flex h-10 items-center justify-between px-7 text-[14px] font-medium text-on-surface"
    >
      <span className="tabular-nums">9:41</span>
      <span className="absolute top-3 left-1/2 size-[13px] -translate-x-1/2 rounded-full bg-[#1B1B1F] ring-[1.5px] ring-[#2E2E34]" />
      <span className="flex items-center gap-1">
        <Icon name="signal_cellular_alt" className="size-4" />
        <Icon name="wifi" className="size-4" />
        <Icon name="battery_full" className="size-4 rotate-90" />
      </span>
    </div>
  )
}
