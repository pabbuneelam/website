import { useEffect, useMemo, useState } from 'react'
import { ApiError, getAttributes, getSlate, submitBuild } from './api'
import type { AttributeDef, Card, Slate } from './types'
import SlotPicker from './components/SlotPicker'
import CardResult from './components/CardResult'
import Collection from './components/Collection'
import DatePicker from './components/DatePicker'
import AccountBar from './components/AccountBar'
import Account from './components/Account'
import League from './components/League'
import Chat from './components/Chat'
import { useAuth } from './useAuth'

const DEFAULT_DATE = '2025-11-14' // the one night with real fixture data; other dates show its players

// Three panels and no router. Adding one would mean a dependency, a build
// config and real URLs for what is still a single screen with a sidebar's
// worth of state -- when there are shareable pages (a league, another user's
// collection) that trade flips, and this is where it flips.
type Tab = 'build' | 'collection' | 'league' | 'messages' | 'account'

export default function App() {
  const { user, loading: authLoading } = useAuth()
  const [tab, setTab] = useState<Tab>('build')
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

  // Derived during render, not corrected in an effect: signing out while on a
  // signed-in-only panel must not paint a dead screen for one frame.
  const activeTab: Tab = user ? tab : 'build'

  // A card belongs to a uid, so a new sign-in is a different collection.
  useEffect(() => {
    setResultCard(null)
  }, [user?.uid])

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

  const canSubmit = allFilled && !!user && !submitting

  const handleSubmit = () => {
    if (!attributes || !canSubmit) return
    setSubmitting(true)
    setSubmitError(null)
    submitBuild(date, {
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
        {/* Top right of the masthead: messages sits beside the account
            control, because that is where a signed-in user looks for
            anything addressed to them. */}
        <div className="masthead-controls">
          {user && (
            <button
              className={activeTab === 'messages' ? 'messages-launch messages-launch--active' : 'messages-launch'}
              onClick={() => setTab('messages')}
            >
              Messages
            </button>
          )}
          <AccountBar user={user} loading={authLoading} onOpenAccount={() => setTab('account')} />
        </div>
        <h1>Slate</h1>
        <p className="app__tagline">Build a player out of tonight's real performances.</p>
      </header>

      <nav className="tabs">
        <button className={activeTab === 'build' ? 'tabs__item tabs__item--active' : 'tabs__item'} onClick={() => setTab('build')}>
          Build
        </button>
        {user && (
          <button
            className={activeTab === 'collection' ? 'tabs__item tabs__item--active' : 'tabs__item'}
            onClick={() => setTab('collection')}
          >
            My Collection
          </button>
        )}
        {user && (
          <button
            className={activeTab === 'league' ? 'tabs__item tabs__item--active' : 'tabs__item'}
            onClick={() => setTab('league')}
          >
            League
          </button>
        )}
        {user && (
          <button
            className={activeTab === 'account' ? 'tabs__item tabs__item--active' : 'tabs__item'}
            onClick={() => setTab('account')}
          >
            Account
          </button>
        )}
      </nav>

      {activeTab === 'build' && (
        <div className="toolbar">
          <label>
            Slate date
            <DatePicker value={date} onChange={setDate} />
          </label>
        </div>
      )}

      {activeTab === 'build' && (
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
                {/* Picking is free; only keeping the card needs an account. */}
                {!user && !authLoading && <span className="hint">log in to build a card</span>}
                {/* League play is the point of a collection, so the way in is
                    on the screen people actually land on -- not only a tab. */}
                {user && (
                  <button className="join-league-link" onClick={() => setTab('league')}>
                    Join league
                  </button>
                )}
              </div>
              {submitError && <p className="error-banner">{submitError}</p>}

              {resultCard && <CardResult card={resultCard} />}
            </>
          )}
        </main>
      )}

      {activeTab === 'collection' && user && (
        <main>
          <Collection />
        </main>
      )}

      {activeTab === 'league' && user && (
        <main>
          <League user={user} />
        </main>
      )}

      {activeTab === 'account' && user && (
        <main>
          <Account user={user} />
        </main>
      )}

      {activeTab === 'messages' && user && (
        <main>
          <Chat user={user} />
        </main>
      )}
    </div>
  )
}
