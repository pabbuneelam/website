import type {
  AttributeDef,
  BuildPayload,
  Card,
  LeagueView,
  Slate,
  TradeInbox,
  TradeView,
  UserProfile,
} from './types'

// Same origin, always: the dev server proxies the API's paths to uvicorn (see
// vite.config.ts), and the deploy serves the built SPA from FastAPI itself.

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// Set once, by useAuth. A provider rather than a token string because Firebase
// ID tokens expire after an hour and the SDK mints a fresh one on demand --
// caching the string here would sign the user out mid-session.
let tokenProvider: () => Promise<string | null> = async () => null

export function setTokenProvider(provider: () => Promise<string | null>) {
  tokenProvider = provider
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await tokenProvider()
  const res = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      // body wasn't JSON -- keep the status text
    }
    throw new ApiError(res.status, detail)
  }
  return (await res.json()) as T
}

export function getAttributes(): Promise<AttributeDef[]> {
  return request('/attributes')
}

export function getSlate(date: string): Promise<Slate> {
  return request(`/slates/${encodeURIComponent(date)}`)
}

export function submitBuild(date: string, payload: BuildPayload): Promise<Card> {
  return request(`/slates/${encodeURIComponent(date)}/builds`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/** The signed-in user's own collection. Needs a token. */
export function getMyCollection(): Promise<Card[]> {
  return request('/cards/me')
}

/** Anyone's collection, by uid. Public -- leagues will want this. */
export function getCollection(uid: string): Promise<Card[]> {
  return request(`/cards/${encodeURIComponent(uid)}`)
}

/** The stored profile for the signed-in user. */
export function getProfile(): Promise<UserProfile> {
  return request('/users/me')
}

/** Record the signed-in user. Idempotent; called on every auth state change. */
export function upsertProfile(): Promise<UserProfile> {
  return request('/users/me', { method: 'POST' })
}

/** The caller's league and its members. `league` is null when there is none. */
export function getMyLeague(): Promise<LeagueView> {
  return request('/leagues/me')
}

/** Start a league and join it. 409 if the caller is already in one. */
export function createLeague(name: string): Promise<LeagueView> {
  return request('/leagues', { method: 'POST', body: JSON.stringify({ name }) })
}

/** Join by invite code. 404 on an unknown code, 409 if already in a league. */
export function joinLeague(code: string): Promise<LeagueView> {
  return request('/leagues/join', { method: 'POST', body: JSON.stringify({ code }) })
}

export function leaveLeague(): Promise<LeagueView> {
  return request('/leagues/leave', { method: 'POST' })
}

/** Both trade inboxes for the signed-in user, newest first. */
export function getTrades(): Promise<TradeInbox> {
  return request('/trades')
}

/** Offer one of your cards for one of theirs. 409 if you are not leaguemates,
 *  or if either card has already changed hands. */
export function proposeTrade(
  recipientUid: string,
  offeredCardId: string,
  requestedCardId: string,
): Promise<TradeView> {
  return request('/trades', {
    method: 'POST',
    body: JSON.stringify({
      recipient_uid: recipientUid,
      offered_card_id: offeredCardId,
      requested_card_id: requestedCardId,
    }),
  })
}

/** Take the deal. Both cards move or neither does -- the server re-checks
 *  ownership inside the same transaction that writes the swap, so a 409 here
 *  means nothing moved. */
export function acceptTrade(tradeId: string): Promise<TradeView> {
  return request(`/trades/${encodeURIComponent(tradeId)}/accept`, { method: 'POST' })
}

/** Turn down an incoming offer. Only the recipient can. */
export function rejectTrade(tradeId: string): Promise<TradeView> {
  return request(`/trades/${encodeURIComponent(tradeId)}/reject`, { method: 'POST' })
}

/** Withdraw an outgoing offer. Only the proposer can. */
export function cancelTrade(tradeId: string): Promise<TradeView> {
  return request(`/trades/${encodeURIComponent(tradeId)}/cancel`, { method: 'POST' })
}
