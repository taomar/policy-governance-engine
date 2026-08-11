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

/** An XACML Rule Effect. XACML 3.0 §5.28 defines exactly two. */
export type XacmlRuleEffect = "Permit" | "Deny";

/**
 * A PDP decision result. XACML 3.0 §7.2.x.
 *
 * Deliberately a *different* type from `XacmlRuleEffect`. A Rule declares
 * Permit or Deny; a PDP returns one of these four after evaluating a request.
 * The two were the same union here, which is what allowed `Effect =
 * NotApplicable` to be displayed as a rule's declared effect — a decision
 * XACML has no way to express.
 *
 * Nothing in the extraction UI may produce a value of this type. It exists so
 * that a future evaluation view has the right vocabulary, and so the
 * distinction is written down rather than remembered.
 */
export type XacmlDecisionResult = "Permit" | "Deny" | "NotApplicable" | "Indeterminate";

export interface XacmlEffect {
  /**
   * The declared Rule Effect, or null when the statement is not a XACML Rule
   * at all. A definition grants and refuses nothing.
   *
   * null is not NotApplicable: NotApplicable asserts that a Rule existed and
   * did not apply to a request, which only a PDP can determine.
   */
  effect: XacmlRuleEffect | null;
  /**
   * XACML §7.18 distinguishes an Obligation — which a PEP MUST discharge —
   * from Advice, which it MAY ignore. The platform's REQUIRE_ACTION is the
   * former and INFORMATIONAL the latter, and collapsing them would turn
   * guidance into a duty.
   */
  directive: "Obligation" | "Advice" | null;
  /** One-line gloss shown beside the effect. */
  gloss: string;
}

/**
 * Platform effect type to XACML Rule Effect.
 *
 * `informational` maps to `effect: null`, not to NotApplicable. A definition
 * or classification is not a Rule, so it declares no Effect — whereas
 * NotApplicable would claim it is a Rule that did not apply, which is a
 * runtime determination no extraction can make.
 */
export const XACML_EFFECTS: Record<string, XacmlEffect> = {
  allow: { effect: "Permit", directive: null, gloss: "the request is granted" },
  deny: { effect: "Deny", directive: null, gloss: "the request is refused" },
  require_action: {
    effect: "Permit",
    directive: "Obligation",
    gloss: "granted, and the obligation below must be discharged",
  },
  informational: {
    effect: null,
    directive: "Advice",
    gloss: "states meaning only — not a XACML Rule, so it declares no Effect",
  },
};

export function xacmlEffect(effectType: string | null | undefined): XacmlEffect {
  return (
    XACML_EFFECTS[(effectType ?? "").toLowerCase()] ?? {
      effect: null,
      directive: null,
      gloss: "no decision is stated",
    }
  );
}

/** How a rule's declared Effect should read. Never a decision result. */
export function effectLabel(effect: XacmlRuleEffect | null): string {
  return effect ?? "No Effect declared";
}

/**
 * Canonical rule types that state meaning rather than conduct.
 *
 * These declare no Rule Effect at all — they grant and refuse nothing. Naming
 * them here keeps the distinction in one place rather than re-derived per view.
 */
const MEANING_ONLY_TYPES = new Set(["classification", "definition"]);

/**
 * The XACML category a canonical subject belongs to — or none.
 *
 * This used to answer `subject.subject-id` for everything except definitions,
 * which asserted that "the allowance", "Annual increase" and "A work nature
 * allowance at the rate of (200) two hundred SR per month" were all XACML
 * subjects. XACML's subject is the *requesting entity*; a benefit requests
 * nothing, and matching a request against `subject-id = "the allowance"`
 * matches nothing, silently.
 *
 * The canonical `subject` slot is a grammatical position, not evidence of
 * role: "The employee shall submit" and "The allowance will be calculated"
 * have the same shape and different roles. So the phrase is treated as a
 * resource unless a party-typed field independently establishes it is a party
 * — which is what `decision_readiness.parties` records, and what the caller
 * passes in.
 *
 * Returns null when nothing establishes the category, so the caller can show
 * the phrase without asserting a category for it.
 */
export function categoryForSubject(
  phrase: string,
  canonicalRuleType: string | null | undefined,
  partyNames: readonly string[]
): { attribute: string; label: string } | null {
  const normalized = phrase.trim().toLowerCase();
  if (!normalized) return null;
  if (partyNames.some((name) => name.trim().toLowerCase() === normalized)) {
    return { attribute: SUBJECT_ATTRIBUTE, label: "Subject" };
  }
  if (MEANING_ONLY_TYPES.has((canonicalRuleType ?? "").toLowerCase())) {
    return { attribute: RESOURCE_ATTRIBUTE, label: "Defined term" };
  }
  return { attribute: RESOURCE_ATTRIBUTE, label: "Resource" };
}

/** `urn:oasis:names:tc:xacml:1.0:subject:subject-id`, short form. */
export const SUBJECT_ATTRIBUTE = "subject.subject-id";

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
