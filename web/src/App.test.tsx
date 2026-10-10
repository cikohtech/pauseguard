import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

import { AppRoutes } from '@/App'
import i18n from '@/i18n'
import en from '@/locales/en.json'
import zh from '@/locales/zh.json'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  )
}

afterEach(async () => {
  await i18n.changeLanguage('en')
})

test('landing page shows the tagline and both entry points', () => {
  renderAt('/')
  expect(screen.getByRole('heading', { name: 'Pause before you pay.' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /Try the customer app/ })).toHaveAttribute('href', '/app')
  expect(screen.getByRole('link', { name: /analyst console/ })).toHaveAttribute('href', '/console')
})

test.each([
  ['/app/home', 'Harbour Bank app with PauseGuard'],
  ['/console/dashboard', 'PauseGuard analyst console'],
  ['/nope', 'Page not found'],
])('route %s renders its area', (path, heading) => {
  renderAt(path)
  expect(screen.getByRole('heading', { name: heading })).toBeInTheDocument()
})

test('language toggle switches the UI to Chinese', async () => {
  renderAt('/')
  await userEvent.click(screen.getByRole('button', { name: 'Language' }))
  expect(screen.getByRole('heading', { name: '付款之前，先停一停。' })).toBeInTheDocument()
})

test('en and zh locale files have the same keys', () => {
  const keys = (o: object, p = ''): string[] =>
    Object.entries(o).flatMap(([k, v]) =>
      typeof v === 'object' ? keys(v, `${p}${k}.`) : [`${p}${k}`],
    )
  expect(keys(zh).sort()).toEqual(keys(en).sort())
})
