import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

/**
 * Test config, kept separate from vite.config.ts so `vite build` never imports
 * the test tooling.
 *
 * TWO SETTINGS THAT LOOK LIKE FUSSINESS AND ARE NOT
 *
 * `environment: 'node'` is the default, and only `App.test.tsx` opts into jsdom
 * with a `@vitest-environment` docblock. jsdom takes the better part of a
 * minute to stand up on this checkout, and standing it up once per test file --
 * five of which never touch the DOM -- was enough for workers to exceed the
 * pool's own startup deadline, so the run reported "no tests" rather than a
 * failure anyone could read.
 *
 * `maxWorkers: 1` for the same reason: several workers starting at once still
 * contend, and a suite this size gains nothing from parallelism it can lose
 * correctness to.
 *
 * `pool: 'forks'` rather than the `threads` the product's web app pins. That
 * app chose threads because the forked pool could not hand a worker its entry
 * point when the repository path contains a space; on the vitest this app
 * resolves, the failure is the other way round. Neither is a preference --
 * whichever pool actually starts is the one that gets used, and this note
 * records which was which so the next person does not "fix" it back.
 *
 * THE VITE VARIABLES ARE PINNED FOR TESTS
 *
 * `envDir` is this directory, so a developer running the demo locally has a
 * git-ignored `.env.local` holding a real `VITE_POLICY_SUBSCRIPTION_KEY` and
 * often a `VITE_POLICY_API_BASE_URL` pointing somewhere other than the
 * committed default. Vite inlines both here too, which would mean the suite
 * rendered that developer's credential into assertions and failure output, and
 * that tests asserting a resolved URL passed or failed depending on which
 * machine ran them. `define` pins both, so what is tested is the committed
 * default and the prefill is exercised explicitly by tests that stub the
 * variables themselves.
 */
export default defineConfig({
  plugins: [react()],
  define: {
    'import.meta.env.VITE_POLICY_SUBSCRIPTION_KEY': '""',
    'import.meta.env.VITE_POLICY_API_BASE_URL': '"http://localhost:8010"',
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.{ts,tsx}'],
    pool: 'forks',
    maxWorkers: 1,
    // One reused worker environment for the whole run, rather than a fresh one
    // per file. jsdom is stood up by a single test file and takes the better
    // part of a minute here; with an environment created per file the pool's
    // own worker-start deadline was exceeded before that file's worker ever
    // answered, and the run reported an unhandled pool error rather than a test
    // result. Adding a seventh test file was enough to cross it.
    //
    // Safe because every file cleans up after itself: `App.test.tsx` unstubs its
    // globals, unmounts, and clears both storages in `afterEach`, and the other
    // six touch no shared state at all.
    isolate: false,
    fileParallelism: false,
    globals: false,
    testTimeout: 20_000,
    hookTimeout: 60_000,
  },
})
