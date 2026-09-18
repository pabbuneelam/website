import { useEffect, useRef, useState } from 'react'

const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

interface Props {
  value: string // YYYY-MM-DD
  onChange: (date: string) => void
}

function pad(n: number) {
  return String(n).padStart(2, '0')
}

function toISO(y: number, m: number, d: number) {
  return `${y}-${pad(m + 1)}-${pad(d)}`
}

function parseISO(value: string) {
  const [y, m, d] = value.split('-').map(Number)
  if (!y || !m || !d) {
    const today = new Date()
    return { y: today.getFullYear(), m: today.getMonth(), d: today.getDate() }
  }
  return { y, m: m - 1, d }
}

function formatLabel(value: string) {
  const { y, m, d } = parseISO(value)
  return `${MONTHS[m].slice(0, 3)} ${d}, ${y}`
}

export default function DatePicker({ value, onChange }: Props) {
  const selected = parseISO(value)
  const [open, setOpen] = useState(false)
  const [viewYear, setViewYear] = useState(selected.y)
  const [viewMonth, setViewMonth] = useState(selected.m)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onPointerDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const openPicker = () => {
    setViewYear(selected.y)
    setViewMonth(selected.m)
    setOpen((o) => !o)
  }

  const stepMonth = (delta: number) => {
    let m = viewMonth + delta
    let y = viewYear
    if (m < 0) {
      m = 11
      y -= 1
    } else if (m > 11) {
      m = 0
      y += 1
    }
    setViewMonth(m)
    setViewYear(y)
  }

  const stepYear = (delta: number) => setViewYear((y) => y + delta)

  const firstOfMonth = new Date(viewYear, viewMonth, 1)
  const startWeekday = firstOfMonth.getDay()
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate()
  const daysInPrevMonth = new Date(viewYear, viewMonth, 0).getDate()

  const today = new Date()
  const isToday = (y: number, m: number, d: number) =>
    y === today.getFullYear() && m === today.getMonth() && d === today.getDate()
  const isSelected = (y: number, m: number, d: number) => y === selected.y && m === selected.m && d === selected.d

  const cells: { y: number; m: number; d: number; outside: boolean }[] = []
  for (let i = 0; i < startWeekday; i++) {
    const d = daysInPrevMonth - startWeekday + 1 + i
    const m = viewMonth === 0 ? 11 : viewMonth - 1
    const y = viewMonth === 0 ? viewYear - 1 : viewYear
    cells.push({ y, m, d, outside: true })
  }
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push({ y: viewYear, m: viewMonth, d, outside: false })
  }
  while (cells.length % 7 !== 0) {
    const last = cells[cells.length - 1]
    const next = new Date(last.y, last.m, last.d + 1)
    cells.push({ y: next.getFullYear(), m: next.getMonth(), d: next.getDate(), outside: true })
  }

  const pick = (y: number, m: number, d: number) => {
    onChange(toISO(y, m, d))
    setOpen(false)
  }

  return (
    <div className="date-picker" ref={rootRef}>
      <button
        type="button"
        className={open ? 'date-picker__trigger date-picker__trigger--open' : 'date-picker__trigger'}
        onClick={openPicker}
      >
        <svg className="date-picker__icon" width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
          <rect x="1.5" y="2.5" width="13" height="12" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.3" />
          <line x1="1.5" y1="6" x2="14.5" y2="6" stroke="currentColor" strokeWidth="1.3" />
          <line x1="4.5" y1="1" x2="4.5" y2="3.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
          <line x1="11.5" y1="1" x2="11.5" y2="3.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
        </svg>
        {formatLabel(value)}
      </button>

      <div className={open ? 'date-picker__panel date-picker__panel--open' : 'date-picker__panel'}>
        <div className="date-picker__nav">
          <button type="button" className="date-picker__step" onClick={() => stepYear(-1)} aria-label="Previous year">
            «
          </button>
          <button type="button" className="date-picker__step" onClick={() => stepMonth(-1)} aria-label="Previous month">
            ‹
          </button>
          <span className="date-picker__label">
            {MONTHS[viewMonth]} {viewYear}
          </span>
          <button type="button" className="date-picker__step" onClick={() => stepMonth(1)} aria-label="Next month">
            ›
          </button>
          <button type="button" className="date-picker__step" onClick={() => stepYear(1)} aria-label="Next year">
            »
          </button>
        </div>

        <div className="date-picker__weekdays">
          {WEEKDAYS.map((w) => (
            <span key={w}>{w}</span>
          ))}
        </div>

        <div className="date-picker__grid">
          {cells.map((c, i) => (
            <button
              type="button"
              key={i}
              className={
                'date-picker__day' +
                (c.outside ? ' date-picker__day--outside' : '') +
                (isSelected(c.y, c.m, c.d) ? ' date-picker__day--selected' : '') +
                (isToday(c.y, c.m, c.d) ? ' date-picker__day--today' : '')
              }
              onClick={() => pick(c.y, c.m, c.d)}
            >
              {c.d}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
