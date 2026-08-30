import type { EnvelopeCommon, PolicyRef } from '../contracts/caseDecision'

/**
 * Comparing what you were handed against what was stored.
 *
 * THE ABSENT/EMPTY DISTINCTION
 *
 * The subtle failure this module exists to catch: `additional_instructions`
 * absent on one side and `""` on the other is a **mismatch**, not a match. Both
 * are falsy in JavaScript and both render as nothing, so the naive comparison
 * agrees they are the same and the page reports a match over a receipt whose
 * record of the request changed. Presence is compared before content, and the
 * two are reported with different words.
 *
 * WHY FIVE FIELDS
 *
 * The decision hash alone proves the decision-defining content is intact, but
 * it deliberately excludes record identity and timing, and it seals the
 * guidance by digest rather than by text. Comparing the version, the timestamp,
 * the guidance itself and the instruction profile covers what the hash does not
 * claim to cover, so a green band means more than "the seal is a seal".
 */

export type FieldVerdict = 'match' | 'mismatch'

export interface ComparisonRow {
  id: string
  label: string
  returned: string | null
  stored: string | null
  verdict: FieldVerdict
  /** True when the two sides differ by presence rather than by content. */
  presenceDiffers: boolean
}

export interface ReceiptComparison {
  rows: ComparisonRow[]
  matches: boolean
  guidanceMismatch: boolean
}

/**
 * `null` means the key was absent; a string means it was present and holds
 * that value. `undefined` on the wire is absence, and so is a missing key.
 */
function presence(value: string | null | undefined): string | null {
  return value === undefined || value === null ? null : value
}

function compare(
  id: string,
  label: string,
  returned: string | null,
  stored: string | null,
): ComparisonRow {
  const presenceDiffers = (returned === null) !== (stored === null)
  const verdict: FieldVerdict = presenceDiffers || returned !== stored ? 'mismatch' : 'match'
  return { id, label, returned, stored, verdict, presenceDiffers }
}

/**
 * Compare a returned envelope with the one read back from storage.
 *
 * The comparison is computed over the full strings even where the display
 * clamps them: a verdict taken over six visible lines of a long guidance block
 * would pass on a difference in the seventh.
 */
export function compareReceipts(
  returned: EnvelopeCommon,
  stored: EnvelopeCommon,
): ReceiptComparison {
  const rows: ComparisonRow[] = [
    compare('decision-hash', 'Decision hash', returned.decision_hash, stored.decision_hash),
    compare(
      'policy-version',
      'Policy version id',
      presence(returned.active_version?.version_id),
      presence(stored.active_version?.version_id),
    ),
    compare('timestamp', 'Timestamp', returned.decided_at, stored.decided_at),
    compare(
      'guidance',
      'Additional instructions (caller guidance)',
      presence(returned.request.additional_instructions),
      presence(stored.request.additional_instructions),
    ),
    compare(
      'profile',
      'Server instruction profile',
      presence(returned.trace.prompt_version),
      presence(stored.trace.prompt_version),
    ),
  ]

  return {
    rows,
    matches: rows.every((row) => row.verdict === 'match'),
    guidanceMismatch: rows.some((row) => row.id === 'guidance' && row.verdict === 'mismatch'),
  }
}

/**
 * The over-claim guard, reproduced from the product's own predicate and
 * extended for rule-level retrieval.
 *
 * "All published policies were evaluated" may be said only when retrieval says
 * it did not narrow, or narrowed and discarded nothing. This is the single most
 * consequential sentence on the page: a reader who believes the whole corpus
 * was read will treat a silence as a considered answer.
 *
 * v2 adds a second way to over-claim that has nothing to do with how many
 * policies survived search. A policy holding seventy-four rules that was read
 * as a slice of eight was *retained* — it appears in `considered` with
 * `retained: true`, it contributes citations, and by the policy-count test
 * nothing was discarded at all. Saying every published policy was evaluated
 * over that receipt is false in the way that matters most: sixty-six rules were
 * never read, and the reader would take their silence for a considered answer.
 * So a sliced policy disqualifies the sentence exactly as a discarded one does.
 */
export function allPublishedPoliciesWereEvaluated(
  envelope: Pick<EnvelopeCommon, 'retrieval' | 'considered'>,
): boolean {
  const considered = envelope.considered ?? []
  const discarded =
    envelope.retrieval.policies_discarded ??
    considered.filter((policy) => policy.retained === false).length

  const policiesWholeAndKept =
    envelope.retrieval.status === 'not_narrowed' ||
    (envelope.retrieval.status === 'narrowed' && discarded === 0)

  return policiesWholeAndKept && !anyPolicyWasRuleSliced(envelope)
}

/** True when at least one retained policy was read as a slice of its rules. */
export function anyPolicyWasRuleSliced(
  envelope: Pick<EnvelopeCommon, 'retrieval' | 'considered'>,
): boolean {
  if ((envelope.retrieval.policies_rule_sliced ?? 0) > 0) return true
  return (envelope.considered ?? []).some(policyWasRuleSliced)
}

/**
 * Whether one policy was read as a slice.
 *
 * `sliced` is the server's own flag and is trusted first; the count comparison
 * is the fallback for a receipt that carried the selection without the flag.
 */
export function policyWasRuleSliced(policy: PolicyRef): boolean {
  const selection = policy.rule_selection
  if (!selection) return false
  if (selection.sliced === true) return true
  return selection.selected_rules < selection.total_rules
}

/** Every retained policy that was read as a slice, in receipt order. */
export function ruleSlicedPolicies(
  envelope: Pick<EnvelopeCommon, 'retrieval' | 'considered'>,
): PolicyRef[] {
  return (envelope.considered ?? []).filter(policyWasRuleSliced)
}

/**
 * Whether the receipt echoed the guidance that was sent.
 *
 * The page never backfills the field from local state. If guidance was sent and
 * the envelope does not carry it, that is a contract violation and is shown as
 * one -- rendering what the client *believed* it sent would make the receipt
 * prove nothing at all.
 */
export function guidanceEchoState(
  envelope: Pick<EnvelopeCommon, 'request'>,
  sentGuidance: string | undefined,
): 'absent' | 'empty' | 'echoed' | 'not-echoed' {
  const returned = envelope.request.additional_instructions
  const sent = (sentGuidance ?? '').trim()

  if (returned === undefined || returned === null) {
    return sent.length > 0 ? 'not-echoed' : 'absent'
  }
  if (returned === '') {
    return sent.length > 0 ? 'not-echoed' : 'empty'
  }
  return 'echoed'
}
