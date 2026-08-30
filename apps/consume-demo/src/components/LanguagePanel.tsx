import { LANGUAGE } from '../copy/strings'
import {
  BOUNDARY_RENDERED,
  GUIDANCE_UNRENDERED_DROPPED,
  OUTPUT_RENDERING_NOT_REQUIRED,
  OUTPUT_RENDERING_TARGET_UNKNOWN,
  type LanguageRef,
} from '../contracts/caseDecision'
import { CodeBlock } from './CodeBlock'

/**
 * Which language each stage worked in, and what was actually adjudicated.
 *
 * ONE PANEL, NOT A SET OF THEM
 *
 * There are eleven fields here and every one of them is provenance. Given a
 * card each they would out-weigh the answer they qualify, which is exactly the
 * failure this page's whole layout was rebuilt to avoid. So they are one
 * bordered register ruled into entries, sitting with the receipt where the rest
 * of the provenance lives, and the only thing lifted out of it is the one fact
 * that changes how the answer should be read: when the text that was
 * adjudicated is not the text the caller sent.
 *
 * THE CLAIM THIS COMPONENT EXISTS TO MAKE
 *
 * A reader who sees an answer rendered into their own language will assume,
 * reasonably and wrongly, that the quotations under Rule evidence were rendered
 * too. They are not, and they must never be: a translated quotation is a
 * paraphrase wearing quotation marks, and the entire grounding apparatus
 * upstream exists to stop paraphrase being presented as authority. So the panel
 * says so in its own row, unprompted, whether or not any rendering happened.
 *
 * ABSENT IS NOT EMPTY
 *
 * A receipt written before the boundary existed carries no `language` block at
 * all. That renders as a sentence saying so, never as blank rows: "no language
 * information was recorded" and "the boundary ran and found nothing" are
 * different facts, and a reader cannot tell them apart from an empty table.
 */

function Row({
  label,
  testId,
  children,
}: {
  label: string
  testId?: string
  children: React.ReactNode
}) {
  return (
    <div className="ledger__row" data-testid={testId}>
      <span className="ledger__label">{label}</span>
      <span className="ledger__value">{children}</span>
    </div>
  )
}

function Tag({ value }: { value: string }) {
  const malformed = value === 'und'
  return (
    <>
      <code className="mono">{value}</code>
      {malformed ? <span className="chip chip--note">{LANGUAGE.undTag}</span> : null}
    </>
  )
}

export function LanguagePanel({
  language,
  requestScenario,
  onAnnounce,
}: {
  /** Null on a receipt written before the boundary existed. */
  language: LanguageRef | null | undefined
  /** The caller's own bytes, for the comparison that catches a changed question. */
  requestScenario: string
  onAnnounce: (message: string) => void
}) {
  if (!language) {
    return (
      <section className="panel" data-testid="playground-language" aria-labelledby="language-heading">
        <div className="panel__head">
          <h3 className="panel__title" id="language-heading">
            {LANGUAGE.heading}
          </h3>
        </div>
        <div className="panel__body">
          <p data-testid="language-absent">{LANGUAGE.absent}</p>
          <p className="small muted">{LANGUAGE.absentCaption}</p>
        </div>
      </section>
    )
  }

  const rendered = language.boundary_state === BOUNDARY_RENDERED
  const processingDiffers = language.processing_scenario.trim() !== requestScenario.trim()
  const guidanceDropped = language.guidance_rendering_state === GUIDANCE_UNRENDERED_DROPPED

  const outputCopy =
    language.output_rendering_state === BOUNDARY_RENDERED
      ? LANGUAGE.outputRendered
      : language.output_rendering_state === OUTPUT_RENDERING_TARGET_UNKNOWN
        ? LANGUAGE.outputTargetUnknown
        : language.output_rendering_state === OUTPUT_RENDERING_NOT_REQUIRED
          ? LANGUAGE.outputNotRequired
          : language.output_rendering_state

  const guidanceCopy = guidanceDropped
    ? LANGUAGE.guidanceDropped
    : language.guidance_rendering_state === BOUNDARY_RENDERED
      ? LANGUAGE.guidanceRendered
      : LANGUAGE.guidanceNotRequired

  return (
    <section className="panel" data-testid="playground-language" aria-labelledby="language-heading">
      <div className="panel__head">
        <h3 className="panel__title" id="language-heading">
          {LANGUAGE.heading}
        </h3>
        <span className="chip chip--neutral" data-testid="language-processing-chip">
          {LANGUAGE.adjudicatedIn} {language.processing_language}
        </span>
      </div>

      <div className="ledger">
        <Row label={LANGUAGE.askedIn} testId="language-source">
          <Tag value={language.source_language} />
          {language.source_language === 'und' ? (
            <span className="ledger__caption">{LANGUAGE.undCaption}</span>
          ) : null}
        </Row>

        <Row label={LANGUAGE.adjudicatedIn} testId="language-processing">
          <Tag value={language.processing_language} />
          <span className="ledger__caption">
            Retrieval, classification and both gathers all ran in this language.
          </span>
        </Row>

        <Row label={LANGUAGE.answeredIn} testId="language-response">
          <Tag value={language.response_language} />
        </Row>

        <Row label={LANGUAGE.boundaryLabel} testId="language-boundary">
          <code className="mono mono--muted">{language.boundary_state}</code>
          <span className="ledger__caption">
            {rendered ? LANGUAGE.boundaryRendered : LANGUAGE.boundaryIdentity}
          </span>
        </Row>

        <Row label={LANGUAGE.outputLabel} testId="language-output">
          <code className="mono mono--muted">{language.output_rendering_state}</code>
          <span className="ledger__caption">{outputCopy}</span>
        </Row>

        <Row label={LANGUAGE.guidanceLabel} testId="language-guidance">
          <code className="mono mono--muted">{language.guidance_rendering_state}</code>
          {guidanceDropped ? <span className="chip chip--action">Dropped</span> : null}
          <span className="ledger__caption">{guidanceCopy}</span>
        </Row>

        {/* Said whether or not anything was rendered. A reader who has just been
            handed prose in their own language is the reader most likely to
            assume the quotations came with it. */}
        <Row label="Cited source text" testId="language-citations">
          <strong>{LANGUAGE.citationsUntranslated}</strong>
          <span className="ledger__caption">{LANGUAGE.citationsUntranslatedBody}</span>
        </Row>

        <Row label={LANGUAGE.profilesLabel} testId="language-profiles">
          <code className="mono">{language.input_translation_profile}</code>
          <span className="pill">Inbound, sealed</span>
          {language.output_translation_profile ? (
            <>
              <code className="mono mono--muted">{language.output_translation_profile}</code>
              <span className="pill">Outbound</span>
            </>
          ) : null}
          <span className="ledger__caption">{LANGUAGE.profilesCaption}</span>
        </Row>

        <Row label={LANGUAGE.projectionLabel} testId="language-projection">
          {language.projection_profile ? (
            <code className="mono">{language.projection_profile}</code>
          ) : (
            <span className="muted small">{LANGUAGE.projectionAbsent}</span>
          )}
          <span className="ledger__caption">{LANGUAGE.projectionCaption}</span>
        </Row>
      </div>

      <div className="panel__body">
        <h4 className="panel__title" style={{ fontSize: 'var(--fs-base)' }}>
          {LANGUAGE.processingHeading}
        </h4>

        {processingDiffers ? (
          <>
            <p data-testid="language-processing-differs">{LANGUAGE.processingDiffers}</p>
            <CodeBlock
              text={language.processing_scenario}
              language="Text"
              what="the question as it was adjudicated"
              downloadName="processing-scenario.txt"
              downloadMime="text/plain"
              testId="language-processing-scenario"
              onAnnounce={onAnnounce}
            />
            <p className="small muted">{LANGUAGE.yourBytesUnchanged}</p>
          </>
        ) : (
          <p className="small muted" data-testid="language-processing-same">
            {LANGUAGE.processingSame} {LANGUAGE.yourBytesUnchanged}
          </p>
        )}

        <p className="field__caption">
          <span className="eyebrow">{LANGUAGE.processingHashLabel}</span>
          <br />
          <code className="mono" data-testid="language-processing-hash">
            {language.processing_scenario_hash}
          </code>
        </p>
        <p className="field__caption">{LANGUAGE.processingHashCaption}</p>
      </div>
    </section>
  )
}
