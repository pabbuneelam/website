import { useState } from 'react'
import type { User } from 'firebase/auth'
import { signInWithGoogle } from '../firebase'

/**
 * Top-right of the masthead. Two states and nothing else: a Log in button, or
 * the signed-in user as a link to their account page.
 */
export default function AccountBar({
  user,
  loading,
  onOpenAccount,
}: {
  user: User | null
  loading: boolean
  onOpenAccount: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const logIn = () => {
    setBusy(true)
    setError(null)
    signInWithGoogle()
      // A closed popup is a decision, not a failure -- saying "error" there
      // would be noise.
      .catch((err: { code?: string }) => {
        if (err?.code !== 'auth/popup-closed-by-user' && err?.code !== 'auth/cancelled-popup-request') {
          setError('sign-in failed')
        }
      })
      .finally(() => setBusy(false))
  }

  // Firebase restores a persisted session asynchronously. Rendering "Log in"
  // during that window makes an already signed-in user flicker.
  if (loading) return <div className="account-bar" aria-hidden="true" />

  return (
    <div className="account-bar">
      {user ? (
        <button className="account-bar__user" onClick={onOpenAccount}>
          {user.photoURL ? (
            <img className="account-bar__avatar" src={user.photoURL} alt="" referrerPolicy="no-referrer" />
          ) : (
            <span className="account-bar__avatar account-bar__avatar--initial">
              {(user.displayName ?? user.email ?? '?').charAt(0)}
            </span>
          )}
          <span className="account-bar__name">{user.displayName ?? user.email}</span>
        </button>
      ) : (
        <button className="account-bar__login" onClick={logIn} disabled={busy}>
          {busy ? 'Opening…' : 'Log in'}
        </button>
      )}
      {error && <span className="account-bar__error">{error}</span>}
    </div>
  )
}
