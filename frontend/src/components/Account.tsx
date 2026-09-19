import { useEffect, useState } from 'react'
import type { User } from 'firebase/auth'
import { ApiError, getProfile } from '../api'
import type { UserProfile } from '../types'
import { signOutOfSlate } from '../firebase'

/** What the signed-in user looks like to Slate, and the way out. */
export default function Account({ user }: { user: User }) {
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getProfile()
      .then(setProfile)
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : 'failed to load profile')
      })
  }, [user.uid])

  return (
    <div className="account">
      <div className="account__head">
        {user.photoURL ? (
          <img className="account__avatar" src={user.photoURL} alt="" referrerPolicy="no-referrer" />
        ) : (
          <span className="account__avatar account__avatar--initial">
            {(user.displayName ?? user.email ?? '?').charAt(0)}
          </span>
        )}
        <div>
          <h2 className="account__name">{user.displayName ?? 'Unnamed'}</h2>
          <p className="account__email">{user.email}</p>
        </div>
      </div>

      {error && <p className="error-banner">{error}</p>}

      <table className="data-table account__table">
        <tbody>
          <tr>
            <th scope="row">Display name</th>
            <td>{profile?.display_name ?? user.displayName ?? '—'}</td>
          </tr>
          <tr>
            <th scope="row">Email</th>
            <td>{profile?.email ?? user.email ?? '—'}</td>
          </tr>
          <tr>
            {/* Shown because it is what every card id is built from -- when a
                collection looks wrong, this is the first thing to compare. */}
            <th scope="row">User ID</th>
            <td className="account__uid">{user.uid}</td>
          </tr>
          <tr>
            <th scope="row">Member since</th>
            <td>{profile?.created_at ? profile.created_at.slice(0, 10) : '—'}</td>
          </tr>
        </tbody>
      </table>

      <div className="account__actions">
        <button className="account__logout" onClick={() => void signOutOfSlate()}>
          Log out
        </button>
      </div>
    </div>
  )
}
