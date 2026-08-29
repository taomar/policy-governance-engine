import { useState } from 'react'
import type { CaseDecisionEnvelope, CitationRef } from '../contracts/caseDecision'
import { headingLabel, humanise } from '../lib/format'
import { resolvePayloadUrl } from '../lib/payloadUrl'

/**
 * The rule-level evidence behind the answer.
 *
 * THE ONE RULE THAT MATTERS HERE
 *
 * A quotation is either verbatim or it is absent. When the projection did not
 * carry the source text, this renders the server's own honest fallback and
 * never a paraphrase, a summary or a reconstruction. A paraphrased "quotation"
 * on a policy receipt is a fabricated citation with extra steps, and the whole
 * grounding apparatus upstream exists to stop exactly that.
 *
 * The table becomes ruled stacked rows below 900px rather than scrolling
 * sideways, because a quoted provision that has slid off the right edge is
 * evidence the reader does not know they are missing.
 */

function Quote({ citation }: { citation: CitationRef }) {
  const [expanded, setExpanded] = useState(false)
  const source = citation.source

  if (!source?.text) {
    return (
      <span className="muted small" data-testid="evidence-quote-missing">
        {source?.state
          ? `The citation source is ${humanise(source.state)}; no verbatim quote was returned.`
          : 'The cited source text was not returned with this citation.'}
      </span>
    )
  }

  return (
    <>
      <span
        className={`quote${expanded ? '' : ' quote--clamped'}`}
        data-testid="evidence-quote"
        style={{ display: 'block' }}
      >
        “{source.text}”
      </span>
      {source.text.length > 220 ? (
        <button type="button" className="btn btn--quiet" onClick={() => setExpanded((v) => !v)}>
          {expanded ? 'Show less' : 'Show full quote'}
        </button>
      ) : null}
    </>
  )
}

function pageSection(citation: CitationRef): string {
  const parts: string[] = []
  if (citation.source?.section) parts.push(`Section ${citation.source.section}`)
  if (typeof citation.source?.page === 'number') parts.push(`Page ${citation.source.page}`)
  return parts.length > 0 ? parts.join(' · ') : '—'
}

function PayloadLink({ citation, baseUrl }: { citation: CitationRef; baseUrl: string }) {
  // Resolved against the API base, never rendered raw: the server returns a
  // relative path, and a browser would resolve it against this page's own
  // origin instead. See `lib/payloadUrl.ts`.
  const url = resolvePayloadUrl(citation.policy?.payload_url, baseUrl)
  if (!url) {
    return (
      <span className="muted small" title="No payload link was returned">
        —
      </span>
    )
  }
  // A quiet inline link, never a boxed button: opening a policy record is
  // reading, not an action on the decision.
  return (
    <a
      className="link small"
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      data-testid="evidence-payload-link"
    >
      View payload →
    </a>
  )
}

export function EvidenceTable({
  envelope,
  baseUrl,
}: {
  envelope: CaseDecisionEnvelope
  /** The API this page is calling. Relative `payload_url`s resolve against it. */
  baseUrl: string
}) {
  const citations = envelope.citations ?? []

  return (
    <section className="panel" id="rule-evidence" aria-labelledby="evidence-heading">
      <div className="panel__head">
        <h3 className="panel__title" id="evidence-heading">
          Rule evidence
        </h3>
      </div>

      {citations.length === 0 ? (
        <div className="panel__body">
          <p className="empty-state" data-testid="evidence-empty">
            No rule citations were returned with this decision. Nothing here should be read as
            evidence that a rule was consulted and found silent — read the retrieval disclosure
            below for what was actually evaluated.
          </p>
        </div>
      ) : (
        <>
          <table className="evidence-table" data-testid="playground-evidence-table">
            <caption className="visually-hidden">
              The rules this decision rests on, with the policy each came from and the verbatim
              source text where it was returned.
            </caption>
            <thead>
              <tr>
                <th scope="col" style={{ width: '16%' }}>
                  Rule ID
                </th>
                <th scope="col" style={{ width: '22%' }}>
                  Provision / heading
                </th>
                <th scope="col" style={{ width: '12%' }}>
                  Route / effect
                </th>
                <th scope="col" style={{ width: '12%' }}>
                  Page / section
                </th>
                <th scope="col" style={{ width: '28%' }}>
                  Quoted source
                </th>
                <th scope="col" style={{ width: '10%' }}>
                  Payload
                </th>
              </tr>
            </thead>
            <tbody>
              {citations.map((citation, index) => (
                <tr key={`${citation.rule_id}-${index}`}>
                  <td>
                    <code className="mono">{citation.rule_id}</code>
                  </td>
                  <td>
                    {headingLabel(citation.policy?.heading_path, citation.policy?.provision_key)}
                  </td>
                  <td>
                    {/* The word is always present; `—` when the envelope
                        reported no route, never a bare colour. */}
                    <span className="tag tag--neutral">
                      {humanise(envelope.decision.decider_route)}
                    </span>
                  </td>
                  <td>{pageSection(citation)}</td>
                  <td>
                    <Quote citation={citation} />
                  </td>
                  <td>
                    <PayloadLink citation={citation} baseUrl={baseUrl} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* The same content as ruled stacked rows for narrow viewports. */}
          <ul className="evidence-list" role="list" data-testid="playground-evidence-list">
            {citations.map((citation, index) => (
              <li className="evidence-list__item" role="listitem" key={`${citation.rule_id}-${index}`}>
                <span>
                  <code className="mono">{citation.rule_id}</code>{' '}
                  {headingLabel(citation.policy?.heading_path, citation.policy?.provision_key)}
                </span>
                <span className="xsmall muted">
                  Route / effect: {humanise(envelope.decision.decider_route)} · Page / section:{' '}
                  {pageSection(citation)}
                </span>
                <Quote citation={citation} />
                <PayloadLink citation={citation} baseUrl={baseUrl} />
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
