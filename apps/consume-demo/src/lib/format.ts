/**
 * Small presentation helpers. Nothing here decides anything; each function
 * turns one server value into the words for it.
 */

/** `mm:ss`, the format the product's own wait strip uses. */
export function formatElapsed(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

/**
 * A machine reason turned into a readable one, without inventing content:
 * `no_match` becomes `No match`, and nothing else changes.
 */
export function humanise(value: string | null | undefined): string {
  if (!value) return '—'
  return value
    .split('_')
    .map((part) => (part ? part.charAt(0).toUpperCase() + part.slice(1) : part))
    .join(' ')
}

/** A heading path as the product renders it. */
export function headingLabel(path: readonly string[] | undefined, fallback?: string | null): string {
  const parts = (path ?? []).filter(Boolean)
  if (parts.length > 0) return parts.join(' › ')
  return fallback || '—'
}

/**
 * An ISO timestamp shown twice: local for a human, UTC ISO-8601 for a record.
 * Both, because a screenshot of a decision needs to be readable by whoever took
 * it and comparable by whoever receives it.
 */
export function formatTimestamp(iso: string): { local: string; utc: string } {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return { local: iso, utc: iso }
  return {
    local: date.toLocaleString(),
    utc: date.toISOString(),
  }
}

/** `{n} lines · {k} KB`, the meta line on every code region. */
export function codeMeta(text: string): string {
  const lines = text.length === 0 ? 0 : text.split('\n').length
  const bytes = new TextEncoder().encode(text).length
  const kb = bytes < 1024 ? (bytes / 1024).toFixed(2) : (bytes / 1024).toFixed(1)
  return `${lines} line${lines === 1 ? '' : 's'} · ${kb} KB`
}

/** Trigger a browser download without touching storage or the network. */
export function downloadText(filename: string, text: string, mime = 'application/json'): void {
  const blob = new Blob([text], { type: `${mime};charset=utf-8` })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}
