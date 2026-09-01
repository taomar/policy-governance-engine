import { V2 } from '../copy/strings'
import type {
  MissingInformationItem,
  VerdictSection,
  VerificationRequirementItem,
} from '../contracts/caseDecision'
import { CopyButton } from './CodeBlock'
import { verdictCopy } from './CaseOutcomeBand'

/**
 * The determination, or the honest account of why there is not one.
 *
 * THE INVARIANT THIS COMPONENT IS BUILT AROUND
 *
 * The verdict node is not rendered at all unless `reached` is true. It is not
 * hidden, not dimmed, not placed second — it does not exist in the DOM. There
 * is therefore no viewport, no zoom level, no screen-reader traversal and no
 * copy-paste of the page on which a reader can obtain a determination without
 * having first obtained the outcome that qualifies it.
 *
 * That matters more in v2 than it did in v1, because a blocked verdict now sits
 * beside an *answered* information track. "The policies say no" and "the case
 * could not be decided" are opposite results, and an empty verdict line under a
 * heading that says Verdict is exactly how they get confused. So a non-answer
 * says so in words, in the space the determination would have occupied.
 *
 * MISSING INFORMATION IS THE PRIMARY CONTENT, NOT A FOOTNOTE
 *
 * When a case is blocked on facts, the facts are the answer — they are the only
 * part of the response the caller can act on. They are rendered as a numbered
 * register of real entries, each carrying what the fact is called, the name the
 * policy record uses, why it decides anything, and which rules are waiting on
 * it, with the whole checklist copyable in one press. A flat list of bare
 * strings in a metadata row is what v1 did, and it is why the v2 contract grew
 * `missing_information` in the first place.
 *
 * CHECKS BEFORE ACTING ARE NOT MISSING FACTS
 *
 * A reached verdict may still carry conditions on *acting* on it — a balance to
 * check, an approval to seek, a window to observe. Those arrive in
 * `verification_requirements`, and the one thing this component must never do is
 * render them where the missing facts go. Missing facts mean there is no answer;
 * these mean there is one, and something has to be confirmed before it is used.
 * So they are a separate section, below the verdict rather than in place of it,
 * carrying none of the blocked panel's tone, and the verdict's own status chip
 * and colour are untouched by their presence.
 */

function MissingItem({ item, index }: { item: MissingInformationItem; index: number }) {
  const ruleIds = item.required_by_rule_ids ?? []
  return (
    <li className="missing-item" data-testid="missing-item">
      <span className="missing-item__ordinal" aria-hidden="true">
        {index + 1}
      </span>
      <div className="missing-item__body">
        <p className="missing-item__label" data-testid="missing-item-label">
          {item.label}
        </p>

        {/* The policy record's own name for the fact, kept beside the human
            label rather than instead of it: the label is what you put in front
            of a user, the fact is what the rule is keyed on. */}
        {item.fact && item.fact !== item.label ? (
          <p className="xsmall muted">
            Named in the policy record as <code className="mono">{item.fact}</code>
          </p>
        ) : null}

        {item.why_needed ? (
          <p className="missing-item__why" data-testid="missing-item-why">
            <span className="eyebrow">{V2.missingWhyNeeded}</span> {item.why_needed}
          </p>
        ) : (
          <p className="xsmall muted" data-testid="missing-item-no-why">
            {V2.missingNoReason}
          </p>
        )}

        {ruleIds.length > 0 ? (
          <p className="xsmall" data-testid="missing-item-rules">
            <span className="eyebrow">{V2.missingRequiredBy}</span>{' '}
            {ruleIds.map((id) => (
              <code className="mono" key={id}>
                {id}
              </code>
            ))}
          </p>
        ) : null}
      </div>
    </li>
  )
}

export function MissingInformation({
  items,
  fallbackLabels,
  onAnnounce,
}: {
  items: MissingInformationItem[]
  /** `missing_required_facts`, used only when the structured list is absent. */
  fallbackLabels: string[]
  onAnnounce: (message: string) => void
}) {
  // The structured list is the field to build against; the flat labels are the
  // compatibility field. Rendering both would print every fact twice, so the
  // flat list is used only when the structured one was not carried.
  const resolved: MissingInformationItem[] =
    items.length > 0
      ? items
      : fallbackLabels.map((label) => ({ fact: label, label, required_by_rule_ids: [] }))

  if (resolved.length === 0) return null

  const checklist = resolved
    .map((item, index) => {
      const why = item.why_needed ? ` — ${item.why_needed}` : ''
      return `${index + 1}. ${item.label}${why}`
    })
    .join('\n')

  return (
    <section
      className="missing-block"
      data-testid="playground-missing-information"
      aria-labelledby="missing-heading"
    >
      <div className="missing-block__head">
        <h4 className="missing-block__heading" id="missing-heading">
          {V2.missingHeading}
        </h4>
        <span className="chip chip--action" data-testid="missing-count">
          {resolved.length === 1 ? '1 fact' : `${resolved.length} facts`}
        </span>
      </div>

      <p className="missing-block__lead">{V2.missingLead}</p>

      <ol className="missing-list">
        {resolved.map((item, index) => (
          <MissingItem item={item} index={index} key={`${item.fact}-${index}`} />
        ))}
      </ol>

      <div className="missing-block__action">
        <CopyButton
          className="btn"
          text={checklist}
          label={V2.missingCopy}
          what="the missing-fact checklist"
          onAnnounce={onAnnounce}
        />
        <span className="small muted">{V2.missingAction}</span>
      </div>
    </section>
  )
}

function VerificationItem({
  item,
  index,
}: {
  item: VerificationRequirementItem
  index: number
}) {
  const ruleIds = item.required_by_rule_ids ?? []
  return (
    <li className="missing-item" data-testid="verification-item">
      <span className="missing-item__ordinal" aria-hidden="true">
        {index + 1}
      </span>
      <div className="missing-item__body">
        <p className="missing-item__label" data-testid="verification-item-label">
          {item.label}
        </p>

        {item.fact && item.fact !== item.label ? (
          <p className="xsmall muted">
            Named in the policy record as <code className="mono">{item.fact}</code>
          </p>
        ) : null}

        {item.why_needed ? (
          <p className="missing-item__why" data-testid="verification-item-why">
            <span className="eyebrow">{V2.verificationWhyNeeded}</span> {item.why_needed}
          </p>
        ) : (
          <p className="xsmall muted" data-testid="verification-item-no-why">
            {V2.verificationNoReason}
          </p>
        )}

        {ruleIds.length > 0 ? (
          <p className="xsmall" data-testid="verification-item-rules">
            <span className="eyebrow">{V2.verificationRequiredBy}</span>{' '}
            {ruleIds.map((id) => (
              <code className="mono" key={id}>
                {id}
              </code>
            ))}
          </p>
        ) : null}
      </div>
    </li>
  )
}

export function VerificationRequirements({
  items,
  onAnnounce,
}: {
  items: VerificationRequirementItem[]
  onAnnounce: (message: string) => void
}) {
  if (items.length === 0) return null

  const checklist = items
    .map((item, index) => {
      const why = item.why_needed ? ` — ${item.why_needed}` : ''
      return `${index + 1}. ${item.label}${why}`
    })
    .join('\n')

  return (
    <section
      className="missing-block missing-block--verify"
      data-testid="playground-verification-requirements"
      aria-labelledby="verification-heading"
    >
      <div className="missing-block__head">
        <h4 className="missing-block__heading" id="verification-heading">
          {V2.verificationHeading}
        </h4>
        <span className="chip chip--neutral" data-testid="verification-count">
          {items.length === 1 ? '1 check' : `${items.length} checks`}
        </span>
      </div>

      <p className="missing-block__lead">{V2.verificationLead}</p>

      <ol className="missing-list">
        {items.map((item, index) => (
          <VerificationItem item={item} index={index} key={`${item.fact}-${index}`} />
        ))}
      </ol>

      <div className="missing-block__action">
        <CopyButton
          className="btn"
          text={checklist}
          label={V2.verificationCopy}
          what="the list of checks before acting"
          onAnnounce={onAnnounce}
        />
        <span className="small muted">{V2.verificationAction}</span>
      </div>
    </section>
  )
}

export function VerdictPanel({
  section,
  onAnnounce,
}: {
  section: VerdictSection
  onAnnounce: (message: string) => void
}) {
  const copy = verdictCopy(section.status)
  const reached = section.reached && Boolean(section.decision?.trim())
  const missing = section.missing_information ?? []
  const fallbackLabels = section.missing_required_facts ?? []
  // Only for a verdict that was actually reached. The server already restricts
  // it to `answered`, and re-asserting it here means a hand-built fixture or a
  // future server cannot make a blocked panel sprout a list of things to confirm
  // before acting on a determination that does not exist.
  const verifications = reached ? (section.verification_requirements ?? []) : []

  return (
    <section
      className={`panel result-panel result-panel--${copy.tone}`}
      data-testid="playground-verdict-panel"
      aria-labelledby="verdict-panel-heading"
    >
      <div className="panel__head">
        <h3 className="panel__title" id="verdict-panel-heading">
          {V2.verdictHeading}
        </h3>
        <span className={`chip chip--${copy.tone}`} data-testid="playground-verdict-status">
          {copy.label}
        </span>
      </div>

      <div className="panel__body">
        {reached ? (
          <p className="result-panel__answer" data-testid="playground-verdict">
            {section.decision}
          </p>
        ) : (
          <p className="result-panel__notreached" data-testid="playground-verdict-not-reached">
            {V2.verdictNotReached} {copy.title}.
          </p>
        )}

        <p className="small muted">{copy.description}</p>

        {section.explanation ? (
          <div className="result-panel__explanation">
            <span className="eyebrow">{V2.explanationLabel}</span>
            <p data-testid="playground-verdict-explanation">{section.explanation}</p>
          </div>
        ) : null}

        {section.note ? (
          <p className="small muted" data-testid="playground-verdict-note">
            <span className="eyebrow">{V2.noteLabel}</span> {section.note}
          </p>
        ) : null}

        <MissingInformation
          items={missing}
          fallbackLabels={fallbackLabels}
          onAnnounce={onAnnounce}
        />

        <VerificationRequirements items={verifications} onAnnounce={onAnnounce} />

        {(section.citations?.length ?? 0) > 0 ? (
          <p className="small">
            <a className="link" href="#rule-evidence" data-testid="playground-verdict-citations">
              {section.citations?.length === 1
                ? 'This rests on 1 cited rule.'
                : `This rests on ${section.citations?.length} cited rules.`}
            </a>
          </p>
        ) : (
          <p className="small muted" data-testid="playground-verdict-no-citations">
            No rule citations were returned for the verdict track.
          </p>
        )}
      </div>
    </section>
  )
}
