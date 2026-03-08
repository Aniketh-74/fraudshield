import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'

const TICK_STYLE = { fill: '#4A6080', fontSize: 9 }

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: '#0F1F38',
      border: '1px solid #1E3050',
      borderRadius: 6,
      padding: '8px 12px',
      fontSize: 12,
      minWidth: 140,
      boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
    }}>
      <div style={{ color: '#8BA3C7', marginBottom: 6, fontSize: 10 }}>
        {label ? label.slice(11, 16) : ''}
      </div>
      {payload.map(p => (
        <div key={p.dataKey} style={{ display: 'flex', justifyContent: 'space-between', gap: 14, marginBottom: 2 }}>
          <span style={{ color: p.fill }}>{p.dataKey}</span>
          <span style={{ fontWeight: 600, color: '#E8F0FF' }}>{p.value}</span>
        </div>
      ))}
    </div>
  )
}

export function TimeSeriesChart({ data = [] }) {
  const transformed = transformHourlyData(data)

  return (
    <div style={{ background: '#0F1F38', borderRadius: 10, padding: '14px 12px', marginBottom: 10, border: '1px solid #1E3050' }}>
      <h3 style={{ color: '#4A6080', fontSize: 10, marginBottom: 10, marginTop: 0, textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 600 }}>
        Decisions per Hour
      </h3>
      <ResponsiveContainer width="100%" height={160}>
        <BarChart data={transformed} margin={{ top: 0, right: 0, left: -22, bottom: 0 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="#1E3050" vertical={false} />
          <XAxis dataKey="hour" stroke="transparent" tick={TICK_STYLE} tickFormatter={h => h.slice(11, 16)} interval="preserveStartEnd" />
          <YAxis stroke="transparent" tick={TICK_STYLE} />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(79,142,247,0.05)' }} />
          <Legend wrapperStyle={{ fontSize: 9, color: '#4A6080', paddingTop: 4 }} />
          <Bar dataKey="APPROVE" stackId="a" fill="#20C997" radius={[0,0,0,0]} />
          <Bar dataKey="FLAG"    stackId="a" fill="#F5A623" />
          <Bar dataKey="BLOCK"   stackId="a" fill="#EF4444" radius={[3,3,0,0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function transformHourlyData(raw) {
  const map = {}
  for (const item of raw) {
    const key = item.hour
    if (!map[key]) map[key] = { hour: key, APPROVE: 0, FLAG: 0, BLOCK: 0 }
    map[key][item.decision] = (map[key][item.decision] || 0) + item.count
  }
  return Object.values(map).sort((a, b) => a.hour.localeCompare(b.hour))
}
