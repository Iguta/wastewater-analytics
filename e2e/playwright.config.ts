import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.ts',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  workers: 1, // one uvicorn worker serves every test
  use: { baseURL: 'http://127.0.0.1:8000', screenshot: 'on' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  outputDir: 'test-results',
  webServer: {
    command: 'make -C .. build-ui serve',
    url: 'http://127.0.0.1:8000/api/scenarios', // warm: the first scenarios call builds the cards and outran a 15 s expect in CI
    reuseExistingServer: true,
    timeout: 180_000,
    env: { ANTHROPIC_API_KEY: '' }, // the offline path is asserted
  },
});
