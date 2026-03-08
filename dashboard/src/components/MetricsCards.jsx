import { useState, useEffect, useRef } from 'react'

const CARDS = [
  {
    key: 'total_transactions',
    label: 'Total Txns',
    icon: '📊',
    color: '#4F8EF7',
    format: v => v?.toLocaleString() ?? '—',
  },
  {
    key: 'fraud_rate',
    label: 'Fraud Rate',
    icon: '⚠️',
    color: '#EF4444',
    format: v => v != null ? (v * 100).toFixed(2) + '%' : '—',
  },
  {
    key: 'approved_count',
    label: 'Approved',
    icon: '✅',
    color: '#20C997',
    format: v => v?.toLocaleString() ?? '—',
  },
  {
    key: 'blocked_count',
    label: 'Blocked',
    icon: '🚫',
    color: '#EF4444',
    format: v => v?.toLocaleString() ?? '—',
  },
  {
    key: 'flagged_count',
    label: 'Flagged',
    icon: '🚩',
    color: '#F5A623',
    format: v => v?.toLocaleString() ?? '—',
  },
  {
    key: 'review_queue_count',
    label: 'Queue',
    icon: '🔍',
    color: '#F5A623',
    format: v => v?.toLocaleString() ?? '—',
  },
]

function AnimatedNumber({ target, color, format }) {
  const [display, setDisplay] = useState(target)
  const prevRef = useRef(target)

  useEffect(() => {
    if (target == null) return
    const start = prevRef.current ?? 0
    const end = target
    prevRef.current = end

    if (typeof end !== 'number') {
      setDisplay(end)
      return
    }

    const steps = 24
    const duration = 500
    const stepMs = duration / steps
    let step = 0

    const timer = setInterval(() => {
      step++
      const progress = step / steps
      const eased = 1 - Math.pow(1 - progress, 3) // ease-out cubic
      const current = start + (end - start) * eased
      setDisplay(current)
      if (step >= steps) {
        setDisplay(end)
        clearInterval(timer)
      }
    }, stepMs)

    return () => clearInterval(timer)
  }, [target])

  return (
    <span style={{ color, fontSize: 20, fontWeight: 700, lineHeight: 1.1 }}>
      {format(display)}
    </span>
  )
}

function SkeletonCard() {
  return (
    <div style={{
      background: '#0F1F38',
      borderRadius: 8,
      padding: 10,
      border: '1px solid #1E3050',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
        <div style={{ width: 16, height: 16, background: '#1E3050', borderRadius: 4, animation: 'pulse 1.5s infinite' }} />
        <div style={{ width: 50, height: 9, background: '#1E3050', borderRadius: 3, animation: 'pulse 1.5s infinite' }} />
      </div>
      <div style={{ width: '70%', height: 20, background: '#1E3050', borderRadius: 3, animation: 'pulse 1.5s infinite' }} />
    </div>
  )
}

export function MetricsCards({ metrics, error }) {
  if (!metrics) {
    return (
      <div style={{ marginBottom: 12 }}>
        <div style={{ color: '#4A6080', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600, marginBottom: 8, paddingLeft: 2 }}>
          Metrics
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
          {CARDS.map(c => <SkeletonCard key={c.key} />)}
        </div>
      </div>
    )
  }

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ color: '#4A6080', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600, marginBottom: 8, paddingLeft: 2 }}>
        Metrics
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
        {CARDS.map(card => (
          <div
            key={card.key}
            style={{
              background: '#0F1F38',
              borderRadius: 8,
              padding: 10,
              border: '1px solid #1E3050',
              transition: 'border-color 0.2s',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 5 }}>
              <span style={{ fontSize: 12 }}>{card.icon}</span>
              <span style={{ color: '#4A6080', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 600 }}>
                {card.label}
              </span>
            </div>
            <AnimatedNumber
              target={metrics[card.key] ?? null}
              color={card.color}
              format={card.format}
            />
          </div>
        ))}
      </div>
      {error && (
        <div style={{ color: '#EF4444', fontSize: 10, marginTop: 6, padding: '4px 6px', background: 'rgba(239,68,68,0.08)', borderRadius: 4, border: '1px solid rgba(239,68,68,0.2)' }}>
          {error}
        </div>
      )}
    </div>
  )
}
