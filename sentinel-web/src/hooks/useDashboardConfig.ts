import { useState } from 'react'

export interface DashboardCardConfig {
  id: string
  visible: boolean
}

const STORAGE_KEY = 'sentinel-dashboard-cards'

// Ordered list of dashboard card ids
export const DEFAULT_CARDS: DashboardCardConfig[] = [
  { id: 'stats', visible: true },
  { id: 'attackHeatmap', visible: true },
  { id: 'threatTrend', visible: true },
  { id: 'ruleHits', visible: true },
  { id: 'llmCost', visible: true },
  { id: 'systemStatus', visible: true },
]

function load(): DashboardCardConfig[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_CARDS
    const saved: DashboardCardConfig[] = JSON.parse(raw)
    // Merge: keep saved order/visibility, append any new cards
    const savedIds = new Set(saved.map((c) => c.id))
    const merged = [...saved]
    for (const c of DEFAULT_CARDS) {
      if (!savedIds.has(c.id)) merged.push(c)
    }
    return merged
  } catch {
    return DEFAULT_CARDS
  }
}

export function useDashboardConfig() {
  const [cards, setCardsState] = useState<DashboardCardConfig[]>(load)

  const persist = (next: DashboardCardConfig[]) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      // ignore
    }
  }

  const toggleCard = (id: string) => {
    setCardsState((prev) => {
      const next = prev.map((c) => (c.id === id ? { ...c, visible: !c.visible } : c))
      persist(next)
      return next
    })
  }

  const moveCard = (id: string, direction: 'up' | 'down') => {
    setCardsState((prev) => {
      const idx = prev.findIndex((c) => c.id === id)
      if (idx === -1) return prev
      const target = direction === 'up' ? idx - 1 : idx + 1
      if (target < 0 || target >= prev.length) return prev
      const next = [...prev]
      ;[next[idx], next[target]] = [next[target], next[idx]]
      persist(next)
      return next
    })
  }

  const isVisible = (id: string) => cards.find((c) => c.id === id)?.visible ?? true

  return { cards, toggleCard, moveCard, isVisible }
}
