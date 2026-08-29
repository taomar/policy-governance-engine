import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'

/**
 * The entire bootstrap. No provider tree, no store, no router, no telemetry
 * client -- a demonstration client that needed any of those would be evidence
 * against the API rather than for it.
 */
const root = document.getElementById('root')
if (!root) throw new Error('The page has no #root element to mount into.')

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
