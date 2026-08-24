import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { AxiosError } from 'axios'
import { DollarSign } from 'lucide-react'
import { api } from '../api/client'

interface LlmCost {
  total_cost_usd?: number
  total_tokens?: number
  by_model?: Array<{ model: string; cost_usd: number; tokens: number }>
  // tolerate unknown shape
  [key: string]: unknown
}

export default function LlmCostPanel() {
  const { t } = useTranslation()

  const { data, error, isLoading } = useQuery<LlmCost>({
    queryKey: ['stats-llm-costs'],
    queryFn: async () => {
      const res = await api.get('/api/v1/stats/llm-costs')
      return res.data
    },
    retry: false,
    refetchInterval: 60000,
  })

  const is404 =
    error instanceof AxiosError && error.response?.status === 404

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
      <h3 className="text-xl font-bold mb-4 flex items-center">
        <DollarSign className="w-5 h-5 mr-2 text-green-500" />
        {t('llmCost.title')}
      </h3>

      {isLoading && <p className="text-gray-500 dark:text-gray-400 text-sm">{t('llmCost.loading')}</p>}

      {is404 && (
        <div className="flex flex-col items-center justify-center h-32 text-gray-400 dark:text-gray-500">
          <p className="text-sm">{t('llmCost.notEnabled')}</p>
        </div>
      )}

      {error && !is404 && (
        <div className="flex flex-col items-center justify-center h-32 text-gray-400 dark:text-gray-500">
          <p className="text-sm">{t('llmCost.unavailable')}</p>
        </div>
      )}

      {data && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">{t('llmCost.totalCost')}</p>
              <p className="text-2xl font-bold">
                ${(data.total_cost_usd ?? 0).toFixed(4)}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400">{t('llmCost.totalTokens')}</p>
              <p className="text-2xl font-bold">
                {(data.total_tokens ?? 0).toLocaleString()}
              </p>
            </div>
          </div>

          {data.by_model && data.by_model.length > 0 && (
            <div>
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">{t('llmCost.byModel')}</p>
              <div className="space-y-2">
                {data.by_model.map((m) => (
                  <div
                    key={m.model}
                    className="flex items-center justify-between bg-gray-50 dark:bg-gray-700/50 rounded p-2"
                  >
                    <span className="text-sm font-medium">{m.model}</span>
                    <span className="text-sm text-gray-600 dark:text-gray-300">
                      ${m.cost_usd.toFixed(4)} · {m.tokens.toLocaleString()} {t('llmCost.tokens')}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
