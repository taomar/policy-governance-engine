import type { CaseDecisionEnvelope } from '../contracts/caseDecision'
import { RETRIEVAL_COPY, RETRIEVAL_NARROWED_HEADING } from '../copy/strings'
import { allPublishedPoliciesWereEvaluated } from '../lib/receiptComparison'
import { headingLabel, humanise } from '../lib/format'
import { resolvePayloadUrl } from '../lib/payloadUrl'

/**
 * What was narrowed away before anything was evaluated.
 *
 * THE OVER-CLAIM GUARD
 *
 * "All published policies were evaluated" is the single most consequential
 * sentence this page can print, because a reader who believes it will treat a
 * silence as a considered answer. It may therefore be printed only when
 * retrieval says it did not narrow, or narrowed and discarded nothing --
 * `allPublishedPoliciesWereEvaluated`, the product's own predicate. In every
 * other case the heading says policies were *considered* by narrowing, and the
 * discarded ones are listed with their reasons so a reader can see what was
 * left out rather than being told it did not matter.
 *
 * For `not_evaluated` this panel is the primary evidence and opens by default.
 */
export function RetrievalDisclosure({
  envelope,
  baseUrl,
}: {
  envelope: CaseDecisionEnvelope
  /** The API this page is calling. Relative `payload_url`s resolve against it. */
  baseUrl: string
}) {
  const retrieval = envelope.retrieval
  const allEvaluated = allPublishedPoliciesWereEvaluated(envelope)
  const copy = allEvaluated ? RETRIEVAL_COPY.not_narrowed : RETRIEVAL_COPY[retrieval.status]

  const considered = envelope.considered ?? []
  const excluded = envelope.excluded ?? []
  const discardedPolicies = [...excluded, ...considered.filter((p) => p.retained === false)]

  const consideredCount = retrieval.policies_considered ?? considered.length
  const retainedCount =
    retrieval.policies_retained ?? considered.filter((p) => p.retained === true).length
  const discardedCount = retrieval.policies_discarded ?? discardedPolicies.length

  const heading = allEvaluated
    ? RETRIEVAL_COPY.not_narrowed.message
    : (copy?.message ?? RETRIEVAL_NARROWED_HEADING)

  const tone = allEvaluated ? 'note' : (copy?.tone ?? 'neutral')

  return (
    <section className="panel" aria-labelledby="retrieval-heading" data-testid="playground-retrieval">
      <div className="panel__head">
        <h3 className="panel__title" id="retrieval-heading">
          Retrieval
        </h3>
        <span className={`chip chip--${tone}`}>{humanise(retrieval.status)}</span>
      </div>
      <div className="panel__body">
        <p style={{ fontWeight: 600 }} data-testid="retrieval-heading-text">
          {heading}
        </p>
        {copy?.description ? <p className="small muted">{copy.description}</p> : null}

        <p className="mono" data-testid="retrieval-counts">
          Considered {consideredCount} · Retained {retainedCount} · Discarded {discardedCount}
        </p>

        {retrieval.method || retrieval.reason ? (
          <p className="xsmall muted">
            {retrieval.method ? `Method: ${retrieval.method}. ` : ''}
            {retrieval.reason ? `Reason: ${humanise(retrieval.reason)}.` : ''}
          </p>
        ) : null}

        {discardedPolicies.length > 0 ? (
          <div className="panel" style={{ borderRadius: 'var(--radius-md)' }}>
            <div className="panel__head">
              <h4 className="panel__title" style={{ fontSize: 'var(--fs-base)' }}>
                Discarded before evaluation
              </h4>
            </div>
            <div className="ledger">
              {discardedPolicies.map((policy, index) => (
                <div className="ledger__row" key={`${policy.provision_key ?? index}`}>
                  <span className="ledger__label" style={{ textTransform: 'none', letterSpacing: 0 }}>
                    <code className="mono">{policy.provision_key ?? '—'}</code>
                  </span>
                  <span className="ledger__value">
                    <span>{headingLabel(policy.heading_path, policy.provision_key)}</span>
                    <span className="pill">{humanise(policy.discard_reason ?? policy.reason)}</span>
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {considered.filter((p) => p.retained === true).length > 0 ? (
          <details className="disclosure">
            <summary>Show retained policies</summary>
            <div className="ledger">
              {considered
                .filter((policy) => policy.retained === true)
                .map((policy, index) => {
                  // Resolved against the API base for the same reason as the
                  // evidence links: the server returns a relative path, and a
                  // browser resolves one against this page's origin.
                  const payloadUrl = resolvePayloadUrl(policy.payload_url, baseUrl)
                  return (
                    <div className="ledger__row" key={`${policy.provision_key ?? index}-retained`}>
                      <span className="ledger__label" style={{ textTransform: 'none', letterSpacing: 0 }}>
                        <code className="mono">{policy.provision_key ?? '—'}</code>
                      </span>
                      <span className="ledger__value">
                        <span>{headingLabel(policy.heading_path, policy.provision_key)}</span>
                        {typeof policy.rules === 'number' ? (
                          <span className="pill">{policy.rules} rules</span>
                        ) : null}
                        {payloadUrl ? (
                          <a
                            className="link small"
                            href={payloadUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            data-testid="retrieval-payload-link"
                          >
                            View payload →
                          </a>
                        ) : null}
                      </span>
                    </div>
                  )
                })}
            </div>
          </details>
        ) : null}
      </div>
    </section>
  )
}
