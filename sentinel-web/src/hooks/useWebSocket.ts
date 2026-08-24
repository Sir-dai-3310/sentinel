import { useEffect, useRef, useState, useCallback } from 'react'

export interface WSMessage {
  type: string
  data?: Record<string, unknown>
}

interface UseWebSocketOptions {
  onMessage?: (message: WSMessage) => void
  onError?: (error: Event) => void
  onOpen?: () => void
  onClose?: () => void
  reconnectInterval?: number
  heartbeatInterval?: number
}

/**
 * WebSocket hook with stable reconnection semantics.
 *
 * Fixes the previous "reconnect storm" bug: callbacks used to live in the
 * connect() dependency array, so every render with inline handlers tore the
 * socket down and reconnected (and each incoming message re-rendered the
 * page, looping). Handlers are now kept in refs; connect() only depends on
 * [url]. A manual-close flag prevents ghost reconnections after unmount, and
 * reconnects use exponential backoff (capped).
 */
export function useWebSocket(url: string, options: UseWebSocketOptions = {}) {
  const {
    reconnectInterval = 5000,
    heartbeatInterval = 30000,
  } = options

  const [isConnected, setIsConnected] = useState(false)
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const heartbeatTimeoutRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Stable handler refs: inline arrow props no longer force reconnects.
  const handlersRef = useRef(options)
  handlersRef.current = options

  // True after an explicit disconnect/unmount: skip auto-reconnect.
  const manualCloseRef = useRef(false)

  // Reconnect attempts since the last successful connection (for backoff).
  const backoffRef = useRef(0)

  const clearTimers = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    if (heartbeatTimeoutRef.current) {
      clearInterval(heartbeatTimeoutRef.current)
      heartbeatTimeoutRef.current = null
    }
  }, [])

  const connect = useCallback(() => {
    try {
      manualCloseRef.current = false
      const ws = new WebSocket(url)

      ws.onopen = () => {
        setIsConnected(true)
        handlersRef.current.onOpen?.()
        if (heartbeatInterval > 0) {
          heartbeatTimeoutRef.current = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: 'ping' }))
            }
          }, heartbeatInterval)
        }
      }

      ws.onmessage = (event) => {
        try {
          const message: WSMessage = JSON.parse(event.data)
          setLastMessage(message)
          handlersRef.current.onMessage?.(message)
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error)
        }
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        handlersRef.current.onError?.(error)
      }

      ws.onclose = () => {
        setIsConnected(false)
        handlersRef.current.onClose?.()
        if (heartbeatTimeoutRef.current) {
          clearInterval(heartbeatTimeoutRef.current)
          heartbeatTimeoutRef.current = null
        }
        // Only reconnect for unexpected disconnects, never after a manual
        // close or unmount (the old code reconnected forever).
        if (!manualCloseRef.current && reconnectInterval > 0) {
          // Exponential backoff: 5s, 10s, 20s ... capped at 60s.
          const attempts = (backoffRef.current += 1)
          const delay = Math.min(reconnectInterval * 2 ** (attempts - 1), 60000)
          reconnectTimeoutRef.current = setTimeout(() => connect(), delay)
        }
      }

      wsRef.current = ws
    } catch (error) {
      console.error('Failed to create WebSocket:', error)
    }
  }, [url, reconnectInterval, heartbeatInterval])

  const disconnect = useCallback(() => {
    manualCloseRef.current = true
    clearTimers()
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
  }, [clearTimers])

  const sendMessage = useCallback((message: WSMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message))
    } else {
      console.error('WebSocket is not connected')
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      disconnect()
    }
  }, [connect, disconnect])

  // Reset backoff whenever the connection is established.
  useEffect(() => {
    if (isConnected) backoffRef.current = 0
  }, [isConnected])

  return {
    isConnected,
    lastMessage,
    sendMessage,
    disconnect,
  }
}
