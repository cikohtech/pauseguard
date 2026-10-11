import { defineConfig, devices } from '@playwright/test'

// `make a11y`: the customer app in a real browser against a production build, with the API
// mocked at the network layer (e2e/fixtures.ts), so it needs no backend or Gemini.
// Every screen is scanned with axe (WCAG 2.1 A/AA) on a desktop and a phone viewport.
const PORT = 4173

export default defineConfig({
  testDir: './e2e',
  outputDir: 'test-results/artifacts', // screens/ (from the tests) survives a re-run
  timeout: 60_000,
  fullyParallel: true,
  reporter: [['list']],
  use: { baseURL: `http://localhost:${PORT}`, trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1280, height: 900 } } },
    { name: 'phone', use: { ...devices['iPhone 13'], browserName: 'chromium' } },
  ],
  webServer: {
    command: `npx vite build --mode e2e --outDir dist-e2e && npx vite preview --outDir dist-e2e --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}/app`,
    reuseExistingServer: false,
    timeout: 120_000,
    env: { VITE_API_BASE_URL: 'http://api.test', VITE_FIREBASE_CONFIG_JSON: '{}' },
  },
})
