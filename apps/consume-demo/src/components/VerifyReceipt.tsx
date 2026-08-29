import { VERIFY } from '../copy/strings'
import type { PlaygroundError } from '../lib/errors'
import type { ReceiptComparison } from '../lib/receiptComparison'

/**
 * The round trip that turns a returned decision into a verified one.
 *
 * WHY THIS IS NOT A TOAST
 *
 * A verification result is evidence, and evidence that disappears after four
 * seconds is not evidence. The comparison block is rendered into the page and
 * stays there. The mismatch band in particular has no dismiss control at all:
 * a reader who has just been told the stored receipt does not match what they
 * were handed must not be able to make that sentence go away.
 *
 * WHY FIVE ROWS AND NOT ONE
 *
 * The decision hash proves the decision-defining content is intact, but it
 * deliberately excludes record identity and timing and seals the caller's
 * guidance by digest rather than by text. Comparing the version, the timestamp,
 * the guidance string itself and the instruction profile covers what the hash
 * does not claim to cover -- and the guidance row is the one that catches the
 * quiet failure, because absent on one side and `""` on the other is a
 * mismatch that a naive comparison reports as a match.
 */

export type VerifyState =
  | { kind: 'idle' }
  | { kind: 'verifying' }
  | { kind: 'compared'; comparison: ReceiptComparison }
  | { kind: 'unavailable'; error: PlaygroundError }

function Definition({ value, testId }: { value: string | null; testId?: string }) {
  if (value === null) {
    return (
      <dd className="compare__def compare__def--absent" data-testid={testId}>
        {VERIFY.absent}
      </dd>
    )
  }
  if (value === '') {
    return (
      <dd className="compare__def compare__def--absent" data-testid={testId}>
        empty string
      </dd>
    )
  }
  return (
    <dd className="compare__def" data-testid={testId}>
      {value}
    </dd>
  )
}

export function VerifyReceipt({
  state,
  onVerify,
  decisionId,
}: {
  state: VerifyState
  onVerify: () => void
  onAnnounce: (message: string) => void
  decisionId: string
}) {
  const chip =
    state.kind === 'compared'
      ? state.comparison.matches
        ? { tone: 'allow', label: 'Verified' }
        : { tone: 'deny', label: 'Mismatch' }
      : state.kind === 'unavailable'
        ? { tone: 'note', label: 'Unverified' }
        : { tone: 'neutral', label: 'Stored' }

  return (
    <>
      <span className={`chip chip--${chip.tone}`} data-testid="receipt-status-chip">
        {chip.label}
      </span>
      <button
        type="button"
        className="btn"
        data-testid="playground-verify"
        onClick={onVerify}
        disabled={state.kind === 'verifying'}
      >
        {state.kind === 'verifying' ? VERIFY.verifying : VERIFY.button}
      </button>
      <span className="ledger__caption">{VERIFY.caption}</span>

      {state.kind === 'verifying' ? (
        <span className="visually-hidden" role="status">
          Fetching stored decision {decisionId}…
        </span>
      ) : null}

      {state.kind === 'unavailable' ? (
        <div
          className={`banner banner--${state.error.status === 410 ? 'deny' : 'note'}`}
          data-testid="verify-unavailable"
          style={{ flexBasis: '100%' }}
        >
          <strong className="banner__heading">{state.error.heading}</strong>
          <span className="banner__body">{state.error.body}</span>
          {state.error.status === 409 ? (
            <span>
              <button type="button" className="btn" onClick={onVerify}>
                {VERIFY.pendingRetry}
              </button>
            </span>
          ) : null}
        </div>
      ) : null}

      {state.kind === 'compared' ? (
        <div style={{ flexBasis: '100%' }}>
          <div
            className={`banner banner--${state.comparison.matches ? 'allow' : 'deny'}`}
            data-testid={state.comparison.matches ? 'verify-match' : 'verify-mismatch'}
          >
            {/* The word carries the meaning; the colour only reinforces it. */}
            <strong className="banner__heading">
              {state.comparison.matches ? VERIFY.match : VERIFY.mismatch}
            </strong>
            {state.comparison.matches ? null : (
              <span className="banner__body">{VERIFY.mismatchBody}</span>
            )}
            {state.comparison.guidanceMismatch ? (
              <span className="banner__body" data-testid="verify-guidance-mismatch">
                {VERIFY.guidanceMismatch}
              </span>
            ) : null}
          </div>

          <dl className="compare" data-testid="verify-comparison" style={{ marginTop: 8 }}>
            {state.comparison.rows.map((row) => (
              <div className="compare__row" key={row.id}>
                <div className="compare__head">
                  <span style={{ fontWeight: 600 }}>{row.label}</span>
                  <span className={`chip chip--${row.verdict === 'match' ? 'allow' : 'deny'}`}>
                    {row.verdict === 'match' ? 'matches' : 'does not match'}
                  </span>
                </div>
                {row.presenceDiffers ? (
                  <p className="xsmall muted">
                    One side records the field and the other does not. Presence and absence are
                    compared, not only content.
                  </p>
                ) : null}
                <div className="compare__pairs">
                  <dt className="compare__term">{VERIFY.returned}</dt>
                  <Definition value={row.returned} testId={`verify-${row.id}-returned`} />
                  <dt className="compare__term">{VERIFY.stored}</dt>
                  <Definition value={row.stored} testId={`verify-${row.id}-stored`} />
                </div>
              </div>
            ))}
          </dl>
        </div>
      ) : null}
    </>
  )
}
