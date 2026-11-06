import path from 'node:path';
import { defineConfig, devices } from '@playwright/test';

const browserLibs = path.join(process.cwd(), '.libs/usr/lib/x86_64-linux-gnu');

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 0,
  use: {
    baseURL: 'http://127.0.0.1:4200',
    trace: 'on-first-retry',
    permissions: ['clipboard-read', 'clipboard-write'],
    launchOptions: {
      env: {
        ...process.env,
        LD_LIBRARY_PATH: [browserLibs, process.env['LD_LIBRARY_PATH']].filter(Boolean).join(':'),
      },
    },
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
  webServer: {
    command: 'npm start -- --host 127.0.0.1 --port 4200',
    url: 'http://127.0.0.1:4200',
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
