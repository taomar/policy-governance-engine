import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { codeMeta, downloadText } from '../lib/format'

/**
 * The Code Night region and the two controls that always accompany it.
 *
 * TWO RULES THIS COMPONENT ENFORCES STRUCTURALLY
 *
 * 1. **What is copied is what is displayed.** `copyText` defaults to the
 *    rendered text and is only ever overridden to something *more* redacted,
 *    never less. The Raw HTTP tab passes the masked form for both, so there is
 *    no code path on which a real bearer token reaches the clipboard.
 *
 * 2. **Code wraps; it never scrolls sideways.** A horizontal scrollbar is how a
 *    long quoted provision or a 64-character hash gets hidden from a reader who
 *    had no reason to suspect there was more.
 */

interface CopyButtonProps {
  text: string
  label: string
  /** What the live region announces, e.g. `the request JSON`. */
  what: string
  onAnnounce: (message: string) => void
  disabled?: boolean
  className?: string
}

export function CopyButton({ text, label, what, onAnnounce, disabled, className }: CopyButtonProps) {
  const [copied, setCopied] = useState(false)
  const [blocked, setBlocked] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => () => clearTimeout(timer.current), [])

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setBlocked(false)
      onAnnounce(`Copied ${what} to the clipboard.`)
      clearTimeout(timer.current)
      timer.current = setTimeout(() => setCopied(false), 1600)
    } catch {
      // Stated rather than swallowed. The block is `user-select: text`, so
      // manual selection is always possible and the caption says so.
      setCopied(false)
      setBlocked(true)
    }
  }, [text, what, onAnnounce])

  return (
    <>
      <button
        type="button"
        className={className ?? 'btn'}
        onClick={copy}
        disabled={disabled}
        title={`Copy ${what}`}
        aria-label={`Copy ${what}`}
      >
        {copied ? 'Copied' : label}
      </button>
      {blocked ? (
        <span className="xsmall" style={{ color: 'var(--danger)' }} data-testid="copy-error">
          Copy was blocked by the browser. Select the text and copy manually.
        </span>
      ) : null}
    </>
  )
}

interface CodeBlockProps {
  /** The text rendered in the block, line-numbered. */
  text: string
  /** What is written to the clipboard and to a download. Defaults to `text`. */
  copyText?: string
  language: string
  /** Used in aria-labels and copy announcements, e.g. `the request JSON`. */
  what: string
  downloadName?: string
  downloadMime?: string
  caption?: ReactNode
  maxHeight?: number
  testId?: string
  onAnnounce: (message: string) => void
  /** Rendered inside the block instead of plain text, for JSON colouring. */
  renderLine?: (line: string, index: number) => ReactNode
}

export function CodeBlock({
  text,
  copyText,
  language,
  what,
  downloadName,
  downloadMime = 'application/json',
  caption,
  maxHeight,
  testId,
  onAnnounce,
  renderLine,
}: CodeBlockProps) {
  const emitted = copyText ?? text
  const lines = text.split('\n')

  return (
    <div>
      <div className="code" data-testid={testId}>
        <div
          className="code__scroll"
          style={maxHeight ? ({ ['--code-max-height' as string]: `${maxHeight}px` } as React.CSSProperties) : undefined}
          tabIndex={0}
          role="group"
          aria-label={`${language} — ${what}`}
        >
          <pre className="code__pre">
            {lines.map((line, index) => (
              <span key={index} style={{ display: 'contents' }}>
                <span className="code__ln" aria-hidden="true">
                  {index + 1}
                </span>
                <span className="code__line">{renderLine ? renderLine(line, index) : line}</span>
              </span>
            ))}
          </pre>
        </div>
        <div className="code__meta">
          <span>{codeMeta(emitted)}</span>
          <span className="btn-row">
            <CopyButton text={emitted} label="Copy" what={what} onAnnounce={onAnnounce} />
            {downloadName ? (
              <button
                type="button"
                className="btn"
                onClick={() => downloadText(downloadName, emitted, downloadMime)}
                title={`Download ${what}`}
                aria-label={`Download ${what} as ${downloadName}`}
                data-download-name={downloadName}
              >
                Download
              </button>
            ) : null}
          </span>
        </div>
      </div>
      {caption ? <p className="code__caption" style={{ marginTop: 6 }}>{caption}</p> : null}
    </div>
  )
}

/**
 * JSON token colouring, applied per line.
 *
 * Deliberately a regex over the already-serialised text rather than a walk of
 * the object: the block must show the bytes that will be sent, including the
 * key order, and re-serialising for display is how a preview stops being a
 * preview of the real thing.
 */
export function renderJsonLine(line: string, index: number): ReactNode {
  const parts: ReactNode[] = []
  const pattern = /("(?:\\.|[^"\\])*"\s*:)|("(?:\\.|[^"\\])*")|(\b-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b)|(\btrue\b|\bfalse\b)|(\bnull\b)/g

  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = pattern.exec(line)) !== null) {
    if (match.index > lastIndex) parts.push(line.slice(lastIndex, match.index))
    const [full, key, str, num, bool, nul] = match
    const className = key
      ? 'tok-key'
      : str
        ? 'tok-string'
        : num
          ? 'tok-number'
          : bool
            ? 'tok-boolean'
            : nul
              ? 'tok-null'
              : ''
    parts.push(
      <span key={`${index}-${match.index}`} className={className}>
        {full}
      </span>,
    )
    lastIndex = match.index + full.length
  }

  if (lastIndex < line.length) parts.push(line.slice(lastIndex))
  return parts.length > 0 ? parts : line
}
