import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

/**
 * Test config, deliberately separate from vite.config.ts.
 *
 * Keeping it here means `vite build` and `vite dev` never import anything from
 * the test tooling: if vitest is removed, the app's build is untouched.
 *
 * `globals` is left off, so the one test file imports what it uses and nothing
 * is added to the type surface of the app's own sources.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    // Threads rather than the default forked processes: the repository path
    // contains a space, and the forks pool fails to hand a worker its entry
    // point when it does.
    pool: 'threads',
    deps: {
      // antd is thousands of modules. Transforming them one at a time cost
      // roughly four minutes a run, which is how a guard test stops being run.
      optimizer: { web: { enabled: true } },
    },
  },
})
