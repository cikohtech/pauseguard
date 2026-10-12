import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from '@/locales/en.json'
import zh from '@/locales/zh.json'

export const SUPPORTED_LANGUAGES = ['en', 'zh'] as const // ms and ta are stretch goals
export type Language = (typeof SUPPORTED_LANGUAGES)[number]

const STORAGE_KEY = 'pauseguard.language'

/** The language this tab last showed (so a reload keeps it); English on a new visit. */
export function initialLanguage(): Language {
  try {
    return sessionStorage.getItem(STORAGE_KEY) === 'zh' ? 'zh' : 'en'
  } catch {
    return 'en' // storage blocked (private mode, previews)
  }
}

const htmlLang = (lng: string) => (lng === 'zh' ? 'zh-Hans' : lng)
const language = initialLanguage()

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, zh: { translation: zh } },
  lng: language,
  fallbackLng: 'en',
  interpolation: { escapeValue: false }, // React already escapes
})
document.documentElement.lang = htmlLang(language)

// One language for the whole site (landing, app, console), changed only by the visitor: the
// header toggle, or picking a persona (who brings their own language).
i18n.on('languageChanged', (lng) => {
  document.documentElement.lang = htmlLang(lng)
  try {
    sessionStorage.setItem(STORAGE_KEY, lng)
  } catch {
    // storage blocked: the language just won't survive a reload
  }
})

export default i18n
