/**
 * What one project's row says about itself in the register.
 *
 * WHY THIS EXISTS
 *
 * The register used to describe every project by its PUBLISHED state: the active
 * version number, the count of approved rules, and the share of those rules whose
 * test is a comparison. For a portfolio where nothing has been published yet that
 * is three constants, so every row read identically and the panel reported nothing.
 * Worse, it contradicted itself: a row said "0 rules" beside a badge counting
 * hundreds of records awaiting review. Both numbers were true. They measure
 * different stages of the same record's life, and the row showed the stage the work
 * had not reached instead of the stage it was actually in.
 *
 * So a row now describes the CURRENT GENERATION of records a project holds, which
 * is what differs between projects, and mentions publication only as a trailing
 * fact rather than as the headline.
 *
 * ROUTES ARE NOT SCORES
 *
 * The old row rendered `machine_executable_count / active_rule_count` as a
 * percentage, and guarded the divide-by-zero by declaring the answer to be 0%.
 * That is an undefined ratio rendered as the worst possible grade.
 *
 * It is replaced with counts, deliberately, and no ratio is offered anywhere. A
 * record whose test the source states as a comparison takes the Deterministic
 * route; a record the source states in words takes the AI Ready route, where a
 * judge reads the rule against the case. Both are routes the
 * source chooses, not marks the extractor earns, and most real policy prose takes
 * the second. Any ratio between them invites reading one as a shortfall of the
 * other, and no caption survives that: a reader who sees a low percentage has
 * already concluded something is wrong before reaching the words. Counts state what
 * is there and imply no target.
 *
 * The two route counts are also independent rather than complementary. A record
 * carrying neither mode belongs to neither count, so they need not sum to the whole
 * and one is never derived by subtracting the other from the total -- that would
 * silently file an unrecorded route under a route name and claim a routing
 * decision the data does not contain.
 */

import { POLICY_ROUTE_LABELS } from "./policyGrouping";

/** The fields of a portfolio insight this module reads. Declared structurally so a
 *  caller can pass the full insight and a test can build a minimal one. */
export interface ProjectRowFacts {
  document_count: number;
  review_pending_policies?: number;
  review_pending: number;
  live_policy_count?: number;
  live_candidate_count: number;
  candidate_direct_count: number;
  candidate_reading_count: number;
  active_version_number: number | null;
  active_rule_count: number;
}

/**
 * The clauses describing a project, in the order a reader needs them: the work it
 * is carrying, how that work is routed, then whether it is published.
 *
 * Returned as parts rather than one string so the caller decides the separator and
 * a test can assert a clause without depending on punctuation.
 */
export function projectRowClauses(facts: ProjectRowFacts): string[] {
  const clauses: string[] = [];

  const live = Math.max(0, facts.live_candidate_count);
  const pending = Math.max(0, facts.review_pending);
  const liveScale = policyRuleScale(facts.live_policy_count, live);
  const pendingScale = policyRuleScale(facts.review_pending_policies, pending);

  // 1. The workload. Leads, because it is the number that differs between projects
  //    and the number a reviewer would act on.
  if (live === 0) {
    // Distinguish "nothing has been loaded" from "something was loaded and holds
    // no records". They call for different actions, and a single empty-ish phrase
    // for both would hide a document that produced nothing.
    clauses.push(facts.document_count === 0 ? "No document loaded yet" : "No policies or rules yet");
  } else if (pending > 0) {
    clauses.push(`${pendingScale} in review`);
  } else {
    clauses.push(`${liveScale} · none in review`);
  }

  // 2. How those records are routed. Counts only; see the header note.
  clauses.push(...routeClauses(live, facts.candidate_direct_count, facts.candidate_reading_count));

  // 3. Publication, last. True and worth stating, but it is the same for every
  //    project in an unpublished portfolio, so it must not lead.
  if (facts.active_version_number !== null) {
    const n = facts.active_rule_count;
    // Only state the published count when it disagrees with the live one.
    // Restating a matching count puts "280 rules" twice in a single row, and a
    // unit repeated in one sentence reads as two different quantities -- the
    // same defect that naming records beside rules produced. The number earns
    // its place only when publication and the current generation have drifted
    // apart, which is the case a reader would act on.
    clauses.push(
      n === live
        ? `v${facts.active_version_number} published`
        : `v${facts.active_version_number} published · ${n} ${n === 1 ? "rule" : "rules"}`,
    );
  } else {
    clauses.push("Not published");
  }

  return clauses;
}

/**
 * Route wording for a set of records, used both for one project's row and for the
 * portfolio-wide statistic.
 *
 * "all AI Ready" rather than "0 Deterministic · 411 AI Ready": a zero shown beside
 * a route reads as a score against a target, which is exactly what counts were
 * adopted to avoid. Naming only the routes that are actually present says the same
 * thing and implies no missing one.
 *
 * The two route names are imported rather than written here, so the register, the
 * card and the detail panel cannot end up calling the same route different things.
 */
export function routeClauses(live: number, direct: number, reading: number): string[] {
  if (live === 0) return [];

  const safeDirect = Math.max(0, direct);
  const safeReading = Math.max(0, reading);

  const readingRoute = POLICY_ROUTE_LABELS.ai_ready;
  const directRoute = POLICY_ROUTE_LABELS.deterministic;

  if (safeReading === live) return [`all ${readingRoute}`];
  if (safeDirect === live) return [`all ${directRoute}`];

  const parts: string[] = [];
  if (safeDirect > 0) parts.push(`${safeDirect} ${directRoute}`);
  if (safeReading > 0) parts.push(`${safeReading} ${readingRoute}`);

  // Records carrying neither mode. Never folded into either route -- that would
  // assert a routing decision the record does not carry -- and never dropped
  // silently, which would make the counts appear to account for every record when
  // they do not.
  const unrouted = live - safeDirect - safeReading;
  if (unrouted > 0) parts.push(`${unrouted} without a recorded route`);

  return parts;
}

function policyRuleScale(policyCount: number | null | undefined, ruleCount: number): string {
  const safeRules = Math.max(0, ruleCount);
  if (policyCount === null || policyCount === undefined) {
    return `${safeRules} ${safeRules === 1 ? "rule" : "rules"}`;
  }
  const safePolicies = Math.max(0, policyCount);
  return `${safePolicies} ${safePolicies === 1 ? "policy" : "policies"} · ${safeRules} ${safeRules === 1 ? "rule" : "rules"}`;
}

/**
 * The same route facts shaped for a two-line cell: a headline and its detail.
 *
 * Both registers render this, from here, so the two cannot drift into describing
 * the same fact in different words -- the failure that put one phrasing in the
 * dashboard and another in the project register in the first place.
 */
export function routeCell(
  live: number,
  direct: number,
  reading: number,
): { headline: string; detail: string } {
  if (live <= 0) return { headline: "No policies or rules yet", detail: "Nothing extracted to decide" };

  const clauses = routeClauses(live, direct, reading);
  const [first, ...rest] = clauses;
  const headline = first.charAt(0).toUpperCase() + first.slice(1);
  const detail = rest.length > 0 ? rest.join(" · ") : `${live} ${live === 1 ? "rule" : "rules"}`;
  return { headline, detail };
}
