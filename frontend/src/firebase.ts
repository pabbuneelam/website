import { initializeApp } from 'firebase/app'
import {
  GoogleAuthProvider,
  connectAuthEmulator,
  getAuth,
  signInWithCredential,
  signInWithPopup,
  signOut,
} from 'firebase/auth'
import { connectFirestoreEmulator, getFirestore } from 'firebase/firestore'

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

// Set only by the e2e run (tests/e2e/playwright.config.ts), to the emulator's
// project id. Vite inlines it at build time, so in a production build every
// branch on it below is dead code and is dropped.
const EMULATOR_PROJECT = import.meta.env.VITE_FIREBASE_EMULATOR

const app = initializeApp(
  EMULATOR_PROJECT ? { ...firebaseConfig, projectId: EMULATOR_PROJECT } : firebaseConfig,
)

export const auth = getAuth(app)

// Messaging talks to Firestore straight from the browser, because real time
// means a live listener and not a poll against the API. Security rules
// (firestore.rules at the repo root) are what make that safe.
export const db = getFirestore(app)

if (EMULATOR_PROJECT) {
  // disableWarnings: the SDK otherwise pins a banner to the page, which would
  // be in every screenshot the visual review looks at.
  connectAuthEmulator(auth, 'http://127.0.0.1:9099', { disableWarnings: true })
  connectFirestoreEmulator(db, '127.0.0.1', 8080)
}

const google = new GoogleAuthProvider()

export function signInWithGoogle() {
  if (EMULATOR_PROJECT) {
    // A headless browser cannot complete Google OAuth. The Auth emulator
    // accepts an unsigned JSON id_token in its place, so the same Log in
    // button yields a real Firebase session for a fixed QA identity.
    const idToken = JSON.stringify({
      sub: 'qa-user',
      email: 'qa@example.com',
      name: 'QA Tester',
      email_verified: true,
    })
    return signInWithCredential(auth, GoogleAuthProvider.credential(idToken))
  }
  return signInWithPopup(auth, google)
}

export function signOutOfSlate() {
  return signOut(auth)
}
