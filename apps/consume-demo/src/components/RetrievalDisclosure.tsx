import type { EnvelopeCommon, PolicyRef, RuleSelectionRef } from '../contracts/caseDecision'
import { DISCARD_DUPLICATE_POLICY_CONTENT } from '../contracts/caseDecision'
import {
  RULE_INDEX_DEGRADED,
  RULE_INDEX_MATCHED,
  RULE_INDEX_UNAVAILABLE,
} from '../contracts/caseDecision'
import {
  DUPLICATES,
  RETRIEVAL_COPY,
  RETRIEVAL_NARROWED_HEADING,
  RETRIEVAL_SLICED_DESCRIPTION,
  RETRIEVAL_SLICED_HEADING,
  RULE_INDEX,
} from '../copy/strings'
import {
  allPublishedPoliciesWereEvaluated,
  policyWasRuleSliced,
  ruleSlicedPolicies,
} from '../lib/receiptComparison'
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
 * `allPublishedPoliciesWereEvaluated` permits it — which now means both that
 * search discarded nothing *and* that no retained policy was read as a slice of
 * its rules. In every other case the heading says policies were *considered* by
 * narrowing, and what was left out is listed with its reason.
 *
 * NARROWING HAPPENS TWICE, SO IT IS DISCLOSED TWICE
 *
 * Search discards whole policies by relevance. Then a policy holding more rules
 * than one case can read is narrowed to a slice of its rules. The second is the
 * easier one to hide, because a sliced policy is *retained*: it appears in
 * `considered`, it contributes citations, and by any policy count nothing was
 * lost. For a seventy-four-row penalties table read as eight rows, the
 * difference between "the schedule was considered" and "eight of its rows were"
 * is the whole of what the reader needs. So each sliced policy states its
 * total, its selection, exactly which rule ids were read, and how many were
 * not.
 *
 * For `not_evaluated` this panel is the primary evidence and opens by default.
 */

function ruleIndexCopy(state: string | null | undefined): string | null {
  if (state === RULE_INDEX_MATCHED) return RULE_INDEX.matched
  if (state === RULE_INDEX_DEGRADED) return RULE_INDEX.degraded
  if (state === RULE_INDEX_UNAVAILABLE) return RULE_INDEX.unavailable
  return null
}

/**
 * What the rule-level rankings did for one policy.
 *
 * Four numbers that a single "candidates" count would flatten into a claim none
 * of them makes. `rule_index_hits: 0` under `matched` says the index was asked
 * and placed nothing — an answer. Under `unavailable` there is no such answer,
 * because nothing was asked. `rules_without_projection` names rules the
 * relevance rank could not score at all; they were not scored badly and they
 * were not scored in the document's own language, which is the one thing a
 * cross-language match must never do.
 */
function RuleRankingDetail({ selection }: { selection: RuleSelectionRef }) {
  const state = selection.rule_index_state
  const hits = selection.rule_index_hits
  const lexical = selection.lexical_candidates
  const quantity = selection.quantity_candidates
  const fused = selection.fused_candidates
  const quota = selection.evidence_diversity_quota
  const unprojected = selection.rules_without_projection

  const hasRanking =
    state != null ||
    typeof lexical === 'number' ||
    typeof quantity === 'number' ||
    typeof fused === 'number' ||
    typeof quota === 'number' ||
    typeof unprojected === 'number'

  if (!hasRanking) return null

  const stateCopy = ruleIndexCopy(state)

  return (
    <div className="rule-ranking" data-testid="rule-ranking">
      {state ? (
        <p className="xsmall" data-testid="rule-ranking-index-state">
          <span className="eyebrow">{RULE_INDEX.stateLabel}</span>{' '}
          <code className="mono">{state}</code>
          {typeof hits === 'number' ? (
            <>
              {' '}
              · {hits === 1 ? '1 rule ranked' : `${hits} rules ranked`}
            </>
          ) : null}
          {stateCopy ? <> — {stateCopy}</> : null}
        </p>
      ) : null}

      {state === RULE_INDEX_MATCHED && hits === 0 ? (
        <p className="xsmall muted" data-testid="rule-ranking-zero-matched">
          {RULE_INDEX.hitsZeroMatched}
        </p>
      ) : null}

      {typeof lexical === 'number' ||
      typeof quantity === 'number' ||
      typeof fused === 'number' ? (
        <p className="xsmall muted" data-testid="rule-ranking-candidates">
          <span className="eyebrow">{RULE_INDEX.candidatesLabel}</span>{' '}
          {typeof lexical === 'number' ? `relevance ${lexical}` : ''}
          {typeof quantity === 'number' ? ` · quantity ${quantity}` : ''}
          {typeof fused === 'number' ? ` · fused ${fused}` : ''}
          {typeof quantity === 'number' && quantity > 0 ? <> — {RULE_INDEX.quantityCaption}</> : null}
        </p>
      ) : null}

      {typeof quota === 'number' && quota > 0 ? (
        <p className="xsmall muted" data-testid="rule-ranking-quota">
          {RULE_INDEX.diversityQuota(quota)}
        </p>
      ) : null}

      {typeof unprojected === 'number' && unprojected > 0 ? (
        <p className="xsmall" data-testid="rule-ranking-unprojected" style={{ color: 'var(--warning)' }}>
          {RULE_INDEX.withoutProjection(unprojected)} {RULE_INDEX.withoutProjectionCaption}
        </p>
      ) : null}
    </div>
  )
}

function RuleSliceDetail({ selection }: { selection: RuleSelectionRef }) {
  const discarded = selection.rules_discarded ?? selection.total_rules - selection.selected_rules
  const omitted = selection.context_rules_omitted ?? []
  const ids = selection.selected_rule_ids ?? []
  const represented = selection.represented_rule_ids ?? []
  const collapsed = selection.duplicate_rules_collapsed ?? 0

  /* THE ARITHMETIC HAS TO SPLIT, OR THE SENTENCE OVERSTATES THE LOSS.
     `represented_rule_ids` is part of `rules_discarded`: those rules were not
     read, and they did not need to be, because an identical rule was. Reporting
     all 66 as content nobody saw would be as wrong in one direction as calling
     them "read" would be in the other -- so the two are counted apart and
     neither is called a reading. */
  const unread = Math.max(discarded - represented.length, 0)

  return (
    <div className="rule-slice" data-testid="retrieval-rule-slice">
      <p className="rule-slice__claim" data-testid="rule-slice-claim">
        {selection.selected_rules} of {selection.total_rules} rules were read.{' '}
        {discarded === 0 ? (
          <>Every rule in this policy was read.</>
        ) : represented.length > 0 ? (
          <>
            {discarded} were not: {represented.length} of those{' '}
            {represented.length === 1 ? 'is an exact copy' : 'are exact copies'} of a rule that was
            read, and {unread === 1 ? '1 rule was' : `${unread} rules were`} not read at all.
          </>
        ) : (
          <>
            {discarded === 1 ? 'One rule was' : `${discarded} rules were`} not read and not
            evaluated.
          </>
        )}
      </p>

      <p className="xsmall muted">
        Selected by <code className="mono">{selection.method}</code>
        {selection.method === 'document_order' ? (
          <>
            {' '}
            — no rule matched the question&apos;s terms, so the first rules were taken. That miss
            is disclosed here rather than hidden.
          </>
        ) : selection.method === 'hybrid_rule_v1' ? (
          <>
            {' '}
            — the rule index took part, and its ranking was fused with the relevance and quantity
            ranks before the budget selected.
          </>
        ) : selection.method === 'scenario_relevance_v3' ? (
          <>
            {' '}
            — rule documents for this policy exist, and the query against them failed recoverably,
            so the selection ran without the rule index&apos;s ranking.
          </>
        ) : selection.method.startsWith('scenario_relevance') ? (
          <> — rules ranked against the question by the policy&apos;s own words.</>
        ) : null}
        {(selection.context_rules_added ?? 0) > 0 ? (
          <>
            {' '}
            · {selection.context_rules_added} of those slots went to context a selected rule
            explicitly names, not to rules selected on their own relevance
          </>
        ) : null}
      </p>

      <RuleRankingDetail selection={selection} />

      {collapsed > 0 ? (
        <p className="xsmall muted" data-testid="rule-slice-collapsed">
          {DUPLICATES.ruleCollapsedCount(collapsed)}
        </p>
      ) : null}

      {ids.length > 0 ? (
        <details className="disclosure rule-slice__ids">
          <summary>Show the {ids.length} rule ids that were read</summary>
          <p className="rule-slice__idlist" data-testid="rule-slice-ids">
            {ids.map((id) => (
              <code className="mono" key={id}>
                {id}
              </code>
            ))}
          </p>
        </details>
      ) : null}

      {/* Kept in its own disclosure, and never in the "rules that were read"
          list: these ids name content the gather saw through another rule, not
          rules it was shown. */}
      {represented.length > 0 ? (
        <details className="disclosure rule-slice__ids">
          <summary>
            {DUPLICATES.representedHeading} ({represented.length})
          </summary>
          <div>
            <p className="rule-slice__idlist" data-testid="rule-slice-represented">
              {represented.map((id) => (
                <code className="mono" key={id}>
                  {id}
                </code>
              ))}
            </p>
            <p className="xsmall muted">{DUPLICATES.representedCaption}</p>
          </div>
        </details>
      ) : null}

      {omitted.length > 0 ? (
        <p className="xsmall" data-testid="rule-slice-omitted" style={{ color: 'var(--warning)' }}>
          Context named by a selected rule that was not admitted, because the rule budget was
          already spent or the record had no room:{' '}
          {omitted.map((id) => (
            <code className="mono" key={id}>
              {id}
            </code>
          ))}
        </p>
      ) : null}

      {selection.oversize ? (
        <p className="xsmall" data-testid="rule-slice-oversize" style={{ color: 'var(--warning)' }}>
          The selected rules do not themselves fit the record budget. Nothing was trimmed to make
          them fit; the record was refused whole.
        </p>
      ) : null}
    </div>
  )
}

export function RetrievalDisclosure({
  envelope,
  baseUrl,
}: {
  /** Typed on the common fields: retrieval is identical in v1 and v2. */
  envelope: Pick<EnvelopeCommon, 'retrieval' | 'considered' | 'excluded'>
  /** The API this page is calling. Relative `payload_url`s resolve against it. */
  baseUrl: string
}) {
  const retrieval = envelope.retrieval
  const allEvaluated = allPublishedPoliciesWereEvaluated(envelope)
  const statusCopy = RETRIEVAL_COPY[retrieval.status]

  const considered = envelope.considered ?? []
  const excluded = envelope.excluded ?? []
  const allDiscarded = [...excluded, ...considered.filter((p) => p.retained === false)]

  /* A COLLAPSED DUPLICATE IS NOT AN ORDINARY DISCARD.
     Every other entry in the discarded register names content the gather never
     saw. A policy collapsed as `duplicate_policy_content` names content it did
     see -- in the representative the entry itself points at. Leaving it under a
     heading that reads "Discarded before evaluation" would tell a reader that
     terms went unweighed when they were weighed, once, which is the opposite of
     what the collapse achieved. So it is split out and said differently. */
  const collapsedDuplicates = allDiscarded.filter(
    (policy) => policy.discard_reason === DISCARD_DUPLICATE_POLICY_CONTENT,
  )
  const discardedPolicies = allDiscarded.filter(
    (policy) => policy.discard_reason !== DISCARD_DUPLICATE_POLICY_CONTENT,
  )
  const retainedPolicies = considered.filter((p) => p.retained === true)
  const sliced = ruleSlicedPolicies(envelope)

  const consideredCount = retrieval.policies_considered ?? considered.length
  const retainedCount = retrieval.policies_retained ?? retainedPolicies.length
  const discardedCount = retrieval.policies_discarded ?? allDiscarded.length
  const slicedCount = retrieval.policies_rule_sliced ?? sliced.length
  const collapsedCount = retrieval.policies_duplicate_collapsed ?? collapsedDuplicates.length
  const deferredCount = retrieval.policies_diversity_deferred ?? 0

  /* THE OVER-CLAIM CANNOT COME IN THROUGH THE STATUS ENTRY EITHER.
     `retrieval.status` is `not_narrowed` when search kept every policy, and its
     copy says every published policy went to evaluation and none was discarded.
     That sentence is false the moment one of those policies was read as eight
     of its seventy-four rules. So the status entry is used only when the
     predicate agrees with it; otherwise the slice is named instead. */
  const statusWouldOverClaim = !allEvaluated && statusCopy === RETRIEVAL_COPY.not_narrowed

  const heading = allEvaluated
    ? RETRIEVAL_COPY.not_narrowed.message
    : statusWouldOverClaim
      ? RETRIEVAL_SLICED_HEADING
      : (statusCopy?.message ?? RETRIEVAL_NARROWED_HEADING)

  const description = allEvaluated
    ? RETRIEVAL_COPY.not_narrowed.description
    : statusWouldOverClaim
      ? RETRIEVAL_SLICED_DESCRIPTION
      : statusCopy?.description

  const tone = allEvaluated ? 'note' : statusWouldOverClaim ? 'action' : (statusCopy?.tone ?? 'neutral')

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
        {description ? <p className="small muted">{description}</p> : null}

        <p className="mono" data-testid="retrieval-counts">
          Considered {consideredCount} · Retained {retainedCount} · Discarded {discardedCount}
          {collapsedCount > 0 ? ` · Duplicates collapsed ${collapsedCount}` : ''}
          {slicedCount > 0 ? ` · Rule-sliced ${slicedCount}` : ''}
        </p>

        {/* Two sentences that must never merge. One names content the gather
            read through another record; the other names an ordering decision
            about policies nothing has been proven identical to. */}
        {collapsedCount > 0 ? (
          <p className="small" data-testid="retrieval-collapsed-note">
            {DUPLICATES.collapsedCount(collapsedCount)}. Their terms still reached the evaluation,
            in the policies they name below.
          </p>
        ) : null}

        {deferredCount > 0 ? (
          <p className="small" data-testid="retrieval-deferred-note">
            {DUPLICATES.deferredCount(deferredCount)}. {DUPLICATES.deferredBody}
          </p>
        ) : null}

        {/* ---------- rule-level discovery (M2) ---------- */}

        {/* A projection that is not ready qualifies every ranking below it, so
            it is said before any of them and not left to be inferred from a
            profile identifier nobody recognises. */}
        {retrieval.projection_ready === false ? (
          <div className="banner banner--action" data-testid="retrieval-projection-not-ready">
            <strong className="banner__heading">{RULE_INDEX.projectionNotReady}</strong>
            <span className="banner__body">
              A question and the text it is scored against must be rendered under one contract, or
              the two are not comparable.
            </span>
          </div>
        ) : null}

        {retrieval.rule_index_state === RULE_INDEX_DEGRADED ? (
          <div className="banner banner--action" data-testid="retrieval-rule-index-degraded">
            <strong className="banner__heading">
              The rule index was available and its query failed recoverably
            </strong>
            <span className="banner__body">{RULE_INDEX.degraded}</span>
          </div>
        ) : null}

        {typeof retrieval.rule_scan === 'number' ||
        typeof retrieval.policy_documents_matched === 'number' ||
        typeof retrieval.rule_documents_matched === 'number' ||
        retrieval.rule_index_state ? (
          <p className="xsmall muted" data-testid="retrieval-rule-discovery">
            {typeof retrieval.rule_scan === 'number'
              ? `Rule documents examined ${retrieval.rule_scan}. `
              : ''}
            {typeof retrieval.policy_documents_matched === 'number'
              ? `Policy documents returned ${retrieval.policy_documents_matched}. `
              : ''}
            {typeof retrieval.rule_documents_matched === 'number'
              ? `Rule documents returned ${retrieval.rule_documents_matched}. `
              : ''}
            {retrieval.rule_index_state
              ? `${RULE_INDEX.stateLabel}: ${retrieval.rule_index_state} — ${
                  ruleIndexCopy(retrieval.rule_index_state) ?? ''
                }`
              : ''}
          </p>
        ) : null}

        {/* The count that answers "did rule-level retrieval change anything
            here?" -- including, honestly, when the answer is no. */}
        {typeof retrieval.policies_elevated_by_rule === 'number' ? (
          <p className="small" data-testid="retrieval-elevated">
            {retrieval.policies_elevated_by_rule > 0 ? (
              <>
                {RULE_INDEX.elevated(retrieval.policies_elevated_by_rule)}.{' '}
                <span className="muted">{RULE_INDEX.elevatedCaption}</span>
              </>
            ) : (
              <span className="muted">{RULE_INDEX.elevatedNone}</span>
            )}
          </p>
        ) : null}

        {retrieval.projection_profile || retrieval.projection_ready === true ? (
          <p className="xsmall muted" data-testid="retrieval-projection">
            {retrieval.projection_profile ? (
              <>
                Corpus projection <code className="mono">{retrieval.projection_profile}</code>.{' '}
              </>
            ) : null}
            {retrieval.projection_ready === true ? RULE_INDEX.projectionReady : ''}
          </p>
        ) : null}

        {/* Said whenever a policy was sliced, at the top of the panel and not
            buried under the retained list, because it qualifies the retention
            count printed directly above it. */}
        {slicedCount > 0 ? (
          <div className="banner banner--action" data-testid="retrieval-sliced-banner">
            <strong className="banner__heading">
              {slicedCount === 1
                ? 'One retained policy was read as a slice of its rules'
                : `${slicedCount} retained policies were read as a slice of their rules`}
            </strong>
            <span className="banner__body">
              A retained policy is not necessarily a policy read whole. The rules that were not
              selected were not read and were not evaluated, so their silence is not a finding.
              Each policy below states exactly which rules it was read on.
            </span>
          </div>
        ) : null}

        {retrieval.method || retrieval.reason ? (
          <p className="xsmall muted">
            {retrieval.method ? `Method: ${retrieval.method}. ` : ''}
            {retrieval.reason ? `Reason: ${humanise(retrieval.reason)}.` : ''}
          </p>
        ) : null}

        {typeof retrieval.large_policy_rule_threshold === 'number' ||
        typeof retrieval.selected_rule_budget === 'number' ||
        typeof retrieval.payload_budget_chars === 'number' ||
        typeof retrieval.policies_over_payload_budget === 'number' ||
        retrieval.policy_selection_order ? (
          <p className="xsmall muted" data-testid="retrieval-budgets">
            {retrieval.policy_selection_order ? (
              <>
                {DUPLICATES.selectionOrderLabel}:{' '}
                <code className="mono">{retrieval.policy_selection_order}</code>.{' '}
                {DUPLICATES.selectionOrderCaption}{' '}
              </>
            ) : null}
            {typeof retrieval.large_policy_rule_threshold === 'number'
              ? `Policies above ${retrieval.large_policy_rule_threshold} rules are read rule by rule. `
              : ''}
            {typeof retrieval.selected_rule_budget === 'number'
              ? `Up to ${retrieval.selected_rule_budget} rules may be selected per case. `
              : ''}
            {typeof retrieval.payload_budget_chars === 'number'
              ? `One grounded pass reads at most ${retrieval.payload_budget_chars.toLocaleString()} characters. `
              : ''}
            {typeof retrieval.policies_over_payload_budget === 'number' &&
            retrieval.policies_over_payload_budget > 0
              ? `${retrieval.policies_over_payload_budget} policy record${
                  retrieval.policies_over_payload_budget === 1 ? '' : 's'
                } ranked inside the retention budget and was set aside on size alone, not on relevance.`
              : ''}
          </p>
        ) : null}

        {/* Its own register, and worded as what it is: not a loss, a
            de-duplication. Each row names where the terms were actually read. */}
        {collapsedDuplicates.length > 0 ? (
          <div
            className="panel"
            style={{ borderRadius: 'var(--radius-md)' }}
            data-testid="retrieval-collapsed-register"
          >
            <div className="panel__head">
              <h4 className="panel__title" style={{ fontSize: 'var(--fs-base)' }}>
                {DUPLICATES.collapsedHeading}
              </h4>
              <p className="panel__subtitle">{DUPLICATES.collapsedLead}</p>
            </div>
            <div className="ledger">
              {collapsedDuplicates.map((policy, index) => (
                <div className="ledger__row" key={`${policy.provision_key ?? index}-duplicate`}>
                  <span className="ledger__label" style={{ textTransform: 'none', letterSpacing: 0 }}>
                    <code className="mono">{policy.provision_key ?? '—'}</code>
                  </span>
                  <span className="ledger__value">
                    <span>{headingLabel(policy.heading_path, policy.provision_key)}</span>
                    <span className="chip chip--neutral">{DUPLICATES.collapsedChip}</span>
                    {policy.duplicate_of_provision_key ? (
                      <span className="small" data-testid="retrieval-duplicate-of">
                        {DUPLICATES.collapsedInto}{' '}
                        <code className="mono">{policy.duplicate_of_provision_key}</code>
                      </span>
                    ) : (
                      <span className="small muted" data-testid="retrieval-duplicate-of-unknown">
                        The receipt did not name which policy it was collapsed into.
                      </span>
                    )}
                  </span>
                </div>
              ))}
            </div>
          </div>
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

        {retainedPolicies.length > 0 ? (
          <details className="disclosure" open={slicedCount > 0}>
            <summary>
              {slicedCount > 0 ? 'Show retained policies and what was read of each' : 'Show retained policies'}
            </summary>
            <div className="ledger">
              {retainedPolicies.map((policy: PolicyRef, index) => {
                // Resolved against the API base for the same reason as the
                // evidence links: the server returns a relative path, and a
                // browser resolves one against this page's origin.
                const payloadUrl = resolvePayloadUrl(policy.payload_url, baseUrl)
                const wasSliced = policyWasRuleSliced(policy)
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
                      {wasSliced ? (
                        <span className="chip chip--action" data-testid="retrieval-sliced-chip">
                          Read as a slice
                        </span>
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
                      {policy.rule_selection ? (
                        wasSliced ? (
                          <RuleSliceDetail selection={policy.rule_selection} />
                        ) : (
                          <>
                            {/* Read whole, and said so: the positive claim is
                                cheap and it stops "no slice reported" being
                                confused with "slice not disclosed". */}
                            <span className="pill" data-testid="retrieval-read-whole">
                              Read whole · {policy.rule_selection.total_rules} of{' '}
                              {policy.rule_selection.total_rules} rules
                            </span>
                            {/* The rankings still ran, and still say something
                                about what could have been found here. */}
                            <RuleRankingDetail selection={policy.rule_selection} />
                          </>
                        )
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
