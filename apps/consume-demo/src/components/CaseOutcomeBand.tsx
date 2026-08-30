import { INFORMATION_OUTCOME_COPY, V2, VERDICT_OUTCOME_COPY } from '../copy/strings'
import {
  NOT_EVALUATED,
  NOT_REQUESTED,
  type CaseDecisionEnvelopeV2,
  type InformationOutcome,
  type VerdictOutcome,
} from '../contracts/caseDecision'

/**
 * The first thing rendered from a v2 decision, and the guard that makes the
 * rest of the page safe.
 *
 * WHAT REPLACED THE SINGLE STATUS BAND
 *
 * v1 had one status, so one band could carry it. v2 answers two independently
 * answerable halves of a question, and the failure mode a single band would
 * reintroduce is the exact one the two-track shape exists to prevent: a reader
 * seeing one green chip and concluding the whole question was answered, when in
 * fact the policies stated what they say and the case itself was never decided.
 *
 * So the band states three things in this order, and never fewer:
 *
 *   1. **What was asked for.** Both tracks, one, or — when retrieval produced
 *      nothing to evaluate — neither, because the classifier never ran.
 *   2. **How each track came out**, as its own ruled row with its own chip and
 *      its own word. Two rows, always, even when one of them says "not asked
 *      for": a track that is absent from the page is a track a reader cannot
 *      distinguish from one that failed silently.
 *   3. **Whether the two disagree**, said in a sentence, when they do.
 *
 * THE MIXED CASE
 *
 * Information answered while the verdict is blocked on missing facts is the
 * case this component is shaped around, because it is the one a reader is most
 * likely to misread in their own favour. It gets its own split register — two
 * halves of one bordered container, divided by a hairline, each carrying its
 * own semantic hue — and an explicit sentence saying that neither result
 * qualifies the other. Green beside gold, in one frame, is not something a
 * reader resolves into "answered".
 *
 * Nothing here means anything by colour alone: every chip carries its word.
 */

const TONE_CLASS: Record<string, string> = {
  allow: 'allow',
  deny: 'deny',
  action: 'action',
  note: 'note',
  neutral: 'neutral',
}

export function informationCopy(outcome: InformationOutcome) {
  return (
    INFORMATION_OUTCOME_COPY[outcome] ?? {
      label: outcome,
      tone: 'neutral' as const,
      title: 'The information track reported an outcome this page does not recognise.',
      description: 'Treat an unrecognised outcome as no answer at all.',
    }
  )
}

export function verdictCopy(outcome: VerdictOutcome) {
  return (
    VERDICT_OUTCOME_COPY[outcome] ?? {
      label: outcome,
      tone: 'neutral' as const,
      title: 'The verdict track reported an outcome this page does not recognise.',
      description: 'Treat an unrecognised outcome as no verdict at all.',
    }
  )
}

function askedSummary(envelope: CaseDecisionEnvelopeV2): string {
  const { information_requested, verdict_requested } = envelope.asked
  if (information_requested && verdict_requested) return V2.askedBoth
  if (information_requested) return V2.askedInformation
  if (verdict_requested) return V2.askedVerdict
  return V2.askedNeither
}

function TrackRow({
  track,
  outcome,
  label,
  tone,
  title,
  testId,
}: {
  track: string
  outcome: string
  label: string
  tone: string
  title: string
  testId: string
}) {
  const toneClass = TONE_CLASS[tone] ?? 'neutral'
  return (
    <div
      className={`track-row track-row--${toneClass}`}
      data-testid={testId}
      data-outcome={outcome}
      data-tone={toneClass}
    >
      <span className="track-row__track">{track}</span>
      <span className="track-row__state">
        <span className={`chip chip--${toneClass}`}>{label}</span>
        <code className="mono mono--muted">{outcome}</code>
      </span>
      <span className="track-row__title">{title}</span>
    </div>
  )
}

export function CaseOutcomeBand({
  envelope,
  stale,
}: {
  envelope: CaseDecisionEnvelopeV2
  stale: boolean
}) {
  const information = envelope.outcome.information
  const verdict = envelope.outcome.verdict
  const infoCopy = informationCopy(information)
  const verdCopy = verdictCopy(verdict)

  const nothingEvaluated = information === NOT_EVALUATED && verdict === NOT_EVALUATED

  // Both tracks ran and came out differently. This is the reading a reader is
  // most likely to get wrong, so it is stated rather than left to be inferred
  // from two chips of different colours.
  const bothRan = information !== NOT_REQUESTED && verdict !== NOT_REQUESTED && !nothingEvaluated
  const informationAnswered = information === 'answered'
  const verdictBlocked = verdict === 'missing_required_facts'
  const split = bothRan && informationAnswered && verdict !== 'answered'

  const missingCount = envelope.verdict?.missing_information?.length ?? 0

  return (
    <section
      className={`outcome-band${stale ? ' stale' : ''}`}
      data-testid="playground-outcome-band"
      data-stale={stale ? 'true' : undefined}
      aria-labelledby="result-heading"
    >
      <h2 className="visually-hidden" id="result-heading" tabIndex={-1}>
        Decision result
      </h2>

      <div className="outcome-band__asked">
        <span className="eyebrow">{V2.askedHeading}</span>
        <p className="outcome-band__askedvalue" data-testid="playground-asked-summary">
          {askedSummary(envelope)}
        </p>
        <p className="xsmall muted">
          {nothingEvaluated ? V2.askedNeitherCaption : V2.askedCaption}
        </p>
      </div>

      {/* Two rows, always. A track missing from the page is a track a reader
          cannot tell apart from one that failed without saying so. */}
      <div className="outcome-band__tracks">
        <TrackRow
          track={V2.informationTrack}
          outcome={information}
          label={infoCopy.label}
          tone={infoCopy.tone}
          title={infoCopy.title}
          testId="playground-track-information"
        />
        <TrackRow
          track={V2.verdictTrack}
          outcome={verdict}
          label={verdCopy.label}
          tone={verdCopy.tone}
          title={verdCopy.title}
          testId="playground-track-verdict"
        />
      </div>

      {split ? (
        <div className="outcome-split" data-testid="playground-outcome-split">
          <strong className="outcome-split__heading">{V2.splitHeading}</strong>
          <span className="outcome-split__body">
            {verdictBlocked ? (
              <>
                {V2.splitAnsweredBlocked}{' '}
                <span data-testid="playground-split-missing-count">
                  {missingCount === 1
                    ? 'One fact is outstanding.'
                    : `${missingCount} facts are outstanding.`}
                </span>{' '}
                {V2.splitBlockedCaption}
              </>
            ) : (
              <>
                The information track answered; the verdict track did not. {verdCopy.description}
              </>
            )}
          </span>
        </div>
      ) : null}

      {envelope.asked.classification_reasoning ? (
        <details className="disclosure outcome-band__reasoning">
          <summary>{V2.classifierReasoning}</summary>
          <div className="panel__body">
            <p data-testid="playground-classification-reasoning">
              {envelope.asked.classification_reasoning}
            </p>
            <p className="xsmall muted">{V2.classifierReasoningCaption}</p>
            {envelope.asked.classifier_version ? (
              <p className="xsmall muted">
                Classifier <code className="mono">{envelope.asked.classifier_version}</code>
              </p>
            ) : null}
          </div>
        </details>
      ) : null}
    </section>
  )
}
