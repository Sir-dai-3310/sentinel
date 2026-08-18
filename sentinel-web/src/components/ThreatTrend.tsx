import { useMemo } from 'react'
import ReactECharts from 'echarts-for-react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import axios from 'axios'
import { useTheme } from '../hooks/useTheme'
import ChartEmpty from './ChartEmpty'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface TrendPoint {
  timestamp: string
  threats: number
}

export default function ThreatTrend() {
  const { t } = useTranslation()
  const { resolvedTheme } = useTheme()
  const isDark = resolvedTheme === 'dark'

  const { data, isError } = useQuery<TrendPoint[]>({
    queryKey: ['stats-threat-trend'],
    queryFn: async () => {
      const res = await axios.get(`${API_URL}/api/v1/stats/threat-trend`)
      return res.data
    },
    retry: 1,
    refetchInterval: 30000,
  })

  const option = useMemo(() => {
    const points = data ?? []
    return {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        textStyle: { color: isDark ? '#e5e7eb' : '#1f2937' },
        backgroundColor: isDark ? '#1f2937' : '#ffffff',
        borderColor: isDark ? '#374151' : '#e5e7eb',
      },
      grid: { left: 8, right: 16, top: 24, bottom: 8, containLabel: true },
      xAxis: {
        type: 'category',
        data: points.map((p) => p.timestamp),
        axisLabel: { color: isDark ? '#9ca3af' : '#6b7280' },
        axisLine: { lineStyle: { color: isDark ? '#374151' : '#d1d5db' } },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: isDark ? '#9ca3af' : '#6b7280' },
        splitLine: { lineStyle: { color: isDark ? '#374151' : '#e5e7eb' } },
      },
      series: [
        {
          name: t('charts.threatTrend'),
          type: 'line',
          smooth: true,
          data: points.map((p) => p.threats),
          areaStyle: { opacity: 0.15 },
          lineStyle: { color: '#0ea5e9' },
          itemStyle: { color: '#0ea5e9' },
        },
      ],
    }
  }, [data, isDark, t])

  const empty = isError || !data || data.length === 0

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
      <h3 className="text-xl font-bold mb-4">{t('charts.threatTrend')}</h3>
      {empty ? (
        <ChartEmpty />
      ) : (
        <ReactECharts option={option} style={{ height: 280 }} notMerge />
      )}
    </div>
  )
}
