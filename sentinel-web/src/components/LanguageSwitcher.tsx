import { useTranslation } from 'react-i18next'
import { Globe } from 'lucide-react'

const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'zh', label: '中文' },
  { code: 'ja', label: '日本語' },
  { code: 'ko', label: '한국어' },
  { code: 'es', label: 'Español' },
]

export default function LanguageSwitcher() {
  const { i18n } = useTranslation()

  return (
    <div className="flex items-center space-x-2" data-testid="language-switcher">
      <Globe className="w-4 h-4 text-gray-400" />
      <select
        aria-label="Language"
        value={i18n.language}
        onChange={(e) => i18n.changeLanguage(e.target.value)}
        className="bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 text-sm rounded px-2 py-1 border border-gray-300 dark:border-gray-600 focus:outline-none focus:border-primary-500"
      >
        {LANGUAGES.map((lang) => (
          <option key={lang.code} value={lang.code}>
            {lang.label}
          </option>
        ))}
      </select>
    </div>
  )
}
