import { useEffect, useRef, useCallback } from 'react'
import { getWsUrl } from '../api/client'

export function useWebSocket(onMessage) {
  const wsRef = useRef(null)
  const reconnectTimer = useRef(null)
  const isUnmounted = useRef(false)

  const connect = useCallback(() => {
    if (isUnmounted.current) return

    const ws = new WebSocket(getWsUrl())
    wsRef.current = ws

    ws.onopen = () => {
      console.log('[WS] connected')
    }

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        onMessage(data)
      } catch (err) {
        console.warn('[WS] failed to parse message', err)
      }
    }

    ws.onerror = (e) => {
      console.warn('[WS] error', e)
    }

    ws.onclose = () => {
      console.log('[WS] disconnected — reconnecting in 3s')
      if (!isUnmounted.current) {
        reconnectTimer.current = setTimeout(connect, 3000)
      }
    }
  }, [onMessage])

  useEffect(() => {
    isUnmounted.current = false
    connect()
    return () => {
      isUnmounted.current = true
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connect])
}
