import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: '.',
  timeout: 15_000,
  use: {
    baseURL: process.env.TETRIS_URL || 'http://127.0.0.1:17500',
    trace: 'retain-on-failure',
  },
})
