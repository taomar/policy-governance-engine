import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

/**
 * The playground is a separate application, not a second entry point of the
 * product's web app.
 *
 * Two consequences are configured here rather than assumed:
 *
 *   * `envDir` is this directory. `apps/web` deliberately reads the repository
 *     root `.env` so the product UI, the API and the browser agree on one set
 *     of values -- but an external client is supposed to be configured the way
 *     an external client would be, from its own file. Reading the product's
 *     root `.env` would let a variable the platform owns leak into a demo that
 *     is meant to prove it needs nothing but a URL.
 *
 *   * The port is fixed at 5179 and `strictPort` is on. 5179 sits inside the
 *     API's default development CORS range, so the browser is allowed to call
 *     it out of the box; silently moving to the next free port would present
 *     as a broken backend rather than as a port collision.
 */
export default defineConfig({
  plugins: [react()],
  envDir: '.',
  server: {
    port: 5179,
    strictPort: true,
  },
})
