/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_FIREBASE_EMULATOR?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
