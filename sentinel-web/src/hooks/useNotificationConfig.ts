import { useState } from 'react'

export interface NotificationConfig {
  enabled: boolean
  webhookUrl: string
  dangerThreshold: number // 0-100; notify when danger_level >= threshold
}

const STORAGE_KEY = 'sentinel-notifications'

const DEFAULTS: NotificationConfig = {
  enabled: false,
  webhookUrl: '',
  dangerThreshold: 70,
}

function load(): NotificationConfig {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULTS
    return { ...DEFAULTS, ...JSON.parse(raw) }
  } catch {
    return DEFAULTS
  }
}

export function useNotificationConfig() {
  const [config, setConfigState] = useState<NotificationConfig>(load)

  const setConfig = (patch: Partial<NotificationConfig>) => {
    setConfigState((prev) => {
      const next = { ...prev, ...patch }
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      } catch {
        // ignore persistence failures
      }
      return next
    })
  }

  return { config, setConfig }
}

export function getNotificationConfig(): NotificationConfig {
  return load()
}
