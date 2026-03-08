import { useState, useEffect, useMemo } from 'react'
import { useMetrics } from './hooks/useMetrics'
import { fetchRecentTransactions, fetchHourlyStats } from './api/client'
import { MetricsCards } from './components/MetricsCards'
import { LiveFeed } from './components/LiveFeed'
import { IndiaMap } from './components/IndiaMap'
import { TimeSeriesChart } from './components/charts/TimeSeriesChart'
import { PieChart } from './components/charts/PieChart'
import { RulesBarChart } from './components/charts/RulesBarChart'
import { HeatmapChart } from './components/charts/HeatmapChart'
import { TransactionDrawer } from './components/TransactionDrawer'
import { FlagQueue } from './components/FlagQueue'

function dedup(arr) {
  const seen = new Set()
  return arr.filter(t => {
    if (seen.has(t.transaction_id)) return false
    seen.add(t.transaction_id)
    return true
  })
}

function aggregateRules(transactions) {
  const counts = {}
  for (const t of transactions) {
    for (const rule of (t.fired_rules || [])) {
      counts[rule] = (counts[rule] || 0) + 1
    }
  }
  return Object.entries(counts)
    .map(([rule, count]) => ({ rule, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 8)
}

function buildHeatmapData(transactions) {
  const map = {}
  for (const t of transactions) {
    const dt   = new Date(t.created_at || t.timestamp || Date.now())
    const hour = dt.getHours()
    const day  = dt.getDay()
    const key  = hour + '-' + day
    if (!map[key]) map[key] = { hour, day, count: 0 }
    map[key].count++
  }
  return Object.values(map)
}

const GLOBAL_CSS = `
  @keyframes livePulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(0.85); }
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  @keyframes fadeSlideIn {
    from { opacity: 0; transform: translateY(-4px); }
    to { opacity: 1; transform: translateY(0); }
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }
  @keyframes pulseRing {
    0% { transform: scale(1); opacity: 0.8; }
    100% { transform: scale(2.5); opacity: 0; }
  }
  .nav-stat:hover { background: rgba(79,142,247,0.12) !important; }
  .tab-btn {
    background: none;
    border: none;
    cursor: pointer;
    font-size: 13px;
    font-weight: 600;
    padding: 6px 16px;
    border-radius: 6px;
    transition: background 0.15s, color 0.15s;
    font-family: 'Inter', -apple-system, sans-serif;
  }
  .tab-btn.active { background: rgba(79,142,247,0.15); color: #4F8EF7; border-bottom: 2px solid #4F8EF7; }
  .tab-btn.inactive { color: #4A6080; }
  .tab-btn.inactive:hover { color: #8BA3C7; background: rgba(255,255,255,0.04); }
  .feed-row:hover { background: rgba(22,37,64,0.8) !important; }
  .flag-row:hover { background: rgba(22,37,64,0.9) !important; }
  .copy-btn:hover { background: rgba(79,142,247,0.2) !important; color: #4F8EF7 !important; }
  .review-btn-confirm:hover { filter: brightness(1.15); }
  .review-btn-fp:hover { filter: brightness(1.15); }
  .collapse-btn:hover { color: #8BA3C7 !important; }
`

export default function App() {
  const { metrics, error: metricsError } = useMetrics()
  const [wsItems, setWsItems]               = useState([])
  const [recentTransactions, setRecentTxns] = useState([])
  const [hourlyStats, setHourlyStats]       = useState([])
  const [selectedTx, setSelectedTx]         = useState(null)
  const [analystId, setAnalystId]           = useState('analyst-1')
  const [activeTab, setActiveTab]           = useState('feed')

  // txnCache: id -> item data for 404-safe drawer lookup
  const txnCache = useMemo(
    () => new Map([...wsItems, ...recentTransactions].map(t => [t.transaction_id, t])),
    [wsItems, recentTransactions]
  )

  // Load initial data + refresh periodically
  useEffect(() => {
    function load() {
      fetchRecentTransactions(200).then(setRecentTxns).catch(console.warn)
      fetchHourlyStats().then(setHourlyStats).catch(console.warn)
    }
    load()
    const id = setInterval(load, 12000)
    return () => clearInterval(id)
  }, [])

  const combinedTransactions = dedup([...wsItems, ...recentTransactions]).slice(0, 300)

  function handleReviewComplete(txId) {
    setWsItems(prev => prev.filter(t => t.transaction_id !== txId))
    setRecentTxns(prev => prev.filter(t => t.transaction_id !== txId))
    setSelectedTx(null)
    setTimeout(() => fetchRecentTransactions(200).then(setRecentTxns).catch(() => {}), 800)
  }

  const rulesData   = aggregateRules(combinedTransactions)
  const heatmapData = buildHeatmapData(combinedTransactions)

  const pieCounts = metrics
    ? { APPROVE: metrics.approved_count || 0, FLAG: metrics.flagged_count || 0, BLOCK: metrics.blocked_count || 0 }
    : combinedTransactions.reduce((acc, t) => { acc[t.decision] = (acc[t.decision] || 0) + 1; return acc }, {})

  const flagCount = metrics?.review_queue_count ?? 0

  return (
    <>
      <style>{GLOBAL_CSS}</style>
      <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#05091A' }}>

        {/* NAV BAR */}
        <nav style={{
          height: 48,
          background: '#0A1628',
          borderBottom: '1px solid #1E3050',
          display: 'flex',
          alignItems: 'center',
          padding: '0 18px',
          gap: 14,
          flexShrink: 0,
          zIndex: 10,
        }}>
          {/* Logo */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <div style={{
              width: 30,
              height: 30,
              borderRadius: 8,
              background: 'linear-gradient(135deg, #4F8EF7 0%, #9B6DFF 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 15,
              flexShrink: 0,
              boxShadow: '0 2px 10px rgba(79,142,247,0.4)',
            }}>🛡️</div>
            <div>
              <div style={{ color: '#E8F0FF', fontWeight: 700, fontSize: 14, lineHeight: 1.2 }}>FraudShield</div>
              <div style={{ color: '#4A6080', fontSize: 9, lineHeight: 1.2 }}>Real-Time Detection</div>
            </div>
          </div>

          <div style={{ width: 1, height: 24, background: '#1E3050', flexShrink: 0 }} />

          {/* System status pill */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            background: 'rgba(32,201,151,0.08)',
            border: '1px solid rgba(32,201,151,0.2)',
            borderRadius: 20,
            padding: '3px 10px',
            flexShrink: 0,
          }}>
            <span style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: '#20C997',
              boxShadow: '0 0 6px #20C997',
              animation: 'livePulse 2s ease-in-out infinite',
              display: 'inline-block',
            }} />
            <span style={{ color: '#20C997', fontSize: 11, fontWeight: 600 }}>System Online</span>
          </div>

          {/* Quick nav stats */}
          {metrics && (
            <div style={{ display: 'flex', gap: 4, marginLeft: 4 }}>
              {[
                { label: 'Total', value: metrics.total_transactions?.toLocaleString() ?? '—', color: '#4F8EF7' },
                { label: 'Fraud Rate', value: metrics.fraud_rate != null ? (metrics.fraud_rate * 100).toFixed(2) + '%' : '—', color: '#EF4444' },
                { label: 'Latency', value: metrics.avg_latency_ms != null ? Math.round(metrics.avg_latency_ms) + 'ms' : '—', color: '#9B6DFF' },
              ].map(m => (
                <div
                  key={m.label}
                  className="nav-stat"
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    padding: '2px 10px',
                    borderRadius: 6,
                    border: '1px solid #1E3050',
                    transition: 'background 0.15s',
                    cursor: 'default',
                  }}
                >
                  <span style={{ color: m.color, fontWeight: 700, fontSize: 13, lineHeight: 1.2 }}>{m.value}</span>
                  <span style={{ color: '#4A6080', fontSize: 9, lineHeight: 1.2 }}>{m.label}</span>
                </div>
              ))}
            </div>
          )}

          {/* Right: analyst input */}
          <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ color: '#4A6080', fontSize: 11 }}>Analyst:</span>
            <input
              value={analystId}
              onChange={e => setAnalystId(e.target.value)}
              style={{
                background: '#0F1F38',
                border: '1px solid #1E3050',
                borderRadius: 6,
                color: '#8BA3C7',
                fontSize: 12,
                padding: '4px 10px',
                width: 110,
                outline: 'none',
                fontFamily: 'inherit',
              }}
            />
          </div>
        </nav>

        {/* BODY */}
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

          {/* LEFT SIDEBAR */}
          <aside style={{
            width: 268,
            background: '#0A1628',
            borderRight: '1px solid #1E3050',
            overflowY: 'auto',
            padding: '10px 8px',
            flexShrink: 0,
          }}>
            <MetricsCards metrics={metrics} error={metricsError} />
            <TimeSeriesChart data={hourlyStats} />
            <PieChart counts={pieCounts} />
            <RulesBarChart data={rulesData} />
            <HeatmapChart data={heatmapData} />
          </aside>

          {/* CENTER CONTENT */}
          <main style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', minWidth: 0 }}>

            {/* Tab bar */}
            <div style={{
              background: '#0A1628',
              borderBottom: '1px solid #1E3050',
              padding: '0 12px',
              display: 'flex',
              alignItems: 'center',
              gap: 2,
              flexShrink: 0,
              height: 40,
            }}>
              <button
                className={'tab-btn ' + (activeTab === 'feed' ? 'active' : 'inactive')}
                onClick={() => setActiveTab('feed')}
              >
                📡 Live Feed
              </button>
              <button
                className={'tab-btn ' + (activeTab === 'flags' ? 'active' : 'inactive')}
                onClick={() => setActiveTab('flags')}
                style={{ position: 'relative' }}
              >
                🚨 Flag Queue
                {flagCount > 0 && (
                  <span style={{
                    position: 'absolute',
                    top: 3,
                    right: 3,
                    background: '#EF4444',
                    color: '#fff',
                    fontSize: 9,
                    fontWeight: 700,
                    borderRadius: 9999,
                    padding: '1px 5px',
                    lineHeight: 1.4,
                    minWidth: 16,
                    textAlign: 'center',
                  }}>
                    {flagCount}
                  </span>
                )}
              </button>
            </div>

            {/* Tab content */}
            <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', padding: 10, gap: 10 }}>
              {activeTab === 'feed' ? (
                <>
                  {/* Live feed — 55% */}
                  <div style={{ flex: '0 0 55%', minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                    <LiveFeed
                      onSelect={item => setSelectedTx(item.transaction_id)}
                      selectedTxId={selectedTx}
                      onWsItem={item => setWsItems(prev => [item, ...prev].slice(0, 300))}
                    />
                  </div>
                  {/* Map — remaining 45% */}
                  <div style={{ flex: 1, minHeight: 0 }}>
                    <IndiaMap transactions={combinedTransactions} />
                  </div>
                </>
              ) : (
                <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
                  <FlagQueue
                    onSelectTx={setSelectedTx}
                    analystId={analystId}
                    onReviewComplete={handleReviewComplete}
                  />
                </div>
              )}
            </div>
          </main>
        </div>
      </div>

      {/* Transaction detail drawer */}
      <TransactionDrawer
        selectedTxId={selectedTx}
        onClose={() => setSelectedTx(null)}
        analystId={analystId}
        onReviewComplete={handleReviewComplete}
        txnCache={txnCache}
      />
    </>
  )
}
