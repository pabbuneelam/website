import { useEffect, useRef, useState } from 'react'
import type { AttributeDef, SlatePlayer } from '../types'
import { formatSalary } from '../format'

interface Props {
  attribute: AttributeDef
  players: SlatePlayer[]
  value: number | null
  usedElsewhere: Set<number>
  onChange: (playerId: number | null) => void
}

export default function SlotPicker({ attribute, players, value, usedElsewhere, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const labelId = `slot-label-${attribute.slot}`

  const available = players
    .filter((p) => p.player_id === value || !usedElsewhere.has(p.player_id))
    .sort((a, b) => a.team.localeCompare(b.team) || a.name.localeCompare(b.name))

  const selected = available.find((p) => p.player_id === value) ?? null

  useEffect(() => {
    if (!open) return
    const handlePointerDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false)
    }
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  const select = (playerId: number | null) => {
    onChange(playerId)
    setOpen(false)
  }

  return (
    <div className="slot-picker" ref={rootRef}>
      <label className="slot-picker__label" id={labelId}>
        {attribute.label}
      </label>
      <p className="slot-picker__guardrail">{attribute.guardrail}</p>

      <div className="dropdown">
        <button
          type="button"
          className={`dropdown__trigger${open ? ' dropdown__trigger--open' : ''}`}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-labelledby={labelId}
          onClick={() => setOpen((o) => !o)}
        >
          <span className={selected ? 'dropdown__value' : 'dropdown__value dropdown__value--placeholder'}>
            {selected
              ? `${selected.name} · ${selected.team} vs ${selected.opponent} · ${formatSalary(selected.salary)}`
              : '— pick a player —'}
          </span>
          <svg className="dropdown__chevron" width="10" height="6" viewBox="0 0 10 6" aria-hidden="true">
            <path d="M1 1L5 5L9 1" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>

        <ul
          className={`dropdown__menu${open ? ' dropdown__menu--open' : ''}`}
          role="listbox"
          aria-labelledby={labelId}
        >
          <li
            role="option"
            aria-selected={value === null}
            className={`dropdown__option dropdown__option--empty${value === null ? ' dropdown__option--selected' : ''}`}
            onClick={() => select(null)}
          >
            — pick a player —
          </li>
          {available.map((p, i) => (
            <li
              key={p.player_id}
              role="option"
              aria-selected={value === p.player_id}
              className={`dropdown__option${value === p.player_id ? ' dropdown__option--selected' : ''}`}
              style={{ transitionDelay: open ? `${Math.min(i, 8) * 15}ms` : '0ms' }}
              onClick={() => select(p.player_id)}
            >
              {p.name} · {p.team} vs {p.opponent} · {formatSalary(p.salary)}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
