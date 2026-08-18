import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  Settings as SettingsIcon,
  CheckCircle,
  XCircle,
  AlertCircle,
  Sun,
  Moon,
  Monitor,
  Bell,
  LayoutDashboard,
  ChevronUp,
  ChevronDown,
} from 'lucide-react'
import axios from 'axios'
import { useTheme, Theme } from '../hooks/useTheme'
import { useNotificationConfig } from '../hooks/useNotificationConfig'
import { useDashboardConfig } from '../hooks/useDashboardConfig'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface Settings {
  llm_model: string
  llm_base_url: string
  llm_temperature: number
  llm_max_tokens: number
  cors_origins: string
  environment: string
  vt_enabled: boolean
  abuseipdb_enabled: boolean
  shodan_enabled: boolean
  rules_dir: string
  log_level: string
}

const CARD_LABEL_KEYS: Record<string, string> = {
  stats: 'dashboardConfig.stats',
  attackHeatmap: 'dashboardConfig.attackHeatmap',
  threatTrend: 'dashboardConfig.threatTrend',
  ruleHits: 'dashboardConfig.ruleHits',
  llmCost: 'dashboardConfig.llmCost',
  systemStatus: 'dashboardConfig.systemStatus',
}

export default function Settings() {
  const { t } = useTranslation()
  const { theme, setTheme } = useTheme()
  const { config: notifConfig, setConfig: setNotifConfig } = useNotificationConfig()
  const { cards, toggleCard, moveCard } = useDashboardConfig()

  const { data: settings, isLoading, error } = useQuery<Settings>({
    queryKey: ['settings'],
    queryFn: async () => {
      const response = await axios.get(`${API_URL}/api/v1/settings`)
      return response.data
    },
    retry: 1,
  })

  const requestNotificationPermission = async (enable: boolean) => {
    if (!enable) {
      setNotifConfig({ enabled: false })
      return
    }
    if (!('Notification' in window)) {
      // Browser doesn't support notifications
      setNotifConfig({ enabled: false })
      return
    }
    if (Notification.permission === 'granted') {
      setNotifConfig({ enabled: true })
      return
    }
    if (Notification.permission === 'denied') {
      setNotifConfig({ enabled: false })
      return
    }
    const result = await Notification.requestPermission()
    setNotifConfig({ enabled: result === 'granted' })
  }

  const themeOptions: Array<{ value: Theme; icon: typeof Sun; labelKey: string }> = [
    { value: 'light', icon: Sun, labelKey: 'settings.themeLight' },
    { value: 'dark', icon: Moon, labelKey: 'settings.themeDark' },
    { value: 'system', icon: Monitor, labelKey: 'settings.themeSystem' },
  ]

  const notifSupported = typeof window !== 'undefined' && 'Notification' in window
  const notifDenied = notifSupported && Notification.permission === 'denied'

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-3xl font-bold mb-2">{t('settings.title')}</h2>
        <p className="text-gray-500 dark:text-gray-400">{t('settings.subtitle')}</p>
      </div>

      {/* Appearance / Theme */}
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
        <h3 className="text-xl font-bold mb-4 flex items-center">
          <Sun className="w-5 h-5 mr-2" />
          {t('settings.appearance')}
        </h3>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">{t('settings.theme')}</p>
        <div className="flex space-x-3" data-testid="theme-switcher">
          {themeOptions.map((opt) => {
            const Icon = opt.icon
            const active = theme === opt.value
            return (
              <button
                key={opt.value}
                onClick={() => setTheme(opt.value)}
                data-theme-option={opt.value}
                className={`flex items-center space-x-2 px-4 py-2 rounded-lg border transition-colors ${
                  active
                    ? 'bg-primary-600 text-white border-primary-600'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:bg-gray-200 dark:hover:bg-gray-600'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{t(opt.labelKey)}</span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Notifications */}
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
        <h3 className="text-xl font-bold mb-4 flex items-center">
          <Bell className="w-5 h-5 mr-2" />
          {t('notifications.title')}
        </h3>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium">{t('notifications.browserNotifications')}</p>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {t('notifications.browserNotificationsDesc')}
              </p>
            </div>
            <button
              onClick={() => requestNotificationPermission(!notifConfig.enabled)}
              disabled={!notifSupported || notifDenied}
              data-testid="notification-toggle"
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                notifConfig.enabled ? 'bg-primary-600' : 'bg-gray-300 dark:bg-gray-600'
              } ${!notifSupported || notifDenied ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  notifConfig.enabled ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>

          {!notifSupported && (
            <p className="text-sm text-yellow-600 dark:text-yellow-400">
              {t('notifications.notSupported')}
            </p>
          )}
          {notifDenied && (
            <p className="text-sm text-red-500 dark:text-red-400">
              {t('notifications.permissionDenied')}
            </p>
          )}

          <div>
            <label className="text-sm text-gray-500 dark:text-gray-400 block mb-1">
              {t('notifications.webhookUrl')}
            </label>
            <input
              type="text"
              value={notifConfig.webhookUrl}
              onChange={(e) => setNotifConfig({ webhookUrl: e.target.value })}
              placeholder={t('notifications.webhookPlaceholder')}
              className="w-full bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary-500"
            />
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
              {t('notifications.webhookHint')}
            </p>
          </div>

          <div>
            <label className="text-sm text-gray-500 dark:text-gray-400 block mb-1">
              {t('notifications.dangerThreshold')}: {notifConfig.dangerThreshold}
            </label>
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={notifConfig.dangerThreshold}
              onChange={(e) => setNotifConfig({ dangerThreshold: Number(e.target.value) })}
              className="w-full"
            />
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
              {t('notifications.thresholdHint')}
            </p>
          </div>
        </div>
      </div>

      {/* Dashboard Configuration */}
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
        <h3 className="text-xl font-bold mb-4 flex items-center">
          <LayoutDashboard className="w-5 h-5 mr-2" />
          {t('dashboardConfig.title')}
        </h3>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          {t('dashboardConfig.description')}
        </p>
        <div className="space-y-2" data-testid="dashboard-config">
          {cards.map((card, idx) => (
            <div
              key={card.id}
              className="flex items-center justify-between bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3"
            >
              <label className="flex items-center space-x-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={card.visible}
                  onChange={() => toggleCard(card.id)}
                  className="w-4 h-4 rounded accent-primary-600"
                />
                <span>{t(CARD_LABEL_KEYS[card.id] ?? card.id)}</span>
              </label>
              <div className="flex items-center space-x-1">
                <button
                  onClick={() => moveCard(card.id, 'up')}
                  disabled={idx === 0}
                  className="p-1 text-gray-500 dark:text-gray-400 hover:text-primary-500 disabled:opacity-30"
                  aria-label="move up"
                >
                  <ChevronUp className="w-4 h-4" />
                </button>
                <button
                  onClick={() => moveCard(card.id, 'down')}
                  disabled={idx === cards.length - 1}
                  className="p-1 text-gray-500 dark:text-gray-400 hover:text-primary-500 disabled:opacity-30"
                  aria-label="move down"
                >
                  <ChevronDown className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* API-driven settings */}
      {isLoading && (
        <div className="flex items-center justify-center h-32">
          <div className="text-gray-500 dark:text-gray-400">{t('settings.loading')}</div>
        </div>
      )}

      {error && (
        <div className="bg-red-500/10 border border-red-500 rounded-lg p-6">
          <div className="flex items-start space-x-3">
            <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="font-medium text-red-500">{t('settings.error')}</h4>
              <p className="text-sm text-red-400">{t('settings.errorHint')}</p>
            </div>
          </div>
        </div>
      )}

      {settings && (
        <>
          {/* LLM Configuration */}
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
            <h3 className="text-xl font-bold mb-4 flex items-center">
              <SettingsIcon className="w-5 h-5 mr-2" />
              {t('settings.llmConfig')}
            </h3>
            <div className="space-y-4">
              <div>
                <label className="text-sm text-gray-500 dark:text-gray-400">{t('settings.model')}</label>
                <p className="text-lg font-medium">{settings.llm_model}</p>
              </div>
              <div>
                <label className="text-sm text-gray-500 dark:text-gray-400">{t('settings.baseUrl')}</label>
                <p className="text-lg font-medium break-all">{settings.llm_base_url}</p>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm text-gray-500 dark:text-gray-400">{t('settings.temperature')}</label>
                  <p className="text-lg font-medium">{settings.llm_temperature}</p>
                </div>
                <div>
                  <label className="text-sm text-gray-500 dark:text-gray-400">{t('settings.maxTokens')}</label>
                  <p className="text-lg font-medium">{settings.llm_max_tokens}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Threat Intelligence */}
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
            <h3 className="text-xl font-bold mb-4">{t('settings.threatIntel')}</h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-gray-600 dark:text-gray-300">VirusTotal</span>
                <span
                  className={`flex items-center space-x-2 ${
                    settings.vt_enabled ? 'text-green-500 dark:text-green-400' : 'text-gray-400 dark:text-gray-500'
                  }`}
                >
                  {settings.vt_enabled ? <CheckCircle className="w-5 h-5" /> : <XCircle className="w-5 h-5" />}
                  <span>{settings.vt_enabled ? t('settings.enabled') : t('settings.disabled')}</span>
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-600 dark:text-gray-300">AbuseIPDB</span>
                <span
                  className={`flex items-center space-x-2 ${
                    settings.abuseipdb_enabled
                      ? 'text-green-500 dark:text-green-400'
                      : 'text-gray-400 dark:text-gray-500'
                  }`}
                >
                  {settings.abuseipdb_enabled ? (
                    <CheckCircle className="w-5 h-5" />
                  ) : (
                    <XCircle className="w-5 h-5" />
                  )}
                  <span>{settings.abuseipdb_enabled ? t('settings.enabled') : t('settings.disabled')}</span>
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-600 dark:text-gray-300">Shodan</span>
                <span
                  className={`flex items-center space-x-2 ${
                    settings.shodan_enabled
                      ? 'text-green-500 dark:text-green-400'
                      : 'text-gray-400 dark:text-gray-500'
                  }`}
                >
                  {settings.shodan_enabled ? <CheckCircle className="w-5 h-5" /> : <XCircle className="w-5 h-5" />}
                  <span>{settings.shodan_enabled ? t('settings.enabled') : t('settings.disabled')}</span>
                </span>
              </div>
            </div>
            <div className="mt-4 p-3 bg-blue-500/10 border border-blue-500/30 rounded text-sm text-blue-500 dark:text-blue-400">
              <p>{t('settings.threatIntelHint')}</p>
            </div>
          </div>

          {/* System Configuration */}
          <div className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700">
            <h3 className="text-xl font-bold mb-4">{t('settings.systemConfig')}</h3>
            <div className="space-y-4">
              <div>
                <label className="text-sm text-gray-500 dark:text-gray-400">{t('settings.environment')}</label>
                <p className="text-lg font-medium">
                  <span
                    className={`px-3 py-1 rounded-full text-sm ${
                      settings.environment === 'production'
                        ? 'bg-red-500/20 text-red-500 dark:text-red-400'
                        : 'bg-yellow-500/20 text-yellow-600 dark:text-yellow-400'
                    }`}
                  >
                    {settings.environment}
                  </span>
                </p>
              </div>
              <div>
                <label className="text-sm text-gray-500 dark:text-gray-400">{t('settings.corsOrigins')}</label>
                <p className="text-lg font-medium break-all">{settings.cors_origins}</p>
              </div>
              <div>
                <label className="text-sm text-gray-500 dark:text-gray-400">{t('settings.rulesDir')}</label>
                <p className="text-lg font-medium">{settings.rules_dir}</p>
              </div>
              <div>
                <label className="text-sm text-gray-500 dark:text-gray-400">{t('settings.logLevel')}</label>
                <p className="text-lg font-medium">{settings.log_level}</p>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Security Notice */}
      <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4">
        <h4 className="font-medium text-yellow-600 dark:text-yellow-400 mb-2">
          {t('settings.securityNote')}
        </h4>
        <p className="text-sm text-yellow-600 dark:text-yellow-300">{t('settings.securityNoteText')}</p>
      </div>
    </div>
  )
}
