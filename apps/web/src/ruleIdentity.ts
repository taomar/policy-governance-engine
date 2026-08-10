import type { CanonicalRule } from "./api";

/**
 * The identity block shared by every JSON view of a rule.
 *
 * The three views — the rule itself, the canonical decomposition, and the DMN
 * projection — are three descriptions of one thing, but each was previously
 * downloadable on its own with no way to tell which rule, document, or version
 * it came from. A reviewer comparing a canonical block against a DMN block had
 * to trust that both files came from the same place.
 *
 * Emitting the same block into all three makes them self-identifying and
 * mutually checkable: if two files disagree here, they are not describing the
 * same rule and any conclusion drawn from comparing them is void.
 */
export interface RuleIdentity {
  /** Platform-internal identity of the rule and the revision being shown. */
  rule_id: string;
  rule_revision: number;
  /** The policy set and version this rule belongs to. */
  policy_set_id: string;
  policy_version_id: string;
  /** Source documents the rule was extracted from, deduplicated. */
  document_version_ids: string[];
  /** Clauses cited as evidence, in the order they were cited. */
  clause_ids: string[];
  /** Content hashes of the source releases, so a re-upload is detectable. */
  source_hashes: string[];
  /**
   * Keys under which this rule's evidence clauses are indexed for retrieval.
   * Mirrors `clause_search_document_id` on the server (`{version}_{clause}`),
   * so a result found in Search can be traced back to the rule that cites it.
   */
  search_document_ids: string[];
  /** Other rules extracted as part of the same decision, when grouped. */
  related_rule_ids: string[];
  /** Rules this one is declared to supersede within the same version. */
  supersedes_rule_ids: string[];
  /** The extraction run that produced it, for tying the rule to its batch. */
  extraction_run_id: string | null;
}

function unique(values: (string | null | undefined)[]): string[] {
  return Array.from(new Set(values.filter((v): v is string => Boolean(v))));
}

/** Build the identity block for one rule. */
export function ruleIdentity(rule: CanonicalRule): RuleIdentity {
  const evidence = rule.evidence ?? [];

  return {
    rule_id: rule.rule_id,
    rule_revision: rule.rule_revision,
    policy_set_id: rule.policy_set_id,
    policy_version_id: rule.policy_version_id,
    document_version_ids: unique(evidence.map((e) => e.document_version_id)),
    clause_ids: unique(evidence.map((e) => e.clause_id)),
    source_hashes: unique(evidence.map((e) => e.source_hash)),
    // Built from the same two parts the indexer uses
    // (`clause_search_document_id`). Derived rather than stored so it cannot
    // drift from the rule's own evidence, and omitted entirely for evidence
    // with no clause — a half-formed key would look resolvable and resolve to
    // nothing.
    search_document_ids: unique(
      evidence.map((e) => (e.clause_id ? `${e.document_version_id}_${e.clause_id}` : null))
    ),
    related_rule_ids: unique(rule.related_rule_ids).filter((id) => id !== rule.rule_id),
    supersedes_rule_ids: unique(rule.supersedes_rule_ids),
    extraction_run_id: rule.lineage?.extraction_run_id ?? null,
  };
}

/**
 * Wrap a JSON payload with the identity of the rule it describes.
 *
 * `_identity` leads with an underscore so it sorts and reads as metadata about
 * the document rather than as part of the extracted content — nothing here came
 * from the source text, and a reviewer must never mistake it for something the
 * policy said.
 */
export function withRuleIdentity<T>(
  payload: T,
  rule: CanonicalRule
): { _identity: RuleIdentity; [key: string]: unknown } {
  return { _identity: ruleIdentity(rule), ...(payload as object) } as {
    _identity: RuleIdentity;
    [key: string]: unknown;
  };
}
