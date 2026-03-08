import { useState, useEffect } from 'react'
import { fetchMetricsSummary } from '../api/client'

export function useMetrics() {
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true

    async function load() {
      try {
        const data = await fetchMetricsSummary()
        if (active) {
          setMetrics(data)
          setError(null)
          setLoading(false)
        }
      } catch (err) {
        if (active) setError(err.message)
      }
    }

    load()
    const interval = setInterval(load, 5000)
    return () => {
      active = false
      clearInterval(interval)
    }
  }, [])

  return { metrics, loading, error }
}
