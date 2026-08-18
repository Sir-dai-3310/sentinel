import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

import enTranslation from '../locales/en/translation.json'
import zhTranslation from '../locales/zh/translation.json'
import jaTranslation from '../locales/ja/translation.json'
import koTranslation from '../locales/ko/translation.json'
import esTranslation from '../locales/es/translation.json'

const resources = {
  en: { translation: enTranslation },
  zh: { translation: zhTranslation },
  ja: { translation: jaTranslation },
  ko: { translation: koTranslation },
  es: { translation: esTranslation },
}

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: 'en',
    supportedLngs: ['en', 'zh', 'ja', 'ko', 'es'],
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
    },
    interpolation: {
      escapeValue: false,
    },
  })

export default i18n
