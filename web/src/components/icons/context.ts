import { createContext } from 'react'

import type { IconSet } from '@/components/icons/names'
import { ROUNDED } from '@/components/icons/rounded'

/** The icon style: Rounded in the customer app and on the landing page (the default), Outlined in the console. */
export const IconSetContext = createContext<IconSet>(ROUNDED)
