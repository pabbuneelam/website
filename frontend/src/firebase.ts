import { initializeApp } from 'firebase/app'
import { GoogleAuthProvider, getAuth, signInWithPopup, signOut } from 'firebase/auth'

// Public by design. A Firebase web config identifies the project; it is not a
// secret and ships in every Firebase web app. What actually guards anything is
// the ID token the backend verifies, plus the authorised-domains list in the
// console.
const firebaseConfig = {
  apiKey: 'AIzaSyACp5uAVW7qgz37fC4KBK3W9ujRJkygdg0',
  authDomain: 'questly-7f3a2.firebaseapp.com',
  projectId: 'questly-7f3a2',
  storageBucket: 'questly-7f3a2.firebasestorage.app',
  messagingSenderId: '76941771778',
  appId: '1:76941771778:web:f6b8ce393cab367711d31b',
}

export const auth = getAuth(initializeApp(firebaseConfig))

const google = new GoogleAuthProvider()

export function signInWithGoogle() {
  return signInWithPopup(auth, google)
}

export function signOutOfSlate() {
  return signOut(auth)
}
