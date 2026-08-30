import { V2 } from '../copy/strings'
import type { InformationSection } from '../contracts/caseDecision'
import { informationCopy } from './CaseOutcomeBand'

/**
 * What the retained published policies state on the subject asked about.
 *
 * The same structural guard as the verdict panel, for the same reason: the
 * answer node exists only when `answered` is true. An information track that
 * did not answer says so in words, in the space the statement would have
 * occupied, because an empty paragraph under a heading that reads "What the
 * policies state" is read as "the policies state nothing" — which is a finding,
 * and not one that was made.
 *
 * This panel is deliberately quieter than the verdict panel even when it is the
 * only one that answered. A statement of what a policy says is not a
 * determination about a case, and the page must never let the first be read as
 * the second: the outcome band above has already said which of the two the
 * caller asked for.
 */
export function InformationPanel({ section }: { section: InformationSection }) {
  const copy = informationCopy(section.status)
  const answered = section.answered && Boolean(section.answer?.trim())

  return (
    <section
      className={`panel result-panel result-panel--${copy.tone}`}
      data-testid="playground-information-panel"
      aria-labelledby="information-panel-heading"
    >
      <div className="panel__head">
        <h3 className="panel__title" id="information-panel-heading">
          {V2.informationHeading}
        </h3>
        <span className={`chip chip--${copy.tone}`} data-testid="playground-information-status">
          {copy.label}
        </span>
      </div>

      <div className="panel__body">
        {answered ? (
          <p className="result-panel__answer" data-testid="playground-information-answer">
            {section.answer}
          </p>
        ) : (
          <p className="result-panel__notreached" data-testid="playground-information-not-answered">
            {V2.informationNotAnswered} {copy.title}.
          </p>
        )}

        <p className="small muted">{copy.description}</p>

        {/* The gather composes `explanation` only when it did *not* answer, so
            the two are never both substance. It is labelled rather than run
            together with the description above: one is this page's account of
            the outcome, the other is the server's. */}
        {section.explanation ? (
          <div className="result-panel__explanation">
            <span className="eyebrow">{V2.explanationLabel}</span>
            <p data-testid="playground-information-explanation">{section.explanation}</p>
          </div>
        ) : null}

        {section.note ? (
          <p className="small muted" data-testid="playground-information-note">
            <span className="eyebrow">{V2.noteLabel}</span> {section.note}
          </p>
        ) : null}

        {(section.citations?.length ?? 0) > 0 ? (
          <p className="small">
            <a className="link" href="#rule-evidence" data-testid="playground-information-citations">
              {section.citations?.length === 1
                ? 'This rests on 1 cited rule.'
                : `This rests on ${section.citations?.length} cited rules.`}
            </a>
          </p>
        ) : (
          <p className="small muted" data-testid="playground-information-no-citations">
            No rule citations were returned for the information track.
          </p>
        )}
      </div>
    </section>
  )
}
