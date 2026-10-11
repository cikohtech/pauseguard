import { Route, Routes } from 'react-router-dom'

import { CustomerApp } from '@/customer/CustomerApp'
import { Landing } from '@/pages/Landing'
import { Placeholder } from '@/pages/Placeholder'

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/app/*" element={<CustomerApp />} />
      <Route path="/console/*" element={<Placeholder area="console" />} />
      <Route path="*" element={<Placeholder area="notFound" />} />
    </Routes>
  )
}
