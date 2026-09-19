import { defineConfig } from '@playwright/test'

// Assumes both dev servers are already running (see tests/e2e/README section
// in the repo root README): `.venv/bin/uvicorn slate.api:app --port 8000`
// and `npm run dev` in `frontend/`. We don't drive them from here -- webServer
// would need to own two independent processes and their lifecycles, which
// buys nothing over documenting the two commands.
export default defineConfig({
  testDir: '.',
  timeout: 30_000,
  fullyParallel: false,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.SLATE_BASE_URL ?? 'http://localhost:5173',
    trace: 'off',
  },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 900 } } },
    { name: 'mobile', use: { viewport: { width: 390, height: 844 } } },
  ],
})
