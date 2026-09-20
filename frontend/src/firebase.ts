import { initializeApp } from 'firebase/app'
import { GoogleAuthProvider, getAuth, signInWithPopup, signOut } from 'firebase/auth'
import { getFirestore } from 'firebase/firestore'

// Public by design. A Firebase web config identifies the project; it is not a
// secret and ships in every Firebase web app. What actually guards anything is
// the ID token the backend verifies, plus the authorised-domains list in the
// console.
const firebaseConfig = {
  apiKey: 'AIzaSyAD0wCL5TpgVH8LpkBk-1iaGtE5cFiOdqg',
  authDomain: 'slate-da17a.firebaseapp.com',
  projectId: 'slate-da17a',
  storageBucket: 'slate-da17a.firebasestorage.app',
  messagingSenderId: '33647225727',
  appId: '1:33647225727:web:0c533b9e29133cdcbd084a',
}

const app = initializeApp(firebaseConfig)

export const auth = getAuth(app)

// Messaging talks to Firestore straight from the browser, because real time
// means a live listener and not a poll against the API. Security rules
// (firestore.rules at the repo root) are what make that safe.
export const db = getFirestore(app)

const google = new GoogleAuthProvider()

export function signInWithGoogle() {
  return signInWithPopup(auth, google)
}

export function signOutOfSlate() {
  return signOut(auth)
}
