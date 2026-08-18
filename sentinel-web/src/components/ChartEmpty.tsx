import { useTranslation } from 'react-i18next'
import { BarChart3 } from 'lucide-react'

export default function ChartEmpty() {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col items-center justify-center h-64 text-gray-400 dark:text-gray-500">
      <BarChart3 className="w-10 h-10 mb-3 opacity-50" />
      <p className="text-sm">{t('charts.noData')}</p>
    </div>
  )
}
