import type { AttributeDef, BuildPayload, Card, LeagueView, Slate, UserProfile } from './types'

// Empty by default: dev proxies (see vite.config.ts) forward the API's own
// root-level paths straight to uvicorn. Set VITE_API_BASE to call a deployed
// backend directly instead (see .env.example).
const API_BASE = import.meta.env.VITE_API_BASE ?? ''

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
  const res = await fetch(`${API_BASE}${path}`, {
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
