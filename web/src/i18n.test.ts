import i18n from '@/i18n'

test('the site is English only', () => {
  expect(i18n.language).toBe('en')
  expect(Object.keys(i18n.options.resources ?? {})).toEqual(['en'])
  expect(document.documentElement.lang).toBe('en')
})
