import { useEffect, useMemo, useRef, useState } from 'react'
import type { Rating } from '../types'

// Text content can't be CSS-transitioned, so the "FINAL" number gets its own
// rAF tween -- it glides between values in step with the SVG geometry, which
// transitions via CSS (same DOM nodes, keyed by time so React only touches
// cx/cy/d and the browser interpolates the rest).
function useAnimatedNumber(target: number, duration = 480) {
  const [display, setDisplay] = useState(target)
  const displayRef = useRef(target)
  const rafRef = useRef<number | null>(null)

  useEffect(() => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    const from = displayRef.current
    if (from === target) return
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      const next = from + (target - from) * eased
      displayRef.current = next
      setDisplay(next)
      if (t < 1) rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    }
  }, [target, duration])

  return display
}

const TIMES = [0, 8, 16, 24, 32, 40, 48]

type MetricId = 'fantasy' | 'pts' | 'reb' | 'ast'

const METRICS: { id: MetricId; label: string; unit: string }[] = [
  { id: 'fantasy', label: 'Fantasy', unit: 'pts' },
  { id: 'pts', label: 'Points', unit: 'pts' },
  { id: 'reb', label: 'Rebounds', unit: 'reb' },
  { id: 'ast', label: 'Assists', unit: 'ast' },
]

const CHART_W = 800
const CHART_H = 220
const PAD_L = 46
const PAD_R = 16
const PAD_T = 18
const PAD_B = 30
const INNER_W = CHART_W - PAD_L - PAD_R
const BASE_Y = CHART_H - PAD_B

const scaleX = (t: number) => PAD_L + (t / 48) * INNER_W
const scaleY = (v: number, max: number) => BASE_Y - (v / max) * (BASE_Y - PAD_T)

// Deterministic per player+metric, so the same card always draws the same
// curve -- real endpoint, a stable (not random-each-render) shape getting
// there, since the box score has no per-minute breakdown to draw from.
function seededRandom(seed: string) {
  let h = 1779033703 ^ seed.length
  for (let i = 0; i < seed.length; i++) {
    h = Math.imul(h ^ seed.charCodeAt(i), 3432918353)
    h = (h << 13) | (h >>> 19)
  }
  return () => {
    h = Math.imul(h ^ (h >>> 16), 2246822519)
    h = Math.imul(h ^ (h >>> 13), 3266489917)
    h ^= h >>> 16
    return (h >>> 0) / 4294967296
  }
}

function buildCurve(final: number, seedKey: string, integer: boolean): number[] {
  const steps = TIMES.length - 1
  if (final <= 0) return new Array(steps + 1).fill(0)

  const rand = seededRandom(seedKey)
  const weights = Array.from({ length: steps }, () => 0.5 + rand())
  const weightSum = weights.reduce((a, b) => a + b, 0)

  const curve = [0]
  let running = 0
  for (let i = 0; i < steps; i++) {
    running += (weights[i] / weightSum) * final
    const v = integer ? Math.round(running) : Math.round(running * 10) / 10
    curve.push(Math.max(v, curve[curve.length - 1]))
  }
  curve[curve.length - 1] = final
  return curve
}

interface Hover {
  x: number
  y: number
  tLabel: string
  valueLabel: string
}

export default function LiveStatGraph({ ratings }: { ratings: Rating[] }) {
  const defaultSlot = useMemo(
    () => ratings.reduce((best, r) => (r.rating > best.rating ? r : best), ratings[0]).slot,
    [ratings],
  )
  const [slot, setSlot] = useState(defaultSlot)
  const [metric, setMetric] = useState<MetricId>('fantasy')
  const [showTable, setShowTable] = useState(false)
  const [hover, setHover] = useState<Hover | null>(null)

  const rating = ratings.find((r) => r.slot === slot) ?? ratings[0]
  const metricDef = METRICS.find((m) => m.id === metric)!
  const finalValue = metric === 'fantasy' ? rating.fantasy : metric === 'pts' ? rating.pts : metric === 'reb' ? rating.reb : rating.ast
  const max = Math.max(finalValue * 1.2, finalValue > 0 ? finalValue + 2 : 5)

  const curve = buildCurve(finalValue, `${rating.player_id}-${metric}`, metric !== 'fantasy')
  const points = TIMES.map((t, i) => ({ t, val: curve[i], x: scaleX(t), y: scaleY(curve[i], max) }))
  const last = points[points.length - 1]

  const linePath = 'M ' + points.map((p) => `${p.x},${p.y}`).join(' L ')
  const areaPath = `${linePath} L ${last.x},${BASE_Y} L ${points[0].x},${BASE_Y} Z`

  const gridLines = [0, 0.5, 1].map((frac) => ({
    frac,
    y: scaleY(frac * max, max),
    label: Math.round(frac * max * 10) / 10,
  }))

  const tableRows = points.map((p) => ({ time: `${p.t}'`, value: `${p.val} ${metricDef.unit}` }))

  const animatedFinal = useAnimatedNumber(finalValue)
  const finalDisplay = metric === 'fantasy' ? animatedFinal.toFixed(1) : Math.round(animatedFinal)

  return (
    <div className="live-stat-card">
      <div className="live-stat-card__players">
        {ratings.map((r) => (
          <button
            key={r.slot}
            type="button"
            className={r.slot === slot ? 'player-chip player-chip--active' : 'player-chip'}
            onClick={() => setSlot(r.slot)}
          >
            {r.player_name}
            <span className="player-chip__slot">{r.label}</span>
          </button>
        ))}
      </div>

      <div className="live-stat-card__head">
        <div>
          <p className="live-stat-card__title">
            {metricDef.label} Through the Game
            <span className="total-chip">
              {finalDisplay} {metricDef.unit}
            </span>
          </p>
          <p className="live-stat-card__subtitle">{rating.player_name} · {rating.label}</p>
          <p className="live-stat-card__note">Real box score, spread across game time</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {METRICS.map((m) => (
            <button
              key={m.id}
              type="button"
              className={m.id === metric ? 'metric-btn metric-btn--active' : 'metric-btn'}
              onClick={() => setMetric(m.id)}
            >
              {m.label}
            </button>
          ))}
          <button type="button" className="link-btn" onClick={() => setShowTable((s) => !s)}>
            {showTable ? 'Chart view' : 'Table view'}
          </button>
        </div>
      </div>

      {showTable ? (
        <table className="data-table">
          <thead>
            <tr>
              <th>Clock</th>
              <th>{metricDef.label}</th>
            </tr>
          </thead>
          <tbody>
            {tableRows.map((row) => (
              <tr key={row.time}>
                <td>{row.time}</td>
                <td>{row.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div style={{ position: 'relative' }}>
          <svg width="100%" viewBox={`0 0 ${CHART_W} ${CHART_H}`} className="live-stat-svg">
            {gridLines.map((g) => (
              <g key={g.frac}>
                <line className="hero-grid" x1={PAD_L} y1={g.y} x2={CHART_W - PAD_R} y2={g.y} />
                <text className="hero-axis-label" x={8} y={g.y + 4}>
                  {g.label}
                </text>
              </g>
            ))}

            <path className="hero-area" d={areaPath} />
            <path className="hero-line" d={linePath} />

            {TIMES.map((t) => (
              <text key={t} className="hero-axis-label" x={scaleX(t)} y={CHART_H - 8} textAnchor="middle">
                {t}'
              </text>
            ))}

            {points.map((p) => (
              <g key={p.t}>
                <circle className="hero-pt" cx={p.x} cy={p.y} r={3.5} />
                <circle
                  className="hero-hit"
                  cx={p.x}
                  cy={p.y}
                  r={10}
                  onMouseEnter={() =>
                    setHover({ x: p.x, y: p.y - 6, tLabel: `${p.t}' mark`, valueLabel: `${p.val} ${metricDef.unit}` })
                  }
                  onMouseLeave={() => setHover(null)}
                />
              </g>
            ))}
          </svg>

          {hover && (
            <div className="tooltip" style={{ left: hover.x, top: hover.y }}>
              <div className="tooltip__muted">{hover.tLabel}</div>
              <div className="tooltip__value">{hover.valueLabel}</div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
