import {
  BarChart, Bar, XAxis, YAxis, Cell, Tooltip, ResponsiveContainer, ReferenceLine
} from 'recharts'

const TOOLTIP_STYLE = {
  backgroundColor: '#0F1F38',
  border: '1px solid #1E3050',
  color: '#E8F0FF',
  fontSize: 12,
  borderRadius: 6,
}

export function ShapWaterfall({ shapValues = [] }) {
  if (!shapValues || shapValues.length === 0) {
    return (
      <div style={{ color: '#4A6080', fontSize: 13, padding: '10px 0' }}>
        SHAP values not yet computed (processing…)
      </div>
    )
  }

  // Normalize: handle [{feature, value}] or [[feature, value]] formats
  const normalized = shapValues
    .map(item => Array.isArray(item)
      ? { feature: item[0], value: item[1] }
      : { feature: item.feature, value: item.value }
    )
    .filter(d => d.feature && d.value != null)
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
    .slice(0, 5)

  if (normalized.length === 0) {
    return (
      <div style={{ color: '#4A6080', fontSize: 13, padding: '10px 0' }}>
        SHAP values not yet computed (processing…)
      </div>
    )
  }

  return (
    <div>
      <h4 style={{ color: '#4A6080', fontSize: 10, marginBottom: 8, marginTop: 0, textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 600 }}>
        SHAP Feature Contributions (top 5)
      </h4>
      <div style={{ fontSize: 10, color: '#4A6080', marginBottom: 8, display: 'flex', gap: 12 }}>
        <span><span style={{ color: '#EF4444' }}>■</span> increases fraud prob</span>
        <span><span style={{ color: '#4F8EF7' }}>■</span> decreases fraud prob</span>
      </div>
      <ResponsiveContainer width="100%" height={Math.max(120, normalized.length * 36)}>
        <BarChart layout="vertical" data={normalized} margin={{ left: 0, right: 16, top: 4, bottom: 4 }}>
          <XAxis
            type="number"
            stroke="transparent"
            tick={{ fill: '#8BA3C7', fontSize: 9 }}
            tickLine={false}
            tickFormatter={v => v.toFixed(3)}
          />
          <YAxis
            type="category"
            dataKey="feature"
            width={160}
            tick={{ fill: '#8BA3C7', fontSize: 10 }}
            stroke="transparent"
            tickLine={false}
          />
          <ReferenceLine x={0} stroke="#1E3050" strokeWidth={1} />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            formatter={(value) => [value.toFixed(4), 'SHAP value']}
            cursor={{ fill: 'rgba(79,142,247,0.06)' }}
          />
          <Bar dataKey="value" radius={[0, 4, 4, 0]}>
            {normalized.map((entry, i) => (
              <Cell key={i} fill={entry.value > 0 ? '#EF4444' : '#4F8EF7'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
