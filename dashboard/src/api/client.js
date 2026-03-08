const BASE_URL = ''

export async function fetchRecentTransactions(limit = 200) {
  const res = await fetch(`${BASE_URL}/api/transactions/recent?limit=${limit}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function fetchMetricsSummary() {
  const res = await fetch(`${BASE_URL}/api/metrics/summary`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function fetchTransactionDetail(id) {
  const res = await fetch(`${BASE_URL}/api/transactions/${id}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function fetchHourlyStats() {
  const res = await fetch(`${BASE_URL}/api/stats/hourly`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function fetchFlagQueue() {
  try {
    const res = await fetch(`${BASE_URL}/api/transactions/flagged`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return res.json()
  } catch {
    // Fallback: filter from recent
    const all = await fetchRecentTransactions()
    return all.filter(t => t.decision === 'FLAG' && !t.analyst_decision)
  }
}

export async function submitReview(transactionId, decision, analystId = 'analyst-1') {
  const res = await fetch(`${BASE_URL}/api/transactions/${transactionId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision, analyst_id: analystId }),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export function getWsUrl() {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}/ws/live`
}
