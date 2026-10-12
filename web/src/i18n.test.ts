import i18n, { initialLanguage } from '@/i18n'

afterEach(async () => {
  vi.restoreAllMocks()
  sessionStorage.clear()
  await i18n.changeLanguage('en')
})

test('a new visit starts in English', () => {
  sessionStorage.clear()
  expect(initialLanguage()).toBe('en')
})

test('a reload keeps the language the tab last showed', async () => {
  await i18n.changeLanguage('zh')
  expect(sessionStorage.getItem('pauseguard.language')).toBe('zh')
  expect(initialLanguage()).toBe('zh')
  expect(document.documentElement.lang).toBe('zh-Hans')
})

test('anything unexpected, or blocked storage, falls back to English', () => {
  sessionStorage.setItem('pauseguard.language', 'fr')
  expect(initialLanguage()).toBe('en')
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
    throw new Error('blocked')
  })
  expect(initialLanguage()).toBe('en')
})
