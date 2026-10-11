import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'

import { CustomerApp } from '@/customer/CustomerApp'
import { Landing } from '@/pages/Landing'
import { Placeholder } from '@/pages/Placeholder'

// The console (Recharts, Firestore) loads only when /console is opened.
const ConsoleApp = lazy(() => import('@/console/ConsoleApp').then((m) => ({ default: m.ConsoleApp })))

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/app/*" element={<CustomerApp />} />
      <Route
        path="/console/*"
        element={
          <Suspense fallback={<div className="min-h-svh bg-background" aria-busy="true" />}>
            <ConsoleApp />
          </Suspense>
        }
      />
      <Route path="*" element={<Placeholder area="notFound" />} />
    </Routes>
  )
}
