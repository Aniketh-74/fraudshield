import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'

const TOOLTIP_STYLE = {
  backgroundColor: '#0F1F38',
  border: '1px solid #1E3050',
  color: '#E8F0FF',
  fontSize: 12,
  borderRadius: 6,
  boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
}

function barColor(rule) {
  if (/high|velocity|international|block/i.test(rule)) return '#EF4444'
  if (/amount|limit|freq/i.test(rule)) return '#F5A623'
  return '#4F8EF7'
}

export function RulesBarChart({ data = [] }) {
  if (data.length === 0) {
    return (
      <div style={{
        background: '#0F1F38',
        borderRadius: 10,
        padding: '14px 12px',
        marginBottom: 10,
        height: 140,
        display: 'flex',
        flexDirection: 'column',
        border: '1px solid #1E3050',
      }}>
        <h3 style={{ color: '#4A6080', fontSize: 10, marginBottom: 0, marginTop: 0, textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 600 }}>
          Top Rules Triggered
        </h3>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#4A6080', fontSize: 12 }}>
          No rules triggered yet
        </div>
      </div>
    )
  }

  return (
    <div style={{ background: '#0F1F38', borderRadius: 10, padding: '14px 12px', marginBottom: 10, border: '1px solid #1E3050' }}>
      <h3 style={{ color: '#4A6080', fontSize: 10, marginBottom: 10, marginTop: 0, textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 600 }}>
        Top Rules Triggered
      </h3>
      <ResponsiveContainer width="100%" height={Math.max(120, data.length * 22)}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 0, right: 12, left: 0, bottom: 0 }}
        >
          <XAxis
            type="number"
            stroke="transparent"
            tick={{ fill: '#4A6080', fontSize: 9 }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            type="category"
            dataKey="rule"
            width={140}
            stroke="transparent"
            tick={{ fill: '#8BA3C7', fontSize: 10 }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            cursor={{ fill: 'rgba(79,142,247,0.06)' }}
          />
          <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={14}>
            {data.map((entry, i) => (
              <Cell key={i} fill={barColor(entry.rule)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
