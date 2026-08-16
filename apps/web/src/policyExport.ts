/**
 * THE POLICY IS THE UNIT — of counting, of selection, and of what a download
 * writes.
 *
 * A rule is something a policy states. It is not a thing this product hands
 * anyone on its own: a reviewer approves a policy, selects a policy, and reads
 * a policy. The surfaces drifted away from that one at a time — a version strip
 * that stated a rule count, a checkbox that offered "select all 412 shown" over
 * thirty-eight cards, and a download that wrote one line per rule so that
 * choosing two policies produced thirteen lines with nothing in the file
 * recording which two had been chosen.
 *
 * Each of those was a separate string in a separate place, which is why they
 * drifted separately. They live here together instead, because they are one
 * idea, and because a phrase nobody can call from a test is a phrase that gets
 * quietly reworded.
 *
 * No count in this module is ever written down. Every number is passed in.
 */
import { policyJsonDocument, type PolicyCard } from "./policyCards";

/**
 * `n policies`, or `1 policy`.
 *
 * A helper rather than a ternary at each site because there were four sites and
 * they disagreed: two said "shown", one said nothing at all, and one counted
 * rules while saying policies.
 */
export function policyUnit(count: number): string {
  return `${count} ${count === 1 ? "policy" : "policies"}`;
}

/** `n rules`, or `1 rule`. Said beside the policy count, never instead of it. */
export function ruleUnit(count: number): string {
  return `${count} ${count === 1 ? "rule" : "rules"}`;
}

/**
 * What a download of these policies contains, in words, before it runs.
 *
 * Named on the button so a reviewer who has exported this page before — and
 * received one line per rule — is told the shape has changed at the moment they
 * choose, rather than discovering it in a text editor afterwards.
 */
export function exportContentsLabel(policyCount: number): string {
  return `Export ${policyUnit(policyCount)} (JSONL)`;
}

/** The same, for the whole version rather than a selection. */
export function exportAllContentsLabel(policyCount: number): string {
  return `Export all ${policyUnit(policyCount)} (JSONL)`;
}

export interface PolicyJsonl {
  /** The file, one policy per line, newline-terminated. */
  text: string;
  /** How many lines, which is how many policies. */
  policyCount: number;
  /** How many rules those policies state, all told. Reported beside the policy
   *  count so a reader who counts in rules is not left thinking rules were
   *  dropped when the line count fell. */
  ruleCount: number;
}

/**
 * Write policies out, one policy per line, its rules nested inside it.
 *
 * The line is `policyJsonDocument` — the same serialisation the JSON tab shows
 * on screen under "this policy as one document". That reuse is deliberate and
 * load-bearing: a second way to write a policy would drift from the one on
 * screen without anyone noticing, because an export is not read until the day
 * it matters, and by then the divergence is old.
 *
 * Order is the order given, so a file follows the page it came from.
 */
export function policiesAsJsonl(
  cards: readonly PolicyCard[],
  documentName?: string | null,
): PolicyJsonl {
  const lines = cards.map((card) => JSON.stringify(policyJsonDocument(card, documentName)));
  return {
    // Trailing newline: every line terminated, so a reader appending to the
    // file or piping it line-by-line gets whole records.
    text: lines.length === 0 ? "" : lines.join("\n") + "\n",
    policyCount: cards.length,
    ruleCount: cards.reduce((total, card) => total + card.rules.length, 0),
  };
}

/**
 * What was written, said afterwards.
 *
 * Policy first, because that is what was chosen; the rule tally in parentheses,
 * because it is a fact about the policies rather than a second thing that was
 * exported.
 */
export function exportedSummary(written: PolicyJsonl, filename: string): string {
  return (
    `${policyUnit(written.policyCount)} ` +
    `(${ruleUnit(written.ruleCount)} nested inside them) ` +
    `exported to ${filename}.`
  );
}
