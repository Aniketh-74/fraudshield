import { useState } from 'react'

const HOURS = Array.from({ length: 24 }, (_, i) => i)
const DAYS  = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

function heatColor(count, maxCount) {
  if (maxCount === 0 || count === 0) return '#0F1F38'
  const t = count / maxCount
  if (t < 0.5) {
    const s = t / 0.5
    const r = Math.round(29  + s * (245 - 29))
    const g = Math.round(78  + s * (158 - 78))
    const b = Math.round(216 + s * (11  - 216))
    return `rgb(${r},${g},${b})`
  } else {
    const s = (t - 0.5) / 0.5
    const r = Math.round(245 + s * (239 - 245))
    const g = Math.round(158 + s * (68  - 158))
    const b = Math.round(11  + s * (68  - 11))
    return `rgb(${r},${g},${b})`
  }
}

const CELL_W = 24, CELL_H = 20, LABEL_W = 30, PAD_TOP = 18

export function HeatmapChart({ data = [] }) {
  const [tooltip, setTooltip] = useState(null)

  const cellMap = {}
  for (const d of data) cellMap[`${d.hour}-${d.day}`] = d.count
  const maxCount = Math.max(...Object.values(cellMap), 1)

  const svgW = LABEL_W + 24 * CELL_W + 8
  const svgH = PAD_TOP + 7 * CELL_H + 20

  return (
    <div style={{ background: '#0F1F38', borderRadius: 10, padding: '14px 12px', marginBottom: 10, position: 'relative', border: '1px solid #1E3050' }}>
      <h3 style={{ color: '#4A6080', fontSize: 10, marginBottom: 10, marginTop: 0, textTransform: 'uppercase', letterSpacing: '0.07em', fontWeight: 600 }}>
        Fraud by Hour × Day
      </h3>

      <div style={{ overflowX: 'auto' }}>
        <svg width={svgW} height={svgH} style={{ display: 'block' }}>
          {/* Hour labels */}
          {HOURS.filter(h => h % 3 === 0).map(h => (
            <text key={h}
              x={LABEL_W + h * CELL_W + CELL_W / 2}
              y={PAD_TOP - 4}
              textAnchor="middle" fill="#4A6080" fontSize={9}
            >
              {String(h).padStart(2, '0')}
            </text>
          ))}

          {/* Day labels + cells */}
          {DAYS.map((day, dayIdx) => (
            <g key={day}>
              <text
                x={LABEL_W - 5} y={PAD_TOP + dayIdx * CELL_H + CELL_H / 2 + 4}
                textAnchor="end" fill="#4A6080" fontSize={9}
              >
                {day}
              </text>
              {HOURS.map(hour => {
                const count = cellMap[`${hour}-${dayIdx}`] || 0
                const fill  = heatColor(count, maxCount)
                return (
                  <rect
                    key={hour}
                    x={LABEL_W + hour * CELL_W + 1}
                    y={PAD_TOP + dayIdx * CELL_H + 1}
                    width={CELL_W - 2}
                    height={CELL_H - 2}
                    fill={fill}
                    rx={3}
                    style={{ cursor: count > 0 ? 'crosshair' : 'default', transition: 'opacity 0.1s' }}
                    onMouseEnter={e => {
                      const rect = e.currentTarget.getBoundingClientRect()
                      setTooltip({ hour, day, dayIdx, count, x: rect.left, y: rect.top })
                    }}
                    onMouseLeave={() => setTooltip(null)}
                    opacity={tooltip && tooltip.hour === hour && tooltip.dayIdx === dayIdx ? 0.72 : 1}
                  />
                )
              })}
            </g>
          ))}

          {/* Legend */}
          <defs>
            <linearGradient id="heatLegend2" x1="0" x2="1" y1="0" y2="0">
              <stop offset="0%"   stopColor="#0F1F38" />
              <stop offset="50%"  stopColor="#1D4ED8" />
              <stop offset="80%"  stopColor="#F5A623" />
              <stop offset="100%" stopColor="#EF4444" />
            </linearGradient>
          </defs>
          <rect x={LABEL_W} y={svgH - 10} width={24 * CELL_W} height={5} rx={2} fill="url(#heatLegend2)" />
          <text x={LABEL_W}             y={svgH - 14} fill="#4A6080" fontSize={8} textAnchor="start">none</text>
          <text x={LABEL_W + 24*CELL_W} y={svgH - 14} fill="#4A6080" fontSize={8} textAnchor="end">peak</text>
        </svg>
      </div>

      {/* Floating tooltip */}
      {tooltip && (
        <div style={{
          position: 'fixed',
          left: tooltip.x + 12,
          top: tooltip.y - 8,
          background: '#0F1F38',
          border: '1px solid #1E3050',
          borderRadius: 6,
          padding: '6px 10px',
          fontSize: 11,
          color: '#E8F0FF',
          pointerEvents: 'none',
          zIndex: 999,
          whiteSpace: 'nowrap',
          boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
        }}>
          <span style={{ color: '#8BA3C7' }}>{DAYS[tooltip.dayIdx]} {String(tooltip.hour).padStart(2,'0')}:00</span>
          <span style={{ marginLeft: 8, fontWeight: 700, color: tooltip.count > 0 ? '#EF4444' : '#4A6080' }}>
            {tooltip.count} event{tooltip.count !== 1 ? 's' : ''}
          </span>
        </div>
      )}
    </div>
  )
}
