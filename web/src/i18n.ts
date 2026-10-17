import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from '@/locales/en.json'

// English only (DECISIONS, 17 Oct 2026): the site has no language switch. The strings stay in a
// locale file, so another language can be added back in one place.
void i18n.use(initReactI18next).init({
  resources: { en: { translation: en } },
  lng: 'en',
  fallbackLng: 'en',
  interpolation: { escapeValue: false }, // React already escapes
})
document.documentElement.lang = 'en'

export default i18n
