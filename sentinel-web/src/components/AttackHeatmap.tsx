import { useMemo } from 'react'
import ReactECharts from 'echarts-for-react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import axios from 'axios'
import { useTheme } from '../hooks/useTheme'
import ChartEmpty from './ChartEmpty'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// MITRE ATT&CK 14 tactics
const TACTICS = [
  'reconnaissance',
  'resource-development',
  'initial-access',
  'execution',
  'persistence',
  'privilege-escalation',
  'defense-evasion',
  'credential-access',
  'discovery',
  'lateral-movement',
  'collection',
  'command-and-control',
  'exfiltration',
  'impact',
]

interface AttackDatum {
  tactic: string
  count: number
}

export default function AttackHeatmap() {
  const { t } = useTranslation()
  const { resolvedTheme } = useTheme()
  const isDark = resolvedTheme === 'dark'

  const { data, isError } = useQuery<AttackDatum[]>({
    queryKey: ['stats-attack-tactics'],
    queryFn: async () => {
      const res = await axios.get(`${API_URL}/api/v1/stats/attack-tactics`)
      return res.data
    },
    retry: 1,
    refetchInterval: 30000,
  })

  const option = useMemo(() => {
    const rows = TACTICS.map((tactic) => {
      const found = data?.find((d) => d.tactic === tactic)
      return found?.count ?? 0
    })
    const max = Math.max(...rows, 1)
    return {
      backgroundColor: 'transparent',
      tooltip: {
        position: 'top',
        textStyle: { color: isDark ? '#e5e7eb' : '#1f2937' },
        backgroundColor: isDark ? '#1f2937' : '#ffffff',
        borderColor: isDark ? '#374151' : '#e5e7eb',
      },
      grid: { left: 8, right: 8, top: 8, bottom: 60, containLabel: true },
      xAxis: {
        type: 'category',
        data: TACTICS,
        splitArea: { show: true },
        axisLabel: {
          color: isDark ? '#9ca3af' : '#6b7280',
          rotate: 45,
          fontSize: 10,
          interval: 0,
        },
        axisLine: { lineStyle: { color: isDark ? '#374151' : '#d1d5db' } },
      },
      yAxis: {
        type: 'category',
        data: [t('charts.hits')],
        axisLabel: { color: isDark ? '#9ca3af' : '#6b7280' },
        axisLine: { lineStyle: { color: isDark ? '#374151' : '#d1d5db' } },
        splitArea: { show: true },
      },
      visualMap: {
        min: 0,
        max,
        calculable: true,
        orient: 'horizontal',
        left: 'center',
        bottom: 0,
        textStyle: { color: isDark ? '#9ca3af' : '#6b7280' },
        inRange: {
          color: isDark
            ? ['#1e293b', '#0ea5e9', '#ef4444']
            : ['#f1f5f9', '#38bdf8', '#dc2626'],
        },
      },
      series: [
        {
          name: t('charts.attackHeatmap'),
          type: 'heatmap',
          data: rows.map((v, i) => [i, 0, v]),
          label: { show: false },
          emphasis: { itemStyle: { shadowBlur: 8, shadowColor: 'rgba(0,0,0,0.4)' } },
        },
      ],
    }
  }, [data, isDark, t])

  const empty = isError || !data || data.length === 0

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
      <h3 className="text-xl font-bold mb-4">{t('charts.attackHeatmap')}</h3>
      {empty ? (
        <ChartEmpty />
      ) : (
        <ReactECharts option={option} style={{ height: 280 }} notMerge />
      )}
    </div>
  )
}
