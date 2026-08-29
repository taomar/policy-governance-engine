import type { CaseDecisionEnvelope } from '../contracts/caseDecision'

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
  returned: CaseDecisionEnvelope,
  stored: CaseDecisionEnvelope,
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
 * The over-claim guard, reproduced from the product's own predicate.
 *
 * "All published policies were evaluated" may be said only when retrieval says
 * it did not narrow, or narrowed and discarded nothing. In every other case the
 * honest heading is that policies were *considered* by narrowing. This is the
 * single most consequential sentence on the page: a reader who believes the
 * whole corpus was read will treat a silence as a considered answer.
 */
export function allPublishedPoliciesWereEvaluated(envelope: CaseDecisionEnvelope): boolean {
  const discarded =
    envelope.retrieval.policies_discarded ??
    (envelope.considered ?? []).filter((policy) => policy.retained === false).length

  return (
    envelope.retrieval.status === 'not_narrowed' ||
    (envelope.retrieval.status === 'narrowed' && discarded === 0)
  )
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
  envelope: CaseDecisionEnvelope,
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
