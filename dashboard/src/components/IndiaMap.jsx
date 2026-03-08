import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'

const DECISION_COLORS = {
  APPROVE: '#20C997',
  FLAG:    '#F5A623',
  BLOCK:   '#EF4444',
}
const DECISION_RADIUS = { APPROVE: 4, FLAG: 6, BLOCK: 8 }

const DARK_TILE = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
const DARK_ATTR = '&copy; <a href="https://carto.com" target="_blank">CARTO</a>'

export function IndiaMap({ transactions = [] }) {
  const plotted = transactions
    .filter(t => t.location_lat != null && t.location_lng != null)
    .slice(0, 200)

  // Latest 3 get pulse ring
  const latestIds = new Set(
    transactions.filter(t => t.location_lat != null).slice(0, 3).map(t => t.transaction_id)
  )

  return (
    <div style={{
      background: '#0F1F38',
      borderRadius: 10,
      border: '1px solid #1E3050',
      overflow: 'hidden',
      height: '100%',
      minHeight: 240,
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* Header */}
      <div style={{
        padding: '8px 14px',
        borderBottom: '1px solid #1E3050',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        background: '#0A1628',
        flexShrink: 0,
      }}>
        <span style={{ color: '#E8F0FF', fontSize: '0.82rem', fontWeight: 600 }}>
          Transaction Map
        </span>
        <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
          {Object.entries(DECISION_COLORS).map(([d, c]) => (
            <span key={d} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: '0.65rem', color: '#4A6080' }}>
              <span style={{ width: DECISION_RADIUS[d] * 2, height: DECISION_RADIUS[d] * 2, borderRadius: '50%', background: c, display: 'inline-block', flexShrink: 0 }} />
              {d}
            </span>
          ))}
          <span style={{ fontSize: '0.65rem', color: '#4A6080', borderLeft: '1px solid #1E3050', paddingLeft: 10 }}>
            {plotted.length} plotted
          </span>
        </div>
      </div>

      {/* Map */}
      <div style={{ flex: 1, position: 'relative', minHeight: 0 }}>
        {plotted.length === 0 ? (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            minHeight: 180,
            color: '#4A6080',
            gap: 8,
          }}>
            <div style={{ fontSize: '2rem' }}>🗺️</div>
            <div style={{ fontSize: '0.8rem' }}>No location data — waiting for transactions…</div>
          </div>
        ) : (
          <MapContainer
            center={[20.5937, 78.9629]}
            zoom={5}
            style={{ height: '100%', width: '100%', minHeight: 180 }}
            zoomControl={true}
            scrollWheelZoom={false}
          >
            <TileLayer url={DARK_TILE} attribution={DARK_ATTR} />
            {plotted.map(t => {
              const color  = DECISION_COLORS[t.decision] || '#8BA3C7'
              const radius = DECISION_RADIUS[t.decision] || 5
              const isNew  = latestIds.has(t.transaction_id)
              return (
                <CircleMarker
                  key={t.transaction_id}
                  center={[t.location_lat, t.location_lng]}
                  radius={isNew ? radius + 2 : radius}
                  pathOptions={{
                    color:       isNew ? color : color + '99',
                    fillColor:   color,
                    fillOpacity: isNew ? 0.95 : 0.55,
                    weight:      isNew ? 2 : 1,
                  }}
                >
                  <Popup>
                    <div style={{
                      fontSize: 12,
                      minWidth: 170,
                      lineHeight: 1.7,
                      color: '#1a1a2e',
                      fontFamily: 'Inter, -apple-system, sans-serif',
                    }}>
                      <div style={{ fontWeight: 700, marginBottom: 4, color: '#0a0a1a', fontSize: 11, fontFamily: 'monospace' }}>
                        {t.transaction_id?.slice(0, 20)}…
                      </div>
                      <div><strong>Amount:</strong> ₹{Number(t.amount || 0).toLocaleString('en-IN')}</div>
                      <div><strong>User:</strong> {t.user_id}</div>
                      <div style={{ color, fontWeight: 700 }}>{t.decision}</div>
                      {t.fraud_probability != null && (
                        <div style={{ color: '#666' }}>
                          Fraud: {(t.fraud_probability * 100).toFixed(1)}%
                        </div>
                      )}
                      <div style={{ color: '#999', fontSize: 11 }}>
                        {new Date(t.created_at || t.timestamp || Date.now()).toLocaleTimeString()}
                      </div>
                    </div>
                  </Popup>
                </CircleMarker>
              )
            })}
          </MapContainer>
        )}
      </div>
    </div>
  )
}
