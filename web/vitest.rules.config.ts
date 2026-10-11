import { defineConfig } from 'vitest/config'

// Firestore rules tests (make test-rules). They need the emulator that `firebase emulators:exec`
// starts with infra/firebase.rules-test.json, so they are not part of the jsdom suite (npm test).
export default defineConfig({
  test: {
    environment: 'node',
    include: ['rules/**/*.test.ts'],
    testTimeout: 15_000,
    hookTimeout: 30_000,
    fileParallelism: false,
  },
})
