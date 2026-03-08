import { useState, useEffect, useRef } from 'react'
import { fetchFlagQueue } from '../api/client'

function probColor(prob) {
  if (prob > 0.7) return '#EF4444'
  if (prob > 0.3) return '#F5A623'
  return '#20C997'
}

function priorityLabel(prob) {
  if (prob > 0.7) return 'HIGH'
  return 'MEDIUM'
}

function formatTime(ts) {
  if (!ts) return '—'
  const d = new Date(ts)
  const now = new Date()
  const diffMs = now - d
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  return d.toLocaleTimeString()
}

function SkeletonRow({ cols }) {
  return (
    <tr>
      {[...Array(cols)].map((_, i) => (
        <td key={i} style={{ padding: '10px 12px' }}>
          <div style={{
            height: 11,
            background: '#1E3050',
            borderRadius: 3,
            width: i === 0 ? 50 : i === 1 ? 110 : i === 2 ? 70 : 60,
            animation: 'pulse 1.5s ease-in-out infinite',
          }} />
        </td>
      ))}
    </tr>
  )
}

export function FlagQueue({ onSelectTx, analystId, onReviewComplete }) {
  const [queue, setQueue]                     = useState([])
  const [loading, setLoading]                 = useState(true)
  const [lastRefreshed, setLastRefreshed]     = useState(null)
  const [optimisticRemoved, setOptimisticRemoved] = useState(new Set())
  const intervalRef = useRef(null)

  function load() {
    fetchFlagQueue()
      .then(data => {
        const sorted = [...data].sort((a, b) => (b.fraud_probability || 0) - (a.fraud_probability || 0))
        setQueue(sorted)
        setLoading(false)
        setLastRefreshed(new Date())
        setOptimisticRemoved(prev => {
          const freshIds = new Set(sorted.map(t => t.transaction_id))
          return new Set([...prev].filter(id => freshIds.has(id)))
        })
      })
      .catch(err => {
        console.warn('[FlagQueue] fetch error', err)
        setLoading(false)
      })
  }

  useEffect(() => {
    load()
    intervalRef.current = setInterval(load, 10000)
    return () => clearInterval(intervalRef.current)
  }, [])

  const visibleQueue = queue.filter(t => !optimisticRemoved.has(t.transaction_id))

  const thStyle = {
    padding: '8px 12px',
    textAlign: 'left',
    color: '#4A6080',
    fontSize: 10,
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    borderBottom: '1px solid #1E3050',
    background: '#081221',
    position: 'sticky',
    top: 0,
    zIndex: 1,
    whiteSpace: 'nowrap',
  }

  const tdStyle = {
    padding: '9px 12px',
    color: '#8BA3C7',
    fontSize: 13,
    borderBottom: '1px solid #0A1628',
    verticalAlign: 'middle',
  }

  return (
    <div style={{
      width: '100%',
      height: '100%',
      background: '#0F1F38',
      borderRadius: 10,
      border: '1px solid #1E3050',
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* Header */}
      <div style={{
        background: '#0A1628',
        padding: '10px 16px',
        borderBottom: '1px solid #1E3050',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        flexShrink: 0,
      }}>
        <span style={{ color: '#E8F0FF', fontWeight: 700, fontSize: 14 }}>🚨 FLAG Queue</span>
        <span style={{
          background: visibleQueue.length > 0 ? 'rgba(245,166,35,0.15)' : '#0F1F38',
          color: visibleQueue.length > 0 ? '#F5A623' : '#4A6080',
          border: `1px solid ${visibleQueue.length > 0 ? 'rgba(245,166,35,0.35)' : '#1E3050'}`,
          borderRadius: 12,
          padding: '2px 10px',
          fontSize: 12,
          fontWeight: 700,
        }}>
          {visibleQueue.length} unreviewed
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 10 }}>
          {lastRefreshed && (
            <span style={{ color: '#4A6080', fontSize: 11 }}>
              Updated {formatTime(lastRefreshed)}
            </span>
          )}
          <button
            onClick={load}
            style={{
              background: 'rgba(79,142,247,0.08)',
              border: '1px solid #1E3050',
              color: '#4F8EF7',
              borderRadius: 5,
              padding: '4px 12px',
              fontSize: 11,
              cursor: 'pointer',
              fontWeight: 600,
              fontFamily: 'inherit',
            }}
          >
            ↻ Refresh
          </button>
        </div>
      </div>

      {/* Table or empty state */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {loading ? (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {['Priority', 'Transaction ID', 'User', 'Amount', 'Fraud %', 'Rules', 'Time', 'Action'].map(h => (
                  <th key={h} style={thStyle}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              <SkeletonRow cols={8} />
              <SkeletonRow cols={8} />
              <SkeletonRow cols={8} />
            </tbody>
          </table>
        ) : visibleQueue.length === 0 ? (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            minHeight: 200,
            gap: 14,
            color: '#4A6080',
          }}>
            <div style={{ fontSize: 48 }}>✅</div>
            <div style={{ fontSize: 18, fontWeight: 700, color: '#8BA3C7' }}>All Clear</div>
            <div style={{ fontSize: 13 }}>No unreviewed FLAG transactions in queue</div>
          </div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                {['Priority', 'Transaction ID', 'User', 'Amount', 'Fraud %', 'Rules', 'Time', 'Action'].map(h => (
                  <th key={h} style={thStyle}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleQueue.map(item => {
                const prob = item.fraud_probability || 0
                const color = probColor(prob)
                const pLabel = priorityLabel(prob)
                return (
                  <tr
                    key={item.transaction_id}
                    className="flag-row"
                    onClick={() => onSelectTx && onSelectTx(item.transaction_id)}
                    style={{
                      cursor: 'pointer',
                      background: 'transparent',
                      transition: 'background 0.12s',
                      borderLeft: `3px solid ${color}66`,
                    }}
                  >
                    {/* Priority */}
                    <td style={tdStyle}>
                      <span style={{
                        display: 'inline-block',
                        background: color + '18',
                        color: color,
                        border: `1px solid ${color}44`,
                        borderRadius: 5,
                        padding: '2px 8px',
                        fontSize: 10,
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                        whiteSpace: 'nowrap',
                      }}>
                        {pLabel}
                      </span>
                    </td>

                    {/* Transaction ID */}
                    <td style={{ ...tdStyle, fontFamily: 'monospace', fontSize: 11, color: '#4A6080' }}>
                      {item.transaction_id?.slice(0, 16)}…
                    </td>

                    {/* User */}
                    <td style={{ ...tdStyle, color: '#8BA3C7' }}>
                      {item.user_id || '—'}
                    </td>

                    {/* Amount */}
                    <td style={{ ...tdStyle, color: '#E8F0FF', fontWeight: 600, whiteSpace: 'nowrap' }}>
                      ₹{typeof item.amount === 'number'
                        ? item.amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                        : item.amount || '—'}
                    </td>

                    {/* Fraud % */}
                    <td style={{ ...tdStyle, whiteSpace: 'nowrap' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                        <span style={{ color, fontWeight: 700, fontSize: 13 }}>
                          {item.fraud_probability != null ? `${(prob * 100).toFixed(1)}%` : '—'}
                        </span>
                        <div style={{ height: 3, width: 56, background: '#1E3050', borderRadius: 2, overflow: 'hidden' }}>
                          <div style={{
                            height: '100%',
                            width: `${Math.min(prob * 100, 100)}%`,
                            background: color,
                            borderRadius: 2,
                          }} />
                        </div>
                      </div>
                    </td>

                    {/* Rules count */}
                    <td style={tdStyle}>
                      {item.fired_rules?.length > 0 ? (
                        <span style={{
                          background: 'rgba(79,142,247,0.1)',
                          color: '#4F8EF7',
                          border: '1px solid rgba(79,142,247,0.25)',
                          borderRadius: 4,
                          padding: '1px 7px',
                          fontSize: 11,
                          fontWeight: 600,
                        }}>
                          {item.fired_rules.length} rules
                        </span>
                      ) : (
                        <span style={{ color: '#4A6080', fontSize: 11 }}>none</span>
                      )}
                    </td>

                    {/* Time */}
                    <td style={{ ...tdStyle, fontSize: 11, color: '#4A6080', whiteSpace: 'nowrap' }}>
                      {formatTime(item.created_at)}
                    </td>

                    {/* Action */}
                    <td style={tdStyle} onClick={e => e.stopPropagation()}>
                      <button
                        onClick={() => onSelectTx && onSelectTx(item.transaction_id)}
                        style={{
                          background: 'rgba(245,166,35,0.12)',
                          border: '1px solid rgba(245,166,35,0.3)',
                          color: '#F5A623',
                          borderRadius: 5,
                          padding: '4px 12px',
                          fontSize: 11,
                          cursor: 'pointer',
                          fontWeight: 700,
                          transition: 'filter 0.15s',
                          fontFamily: 'inherit',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        Review →
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
