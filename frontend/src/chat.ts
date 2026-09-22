// 1-on-1 messaging, straight from the browser to Firestore.
//
// The backend is not in this path on purpose: a message has to appear on the
// other screen without anyone pressing anything, and that means a live
// `onSnapshot` listener, not a poll against FastAPI. Every rule the server
// would have enforced lives in firestore.rules instead.
//
// Shape:
//   conversations/{convId}                     participants, last-message preview
//   conversations/{convId}/messages/{msgId}    one document per message
//
// One document per message, never an array on the conversation: an array is
// rewritten whole on every send, races between two senders, and caps the
// thread at the 1 MiB document limit.

import {
  addDoc,
  collection,
  doc,
  getDocs,
  limit,
  onSnapshot,
  orderBy,
  query,
  serverTimestamp,
  setDoc,
  where,
  type DocumentData,
  type QueryDocumentSnapshot,
} from 'firebase/firestore'
import { db } from './firebase'

/** Mirrored by the `text.size()` check in firestore.rules. That copy is the
 *  one that is actually enforced; this one exists to give a typing user a
 *  counter instead of a rejected write. */
export const MAX_MESSAGE_LENGTH = 1000

/** How much history the thread opens with. The rest stays unread on the
 *  server rather than being pulled down to be scrolled past. */
const PAGE_SIZE = 50

export interface ChatUser {
  uid: string
  displayName: string
  photoURL: string | null
}

export interface Conversation {
  id: string
  participants: string[]
  /** uid → display name, denormalised so the conversation list renders from
   *  one query instead of one extra read per row. */
  names: Record<string, string>
  lastMessage: string
  lastMessageAt: Date | null
  lastSenderId: string | null
}

export interface Message {
  id: string
  senderId: string
  text: string
  /** Null only in the instant between a local send and the server stamping
   *  it. Ordering is always the server's clock, never the sender's. */
  createdAt: Date | null
  pending: boolean
}

/**
 * The id for a pair of users: both uids, sorted, joined.
 *
 * Deterministic so that "Alice opens a thread with Bob" and "Bob opens a
 * thread with Alice" are the same document rather than two half-empty ones.
 * firestore.rules re-derives this server-side, so the id cannot be forged to
 * point at a pair the sender is not part of.
 */
export function conversationId(a: string, b: string): string {
  return [a, b].sort().join('__')
}

/** The other person in a 1-on-1. */
export function otherParticipant(conv: Conversation, me: string): string {
  return conv.participants.find((p) => p !== me) ?? me
}

function toDate(value: unknown): Date | null {
  // A Firestore Timestamp before it has been converted, or null while the
  // serverTimestamp() sentinel is still in flight.
  const ts = value as { toDate?: () => Date } | null | undefined
  return ts && typeof ts.toDate === 'function' ? ts.toDate() : null
}

/**
 * Everyone who has signed in, minus you — the directory the "new message"
 * picker is built from. `users/{uid}` is written by the backend on every auth
 * state change, so this is simply the roster of the app.
 */
export async function listDirectory(excludeUid: string): Promise<ChatUser[]> {
  const snap = await getDocs(query(collection(db, 'users'), limit(100)))
  return snap.docs
    .map((d: QueryDocumentSnapshot<DocumentData>) => {
      const data = d.data()
      return {
        uid: d.id,
        // Stored by slate/store.py, hence snake_case.
        displayName: (data.display_name as string) || d.id.slice(0, 8),
        photoURL: (data.photo_url as string | null) ?? null,
      }
    })
    .filter((u: ChatUser) => u.uid !== excludeUid)
    .sort((a: ChatUser, b: ChatUser) => a.displayName.localeCompare(b.displayName))
}

/**
 * Live list of the threads you are in.
 *
 * Sorted in JS rather than with `orderBy('lastMessageAt')`: pairing an
 * array-contains filter with an order on a different field needs a composite
 * index, and a prototype should not require an index deploy to boot. At fifty
 * threads the sort is free.
 */
export function listenConversations(
  uid: string,
  onChange: (conversations: Conversation[]) => void,
  onError: (message: string) => void,
): () => void {
  const q = query(
    collection(db, 'conversations'),
    where('participants', 'array-contains', uid),
    limit(PAGE_SIZE),
  )
  return onSnapshot(
    q,
    (snap) => {
      const rows: Conversation[] = snap.docs.map((d) => {
        const data = d.data()
        return {
          id: d.id,
          participants: (data.participants as string[]) ?? [],
          names: (data.names as Record<string, string>) ?? {},
          lastMessage: (data.lastMessage as string) ?? '',
          lastMessageAt: toDate(data.lastMessageAt),
          lastSenderId: (data.lastSenderId as string | null) ?? null,
        }
      })
      rows.sort((a, b) => (b.lastMessageAt?.getTime() ?? 0) - (a.lastMessageAt?.getTime() ?? 0))
      onChange(rows)
    },
    () => onError('could not load conversations'),
  )
}

/**
 * Live view of the latest messages in one thread.
 *
 * Queried newest-first so the limit keeps the *recent* end of a long thread,
 * then reversed for display so the newest sits at the bottom where a reader
 * expects it.
 */
export function listenMessages(
  convId: string,
  onChange: (messages: Message[]) => void,
  onError: (message: string) => void,
): () => void {
  const q = query(
    collection(db, 'conversations', convId, 'messages'),
    orderBy('createdAt', 'desc'),
    limit(PAGE_SIZE),
  )
  return onSnapshot(
    q,
    (snap) => {
      const rows: Message[] = snap.docs.map((d) => {
        const data = d.data()
        return {
          id: d.id,
          senderId: (data.senderId as string) ?? '',
          text: (data.text as string) ?? '',
          createdAt: toDate(data.createdAt),
          // True while the server timestamp is still unresolved locally.
          pending: d.metadata.hasPendingWrites,
        }
      })
      rows.reverse()
      onChange(rows)
    },
    () => onError('could not load messages'),
  )
}

export class ChatError extends Error {}

/**
 * Send one message, creating the thread if this is the first.
 *
 * The conversation document is written *before* the message, not for tidiness:
 * the message rule reads the parent's participant list to decide whether the
 * sender is allowed to write here, and a missing parent means a denied write.
 */
export async function sendMessage(
  me: ChatUser,
  them: ChatUser,
  rawText: string,
): Promise<void> {
  const text = rawText.trim()
  if (!text) throw new ChatError('nothing to send')
  if (text.length > MAX_MESSAGE_LENGTH) {
    throw new ChatError(`messages are limited to ${MAX_MESSAGE_LENGTH} characters`)
  }

  const convId = conversationId(me.uid, them.uid)
  const conv = doc(db, 'conversations', convId)

  await setDoc(
    conv,
    {
      // Sorted, because the id is derived from the sorted pair and the rules
      // check the two agree.
      participants: [me.uid, them.uid].sort(),
      names: { [me.uid]: me.displayName, [them.uid]: them.displayName },
      lastMessage: text.slice(0, 140),
      lastMessageAt: serverTimestamp(),
      lastSenderId: me.uid,
    },
    { merge: true },
  )

  await addDoc(collection(conv, 'messages'), {
    senderId: me.uid,
    text,
    // The server's clock. A client clock is wrong often enough by accident,
    // and trivially wrong on purpose.
    createdAt: serverTimestamp(),
  })
}
