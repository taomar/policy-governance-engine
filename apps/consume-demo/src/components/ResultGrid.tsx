import { STATUS_WITH_VERDICT, type CaseDecisionEnvelope } from '../contracts/caseDecision'
import { RECEIPT } from '../copy/strings'
import { humanise } from '../lib/format'
import { CopyButton } from './CodeBlock'
import { statusCopy } from './DecisionStatusBand'

/**
 * The result grid from the target screenshot, extended and re-ordered so it
 * cannot mislead.
 *
 * `Decision status` is the first row, always. `Verdict` renders the literal
 * `Not reached — status is "{status}"` for the six statuses that carry none,
 * rather than an em dash: an empty cell in a policy result reads as "nothing
 * was prohibited", which is a verdict, and the opposite of what happened.
 *
 * Rows with no content are omitted rather than rendered empty -- except
 * `Missing facts`, which renders whenever it is non-empty regardless of status,
 * because facts a policy needs are useful to a caller even when the policy did
 * not get as far as needing them.
 */

function ActionRow({
  label,
  values,
  tone,
  testId,
}: {
  label: string
  values: string[]
  tone: 'allow' | 'deny' | 'action' | 'neutral'
  testId?: string
}) {
  if (values.length === 0) return null
  return (
    <div className="ledger__row">
      <span className="ledger__label">{label}</span>
      <span className="ledger__value">
        <span className="tag-row" data-testid={testId}>
          {values.map((value) => (
            <span key={value} className={`tag tag--${tone}`}>
              {value}
            </span>
          ))}
        </span>
      </span>
    </div>
  )
}

export function ResultGrid({
  envelope,
  onAnnounce,
}: {
  envelope: CaseDecisionEnvelope
  onAnnounce: (message: string) => void
}) {
  const status = envelope.decision_status
  const copy = statusCopy(status)
  const answered = status === STATUS_WITH_VERDICT
  const missingFacts = envelope.decision.missing_required_facts ?? []

  return (
    <section className="panel" data-testid="playground-result-grid" aria-labelledby="result-grid-heading">
      <div className="panel__head">
        <h3 className="panel__title" id="result-grid-heading">
          Result
        </h3>
      </div>
      <div className="ledger">
        <div className="ledger__row">
          <span className="ledger__label">Decision status</span>
          <span className="ledger__value">
            <span className={`chip chip--${copy.tone}`}>{copy.label}</span>
            <code className="mono mono--muted">{status}</code>
          </span>
        </div>

        <div className="ledger__row" data-testid="playground-verdict-row">
          <span className="ledger__label">Verdict</span>
          <span className="ledger__value">
            {answered && envelope.decision.verdict ? (
              <span data-testid="playground-verdict-grid">{envelope.decision.verdict}</span>
            ) : (
              <span className="muted">Not reached — status is &quot;{status}&quot;</span>
            )}
          </span>
        </div>

        <div className="ledger__row">
          <span className="ledger__label">Route that decided</span>
          <span className="ledger__value" data-testid="playground-route">
            {envelope.decision.decider_route
              ? `${humanise(envelope.decision.decider_route)} gather`
              : 'Nothing was evaluated, so no route decided.'}
            {envelope.decision.intent ? (
              <span className="pill">intent: {envelope.decision.intent}</span>
            ) : null}
          </span>
        </div>

        {envelope.decision.explanation ? (
          <div className="ledger__row">
            <span className="ledger__label">Explanation</span>
            <span className="ledger__value" style={{ display: 'block', whiteSpace: 'pre-wrap' }}>
              {envelope.decision.explanation}
            </span>
          </div>
        ) : null}

        {/* The envelope's DecisionRef carries no allowed/denied/exception
            collections -- those belong to the deterministic evaluator's own
            contract, not to this one. Rows for them are omitted rather than
            rendered empty, because an empty `Denied actions` row on a policy
            receipt is a claim that nothing was denied. */}
        <ActionRow
          label="Missing facts"
          values={missingFacts}
          tone="action"
          testId="playground-missing-facts"
        />

        {missingFacts.length > 0 ? (
          <div className="ledger__row">
            <span className="ledger__label" />
            <span className="ledger__value muted small">
              Add these to your scenario and send again.
            </span>
          </div>
        ) : null}

        <div className="ledger__row">
          <span className="ledger__label">Decision hash</span>
          <span className="ledger__value">
            <code className="mono" data-testid="receipt-decision-hash">
              {envelope.decision_hash}
            </code>
            <CopyButton
              className="btn btn--quiet"
              text={envelope.decision_hash}
              label="Copy"
              what="the decision hash"
              onAnnounce={onAnnounce}
            />
            <span className="ledger__caption">{RECEIPT.hashCaption}</span>
          </span>
        </div>
      </div>
    </section>
  )
}
