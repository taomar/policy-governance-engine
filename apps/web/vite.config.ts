import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Read the repo-root .env so the dev server and the API agree on one port.
  // Without this, Vite picks its own port when the default is taken, and the
  // API's CORS allowlist — built from WEB_DEV_SERVER_PORT — no longer contains
  // the origin the browser actually uses. The symptom is a blocked request with
  // nothing in the server log to explain it.
  const env = loadEnv(mode, '../../', '')
  const port = Number(env.WEB_DEV_SERVER_PORT) || 5173

  return {
    plugins: [react()],
    server: {
      port,
      // Fail rather than silently move to the next free port: a UI served from
      // an origin the API does not allow looks like a broken backend.
      strictPort: true,
    },
  }
})
