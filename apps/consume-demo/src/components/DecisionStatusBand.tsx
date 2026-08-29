import { DECISION_STATUS_COPY } from '../copy/strings'
import {
  STATUS_WITH_VERDICT,
  type CaseDecisionEnvelope,
  type DecisionStatus,
} from '../contracts/caseDecision'

/**
 * The first thing rendered from a decision, and the guard that makes the rest
 * of the page safe.
 *
 * THE STATUS-BEFORE-VERDICT RULE IS STRUCTURAL, NOT STYLISTIC
 *
 * The verdict node is not rendered at all unless the status is `answered`. It
 * is not hidden, not de-emphasised, not placed second -- it does not exist in
 * the DOM. There is therefore no viewport, no zoom level, no screen reader
 * traversal and no copy-paste of the page on which a reader can obtain a
 * verdict without having first obtained the status that qualifies it.
 *
 * That matters because six of the seven statuses mean something other than
 * "the policies decided". "No published rule bears on this case" and "the
 * policies say no" are opposite answers, and an empty verdict field beside a
 * green tick is how they get confused.
 */

const TONE_CLASS: Record<string, string> = {
  allow: 'allow',
  deny: 'deny',
  action: 'action',
  note: 'note',
  neutral: 'neutral',
}

export function statusCopy(status: DecisionStatus) {
  return (
    DECISION_STATUS_COPY[status] ?? {
      label: status,
      tone: 'neutral' as const,
      title: 'This decision reported a status this page does not recognise.',
      description:
        'The envelope is rendered as returned. Treat an unrecognised status as no verdict at all.',
    }
  )
}

export function DecisionStatusBand({
  envelope,
  stale,
}: {
  envelope: CaseDecisionEnvelope
  stale: boolean
}) {
  const status = envelope.decision_status
  const copy = statusCopy(status)
  const tone = TONE_CLASS[copy.tone] ?? 'neutral'
  const answered = status === STATUS_WITH_VERDICT
  const citations = envelope.citations ?? []
  const fabricated = envelope.grounding?.fabricated_citations ?? []

  return (
    <section
      className={`verdict-band verdict-band--${tone}${stale ? ' stale' : ''}`}
      data-testid="playground-verdict-band"
      data-stale={stale ? 'true' : undefined}
      aria-labelledby="result-heading"
    >
      <h2 className="visually-hidden" id="result-heading" tabIndex={-1}>
        Decision result
      </h2>

      {/* Always first in document order, always carrying the word as well as
          the colour -- nothing on this page means anything by colour alone. */}
      <span className={`chip chip--${tone}`} data-testid="playground-decision-status">
        {copy.label}
      </span>

      <p className="verdict-band__heading">{copy.title}</p>

      {answered && envelope.decision.verdict ? (
        <p className="verdict-band__verdict" data-testid="playground-verdict">
          {envelope.decision.verdict}
        </p>
      ) : null}

      <p className="verdict-band__explanation">{copy.description}</p>

      {envelope.decision.explanation ? (
        <p className="verdict-band__explanation" data-testid="playground-explanation">
          {envelope.decision.explanation}
        </p>
      ) : null}

      {envelope.decision.note ? (
        <p className="small muted" data-testid="playground-decision-note">
          {envelope.decision.note}
        </p>
      ) : null}

      {/* No count badge for zero. When there are no citations the sentence
          says so; a `0 citations` pill is decoration pretending to be data. */}
      {citations.length > 0 ? (
        <p className="small">
          <a className="link" href="#rule-evidence">
            {citations.length === 1
              ? 'The answer rests on this cited rule.'
              : `The answer rests on these ${citations.length} cited rules.`}
          </a>
        </p>
      ) : (
        <p className="small muted">No rule citations were returned with this decision.</p>
      )}

      {fabricated.length > 0 ? (
        <div className="banner banner--action" data-testid="playground-fabricated">
          <strong className="banner__heading">
            {fabricated.length === 1
              ? 'A fabricated citation was refused'
              : `${fabricated.length} fabricated citations were refused`}
          </strong>
          <span className="banner__body">
            The answer tried to cite {fabricated.join(', ')},{' '}
            {fabricated.length === 1 ? 'which is not a rule' : 'which are not rules'} in the
            evaluated policies.{' '}
            {fabricated.length === 1 ? 'It was' : 'They were'} dropped and reported here rather than
            shown as evidence.
          </span>
        </div>
      ) : null}

      {envelope.size?.oversize ? (
        <div className="banner banner--action">
          <strong className="banner__heading">
            The evaluated policy payload was too large to read in one grounded pass
          </strong>
          <span className="banner__body">No partial answer should be treated as complete.</span>
        </div>
      ) : null}
    </section>
  )
}
