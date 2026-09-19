import { useEffect, useLayoutEffect, useRef, useState, type FormEvent } from 'react'
import { MAX_MESSAGE_LENGTH, listenMessages, sendMessage, type ChatUser, type Message } from '../chat'

/** How close to the bottom still counts as "reading the newest". Slack-ish. */
const STICK_PX = 64

function initial(name: string) {
  return name.charAt(0) || '?'
}

function stamp(at: Date | null) {
  if (!at) return 'sending…'
  const today = new Date().toDateString() === at.toDateString()
  return at.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) + (today ? '' : ` · ${at.toLocaleDateString([], { month: 'short', day: 'numeric' })}`)
}

/**
 * One open conversation: header, the messages, the composer.
 *
 * `exists` is false for a thread that has been picked from the directory but
 * never written to. There is no document yet, and the security rules read the
 * parent conversation to decide who may read its messages — so attaching a
 * listener would be denied rather than empty. The first send creates it.
 */
export default function ChatThread({
  me,
  them,
  convId,
  exists,
  onBack,
}: {
  me: ChatUser
  them: ChatUser
  convId: string
  exists: boolean
  onBack: () => void
}) {
  const [messages, setMessages] = useState<Message[] | null>(exists ? null : [])
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)

  const scroller = useRef<HTMLDivElement | null>(null)
  // Whether the view should follow new messages. Flipped by the reader, not
  // by us: someone scrolled up into history must not be yanked back down
  // every time the other person types.
  const stick = useRef(true)
  const [pinned, setPinned] = useState(true)

  useEffect(() => {
    setMessages(exists ? null : [])
    setError(null)
    stick.current = true
    setPinned(true)
    if (!exists) return
    return listenMessages(convId, setMessages, setError)
  }, [convId, exists])

  // Layout effect, so the jump to the bottom happens in the same frame the
  // message paints -- an effect would show one frame of the old position.
  useLayoutEffect(() => {
    const el = scroller.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [messages])

  const onScroll = () => {
    const el = scroller.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_PX
    stick.current = atBottom
    setPinned(atBottom)
  }

  const jumpToLatest = () => {
    const el = scroller.current
    if (!el) return
    el.scrollTop = el.scrollHeight
    stick.current = true
    setPinned(true)
  }

  const send = (event: FormEvent) => {
    event.preventDefault()
    const text = draft.trim()
    if (!text || sending) return
    setSending(true)
    setError(null)
    // Clear optimistically: the input is the one thing that must feel instant.
    setDraft('')
    // Sending is always an intent to watch the result of it.
    stick.current = true
    setPinned(true)
    sendMessage(me, them, text)
      .catch(() => {
        setError('message not sent')
        setDraft(text)
      })
      .finally(() => setSending(false))
  }

  const over = draft.trim().length > MAX_MESSAGE_LENGTH

  return (
    <section className="chat-thread">
      <header className="chat-thread__head">
        <button className="chat-thread__back" onClick={onBack} aria-label="Back to conversations">
          ←
        </button>
        {them.photoURL ? (
          <img className="chat-thread__avatar" src={them.photoURL} alt="" referrerPolicy="no-referrer" />
        ) : (
          <span className="chat-thread__avatar chat-thread__avatar--initial">{initial(them.displayName)}</span>
        )}
        <h2 className="chat-thread__name">{them.displayName}</h2>
      </header>

      <div className="chat-thread__scroll" ref={scroller} onScroll={onScroll}>
        {messages === null && <p className="chat__note">Loading messages…</p>}
        {messages !== null && messages.length === 0 && (
          <p className="chat__note">No messages yet. Say something.</p>
        )}
        {messages?.map((m) => {
          const mine = m.senderId === me.uid
          return (
            <div key={m.id} className={mine ? 'chat-msg chat-msg--mine' : 'chat-msg'}>
              <div className="chat-msg__bubble">
                <p className="chat-msg__text">{m.text}</p>
                <span className="chat-msg__stamp">{stamp(m.createdAt)}</span>
              </div>
            </div>
          )
        })}
      </div>

      {!pinned && (
        <button className="chat-thread__jump" onClick={jumpToLatest}>
          Latest ↓
        </button>
      )}

      {error && <p className="error-banner chat__error">{error}</p>}

      <form className="chat-compose" onSubmit={send}>
        <input
          className="chat-compose__input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={`Message ${them.displayName}`}
          maxLength={MAX_MESSAGE_LENGTH + 1}
          aria-label="Message"
        />
        <button className="chat-compose__send" type="submit" disabled={sending || !draft.trim() || over}>
          {sending ? 'Sending…' : 'Send'}
        </button>
      </form>
      {over && <p className="chat__note chat__note--warn">{MAX_MESSAGE_LENGTH} characters is the limit.</p>}
    </section>
  )
}
