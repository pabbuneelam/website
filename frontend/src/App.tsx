import { useEffect, useMemo, useState } from 'react'
import { ApiError, getAttributes, getSlate, submitBuild } from './api'
import type { AttributeDef, Card, Slate } from './types'
import SlotPicker from './components/SlotPicker'
import CardResult from './components/CardResult'
import Collection from './components/Collection'
import DatePicker from './components/DatePicker'

const DEFAULT_DATE = '2025-11-14' // the only date with fixture data today
const CREATOR_STORAGE_KEY = 'slate:creator'

type Tab = 'build' | 'collection'

export default function App() {
  const [tab, setTab] = useState<Tab>('build')
  const [creator, setCreator] = useState(() => localStorage.getItem(CREATOR_STORAGE_KEY) ?? '')
  const [date, setDate] = useState(DEFAULT_DATE)

  const [attributes, setAttributes] = useState<AttributeDef[] | null>(null)
  const [slate, setSlate] = useState<Slate | null>(null)
  const [slateLoading, setSlateLoading] = useState(false)
  const [slateError, setSlateError] = useState<string | null>(null)

  const [selections, setSelections] = useState<Record<string, number | null>>({})
  const [resultCard, setResultCard] = useState<Card | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  useEffect(() => {
    getAttributes()
      .then(setAttributes)
      .catch((err: unknown) => {
        setSlateError(err instanceof ApiError ? err.message : 'failed to load attributes')
      })
  }, [])

  useEffect(() => {
    localStorage.setItem(CREATOR_STORAGE_KEY, creator)
  }, [creator])

  useEffect(() => {
    setSlateLoading(true)
    setSlateError(null)
    setSlate(null)
    setResultCard(null)
    setSelections({})
    getSlate(date)
      .then(setSlate)
      .catch((err: unknown) => {
        setSlateError(err instanceof ApiError ? err.message : 'failed to load slate')
      })
      .finally(() => setSlateLoading(false))
  }, [date])

  const usedByOther = (slot: string) => {
    const used = new Set<number>()
    for (const [s, playerId] of Object.entries(selections)) {
      if (s !== slot && playerId !== null) used.add(playerId)
    }
    return used
  }

  const allFilled = useMemo(() => {
    if (!attributes) return false
    return attributes.every((a) => selections[a.slot] != null)
  }, [attributes, selections])

  const canSubmit = allFilled && creator.trim().length > 0 && !submitting

  const handleSubmit = () => {
    if (!attributes || !canSubmit) return
    setSubmitting(true)
    setSubmitError(null)
    submitBuild(date, {
      creator: creator.trim(),
      selections: attributes.map((a) => ({ slot: a.slot, player_id: selections[a.slot]! })),
    })
      .then(setResultCard)
      .catch((err: unknown) => {
        setSubmitError(err instanceof ApiError ? err.message : 'failed to submit build')
      })
      .finally(() => setSubmitting(false))
  }

  return (
    <div className="app">
      <header className="app__header">
        <h1>Slate</h1>
        <p className="app__tagline">Build a player out of tonight's real performances.</p>
      </header>

      <nav className="tabs">
        <button className={tab === 'build' ? 'tabs__item tabs__item--active' : 'tabs__item'} onClick={() => setTab('build')}>
          Build
        </button>
        <button
          className={tab === 'collection' ? 'tabs__item tabs__item--active' : 'tabs__item'}
          onClick={() => setTab('collection')}
        >
          My Collection
        </button>
      </nav>

      <div className="toolbar">
        <label>
          Creator name
          <input value={creator} onChange={(e) => setCreator(e.target.value)} placeholder="your name" />
        </label>
        {tab === 'build' && (
          <label>
            Slate date
            <DatePicker value={date} onChange={setDate} />
          </label>
        )}
      </div>

      {tab === 'build' && (
        <main>
          {slateLoading && <p>Loading slate…</p>}
          {slateError && <p className="error-banner">{slateError}</p>}

          {slate && attributes && (
            <>
              <section className="slots">
                {attributes.map((a) => (
                  <SlotPicker
                    key={a.slot}
                    attribute={a}
                    players={slate.players}
                    value={selections[a.slot] ?? null}
                    usedElsewhere={usedByOther(a.slot)}
                    onChange={(playerId) => setSelections((s) => ({ ...s, [a.slot]: playerId }))}
                  />
                ))}
              </section>

              <div className="submit-row">
                <button onClick={handleSubmit} disabled={!canSubmit}>
                  {submitting ? 'Building…' : 'Build card'}
                </button>
                {!creator.trim() && <span className="hint">enter a creator name</span>}
              </div>
              {submitError && <p className="error-banner">{submitError}</p>}

              {resultCard && <CardResult card={resultCard} />}
            </>
          )}
        </main>
      )}

      {tab === 'collection' && (
        <main>
          <Collection creator={creator} />
        </main>
      )}
    </div>
  )
}
