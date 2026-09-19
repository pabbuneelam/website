import { useEffect, useState } from 'react'
import { onAuthStateChanged, type User } from 'firebase/auth'
import { auth } from './firebase'
import { setTokenProvider, upsertProfile } from './api'

export interface AuthState {
  user: User | null
  /** True until Firebase has restored (or ruled out) a persisted session.
   *  Rendering "Log in" during that window makes a signed-in user flicker. */
  loading: boolean
}

// Wired once per app load, at module scope rather than in an effect: a request
// could otherwise be in flight before the effect ran and would go out
// unauthenticated. The token is short-lived and the SDK refreshes it, so this
// is a provider, not a cached string.
setTokenProvider(() => auth.currentUser?.getIdToken() ?? Promise.resolve(null))

export function useAuth(): AuthState {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    return onAuthStateChanged(auth, (next) => {
      setUser(next)
      setLoading(false)
      // Fire-and-forget: a failed profile write must not block the UI, and
      // the next sign-in retries it anyway.
      if (next) upsertProfile().catch(() => {})
    })
  }, [])

  return { user, loading }
}
