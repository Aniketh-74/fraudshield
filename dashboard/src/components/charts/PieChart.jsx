import { PieChart as RechartsPie, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'

const SLICES = [
  { key: 'APPROVE', color: '#20C997', label: 'Approve' },
  { key: 'FLAG',    color: '#F5A623', label: 'Flag' },
  { key: 'BLOCK',   color: '#EF4444', label: 'Block' },
]

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const { name, value } = payload[0]
  const slice = SLICES.find(s => s.key === name)
  return (
    <div style={{
      background: '#0F1F38',
      border: '1px solid #1E3050',
      borderRadius: 6,
      padding: '6px 12px',
      fontSize: 12,
      boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
    }}>
      <span style={{ color: slice?.color || '#8BA3C7', fontWeight: 700 }}>{name}</span>
      <span style={{ color: '#E8F0FF', marginLeft: 8 }}>{value?.toLocaleString()}</span>
    </div>
  )
}

function CustomLabel({ cx, cy, midAngle, innerRadius, outerRadius, percent }) {
  if (percent < 0.04) return null
  const RADIAN = Math.PI / 180
  const r = innerRadius + (outerRadius - innerRadius) * 0.55
  const x = cx + r * Math.cos(-midAngle * RADIAN)
  const y = cy + r * Math.sin(-midAngle * RADIAN)
  return (
    <text x={x} y={y} fill="#fff" textAnchor="middle" dominantBaseline="central" fontSize={10} fontWeight={700}>
      {`${(percent * 100).toFixed(0)}%`}
    </text>
  )
}

export function PieChart({ counts = {} }) {
  const total = (counts.APPROVE || 0) + (counts.FLAG || 0) + (counts.BLOCK || 0)
  const data = SLICES.map(s => ({ name: s.key, value: counts[s.key] || 0 })).filter(d => d.value > 0)

  return (
    <div style={{ background: '#0F1F38', borderRadius: 10, padding: '14px 12px', marginBottom: 10, border: '1px solid #1E3050' }}>
      <h3 style={{ color: '#4A6080', fontSize: 10, marginBottom: 8, marginTop: 0, textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 600 }}>
        Decision Distribution
      </h3>

      {data.length === 0 ? (
        <div style={{ height: 140, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#4A6080', fontSize: 12 }}>
          No data yet
        </div>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={140}>
            <RechartsPie>
              <Pie
                data={data}
                cx="50%" cy="50%"
                innerRadius={36} outerRadius={62}
                dataKey="value"
                labelLine={false}
                label={CustomLabel}
                strokeWidth={0}
              >
                {data.map(entry => {
                  const s = SLICES.find(sl => sl.key === entry.name)
                  return <Cell key={entry.name} fill={s?.color || '#8BA3C7'} />
                })}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
            </RechartsPie>
          </ResponsiveContainer>

          {/* Legend */}
          <div style={{ display: 'flex', justifyContent: 'center', gap: 12, marginTop: 4 }}>
            {SLICES.map(s => {
              const v = counts[s.key] || 0
              const pct = total > 0 ? ((v / total) * 100).toFixed(1) : '0.0'
              return (
                <div key={s.key} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: s.color, display: 'inline-block' }} />
                  <span style={{ fontSize: 10, color: '#4A6080' }}>{s.label}</span>
                  <span style={{ fontSize: 10, color: s.color, fontWeight: 700 }}>{pct}%</span>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
