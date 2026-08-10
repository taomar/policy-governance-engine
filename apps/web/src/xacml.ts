/**
 * XACML 3.0 vocabulary for displaying a rule's stated logic.
 *
 * One standard, used everywhere. `docs/policy-standards-research.md` records
 * OASIS XACML 3.0 as directly adopted, and the platform already follows it:
 * PolicyScope is an XACML Target, `advice` is XACML Advice, and the evaluator's
 * combining algorithms are XACML's. Introducing a second vocabulary for the
 * display would mean a reviewer reading one screen in RFC 2119 terms and the
 * next in XACML terms, with nothing saying the two describe the same rule.
 *
 * Everything here is presentation. None of it is evaluated, and none of it is
 * written into `rule.condition`, which is the evaluator's contract and admits
 * only fact paths a fact model actually defines.
 *
 * Reference: OASIS XACML 3.0 core specification (OS, January 2013) —
 * decisions (§7.2.x), Obligations and Advice (§7.18), and attribute categories
 * for Subject, Action and Resource (§B.2, §B.5-B.8).
 */

/** An XACML authorization decision. */
export type XacmlDecision = "Permit" | "Deny" | "NotApplicable";

export interface XacmlEffect {
  decision: XacmlDecision;
  /**
   * XACML §7.18 distinguishes an Obligation — which a PEP MUST discharge —
   * from Advice, which it MAY ignore. The platform's REQUIRE_ACTION is the
   * former and INFORMATIONAL the latter, and collapsing them would turn
   * guidance into a duty.
   */
  directive: "Obligation" | "Advice" | null;
  /** One-line gloss shown beside the decision. */
  gloss: string;
}

/**
 * Platform effect type to XACML decision.
 *
 * INFORMATIONAL maps to NotApplicable rather than Permit: a definition or a
 * classification authorizes nothing, and XACML reserves Permit for an actual
 * grant. This mirrors `_RULE_TYPE_MAP` on the server, which refuses to project
 * a definition as ALLOW for the same reason.
 */
export const XACML_EFFECTS: Record<string, XacmlEffect> = {
  allow: { decision: "Permit", directive: null, gloss: "the request is granted" },
  deny: { decision: "Deny", directive: null, gloss: "the request is refused" },
  require_action: {
    decision: "Permit",
    directive: "Obligation",
    gloss: "granted, and the obligation below must be discharged",
  },
  informational: {
    decision: "NotApplicable",
    directive: "Advice",
    gloss: "nothing is granted or refused; this states meaning only",
  },
};

export function xacmlEffect(effectType: string | null | undefined): XacmlEffect {
  return (
    XACML_EFFECTS[(effectType ?? "").toLowerCase()] ?? {
      decision: "NotApplicable",
      directive: null,
      gloss: "no decision is stated",
    }
  );
}

/**
 * Canonical rule types that state meaning rather than conduct.
 *
 * XACML has no notion of a rule that only classifies, so these are shown as
 * NotApplicable with Advice: they carry information a PEP may act on, but they
 * grant and refuse nothing. Naming them here keeps the distinction in one
 * place rather than re-derived per view.
 */
const MEANING_ONLY_TYPES = new Set(["classification", "definition"]);

/**
 * The XACML attribute a stated subject is asserted against.
 *
 * XACML describes a request by Subject, Action and Resource. A rule about
 * conduct names its actor, so `subject.role` — the short form of
 * `urn:oasis:names:tc:xacml:2.0:subject:role` — is correct. A rule that only
 * classifies names the thing classified, which is a Resource: calling
 * "Security incidents" a subject role would claim the document assigned
 * conduct to a category, which it did not.
 */
export function subjectAttribute(canonicalRuleType: string | null | undefined): string {
  return MEANING_ONLY_TYPES.has((canonicalRuleType ?? "").toLowerCase())
    ? RESOURCE_ATTRIBUTE
    : SUBJECT_ATTRIBUTE;
}

/** `urn:oasis:names:tc:xacml:2.0:subject:role`, short form. */
export const SUBJECT_ATTRIBUTE = "subject.role";

/** `urn:oasis:names:tc:xacml:1.0:action:action-id`, short form. */
export const ACTION_ATTRIBUTE = "action.action-id";

/** `urn:oasis:names:tc:xacml:1.0:resource:resource-id`, short form. */
export const RESOURCE_ATTRIBUTE = "resource.resource-id";

/**
 * Cited under any view that uses this vocabulary. Kept beside the mapping so
 * the citation cannot drift from what is actually applied.
 */
export const XACML_NOTE =
  "Decisions, Obligations and attribute naming follow OASIS XACML 3.0, the platform's adopted policy standard.";
