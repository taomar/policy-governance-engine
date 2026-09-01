import type { PolicyRetrievalEnvelope } from '../contracts/caseDecision'
import { CodeBlock, renderJsonLine } from './CodeBlock'

interface PolicyRetrievalResultProps {
  envelope: PolicyRetrievalEnvelope
  onAnnounce: (message: string) => void
}

/** The light mode deliberately interprets nothing beyond the retrieval count. */
export function PolicyRetrievalResult(props: PolicyRetrievalResultProps) {
  const count = props.envelope.policies.length
  return (
    <section
      className="panel policy-json-result"
      aria-labelledby="result-heading"
      data-testid="playground-policy-result"
    >
      <div className="panel__head policy-json-result__head">
        <div>
          <span className="eyebrow">Retrieval-only response</span>
          <h2 className="panel__title" id="result-heading" tabIndex={-1}>
            Filtered policy JSON
          </h2>
        </div>
        <span className="pill" data-testid="playground-policy-count">
          {count} {count === 1 ? 'policy' : 'policies'}
        </span>
        <p className="panel__subtitle">
          These are the exact selected published records. No verdict, explanation, or receipt was
          generated.
        </p>
      </div>
      <div className="panel__body">
        <CodeBlock
          text={JSON.stringify(props.envelope, null, 2)}
          language="JSON"
          what="the filtered policy JSON"
          downloadName="filtered-policies.json"
          testId="playground-policy-json"
          onAnnounce={props.onAnnounce}
          renderLine={renderJsonLine}
          maxHeight={720}
        />
      </div>
    </section>
  )
}
