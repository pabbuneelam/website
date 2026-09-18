import type { AttributeDef, BuildPayload, Card, Slate } from './types'

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
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

export function getCollection(creator: string): Promise<Card[]> {
  return request(`/cards/${encodeURIComponent(creator)}`)
}
