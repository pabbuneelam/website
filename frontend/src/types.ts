// Mirrors slate/models.py and the shapes returned by slate/api.py.

export interface AttributeDef {
  slot: string
  label: string
  requires: string
  guardrail: string
}

export interface Game {
  game_id: number
  home: string
  away: string
  tipoff: string
}

export interface SlatePlayer {
  player_id: number
  name: string
  team: string
  opponent: string
  salary: number | null
}

export interface Slate {
  date: string
  slots: string[]
  games: Game[]
  players: SlatePlayer[]
}

export interface Selection {
  slot: string
  player_id: number
}

export interface BuildPayload {
  // No creator: the backend takes identity from the bearer token.
  selections: Selection[]
}

export interface Rating {
  slot: string
  label: string
  player_id: number
  player_name: string
  rating: number
  value: number | null
  percentile: number
  salary: number | null
  note: string
  pts: number
  reb: number
  ast: number
  fantasy: number
}

export interface UserProfile {
  uid: string
  display_name: string
  email: string | null
  photo_url: string | null
  created_at: string
}

export interface Card {
  card_id: string
  uid: string
  creator_name: string
  date: string
  ovr: number
  contract: number
  ratings: Rating[]
  void: boolean
  void_reason: string
}

/** A league. The invite code is the whole join flow -- there is no browse. */
export interface League {
  league_id: string
  name: string
  code: string
  owner_uid: string
  created_at: string
}

/** One user's place in one league. A user is in exactly one at a time, so
 *  uid keys this the same way it keys a card. */
export interface Membership {
  uid: string
  league_id: string
  display_name: string
  joined_at: string
}

/** What /leagues/me, /leagues and /leagues/join all return. `league` is null
 *  when the caller is not in one -- an ordinary state, not an error. */
export interface LeagueView {
  league: League | null
  members: Membership[]
}

/** A trade is card-for-card and nothing else. No currency: it would turn good
 *  predictors into farmers running a secondary market. Build picks and cap
 *  space are deferred until an entitlement model and a payroll cap exist. */
export type TradeStatus = 'pending' | 'accepted' | 'rejected' | 'cancelled'

export interface Trade {
  trade_id: string
  league_id: string
  proposer_uid: string
  recipient_uid: string
  offered_card_id: string
  requested_card_id: string
  status: TradeStatus
  proposer_name: string
  recipient_name: string
  created_at: string
  resolved_at: string
  resolution_note: string
}

/** A trade with both cards read live, so an offer can be judged on OVR and
 *  contract rather than on two opaque ids. Either can be null if a card was
 *  removed out from under the trade. */
export interface TradeView {
  trade: Trade
  offered_card: Card | null
  requested_card: Card | null
}

/** Split by side because the actions differ: you accept or reject what came
 *  in, you cancel what went out. */
export interface TradeInbox {
  incoming: TradeView[]
  outgoing: TradeView[]
}
