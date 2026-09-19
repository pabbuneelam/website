import { useEffect, useState } from 'react'
import type { User } from 'firebase/auth'
import { ApiError, createLeague, getMyLeague, joinLeague, leaveLeague } from '../api'
import type { LeagueView } from '../types'
import Trades from './Trades'

/** The league panel: one league at a time, joined by invite code.
 *
 *  Two screens in one component because they are two states of one fact --
 *  either you are in a league or you are not, and there is no third thing to
 *  route to. No browse, no discovery: the code is the only way in. */
export default function League({ user }: { user: User }) {
  const [view, setView] = useState<LeagueView | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    setLoading(true)
    setError(null)
    getMyLeague()
      .then(setView)
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : 'failed to load your league')
      })
      .finally(() => setLoading(false))
  }, [user.uid])

  // Every action returns the same shape, so they all land the same way.
  const run = (action: () => Promise<LeagueView>, fallback: string) => {
    setBusy(true)
    setError(null)
    action()
      .then((next) => {
        setView(next)
        setCode('')
        setName('')
        setCopied(false)
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : fallback)
      })
      .finally(() => setBusy(false))
  }

  const copy = () => {
    const invite = view?.league?.code
    if (!invite) return
    // Clipboard access can be refused (insecure origin, denied permission);
    // the code is on screen either way, so a failure is not worth an error.
    void navigator.clipboard?.writeText(invite).then(
      () => setCopied(true),
      () => setCopied(false),
    )
  }

  if (loading) return <p>Loading your league…</p>

  const league = view?.league ?? null
  const members = view?.members ?? []

  if (!league) {
    return (
      <div className="league">
        {error && <p className="error-banner">{error}</p>}

        <p className="league__blurb">
          You are in no league. Join one with the code a commissioner sent you, or start
          your own and send the code out yourself. One league at a time.
        </p>

        <section className="league__entry">
          <h2 className="league__entry-title">Join a league</h2>
          <form
            className="league__form"
            onSubmit={(e) => {
              e.preventDefault()
              if (code.trim()) run(() => joinLeague(code), 'failed to join')
            }}
          >
            <input
              className="league__code-input"
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              placeholder="invite code"
              aria-label="Invite code"
              maxLength={16}
              autoCapitalize="characters"
              spellCheck={false}
            />
            <button type="submit" disabled={busy || !code.trim()}>
              {busy ? 'Joining…' : 'Join league'}
            </button>
          </form>
        </section>

        <section className="league__entry">
          <h2 className="league__entry-title">Or start one</h2>
          <form
            className="league__form"
            onSubmit={(e) => {
              e.preventDefault()
              if (name.trim()) run(() => createLeague(name), 'failed to create league')
            }}
          >
            <input
              className="league__name-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="league name"
              aria-label="League name"
              maxLength={60}
            />
            <button type="submit" disabled={busy || !name.trim()}>
              {busy ? 'Creating…' : 'Create league'}
            </button>
          </form>
        </section>
      </div>
    )
  }

  return (
    <div className="league">
      {error && <p className="error-banner">{error}</p>}

      <div className="league__head">
        <div>
          <p className="league__eyebrow">Your league</p>
          <h2 className="league__name">{league.name}</h2>
        </div>
        <div className="league__invite">
          <p className="league__eyebrow">Invite code</p>
          <button className="league__code" onClick={copy} title="Copy invite code">
            {league.code}
          </button>
          <p className="league__copied">{copied ? 'copied' : 'tap to copy'}</p>
        </div>
      </div>

      <table className="data-table league__members">
        <thead>
          <tr>
            <th scope="col">Member</th>
            <th scope="col">Joined</th>
          </tr>
        </thead>
        <tbody>
          {members.map((m) => (
            <tr key={m.uid}>
              <td>
                {m.display_name || m.uid}
                {m.uid === league.owner_uid && <span className="league__tag">commissioner</span>}
                {m.uid === user.uid && <span className="league__tag league__tag--you">you</span>}
              </td>
              <td>{m.joined_at ? m.joined_at.slice(0, 10) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Trading is between leaguemates and nowhere else, so it lives on the
          league screen rather than behind a tab of its own. */}
      <Trades uid={user.uid} members={members} />

      <div className="league__actions">
        <button className="league__leave" onClick={() => run(leaveLeague, 'failed to leave')} disabled={busy}>
          {busy ? 'Leaving…' : 'Leave league'}
        </button>
        {/* Cards are owned by the uid, so nothing about the collection moves. */}
        <span className="hint">
          Your cards stay yours — a collection is not league property. Leaving
          cancels any trade you still have pending.
        </span>
      </div>
    </div>
  )
}
