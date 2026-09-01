import type {
  CaseDecisionLightEnvelope,
  InformationSection,
  MergedCitationRef,
  VerdictSection,
} from '../contracts/caseDecision'
import { headingLabel, humanise } from '../lib/format'
import { CodeBlock, renderJsonLine } from './CodeBlock'
import { EvidenceTable } from './EvidenceTable'
import { InformationPanel } from './InformationPanel'
import { VerdictPanel } from './VerdictPanel'

interface DecisionLightResultProps {
  envelope: CaseDecisionLightEnvelope
  baseUrl: string
  onAnnounce: (message: string) => void
}

function lightVerdict(envelope: CaseDecisionLightEnvelope): VerdictSection | null {
  if (!envelope.verdict) return null
  return {
    status: envelope.verdict.status,
    reached: envelope.verdict.reached,
    decision: envelope.verdict.decision,
    explanation: envelope.verdict.explanation,
    missing_information: envelope.verdict.missing_information,
    verification_requirements: envelope.verdict.verification_requirements,
    citations: envelope.citations.filter((citation) => citation.serves.includes('verdict')),
    note: envelope.verdict.note,
  }
}

function lightInformation(envelope: CaseDecisionLightEnvelope): InformationSection | null {
  if (!envelope.information) return null
  return {
    status: envelope.information.status,
    answered: envelope.information.status === 'answered',
    answer: envelope.information.answer,
    explanation: envelope.information.explanation,
    citations: envelope.citations.filter((citation) => citation.serves.includes('information')),
    note: envelope.information.note,
  }
}

export function DecisionLightResult(props: DecisionLightResultProps) {
  const verdict = lightVerdict(props.envelope)
  const information = lightInformation(props.envelope)
  const citations: MergedCitationRef[] = props.envelope.citations

  return (
    <>
      <section
        className="panel decision-light-result"
        aria-labelledby="result-heading"
        data-testid="playground-light-decision-result"
      >
        <div className="panel__head decision-light-result__head">
          <div>
            <span className="eyebrow">Compact audited response</span>
            <h2 className="panel__title" id="result-heading" tabIndex={-1}>
              Decision Light
            </h2>
          </div>
          <span className="pill">{props.envelope.response_type}</span>
          <p className="panel__subtitle">
            The essential decision is shown first. Its exact fixed-schema JSON remains below, and
            the complete stored receipt is available at <code>{props.envelope.receipt_url}</code>.
          </p>
        </div>

        <div className="light-outcome-register" aria-label="Decision Light outcomes">
          <div>
            <span className="eyebrow">Verdict track</span>
            <strong data-testid="playground-light-verdict-outcome">
              {humanise(props.envelope.outcome.verdict)}
            </strong>
            <span>
              {props.envelope.asked.verdict_requested ? 'Requested' : 'Not requested'}
            </span>
          </div>
          <div>
            <span className="eyebrow">Information track</span>
            <strong data-testid="playground-light-information-outcome">
              {humanise(props.envelope.outcome.information)}
            </strong>
            <span>
              {props.envelope.asked.information_requested ? 'Requested' : 'Not requested'}
            </span>
          </div>
          <div>
            <span className="eyebrow">Policies carried</span>
            <strong>{props.envelope.policies.length}</strong>
            <span>{props.envelope.retrieval.method ?? 'Method not reported'}</span>
          </div>
          <div>
            <span className="eyebrow">Cited rules</span>
            <strong>{props.envelope.citations.length}</strong>
            <span>{props.envelope.retrieval.status}</span>
          </div>
        </div>

        {props.envelope.policies.length > 0 ? (
          <div className="decision-light-result__policies">
            <span className="eyebrow">Policies behind this response</span>
            <ul>
              {props.envelope.policies.map((policy) => (
                <li key={policy.provision_id ?? policy.provision_key}>
                  <span>{headingLabel(policy.heading_path, policy.provision_key)}</span>
                  <code className="mono mono--muted">{policy.provision_key ?? 'No policy key'}</code>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      {verdict ? <VerdictPanel section={verdict} onAnnounce={props.onAnnounce} /> : null}
      {information ? <InformationPanel section={information} /> : null}
      <EvidenceTable citations={citations} baseUrl={props.baseUrl} />

      <section className="panel policy-json-result" aria-labelledby="light-json-heading">
        <div className="panel__head policy-json-result__head">
          <div>
            <span className="eyebrow">Integration contract</span>
            <h3 className="panel__title" id="light-json-heading">
              Decision Light JSON
            </h3>
          </div>
          <span className="pill">{props.envelope.schema_version}</span>
          <p className="panel__subtitle">
            This is the unmodified response body used by an agent, workflow, or service.
          </p>
        </div>
        <div className="panel__body">
          <CodeBlock
            text={JSON.stringify(props.envelope, null, 2)}
            language="JSON"
            what="the Decision Light JSON"
            downloadName={`${props.envelope.decision_id}-light.json`}
            testId="playground-light-decision-json"
            onAnnounce={props.onAnnounce}
            renderLine={renderJsonLine}
            maxHeight={720}
          />
        </div>
      </section>
    </>
  )
}
