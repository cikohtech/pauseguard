import { createContext, use } from 'react'

/** The phone screen element: dialogs and the check-in sheet portal into it (PhoneFrame). */
export const PortalContainer = createContext<HTMLElement | null>(null)
export const usePortalContainer = () => use(PortalContainer)
