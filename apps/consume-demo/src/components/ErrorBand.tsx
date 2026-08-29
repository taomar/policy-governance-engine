import { STALE_CAPTION } from '../copy/strings'
import type { PlaygroundError, RecoveryKind } from '../lib/errors'
import { CopyButton } from './CodeBlock'

/**
 * A failure stays on the page.
 *
 * A failed policy decision is itself evidence -- of a token that was refused, a
 * project that does not exist, a key that was already spent -- and evidence
 * that vanishes on a timer is not evidence. So this is a band in the document
 * flow, `role="alert"`, with the correlation id of the failed attempt and a
 * control that copies the details for a support conversation.
 *
 * The previous successful receipt, if there was one, is retained and dimmed
 * rather than replaced. A caller who has just failed a refresh still needs the
 * decision they already had, and silently swapping it for an error is how a
 * stale verdict gets mistaken for a current one -- so it stays, marked.
 */

export function ErrorBand({
  error,
  onRetry,
  onGenerateKey,
  onLookup,
  baseUrl,
  onAnnounce,
}: {
  error: PlaygroundError
  onRetry: () => void
  onGenerateKey: () => void
  onLookup: (decisionId: string) => void
  baseUrl: string
  onAnnounce: (message: string) => void
}) {
  const details = JSON.stringify(
    {
      status: error.status,
      code: error.code ?? null,
      correlation_id: error.correlationId ?? null,
      decision_id: error.decisionId ?? null,
      detail: error.detail ?? null,
    },
    null,
    2,
  )

  const recovery: Record<RecoveryKind, React.ReactNode> = {
    retry: (
      <button type="button" className="btn" onClick={onRetry}>
        Retry
      </button>
    ),
    'retry-open-base': (
      <>
        <button type="button" className="btn" onClick={onRetry}>
          Retry
        </button>
        <a className="link small" href={baseUrl} target="_blank" rel="noopener noreferrer">
          Open the API base in a new tab →
        </a>
      </>
    ),
    'retry-lookup': (
      <>
        <button type="button" className="btn" onClick={onRetry}>
          Retry
        </button>
        <form
          style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}
          onSubmit={(event) => {
            event.preventDefault()
            const input = event.currentTarget.elements.namedItem('decision-id')
            if (input instanceof HTMLInputElement && input.value.trim()) onLookup(input.value.trim())
          }}
        >
          <input
            className="input input--mono"
            name="decision-id"
            data-testid="playground-lookup-id"
            placeholder="decision id"
            defaultValue={error.decisionId ?? ''}
            aria-label="Look up a decision by id"
            style={{ width: 300, maxWidth: '100%' }}
          />
          <button type="submit" className="btn">
            Look up by decision id
          </button>
        </form>
      </>
    ),
    'generate-key': (
      <button type="button" className="btn" data-testid="playground-generate-new-key" onClick={onGenerateKey}>
        Generate a new key
      </button>
    ),
    'focus-subscription-key': null,
    'focus-key': null,
    'focus-scenario': null,
    'focus-guidance': null,
    none: null,
  }

  return (
    <div className="banner banner--deny" role="alert" data-testid="playground-error">
      <span style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <code className="mono" data-testid="playground-error-status">
          {typeof error.status === 'number' ? `HTTP ${error.status}` : error.status}
        </code>
        {error.code ? <span className="pill">{error.code}</span> : null}
      </span>
      <strong className="banner__heading" data-testid="playground-error-heading">
        {error.heading}
      </strong>
      <span className="banner__body">{error.body}</span>
      {error.correlationId ? (
        <span className="xsmall">
          Correlation id: <code className="mono">{error.correlationId}</code>
        </span>
      ) : null}
      <span className="btn-row" style={{ marginTop: 4 }}>
        {recovery[error.recovery]}
        <CopyButton
          text={details}
          label="Copy error details"
          what="the error details"
          onAnnounce={onAnnounce}
        />
      </span>
    </div>
  )
}

export function StaleCaption() {
  return (
    <p className="small muted" data-testid="playground-stale-caption">
      {STALE_CAPTION}
    </p>
  )
}
