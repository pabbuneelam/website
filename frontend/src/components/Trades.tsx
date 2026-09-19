import { useEffect, useState } from 'react'
import {
  ApiError,
  acceptTrade,
  cancelTrade,
  getCollection,
  getMyCollection,
  getTrades,
  proposeTrade,
  rejectTrade,
} from '../api'
import type { Card, Membership, TradeInbox, TradeView } from '../types'
import { formatSalary } from '../format'

/** The trade block on the league screen.
 *
 *  Card for card, between two members of one league. No currency and no
 *  picks: those are the other two tradeable assets in the design and neither
 *  has anything to validate against yet.
 *
 *  Native <select> for the three pickers on purpose. The custom dropdown used
 *  on the build screen has to fight its own stacking context to stay above
 *  the slots below it; a form that lives inside a scrolling panel does not
 *  need to re-fight that, and the browser's own listbox always wins.
 */
export default function Trades({
  uid,
  members,
}: {
  uid: string
  members: Membership[]
}) {
  const [inbox, setInbox] = useState<TradeInbox | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const [mine, setMine] = useState<Card[] | null>(null)
  const [partner, setPartner] = useState('')
  const [theirs, setTheirs] = useState<Card[] | null>(null)
  const [theirsLoading, setTheirsLoading] = useState(false)
  const [offered, setOffered] = useState('')
  const [requested, setRequested] = useState('')

  const others = members.filter((m) => m.uid !== uid)

  const load = () => {
    setLoading(true)
    setError(null)
    Promise.all([getTrades(), getMyCollection()])
      .then(([next, cards]) => {
        setInbox(next)
        setMine(cards)
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : 'failed to load trades')
      })
      .finally(() => setLoading(false))
  }

  useEffect(load, [uid])

  // Their collection is public by uid, so the picker shows real cards rather
  // than asking anyone to type an id.
  useEffect(() => {
    if (!partner) {
      setTheirs(null)
      return
    }
    setTheirsLoading(true)
    setRequested('')
    getCollection(partner)
      .then(setTheirs)
      .catch(() => setTheirs([]))
      .finally(() => setTheirsLoading(false))
  }, [partner])

  /** Every action returns one trade and then everything is re-read, because
   *  an accept moves two cards and both collections are now wrong. */
  const act = (key: string, action: () => Promise<unknown>, fallback: string) => {
    setBusy(key)
    setError(null)
    action()
      .then(() => {
        setOffered('')
        setRequested('')
        load()
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : fallback)
      })
      .finally(() => setBusy(null))
  }

  if (loading && !inbox) return <p className="trades__note">Loading trades…</p>

  const incoming = inbox?.incoming ?? []
  const outgoing = inbox?.outgoing ?? []
  const canPropose = !!partner && !!offered && !!requested && busy === null

  return (
    <section className="trades">
      <div className="trades__head">
        <div>
          <p className="league__eyebrow">Trades</p>
          <h2 className="trades__title">The Wire</h2>
        </div>
        <button className="trades__refresh" onClick={load} disabled={loading}>
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      {error && <p className="error-banner">{error}</p>}

      <div className="trades__propose">
        <h3 className="trades__subtitle">Propose a trade</h3>
        {others.length === 0 ? (
          <p className="trades__note">
            Nobody else is in your league yet. Send the invite code out and the
            trade block opens itself.
          </p>
        ) : (
          <form
            className="trades__form"
            onSubmit={(e) => {
              e.preventDefault()
              if (canPropose) {
                act(
                  'propose',
                  () => proposeTrade(partner, offered, requested),
                  'failed to propose the trade',
                )
              }
            }}
          >
            <label className="trades__field">
              <span className="trades__label">With</span>
              <select
                className="trades__select"
                value={partner}
                onChange={(e) => setPartner(e.target.value)}
              >
                <option value="">choose a member</option>
                {others.map((m) => (
                  <option key={m.uid} value={m.uid}>
                    {m.display_name || m.uid}
                  </option>
                ))}
              </select>
            </label>

            <label className="trades__field">
              <span className="trades__label">You give</span>
              <select
                className="trades__select"
                value={offered}
                onChange={(e) => setOffered(e.target.value)}
                disabled={!mine || mine.length === 0}
              >
                <option value="">
                  {mine && mine.length === 0 ? 'no cards yet' : 'choose your card'}
                </option>
                {(mine ?? []).map((c) => (
                  <option key={c.card_id} value={c.card_id}>
                    {describe(c)}
                  </option>
                ))}
              </select>
            </label>

            <label className="trades__field">
              <span className="trades__label">You get</span>
              <select
                className="trades__select"
                value={requested}
                onChange={(e) => setRequested(e.target.value)}
                disabled={!partner || theirsLoading || (theirs ?? []).length === 0}
              >
                <option value="">
                  {!partner
                    ? 'choose a member first'
                    : theirsLoading
                      ? 'loading…'
                      : (theirs ?? []).length === 0
                        ? 'they have no cards'
                        : 'choose their card'}
                </option>
                {(theirs ?? []).map((c) => (
                  <option key={c.card_id} value={c.card_id}>
                    {describe(c)}
                  </option>
                ))}
              </select>
            </label>

            <button type="submit" disabled={!canPropose}>
              {busy === 'propose' ? 'Sending…' : 'Propose'}
            </button>
          </form>
        )}
      </div>

      <div className="trades__inbox">
        <h3 className="trades__subtitle">Incoming</h3>
        {incoming.length === 0 && <p className="trades__note">No offers on the table.</p>}
        {incoming.map((view) => (
          <TradeRow
            key={view.trade.trade_id}
            view={view}
            side="incoming"
            busy={busy}
            onAccept={() =>
              act(view.trade.trade_id, () => acceptTrade(view.trade.trade_id), 'failed to accept')
            }
            onReject={() =>
              act(view.trade.trade_id, () => rejectTrade(view.trade.trade_id), 'failed to reject')
            }
          />
        ))}
      </div>

      <div className="trades__inbox">
        <h3 className="trades__subtitle">Outgoing</h3>
        {outgoing.length === 0 && <p className="trades__note">You have made no offers.</p>}
        {outgoing.map((view) => (
          <TradeRow
            key={view.trade.trade_id}
            view={view}
            side="outgoing"
            busy={busy}
            onCancel={() =>
              act(view.trade.trade_id, () => cancelTrade(view.trade.trade_id), 'failed to cancel')
            }
          />
        ))}
      </div>
    </section>
  )
}

/** OVR, contract and the night it was built -- enough to tell two cards apart
 *  and to judge whether the deal is any good. */
function describe(card: Card): string {
  return `OVR ${card.ovr} · ${formatSalary(card.contract)}/yr · ${card.date}`
}

function TradeRow({
  view,
  side,
  busy,
  onAccept,
  onReject,
  onCancel,
}: {
  view: TradeView
  side: 'incoming' | 'outgoing'
  busy: string | null
  onAccept?: () => void
  onReject?: () => void
  onCancel?: () => void
}) {
  const { trade, offered_card, requested_card } = view
  const pending = trade.status === 'pending'
  const working = busy === trade.trade_id
  // An incoming trade reads from the recipient's side: what the proposer
  // offered is what you get.
  const youGet = side === 'incoming' ? offered_card : requested_card
  const youGive = side === 'incoming' ? requested_card : offered_card
  const other = side === 'incoming' ? trade.proposer_name : trade.recipient_name

  return (
    <article className={pending ? 'trade' : 'trade trade--resolved'}>
      <div className="trade__head">
        <p className="trade__who">{other || (side === 'incoming' ? trade.proposer_uid : trade.recipient_uid)}</p>
        <p className={pending ? 'trade__status' : 'trade__status trade__status--done'}>
          {trade.status}
        </p>
      </div>

      <div className="trade__legs">
        <div className="trade__leg">
          <p className="trade__leg-label">You get</p>
          <p className="trade__card">{youGet ? describe(youGet) : 'card no longer exists'}</p>
        </div>
        <div className="trade__leg">
          <p className="trade__leg-label">You give</p>
          <p className="trade__card">{youGive ? describe(youGive) : 'card no longer exists'}</p>
        </div>
      </div>

      {trade.resolution_note && <p className="trade__note">{trade.resolution_note}</p>}

      {pending && (
        <div className="trade__actions">
          {side === 'incoming' ? (
            <>
              <button className="trade__accept" onClick={onAccept} disabled={working}>
                {working ? 'Working…' : 'Accept'}
              </button>
              <button className="trade__decline" onClick={onReject} disabled={working}>
                Reject
              </button>
            </>
          ) : (
            <button className="trade__decline" onClick={onCancel} disabled={working}>
              {working ? 'Working…' : 'Cancel'}
            </button>
          )}
        </div>
      )}
    </article>
  )
}
