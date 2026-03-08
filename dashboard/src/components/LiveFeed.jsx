import { useState, useRef, useEffect, useCallback } from 'react'

const DECISION_COLOR = {
  APPROVE: '#20C997',
  FLAG:    '#F5A623',
  BLOCK:   '#EF4444',
}
const DECISION_BG = {
  APPROVE: 'rgba(32,201,151,0.1)',
  FLAG:    'rgba(245,166,35,0.1)',
  BLOCK:   'rgba(239,68,68,0.1)',
}

function DecisionBadge({ decision }) {
  const c = DECISION_COLOR[decision] || '#8BA3C7'
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      background: (DECISION_BG[decision] || 'transparent'),
      color: c,
      fontSize: '0.65rem',
      fontWeight: 700,
      padding: '2px 7px',
      borderRadius: 9999,
      textTransform: 'uppercase',
      letterSpacing: '0.07em',
      border: `1px solid ${c}55`,
      flexShrink: 0,
      whiteSpace: 'nowrap',
    }}>
      {decision}
    </span>
  )
}

export function LiveFeed({ onSelect, selectedTxId, onWsItem }) {
  const [items, setItems] = useState([])
  const [connected, setConnected] = useState(false)
  const [paused, setPaused] = useState(false)
  const feedRef   = useRef(null)
  const pausedRef = useRef(false)
  const wsRef     = useRef(null)
  const retryRef  = useRef(null)
  const unmounted = useRef(false)

  const addItem = useCallback((data) => {
    setItems(prev => [data, ...prev].slice(0, 300))
    if (onWsItem) onWsItem(data)
  }, [onWsItem])

  const connect = useCallback(() => {
    if (unmounted.current) return
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/live`)
    wsRef.current = ws

    ws.onopen  = () => setConnected(true)
    ws.onerror = () => setConnected(false)
    ws.onclose = () => {
      setConnected(false)
      if (!unmounted.current) retryRef.current = setTimeout(connect, 3000)
    }
    ws.onmessage = (e) => {
      try { addItem(JSON.parse(e.data)) } catch {}
    }
  }, [addItem])

  useEffect(() => {
    unmounted.current = false
    connect()
    return () => {
      unmounted.current = true
      clearTimeout(retryRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  useEffect(() => {
    if (!pausedRef.current && feedRef.current) {
      feedRef.current.scrollTop = 0
    }
  }, [items.length])

  function handleMouseEnter() { pausedRef.current = true;  setPaused(true) }
  function handleMouseLeave() { pausedRef.current = false; setPaused(false) }

  return (
    <div style={{
      background: '#0F1F38',
      borderRadius: 10,
      border: '1px solid #1E3050',
      display: 'flex',
      flexDirection: 'column',
      flex: 1,
      minHeight: 0,
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        padding: '8px 14px',
        borderBottom: '1px solid #1E3050',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexShrink: 0,
        background: '#0A1628',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ color: '#E8F0FF', fontSize: '0.82rem', fontWeight: 600 }}>
            Transaction Stream
          </span>
          {items.length > 0 && (
            <span style={{
              background: '#05091A',
              color: '#4A6080',
              fontSize: '0.65rem',
              padding: '1px 7px',
              borderRadius: 9999,
              border: '1px solid #1E3050',
              fontWeight: 600,
            }}>
              {items.length}
            </span>
          )}
          {paused && (
            <span style={{
              fontSize: '0.65rem',
              color: '#F5A623',
              background: 'rgba(245,166,35,0.1)',
              border: '1px solid rgba(245,166,35,0.3)',
              padding: '1px 8px',
              borderRadius: 9999,
              fontWeight: 600,
            }}>
              ⏸ paused
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{
            width: 6, height: 6, borderRadius: '50%',
            background: connected ? '#20C997' : '#F5A623',
            boxShadow: connected ? '0 0 6px #20C997' : 'none',
            animation: connected ? 'livePulse 2s ease-in-out infinite' : 'none',
            display: 'inline-block',
          }} />
          <span style={{ color: connected ? '#20C997' : '#F5A623', fontSize: '0.7rem', fontWeight: 500 }}>
            {connected ? 'Live' : 'Reconnecting…'}
          </span>
        </div>
      </div>

      {/* Column headers */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '130px 90px 1fr 90px 80px 72px',
        padding: '5px 12px 5px 16px',
        borderBottom: '1px solid #1E3050',
        background: '#081221',
        flexShrink: 0,
        gap: 6,
      }}>
        {['ID', 'User', 'Amount', 'Decision', 'Fraud %', 'Time'].map(h => (
          <span key={h} style={{ color: '#4A6080', fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 600 }}>
            {h}
          </span>
        ))}
      </div>

      {/* Feed rows */}
      <div
        ref={feedRef}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        style={{ overflowY: 'auto', flex: 1, minHeight: 0 }}
      >
        {items.length === 0 ? (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            minHeight: 120,
            color: '#4A6080',
            gap: 8,
          }}>
            <div style={{ fontSize: '1.8rem' }}>📡</div>
            <div style={{ fontSize: '0.8rem', color: '#4A6080' }}>Waiting for live decisions…</div>
          </div>
        ) : (
          items.map((item, idx) => {
            const isSelected  = item.transaction_id === selectedTxId
            const borderColor = DECISION_COLOR[item.decision] || '#1E3050'
            const fraudPct    = item.fraud_probability != null ? item.fraud_probability * 100 : null
            const fraudColor  = item.fraud_probability > 0.7 ? '#EF4444' : item.fraud_probability > 0.3 ? '#F5A623' : '#20C997'

            return (
              <div
                key={item.transaction_id || idx}
                className="feed-row"
                onClick={() => onSelect && onSelect(item)}
                style={{
                  borderLeft: `3px solid ${isSelected ? borderColor : borderColor + '55'}`,
                  padding: '6px 12px 6px 13px',
                  borderBottom: '1px solid #0A1628',
                  cursor: 'pointer',
                  display: 'grid',
                  gridTemplateColumns: '130px 90px 1fr 90px 80px 72px',
                  alignItems: 'center',
                  gap: 6,
                  background: isSelected
                    ? `${DECISION_BG[item.decision] || 'rgba(79,142,247,0.08)'}`
                    : 'transparent',
                  transition: 'background 0.1s',
                  animation: idx === 0 ? 'fadeSlideIn 0.25s ease' : 'none',
                }}
              >
                {/* ID */}
                <span style={{
                  color: '#4A6080',
                  fontSize: '0.7rem',
                  fontFamily: 'monospace',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}>
                  {(item.transaction_id || '').slice(0, 13)}…
                </span>

                {/* User */}
                <span style={{
                  color: '#8BA3C7',
                  fontSize: '0.72rem',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}>
                  {item.user_id || '—'}
                </span>

                {/* Amount */}
                <span style={{ color: '#E8F0FF', fontSize: '0.82rem', fontWeight: 600 }}>
                  ₹{Number(item.amount || 0).toLocaleString('en-IN')}
                </span>

                {/* Decision badge */}
                <DecisionBadge decision={item.decision} />

                {/* Fraud % mini bar */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {fraudPct != null ? (
                    <>
                      <div style={{
                        height: 3,
                        borderRadius: 2,
                        background: '#1E3050',
                        overflow: 'hidden',
                      }}>
                        <div style={{
                          height: '100%',
                          width: `${Math.min(fraudPct, 100)}%`,
                          background: fraudColor,
                          borderRadius: 2,
                          transition: 'width 0.3s ease',
                        }} />
                      </div>
                      <span style={{ color: fraudColor, fontSize: '0.6rem', fontWeight: 700, lineHeight: 1 }}>
                        {fraudPct.toFixed(1)}%
                      </span>
                    </>
                  ) : (
                    <span style={{ color: '#4A6080', fontSize: '0.6rem' }}>—</span>
                  )}
                </div>

                {/* Time */}
                <span style={{ color: '#4A6080', fontSize: '0.65rem', textAlign: 'right', whiteSpace: 'nowrap' }}>
                  {new Date(item.timestamp || item.created_at || Date.now()).toLocaleTimeString()}
                </span>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
