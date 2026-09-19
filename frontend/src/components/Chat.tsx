import { useEffect, useMemo, useState } from 'react'
import type { User } from 'firebase/auth'
import {
  conversationId,
  listDirectory,
  listenConversations,
  otherParticipant,
  type ChatUser,
  type Conversation,
} from '../chat'
import ChatThread from './ChatThread'

function initial(name: string) {
  return name.charAt(0) || '?'
}

function when(at: Date | null) {
  if (!at) return ''
  const today = new Date().toDateString() === at.toDateString()
  return today
    ? at.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    : at.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

/**
 * Messages: the thread list on the left, one open conversation on the right.
 *
 * Both panes are live Firestore listeners. Nothing in here polls, and nothing
 * in here goes through the FastAPI backend -- see chat.ts.
 */
export default function Chat({ user }: { user: User }) {
  const me: ChatUser = useMemo(
    () => ({
      uid: user.uid,
      displayName: user.displayName ?? user.email ?? 'You',
      photoURL: user.photoURL ?? null,
    }),
    [user.uid, user.displayName, user.email, user.photoURL],
  )

  // null means "still loading" -- distinct from an empty inbox, which is a
  // real and common state that deserves its own copy.
  const [conversations, setConversations] = useState<Conversation[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const [partner, setPartner] = useState<ChatUser | null>(null)

  const [directory, setDirectory] = useState<ChatUser[] | null>(null)
  const [picking, setPicking] = useState(false)

  useEffect(() => {
    setConversations(null)
    setError(null)
    return listenConversations(me.uid, setConversations, setError)
  }, [me.uid])

  const openPicker = () => {
    setPicking(true)
    if (directory) return
    listDirectory(me.uid)
      .then(setDirectory)
      .catch(() => setError('could not load the directory'))
  }

  // Known display names and avatars, so a thread opened from the list still
  // has a face on it without a per-row read.
  const known = useMemo(() => {
    const map = new Map<string, ChatUser>()
    for (const u of directory ?? []) map.set(u.uid, u)
    return map
  }, [directory])

  const openConversation = (conv: Conversation) => {
    const uid = otherParticipant(conv, me.uid)
    setPartner(known.get(uid) ?? { uid, displayName: conv.names[uid] ?? uid.slice(0, 8), photoURL: null })
    setPicking(false)
  }

  const activeId = partner ? conversationId(me.uid, partner.uid) : null
  // A thread picked from the directory but never written to has no document
  // yet. See ChatThread -- listening to its messages would be denied, not
  // empty, because the rules read the parent to authorise the read.
  const activeExists = !!activeId && !!conversations?.some((c) => c.id === activeId)

  return (
    <div className={partner ? 'chat chat--open' : 'chat'}>
      <aside className="chat-list">
        <div className="chat-list__head">
          <h2 className="chat-list__title">Messages</h2>
          <button className="chat-list__new" onClick={openPicker}>
            New
          </button>
        </div>

        {error && <p className="error-banner chat__error">{error}</p>}

        {picking && (
          <div className="chat-directory">
            <p className="chat-directory__label">Start a conversation</p>
            {directory === null && <p className="chat__note">Loading people…</p>}
            {directory?.length === 0 && <p className="chat__note">Nobody else has signed in yet.</p>}
            {directory?.map((u) => (
              <button
                key={u.uid}
                className="chat-row"
                onClick={() => {
                  setPartner(u)
                  setPicking(false)
                }}
              >
                {u.photoURL ? (
                  <img className="chat-row__avatar" src={u.photoURL} alt="" referrerPolicy="no-referrer" />
                ) : (
                  <span className="chat-row__avatar chat-row__avatar--initial">{initial(u.displayName)}</span>
                )}
                <span className="chat-row__body">
                  <span className="chat-row__name">{u.displayName}</span>
                </span>
              </button>
            ))}
            <button className="chat-directory__cancel" onClick={() => setPicking(false)}>
              Cancel
            </button>
          </div>
        )}

        {!picking && conversations === null && <p className="chat__note">Loading conversations…</p>}
        {!picking && conversations?.length === 0 && (
          <p className="chat__note">No conversations yet. Press New to start one.</p>
        )}

        {!picking &&
          conversations?.map((conv) => {
            const uid = otherParticipant(conv, me.uid)
            const name = known.get(uid)?.displayName ?? conv.names[uid] ?? uid.slice(0, 8)
            const photo = known.get(uid)?.photoURL ?? null
            return (
              <button
                key={conv.id}
                className={conv.id === activeId ? 'chat-row chat-row--active' : 'chat-row'}
                onClick={() => openConversation(conv)}
              >
                {photo ? (
                  <img className="chat-row__avatar" src={photo} alt="" referrerPolicy="no-referrer" />
                ) : (
                  <span className="chat-row__avatar chat-row__avatar--initial">{initial(name)}</span>
                )}
                <span className="chat-row__body">
                  <span className="chat-row__name">{name}</span>
                  <span className="chat-row__preview">
                    {conv.lastSenderId === me.uid ? 'You: ' : ''}
                    {conv.lastMessage}
                  </span>
                </span>
                <span className="chat-row__when">{when(conv.lastMessageAt)}</span>
              </button>
            )
          })}
      </aside>

      {partner && activeId ? (
        <ChatThread
          me={me}
          them={partner}
          convId={activeId}
          exists={activeExists}
          onBack={() => setPartner(null)}
        />
      ) : (
        <section className="chat-thread chat-thread--empty">
          <p className="chat__note">Pick a conversation, or start a new one.</p>
        </section>
      )}
    </div>
  )
}
