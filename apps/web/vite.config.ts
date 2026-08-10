import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Read the repo-root .env so the dev server, the browser and the API all
  // agree. `envDir` also makes VITE_* variables resolve from that one file
  // rather than a second copy under apps/web that would drift.
  const env = loadEnv(mode, '../../', '')
  const port = Number(env.WEB_DEV_SERVER_PORT) || 5173

  return {
    plugins: [react()],
    envDir: '../../',
    server: {
      port,
      // Fail rather than silently move to the next free port: a UI served from
      // an origin the API does not allow looks like a broken backend.
      strictPort: true,
    },
  }
})
