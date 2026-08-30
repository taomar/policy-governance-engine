import { useState } from 'react'
import type { CitationRef, MergedCitationRef } from '../contracts/caseDecision'
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
 * WHY "CITED BY" IS A COLUMN AND NOT A HEADING
 *
 * A v2 receipt answers two tracks from one corpus and merges their citations by
 * rule id, tagging each with the track or tracks that rested on it. The rule
 * that *states* a cap is frequently the same rule that *decides* whether a case
 * was within it, and it is one authority, not two. Splitting the evidence into
 * an "information evidence" table and a "verdict evidence" table would print
 * that rule twice and invite a reader to count two. So there is one table, and
 * the track tags travel per row. A v1 receipt has no tracks; its rows carry the
 * decider route in the same column, which is the same question — what produced
 * this — answered with the vocabulary that receipt has.
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

/**
 * Which track (or tracks) rested on this rule, or — on a v1 receipt that has no
 * tracks — which gather route decided. Always a word, never a bare colour.
 */
function CitedBy({
  citation,
  fallbackRoute,
}: {
  citation: MergedCitationRef
  fallbackRoute?: string | null
}) {
  const serves = citation.serves ?? []
  if (serves.length === 0) {
    return (
      <span className="tag tag--neutral" data-testid="evidence-cited-by">
        {humanise(fallbackRoute)}
      </span>
    )
  }
  return (
    <span className="tag-row" data-testid="evidence-cited-by">
      {serves.map((track) => (
        <span
          key={track}
          className={`tag tag--${track === 'verdict' ? 'action' : 'neutral'}`}
          data-testid={`evidence-serves-${track}`}
        >
          {track === 'verdict' ? 'Verdict' : 'Information'}
        </span>
      ))}
    </span>
  )
}

export function EvidenceTable({
  citations,
  baseUrl,
  fallbackRoute,
}: {
  /** The merged citation list. v1 rows simply carry no `serves`. */
  citations: MergedCitationRef[]
  /** The API this page is calling. Relative `payload_url`s resolve against it. */
  baseUrl: string
  /** v1's decider route, shown in `Cited by` when a row has no track tags. */
  fallbackRoute?: string | null
}) {
  return (
    <section className="panel" id="rule-evidence" aria-labelledby="evidence-heading">
      <div className="panel__head">
        <h3 className="panel__title" id="evidence-heading">
          Rule evidence
        </h3>
        {citations.length > 0 ? (
          <span className="chip chip--neutral" data-testid="evidence-count">
            {citations.length === 1 ? '1 rule' : `${citations.length} rules`}
          </span>
        ) : null}
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
              The rules this decision rests on, with the policy each came from, which track cited
              it, and the verbatim source text where it was returned.
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
                  Cited by
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
                    <CitedBy citation={citation} fallbackRoute={fallbackRoute} />
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
                <CitedBy citation={citation} fallbackRoute={fallbackRoute} />
                <span className="xsmall muted">Page / section: {pageSection(citation)}</span>
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
