import { useState, useEffect, useRef } from 'react'
import { fetchTransactionDetail, submitReview } from '../api/client'
import { ShapWaterfall } from './ShapWaterfall'

const DC = {
  APPROVE: '#20C997',
  FLAG:    '#F5A623',
  BLOCK:   '#EF4444',
}
const DC_BG = {
  APPROVE: 'rgba(32,201,151,0.1)',
  FLAG:    'rgba(245,166,35,0.1)',
  BLOCK:   'rgba(239,68,68,0.1)',
}
const RISK_COLOR = {
  LOW:    '#20C997',
  MEDIUM: '#F5A623',
  HIGH:   '#EF4444',
}

const FEATURE_LABELS = {
  amount: 'Amount',
  hour_of_day: 'Hour of Day',
  day_of_week: 'Day of Week',
  txn_count_1h: 'Txn Count (1h)',
  txn_count_24h: 'Txn Count (24h)',
  avg_amount_24h: 'Avg Amount (24h)',
  max_amount_24h: 'Max Amount (24h)',
  amount_vs_avg: 'Amount vs Avg',
  distinct_merchants_24h: 'Distinct Merchants (24h)',
  failed_txn_count_24h: 'Failed Txns (24h)',
  geo_distance_km: 'Geo Distance (km)',
  geo_velocity_kmh: 'Geo Velocity (km/h)',
  time_since_last_txn_seconds: 'Time Since Last Txn (s)',
  merchant_category_enc: 'Merchant Category (enc)',
  is_international: 'Is International',
}

function Spinner() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', padding: 48 }}>
      <div style={{
        width: 28,
        height: 28,
        border: '3px solid #1E3050',
        borderTop: '3px solid #4F8EF7',
        borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
      }} />
    </div>
  )
}

function InfoField({ label, children, mono = false }) {
  return (
    <div>
      <div style={{ color: '#4A6080', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600, marginBottom: 3 }}>
        {label}
      </div>
      <div style={{ color: '#E8F0FF', fontSize: 13, fontFamily: mono ? 'monospace' : 'inherit', wordBreak: mono ? 'break-all' : 'normal', userSelect: mono ? 'text' : 'auto' }}>
        {children}
      </div>
    </div>
  )
}

function RulePill({ rule }) {
  const isHigh = /high|velocity|international|block/i.test(rule)
  const isMed  = /amount|freq|limit/i.test(rule)
  const color  = isHigh ? '#EF4444' : isMed ? '#F5A623' : '#4F8EF7'
  return (
    <span style={{
      display: 'inline-block',
      background: color + '18',
      color: color,
      border: `1px solid ${color}44`,
      borderRadius: 5,
      padding: '3px 9px',
      fontSize: 11,
      fontFamily: 'monospace',
      fontWeight: 500,
    }}>
      {rule}
    </span>
  )
}

function FeatureVector({ featureVector }) {
  const [open, setOpen] = useState(false)
  if (!featureVector || Object.keys(featureVector).length === 0) return null
  return (
    <div>
      <button
        className="collapse-btn"
        onClick={() => setOpen(v => !v)}
        style={{
          background: 'none',
          border: '1px solid #1E3050',
          color: '#4A6080',
          borderRadius: 5,
          padding: '4px 12px',
          fontSize: 11,
          cursor: 'pointer',
          marginBottom: 8,
          transition: 'color 0.15s',
          fontFamily: 'inherit',
        }}
      >
        {open ? '▲ Hide' : '▼ Show'} features ({Object.keys(featureVector).length})
      </button>
      {open && (
        <div style={{
          background: '#05091A',
          borderRadius: 6,
          border: '1px solid #1E3050',
          overflow: 'hidden',
        }}>
          {Object.entries(featureVector).map(([key, val], i) => (
            <div key={key} style={{
              display: 'flex',
              justifyContent: 'space-between',
              padding: '5px 12px',
              background: i % 2 === 0 ? 'transparent' : 'rgba(14,31,56,0.4)',
              fontSize: 11,
              fontFamily: 'monospace',
            }}>
              <span style={{ color: '#8BA3C7' }}>{FEATURE_LABELS[key] || key}</span>
              <span style={{ color: '#E8F0FF' }}>{typeof val === 'number' ? val.toFixed(4) : String(val)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function TransactionDrawer({ selectedTxId, onClose, analystId = 'analyst-1', onReviewComplete, txnCache }) {
  const [detail, setDetail]           = useState(null)
  const [fallback, setFallback]       = useState(null)
  const [loading, setLoading]         = useState(false)
  const [partialData, setPartialData] = useState(false)
  const [error, setError]             = useState(null)
  const [copied, setCopied]           = useState(false)
  const [reviewStatus, setReviewStatus]   = useState(null)
  const [reviewError, setReviewError]     = useState(null)
  const attemptRef = useRef(0)

  useEffect(() => {
    if (!selectedTxId) {
      setDetail(null)
      setFallback(null)
      setError(null)
      setPartialData(false)
      setReviewStatus(null)
      setReviewError(null)
      return
    }

    let cancelled = false
    setDetail(null)
    setError(null)
    setPartialData(false)
    setLoading(true)
    setReviewStatus(null)
    setReviewError(null)

    // Immediately show cached data if available (avoids blank state on 404)
    const cached = txnCache?.get(selectedTxId) || null
    setFallback(cached)

    const MAX_ATTEMPTS = 3
    const RETRY_MS = 800

    async function fetchWithRetry(attempt) {
      if (cancelled) return
      try {
        const data = await fetchTransactionDetail(selectedTxId)
        if (!cancelled) {
          setDetail(data)
          setFallback(null)
          setPartialData(false)
          setLoading(false)
        }
      } catch (err) {
        if (cancelled) return
        if (attempt < MAX_ATTEMPTS) {
          setTimeout(() => fetchWithRetry(attempt + 1), RETRY_MS)
        } else {
          // All retries failed
          if (cached) {
            setPartialData(true)
            setLoading(false)
          } else {
            setError(err.message || 'Failed to load transaction detail')
            setLoading(false)
          }
        }
      }
    }

    fetchWithRetry(1)
    return () => { cancelled = true }
  }, [selectedTxId, txnCache])

  async function handleReview(decision) {
    if (reviewStatus === 'pending' || reviewStatus === 'done') return
    setReviewStatus('pending')
    setReviewError(null)
    try {
      await submitReview(selectedTxId, decision, analystId)
      setReviewStatus('done')
      if (onReviewComplete) onReviewComplete(selectedTxId, decision)
    } catch (err) {
      setReviewStatus('error')
      setReviewError(err.message || 'Review submission failed')
    }
  }

  function copyId() {
    const id = (detail || fallback)?.transaction_id
    if (!id) return
    navigator.clipboard.writeText(id).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    })
  }

  // Display data = full detail or fallback (partial)
  const data = detail || (partialData ? fallback : null)

  return (
    <>
      {/* Backdrop */}
      {selectedTxId && (
        <div
          onClick={onClose}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.55)',
            zIndex: 40,
          }}
        />
      )}

      {/* Drawer */}
      <div style={{
        position: 'fixed',
        top: 0,
        right: 0,
        width: 560,
        height: '100vh',
        background: '#0A1628',
        borderLeft: '1px solid #1E3050',
        zIndex: 50,
        transform: selectedTxId ? 'translateX(0)' : 'translateX(100%)',
        transition: 'transform 0.25s cubic-bezier(0.4,0,0.2,1)',
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
      }}>

        {/* ── HEADER ── */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '14px 20px',
          borderBottom: '1px solid #1E3050',
          flexShrink: 0,
          background: '#081221',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ color: '#E8F0FF', fontWeight: 700, fontSize: 15 }}>
              Transaction Detail
            </span>
            {(detail || fallback) && (
              <button
                className="copy-btn"
                onClick={copyId}
                title="Copy transaction ID"
                style={{
                  background: copied ? 'rgba(32,201,151,0.12)' : 'rgba(79,142,247,0.08)',
                  border: `1px solid ${copied ? 'rgba(32,201,151,0.3)' : '#1E3050'}`,
                  borderRadius: 5,
                  color: copied ? '#20C997' : '#4A6080',
                  fontSize: 11,
                  padding: '3px 9px',
                  cursor: 'pointer',
                  transition: 'all 0.15s',
                  fontFamily: 'inherit',
                }}
              >
                {copied ? '✓ Copied' : '⎘ Copy ID'}
              </button>
            )}
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'rgba(255,255,255,0.04)',
              border: '1px solid #1E3050',
              color: '#4A6080',
              fontSize: 18,
              cursor: 'pointer',
              lineHeight: 1,
              padding: '2px 8px',
              borderRadius: 5,
              transition: 'color 0.15s, background 0.15s',
              fontFamily: 'inherit',
            }}
            aria-label="Close drawer"
          >
            ×
          </button>
        </div>

        {/* ── CONTENT ── */}
        {loading && !fallback && <Spinner />}

        {partialData && (
          <div style={{
            padding: '6px 20px',
            background: 'rgba(245,166,35,0.08)',
            borderBottom: '1px solid rgba(245,166,35,0.2)',
            color: '#F5A623',
            fontSize: 11,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}>
            <span>⚠️</span>
            <span>Partial data — full record still loading. Retrying…</span>
          </div>
        )}

        {error && !data && (
          <div style={{ padding: 24, color: '#EF4444', fontSize: 13 }}>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Failed to load transaction</div>
            <div style={{ color: '#8BA3C7', fontSize: 11 }}>{error}</div>
          </div>
        )}

        {data && (
          <>
            {/* Decision banner */}
            <div style={{
              padding: '14px 20px',
              background: DC_BG[data.decision] || 'rgba(79,142,247,0.08)',
              borderBottom: `2px solid ${DC[data.decision] || '#1E3050'}`,
              display: 'flex',
              alignItems: 'center',
              gap: 20,
              flexShrink: 0,
            }}>
              <div>
                <div style={{ color: '#4A6080', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 600, marginBottom: 2 }}>
                  Decision
                </div>
                <div style={{
                  color: DC[data.decision] || '#8BA3C7',
                  fontSize: 18,
                  fontWeight: 800,
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                }}>
                  {data.decision}
                </div>
              </div>
              <div style={{ borderLeft: '1px solid #1E3050', height: 36, flexShrink: 0 }} />
              <div>
                <div style={{ color: '#4A6080', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 600, marginBottom: 2 }}>
                  Fraud Probability
                </div>
                <div style={{
                  fontSize: 34,
                  fontWeight: 800,
                  color: data.fraud_probability > 0.7 ? '#EF4444'
                       : data.fraud_probability > 0.3 ? '#F5A623'
                       : '#20C997',
                  lineHeight: 1,
                }}>
                  {data.fraud_probability != null ? `${(data.fraud_probability * 100).toFixed(1)}%` : '—'}
                </div>
              </div>
            </div>

            {/* Risk gauge */}
            {data.fraud_probability != null && (
              <div style={{ padding: '12px 20px', borderBottom: '1px solid #1E3050', flexShrink: 0 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                  <span style={{ color: '#4A6080', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600 }}>
                    Risk Level
                  </span>
                  <span style={{ color: '#8BA3C7', fontSize: 10 }}>
                    {data.risk_level || (data.fraud_probability > 0.7 ? 'HIGH' : data.fraud_probability > 0.3 ? 'MEDIUM' : 'LOW')}
                  </span>
                </div>
                <div style={{ height: 8, borderRadius: 4, background: '#1E3050', overflow: 'hidden' }}>
                  <div style={{
                    height: '100%',
                    width: `${Math.min((data.fraud_probability || 0) * 100, 100)}%`,
                    borderRadius: 4,
                    background: `linear-gradient(90deg, #20C997 0%, #F5A623 50%, #EF4444 100%)`,
                    backgroundSize: '100% 100%',
                    backgroundAttachment: 'fixed',
                    transition: 'width 0.5s ease',
                  }} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 3 }}>
                  <span style={{ color: '#20C997', fontSize: 9 }}>Low Risk</span>
                  <span style={{ color: '#EF4444', fontSize: 9 }}>High Risk</span>
                </div>
              </div>
            )}

            {/* Info grid */}
            <div style={{ padding: '14px 20px', borderBottom: '1px solid #1E3050' }}>
              <div style={{ color: '#4A6080', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 600, marginBottom: 10 }}>
                Transaction Info
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px 20px' }}>
                <InfoField label="Transaction ID" mono>
                  <span style={{ fontSize: 11 }}>{data.transaction_id}</span>
                </InfoField>
                <InfoField label="User ID">
                  {data.user_id || '—'}
                </InfoField>
                <InfoField label="Amount">
                  <span style={{ color: '#E8F0FF', fontWeight: 700 }}>
                    ₹{typeof data.amount === 'number'
                      ? data.amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                      : data.amount || '—'}
                  </span>
                </InfoField>
                <InfoField label="Decision">
                  <span style={{
                    display: 'inline-block',
                    background: DC_BG[data.decision] || 'transparent',
                    color: DC[data.decision] || '#8BA3C7',
                    border: `1px solid ${(DC[data.decision] || '#4A6080') + '55'}`,
                    borderRadius: 5,
                    padding: '2px 9px',
                    fontSize: 11,
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.06em',
                  }}>
                    {data.decision}
                  </span>
                </InfoField>
                <InfoField label="Risk Level">
                  {data.risk_level ? (
                    <span style={{ color: RISK_COLOR[data.risk_level] || '#8BA3C7', fontWeight: 700 }}>
                      {data.risk_level}
                    </span>
                  ) : '—'}
                </InfoField>
                <InfoField label="Timestamp">
                  <span style={{ fontSize: 12 }}>
                    {data.created_at ? new Date(data.created_at).toLocaleString() : '—'}
                  </span>
                </InfoField>
                {(data.location_lat != null && data.location_lng != null) && (
                  <InfoField label="Location">
                    <span style={{ fontSize: 12, fontFamily: 'monospace' }}>
                      {data.location_lat.toFixed(4)}, {data.location_lng.toFixed(4)}
                    </span>
                  </InfoField>
                )}
                {data.processing_latency_ms != null && (
                  <InfoField label="Latency">
                    <span style={{ color: data.processing_latency_ms > 500 ? '#F5A623' : '#20C997', fontWeight: 600 }}>
                      {data.processing_latency_ms} ms
                    </span>
                  </InfoField>
                )}
              </div>
            </div>

            {/* Rules Triggered */}
            <div style={{ padding: '12px 20px', borderBottom: '1px solid #1E3050' }}>
              <div style={{ color: '#4A6080', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 600, marginBottom: 8 }}>
                Rules Triggered
              </div>
              {data.fired_rules && data.fired_rules.length > 0 ? (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {data.fired_rules.map((rule, i) => (
                    <RulePill key={i} rule={rule} />
                  ))}
                </div>
              ) : (
                <div style={{ color: '#4A6080', fontSize: 13 }}>No rules triggered</div>
              )}
            </div>

            {/* SHAP Explanation */}
            {data.shap_values && data.shap_values.length > 0 && (
              <div style={{ padding: '12px 20px', borderBottom: '1px solid #1E3050' }}>
                <ShapWaterfall shapValues={data.shap_values} />
              </div>
            )}

            {/* Feature Vector (collapsible) */}
            {data.feature_vector && Object.keys(data.feature_vector).length > 0 && (
              <div style={{ padding: '12px 20px', borderBottom: '1px solid #1E3050' }}>
                <div style={{ color: '#4A6080', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 600, marginBottom: 8 }}>
                  Feature Vector
                </div>
                <FeatureVector featureVector={data.feature_vector} />
              </div>
            )}

            {/* Analyst Review — FLAG only */}
            {data.decision === 'FLAG' && (
              <div style={{ padding: '14px 20px', borderBottom: '1px solid #1E3050' }}>
                <div style={{ color: '#4A6080', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 600, marginBottom: 10 }}>
                  Analyst Review
                </div>
                {data.analyst_decision ? (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ color: '#8BA3C7', fontSize: 13 }}>Previously reviewed:</span>
                    <span style={{
                      background: (data.analyst_decision === 'CONFIRMED_FRAUD' ? '#EF4444' : '#20C997') + '20',
                      color: data.analyst_decision === 'CONFIRMED_FRAUD' ? '#EF4444' : '#20C997',
                      border: `1px solid ${data.analyst_decision === 'CONFIRMED_FRAUD' ? '#EF4444' : '#20C997'}44`,
                      borderRadius: 5,
                      padding: '3px 10px',
                      fontSize: 12,
                      fontWeight: 700,
                    }}>
                      {data.analyst_decision}
                    </span>
                  </div>
                ) : reviewStatus === 'done' ? (
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    color: '#20C997',
                    fontSize: 13,
                    background: 'rgba(32,201,151,0.08)',
                    border: '1px solid rgba(32,201,151,0.2)',
                    borderRadius: 7,
                    padding: '8px 14px',
                  }}>
                    <span>✓</span>
                    <span>Review submitted successfully</span>
                  </div>
                ) : (
                  <div>
                    <div style={{ color: '#8BA3C7', fontSize: 12, marginBottom: 10 }}>
                      Analyst <strong style={{ color: '#E8F0FF' }}>{analystId}</strong> — choose your verdict:
                    </div>
                    <div style={{ display: 'flex', gap: 10 }}>
                      <button
                        className="review-btn-confirm"
                        onClick={() => handleReview('CONFIRMED_FRAUD')}
                        disabled={reviewStatus === 'pending'}
                        style={{
                          background: reviewStatus === 'pending' ? '#1E3050' : '#EF4444',
                          color: '#fff',
                          border: 'none',
                          borderRadius: 7,
                          padding: '9px 18px',
                          fontSize: 13,
                          fontWeight: 700,
                          cursor: reviewStatus === 'pending' ? 'not-allowed' : 'pointer',
                          opacity: reviewStatus === 'pending' ? 0.6 : 1,
                          transition: 'filter 0.15s, background 0.15s',
                          fontFamily: 'inherit',
                        }}
                      >
                        {reviewStatus === 'pending' ? '⏳ Submitting…' : '🚫 Confirm Fraud'}
                      </button>
                      <button
                        className="review-btn-fp"
                        onClick={() => handleReview('FALSE_POSITIVE')}
                        disabled={reviewStatus === 'pending'}
                        style={{
                          background: reviewStatus === 'pending' ? '#1E3050' : '#20C997',
                          color: '#fff',
                          border: 'none',
                          borderRadius: 7,
                          padding: '9px 18px',
                          fontSize: 13,
                          fontWeight: 700,
                          cursor: reviewStatus === 'pending' ? 'not-allowed' : 'pointer',
                          opacity: reviewStatus === 'pending' ? 0.6 : 1,
                          transition: 'filter 0.15s, background 0.15s',
                          fontFamily: 'inherit',
                        }}
                      >
                        {reviewStatus === 'pending' ? '⏳ Submitting…' : '✅ False Positive'}
                      </button>
                    </div>
                    {reviewError && (
                      <div style={{
                        color: '#EF4444',
                        fontSize: 12,
                        marginTop: 8,
                        background: 'rgba(239,68,68,0.08)',
                        border: '1px solid rgba(239,68,68,0.2)',
                        borderRadius: 5,
                        padding: '5px 10px',
                      }}>
                        {reviewError}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Bottom padding */}
            <div style={{ height: 32 }} />
          </>
        )}
      </div>
    </>
  )
}
