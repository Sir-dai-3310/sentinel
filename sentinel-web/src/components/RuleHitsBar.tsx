import { useMemo } from 'react'
import ReactECharts from 'echarts-for-react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import axios from 'axios'
import { useTheme } from '../hooks/useTheme'
import ChartEmpty from './ChartEmpty'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const TOP_N = 10

interface RuleHit {
  rule_name: string
  count: number
}

export default function RuleHitsBar() {
  const { t } = useTranslation()
  const { resolvedTheme } = useTheme()
  const isDark = resolvedTheme === 'dark'

  const { data, isError } = useQuery<RuleHit[]>({
    queryKey: ['stats-rule-hits'],
    queryFn: async () => {
      const res = await axios.get(`${API_URL}/api/v1/stats/rule-hits`)
      return res.data
    },
    retry: 1,
    refetchInterval: 30000,
  })

  const option = useMemo(() => {
    const top = (data ?? []).slice(0, TOP_N)
    return {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        textStyle: { color: isDark ? '#e5e7eb' : '#1f2937' },
        backgroundColor: isDark ? '#1f2937' : '#ffffff',
        borderColor: isDark ? '#374151' : '#e5e7eb',
      },
      grid: { left: 8, right: 24, top: 8, bottom: 8, containLabel: true },
      xAxis: {
        type: 'value',
        axisLabel: { color: isDark ? '#9ca3af' : '#6b7280' },
        splitLine: { lineStyle: { color: isDark ? '#374151' : '#e5e7eb' } },
      },
      yAxis: {
        type: 'category',
        data: top.map((r) => r.rule_name),
        axisLabel: { color: isDark ? '#9ca3af' : '#6b7280', fontSize: 11 },
        axisLine: { lineStyle: { color: isDark ? '#374151' : '#d1d5db' } },
      },
      series: [
        {
          name: t('charts.ruleHits'),
          type: 'bar',
          data: top.map((r) => r.count),
          itemStyle: { color: '#0ea5e9', borderRadius: [0, 4, 4, 0] },
        },
      ],
    }
  }, [data, isDark, t])

  const empty = isError || !data || data.length === 0

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
      <h3 className="text-xl font-bold mb-4">{t('charts.ruleHits')}</h3>
      {empty ? (
        <ChartEmpty />
      ) : (
        <ReactECharts option={option} style={{ height: 280 }} notMerge />
      )}
    </div>
  )
}
