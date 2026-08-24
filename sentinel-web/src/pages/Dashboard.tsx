import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Shield, AlertTriangle, TrendingUp, Activity } from 'lucide-react'
import AttackHeatmap from '../components/AttackHeatmap'
import ThreatTrend from '../components/ThreatTrend'
import RuleHitsBar from '../components/RuleHitsBar'
import LlmCostPanel from '../components/LlmCostPanel'
import { api } from '../api/client'
import { useDashboardConfig } from '../hooks/useDashboardConfig'

interface Stats {
  total_events: number
  alerts: number
  critical: number
  accuracy: number
}

export default function Dashboard() {
  const { t } = useTranslation()
  const { cards, isVisible } = useDashboardConfig()
  const { data: stats, isLoading, error } = useQuery<Stats>({
    queryKey: ['stats'],
    queryFn: async ({ signal }) => {
      const response = await api.get('/api/v1/stats', { signal })
      return response.data
    },
    refetchInterval: 5000, // Refresh every 5s
    retry: 1,
  })

  const statCards = [
    {
      icon: Activity,
      label: t('dashboard.totalEvents'),
      value: stats?.total_events ?? 0,
      color: 'text-blue-500',
      bg: 'bg-blue-500/10',
    },
    {
      icon: AlertTriangle,
      label: t('dashboard.alerts'),
      value: stats?.alerts ?? 0,
      color: 'text-yellow-500',
      bg: 'bg-yellow-500/10',
    },
    {
      icon: Shield,
      label: t('dashboard.critical'),
      value: stats?.critical ?? 0,
      color: 'text-red-500',
      bg: 'bg-red-500/10',
    },
    {
      icon: TrendingUp,
      label: t('dashboard.accuracy'),
      value: `${((stats?.accuracy ?? 0) * 100).toFixed(1)}%`,
      color: 'text-green-500',
      bg: 'bg-green-500/10',
    },
  ]

  const statsCard = (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      {statCards.map((stat) => {
        const Icon = stat.icon
        return (
          <div
            key={stat.label}
            className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700"
          >
            <div className="flex items-center justify-between mb-4">
              <div className={`p-3 rounded-lg ${stat.bg}`}>
                <Icon className={`w-6 h-6 ${stat.color}`} />
              </div>
            </div>
            <div>
              <p className="text-gray-500 dark:text-gray-400 text-sm mb-1">{stat.label}</p>
              <p className="text-3xl font-bold">
                {isLoading ? (
                  <span className="text-gray-400 dark:text-gray-600">{t('dashboard.loading')}</span>
                ) : (
                  stat.value
                )}
              </p>
            </div>
          </div>
        )
      })}
    </div>
  )

  const systemStatusCard = (
    <div className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
      <h3 className="text-xl font-bold mb-4">{t('dashboard.systemStatus')}</h3>
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-gray-500 dark:text-gray-400">{t('dashboard.apiConnection')}</span>
          <span
            className={`px-3 py-1 rounded-full text-sm ${
              error
                ? 'bg-red-500/20 text-red-500 dark:text-red-400'
                : 'bg-green-500/20 text-green-600 dark:text-green-400'
            }`}
          >
            {error ? t('dashboard.disconnected') : t('dashboard.connected')}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-gray-500 dark:text-gray-400">{t('dashboard.dataRefresh')}</span>
          <span className="text-gray-600 dark:text-gray-300 text-sm">{t('dashboard.every5s')}</span>
        </div>
      </div>
    </div>
  )

  const cardMap: Record<string, JSX.Element> = {
    stats: statsCard,
    attackHeatmap: <AttackHeatmap />,
    threatTrend: <ThreatTrend />,
    ruleHits: <RuleHitsBar />,
    llmCost: <LlmCostPanel />,
    systemStatus: systemStatusCard,
  }

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-3xl font-bold mb-2">{t('dashboard.title')}</h2>
        <p className="text-gray-500 dark:text-gray-400">{t('dashboard.subtitle')}</p>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500 rounded-lg p-4">
          <p className="text-red-500 dark:text-red-400">{t('dashboard.loadError')}</p>
        </div>
      )}

      {/* Configurable cards in saved order */}
      {cards
        .filter((c) => isVisible(c.id))
        .map((c) => (
          <div key={c.id}>{cardMap[c.id]}</div>
        ))}
    </div>
  )
}
