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
  const [query, setQuery] = useState('')
  const [highlight, setHighlight] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const labelId = `slot-label-${attribute.slot}`
  const listId = `slot-listbox-${attribute.slot}`
  const optionId = (id: number | null) => `slot-option-${attribute.slot}-${id ?? 'empty'}`

  const available = players
    .filter((p) => p.player_id === value || !usedElsewhere.has(p.player_id))
    .sort((a, b) => a.team.localeCompare(b.team) || a.name.localeCompare(b.name))

  const selected = available.find((p) => p.player_id === value) ?? null

  const q = query.trim().toLowerCase()
  const filtered = q
    ? available.filter((p) => p.name.toLowerCase().includes(q) || p.team.toLowerCase().includes(q))
    : available

  // Keyboard-navigable options: the "clear" entry always first, then filtered players.
  const navItems: { id: number | null; label: string }[] = [
    { id: null, label: '— pick a player —' },
    ...filtered.map((p) => ({
      id: p.player_id,
      label: `${p.name} · ${p.team} vs ${p.opponent} · ${formatSalary(p.salary)}`,
    })),
  ]
  const activeItem = navItems[highlight]

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

  useEffect(() => {
    if (open) {
      searchRef.current?.focus()
    } else {
      setQuery('')
      setHighlight(0)
    }
  }, [open])

  useEffect(() => {
    setHighlight(0)
  }, [query])

  useEffect(() => {
    if (!open || !activeItem) return
    listRef.current?.querySelector(`#${CSS.escape(optionId(activeItem.id))}`)?.scrollIntoView({ block: 'nearest' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlight, open])

  const select = (playerId: number | null) => {
    onChange(playerId)
    setOpen(false)
  }

  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlight((h) => Math.min(h + 1, navItems.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlight((h) => Math.max(h - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (activeItem) select(activeItem.id)
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
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

        <div className={`dropdown__menu${open ? ' dropdown__menu--open' : ''}`}>
          <input
            ref={searchRef}
            type="text"
            className="dropdown__search"
            placeholder="Search name or team…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleSearchKeyDown}
            role="combobox"
            aria-expanded={open}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={activeItem ? optionId(activeItem.id) : undefined}
            aria-label={`Search players for ${attribute.label}`}
          />
          <ul id={listId} ref={listRef} className="dropdown__list" role="listbox" aria-labelledby={labelId}>
            <li
              id={optionId(null)}
              role="option"
              aria-selected={value === null}
              className={`dropdown__option dropdown__option--empty${value === null ? ' dropdown__option--selected' : ''}${highlight === 0 ? ' dropdown__option--highlighted' : ''}`}
              onMouseEnter={() => setHighlight(0)}
              onClick={() => select(null)}
            >
              — pick a player —
            </li>
            {filtered.map((p, i) => {
              const navIndex = i + 1
              return (
                <li
                  key={p.player_id}
                  id={optionId(p.player_id)}
                  role="option"
                  aria-selected={value === p.player_id}
                  className={`dropdown__option${value === p.player_id ? ' dropdown__option--selected' : ''}${highlight === navIndex ? ' dropdown__option--highlighted' : ''}`}
                  style={{ transitionDelay: open ? `${Math.min(i, 8) * 15}ms` : '0ms' }}
                  onMouseEnter={() => setHighlight(navIndex)}
                  onClick={() => select(p.player_id)}
                >
                  {p.name} · {p.team} vs {p.opponent} · {formatSalary(p.salary)}
                </li>
              )
            })}
          </ul>
          {q && filtered.length === 0 && <p className="dropdown__no-match">No players match “{query}”.</p>}
        </div>
      </div>
    </div>
  )
}
