import { defineConfig } from '@playwright/test'

// Run through `npm test`, which wraps this in `firebase emulators:exec`. That
// starts the Auth and Firestore emulators and exports FIREBASE_AUTH_EMULATOR_HOST
// and FIRESTORE_EMULATOR_HOST, which both servers below inherit -- so the API
// verifies emulator tokens and stores cards in the emulator, and nothing in a
// run can reach a real Firebase project. `demo-` project ids are refused by
// every real Google service, which is the second lock on that door.
const EMULATOR_PROJECT = 'demo-slate'

export default defineConfig({
  testDir: '.',
  timeout: 30_000,
  fullyParallel: false,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.SLATE_BASE_URL ?? 'http://localhost:5173',
    trace: 'off',
    // The design animates every entrance (see the `press` keyframe in
    // styles.css). Without this, screenshots land mid-fade and the captures
    // are both non-deterministic and misleading -- a fully working card reads
    // as a rendering failure at 5% opacity. styles.css already honours
    // prefers-reduced-motion, so emulating it settles the UI instantly and
    // needs no arbitrary sleeps.
    reducedMotion: 'reduce',
  },
  webServer: [
    {
      command: '.venv/bin/uvicorn slate.api:app --port 8000',
      cwd: '../..',
      url: 'http://127.0.0.1:8000/health',
      env: { SLATE_FIREBASE_PROJECT: EMULATOR_PROJECT },
      reuseExistingServer: false,
    },
    {
      command: 'npm run dev -- --port 5173 --strictPort',
      cwd: '../../frontend',
      url: 'http://localhost:5173',
      env: { VITE_FIREBASE_EMULATOR: EMULATOR_PROJECT },
      reuseExistingServer: false,
    },
  ],
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'mobile', use: { viewport: { width: 390, height: 844 } } },
  ],
})
