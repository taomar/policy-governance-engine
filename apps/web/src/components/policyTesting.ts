/**
 * Asking a policy's tests to exist, and to run.
 *
 * WHY THIS IS A SEPARATE FILE
 *
 * The Tests tab is one component serving two surfaces, and it needs to *do*
 * things, not only display them. The doing needs an actor, a policy set key and
 * a version id, none of which the shared pane should hold — a pane that knows
 * which version it is looking at is a pane that can be written to behave
 * differently on one of them. So the pane takes verbs, and this supplies them.
 * Both surfaces call this, which is what stops there being two implementations
 * of "generate tests for this policy" that drift apart.
 *
 * WHY THIS EXISTS AT ALL
 *
 * The endpoints have been complete on the server for some time and nothing
 * called them. The Tests tab reported, honestly, that no test covered any rule
 * — and then offered no way to change that, so a reviewer read "nothing has
 * been checked" and could do nothing about it. A tab that reports an absence it
 * gives you no way to fill is worse than no tab, because it converts a missing
 * feature into a permanent-looking fact about the document.
 *
 * WHAT IS DELIBERATELY NOT HERE
 *
 * No editability check. Generating a test is not a change to the policy: it
 * writes a row to `policy_tests` that asks a question *about* the record, and
 * the record is not touched. A sealed policy is if anything the one most worth
 * testing, because it is the one being relied on. So this is offered on both
 * surfaces and there is no branch to get wrong.
 */
import { useCallback, useMemo, useState } from "react";
import {
  aiApi,
  PolicyPlatformApiError,
  policyTestApi,
  type CanonicalRule,
  type EvaluationStatus,
} from "../api";
import { engineDecidesRule } from "../ruleExecutability";

/**
 * How many scenarios to ask for per rule.
 *
 * One, and the endpoint is strict about it: it rejects the whole batch unless
 * every selected rule received exactly this many, so a larger number is a
 * larger chance of a refusal after the model has already been paid for. One
 * scenario per rule is also the honest first question — does this rule hold up
 * at all — and a reviewer who wants more can generate again.
 *
 * This is a product default, not a measurement of any document.
 */
const SCENARIOS_PER_RULE = 1;

/**
 * TWO INDEPENDENT AXES: WHO DECIDES, AND WHAT THEY DECIDE ABOUT
 *
 * Testing a rule needs two facts, and they come from two different places.
 *
 * WHO DECIDES comes from the rule's own route. A rule states its test either as
 * a comparison between named quantities or in words. The first is computed by
 * the deterministic engine; the second is read by a judge that returns a verdict
 * on it. That is a property of the rule and of nothing else.
 *
 * WHAT IS DECIDED ABOUT comes from the version the record is being read at. A
 * reviewer is deciding whether to approve *this draft*, so the target is the
 * candidate as it stands — a candidate is not versioned, and on a set that has
 * never published there is no version to name. A policy admin is asking about
 * what is in force, so the target is a named published version, and which one is
 * their choice rather than an implicit "whatever is active now".
 *
 * THESE TWO WERE PREVIOUSLY ONE AXIS, AND THAT WAS THE BUG
 *
 * A single `door` value collapsed them, which made "computed" imply "published"
 * and produced a refusal — *this set has no active approved version to propose
 * tests against* — on exactly the surface where testing matters most. The engine
 * does not need a published version to compute a comparison; it needs a rule.
 * Only the *batch* endpoint, which builds its rule list out of a version's
 * assembled package, genuinely needs one.
 *
 * So all four combinations are live, and none of them is a refusal:
 *
 *   engine + draft      -> compute-scenario, handed the rule itself
 *   engine + published  -> test-scenario at the named version
 *   judge  + draft      -> evaluate-scenario, handed the rule itself
 *   judge  + published  -> evaluate-scenario, handed the published rule
 *
 * Both are derived from the record — how it states its test, and the version it
 * was read at. Neither is a capability a caller passes in, so no caller can open
 * a door the server will slam, and no surface can quietly aim at a target the
 * reader was not told about.
 */
export type Decider = "engine" | "judge";

export function ruleDecider(rule: CanonicalRule): Decider {
  return engineDecidesRule(rule) ? "engine" : "judge";
}

/**
 * What a test runs against.
 *
 * Carried as a value rather than inferred from which page is rendering, because
 * a verdict with no target is not evidence. The same rule can be put to the same
 * case on the review surface and on the published surface and honestly return
 * two different answers — the draft and the published version are two different
 * records. A reader who is not told which one answered cannot use either.
 */
export type TestTarget =
  | { readonly kind: "draft" }
  | {
      readonly kind: "published_version";
      readonly policyVersionId: string;
      readonly versionNumber: number | null;
    };

export const DRAFT_TARGET: TestTarget = { kind: "draft" };

export function testTarget(
  publishedVersionId: string | null | undefined,
  versionNumber?: number | null,
): TestTarget {
  if (!publishedVersionId) return DRAFT_TARGET;
  return {
    kind: "published_version",
    policyVersionId: publishedVersionId,
    versionNumber: versionNumber ?? null,
  };
}

/**
 * The target in a reviewer's words. Matches what the server puts in
 * `tested_against.label`, so a result never contradicts the control that ran it.
 */
export function targetLabel(target: TestTarget): string {
  if (target.kind === "draft") return "the rule as it is drafted now";
  return target.versionNumber == null
    ? "the published version on screen"
    : `published version ${target.versionNumber}`;
}

/**
 * Why a draft answer never becomes a published one.
 *
 * A reviewer tests a candidate and it passes. That is a fact about the draft. It
 * is not a fact about the record that later publishes, which no one has put a
 * case to — so on the published surface that rule is `untested`, not `passing`.
 * Carrying the result across would be the most dangerous kind of false
 * assurance, because it would be green and it would be wrong.
 */
export const RESULT_DOES_NOT_CARRY_OVER =
  "This answer is about the draft. Publishing does not carry it over — the published record starts with nothing put to it.";

/**
 * The three answers a judge can return, in the words a reviewer reads.
 *
 * `uncertain` is an answer about the case, not about the rule: the rule was
 * read, and what it needs in order to decide was not described. Wording it as a
 * property of the rule would report a route as a defect.
 */
export const JUDGED_ANSWER: Record<"yes" | "no" | "uncertain", { label: string; color: string }> = {
  yes: { label: "This rule applies to the case", color: "green" },
  no: { label: "This rule stands aside from the case", color: "blue" },
  uncertain: { label: "The case as described does not settle it", color: "gold" },
};

/**
 * The engine's answers, in the same register as the judge's.
 *
 * These are deliberately not the same question. The engine computes whether the
 * case *satisfies* the rule; the judge reads whether the rule *applies* to the
 * case. Rendering the raw enum on one side and a sentence on the other made the
 * computed route read as machine output and the judged route as prose, which is
 * a ranking arrived at through typography rather than words. Both now answer in
 * a sentence, and neither answer is translated into the other's scale — a
 * reviewer who needs the exact status has the JSON.
 *
 * `INDETERMINATE` shares its wording with the judge's `uncertain` because it is
 * the same honest report: the case did not state what deciding it needs.
 */
export const COMPUTED_ANSWER: Record<EvaluationStatus, { label: string; color: string }> = {
  SATISFIED: { label: "The case meets this rule", color: "green" },
  NOT_SATISFIED: { label: "The case breaches this rule", color: "red" },
  NOT_APPLICABLE: { label: "This rule stands aside from the case", color: "blue" },
  INDETERMINATE: { label: "The case as described does not settle it", color: "gold" },
  ERROR: { label: "This could not be computed", color: "default" },
};

/**
 * Where a rule's answer leaves the case, as a category rather than a sentence.
 *
 * A policy-level reading has to lead with the rules that *settle* the case and
 * keep the rest as supporting detail, and it must do that without re-reading the
 * prose each answer already carries. This is that category, derived from the
 * decider's own status and never from the words on screen, so a reworded label
 * can never move a rule between buckets.
 *
 *   - `settles`      the decider reached the case: the engine computed that it
 *                    meets or breaches the rule, or the judge read the rule as
 *                    applying to it.
 *   - `stands_aside` the rule does not bear on the case.
 *   - `unsettled`    the rule bears, but what deciding it needs was not stated.
 *   - `uncomputable` the engine could not compute a verdict.
 *   - `unanswered`   nobody answered; the request for this rule did not complete.
 */
export type CaseSettlement =
  | "settles"
  | "stands_aside"
  | "unsettled"
  | "uncomputable"
  | "unanswered";

/**
 * The engine's status, bucketed into where it leaves the case. Keyed on the
 * status enum, not the label, so the sentence a reviewer reads can be reworded
 * without silently re-bucketing a rule.
 */
const SETTLEMENT_OF_STATUS: Record<EvaluationStatus, CaseSettlement> = {
  SATISFIED: "settles",
  NOT_SATISFIED: "settles",
  NOT_APPLICABLE: "stands_aside",
  INDETERMINATE: "unsettled",
  ERROR: "uncomputable",
};

/** One rule's answer to one case, in the terms of whichever decider answered. */
export interface CaseAnswer {
  ruleId: string;
  title: string;
  /**
   * Which decider answered. Not a ranking and not a quality: it is which
   * instrument the rule's own route called for.
   */
  decidedBy: "engine" | "judge" | "nobody";
  /** The answer, already in a reviewer's words. Null when nobody answered. */
  label: string | null;
  color: string;
  /** The decider's account of how it got there. */
  account: string;
  /** What the case would have to state for this to be settled. */
  missing: readonly string[];
  /** Why nobody answered, when nobody did. Never a judgement of the rule. */
  unanswered: string | null;
  /**
   * What this answer was about: the draft, or a named published version.
   *
   * Part of the answer, not of the page that asked. A verdict whose target the
   * reader has to infer from context is the same failure as an answer that
   * silently resolved against draft rows and looked grounded.
   */
  testedAgainst: TestTarget;
  /**
   * Where this answer leaves the case, for a policy-level reading to lead with
   * what settles it and keep the rest as supporting detail. Derived from the
   * decider's status, never from `label`.
   */
  settlement: CaseSettlement;
  /**
   * True only when a rule the case *settles* is one it breaches. It lets a
   * policy-level reading say plainly when the rules that settle a case do not all
   * point the same way — one met and one breached is exactly the divergence that
   * must never be hidden — without picking a winner or averaging them.
   */
  adverse: boolean;
}

/**
 * Put one case to one rule: the rule's route picks the decider, the record's
 * version picks the target, and every combination of the two is answerable.
 *
 * The single implementation of "ask about this rule". Rule scope and policy
 * scope both call it, and so do both surfaces, so the same rule asked the same
 * question cannot reach different deciders — which is exactly the drift that two
 * copies of this routing would produce, and it would be invisible until two
 * surfaces disagreed about one rule.
 */
export async function putCaseToRule(
  rule: CanonicalRule,
  options: {
    scenario: string;
    reasoningEffort: string;
    policySetKey: string | null | undefined;
    target: TestTarget;
  },
): Promise<CaseAnswer> {
  const { scenario, reasoningEffort, policySetKey, target } = options;
  const decider = ruleDecider(rule);
  const base = { ruleId: rule.rule_id, title: rule.title, testedAgainst: target };

  try {
    if (decider === "engine") {
      // Published and named: address the rule through its set at that version,
      // so it is evaluated among its siblings and its version's aggregate
      // limits. Otherwise hand the engine the rule itself — the comparison is
      // computable from the rule, and waiting for a publication that may never
      // come is not a property of the arithmetic.
      const result =
        target.kind === "published_version" && policySetKey
          ? await aiApi.testRuleScenario(
              policySetKey,
              rule.rule_id,
              scenario,
              reasoningEffort,
              target.policyVersionId,
            )
          : await aiApi.computeScenario(rule, scenario, reasoningEffort);
      const status = result.rule_result?.status ?? "ERROR";
      const answer = COMPUTED_ANSWER[status] ?? COMPUTED_ANSWER.ERROR;
      return {
        ...base,
        decidedBy: "engine",
        label: answer.label,
        color: answer.color,
        account: result.explanation ?? "",
        missing: result.missing_facts ?? [],
        unanswered: null,
        settlement: SETTLEMENT_OF_STATUS[status] ?? "uncomputable",
        // A breach is the one settled outcome that points against the case, and
        // the only one that can make two settling rules disagree.
        adverse: status === "NOT_SATISFIED",
      };
    }

    // The judge is handed the record it is to read. Which record that is has
    // already been decided by whoever loaded it — a candidate row on the review
    // surface, a published row at the chosen version here — so the target is
    // honoured by the rule that arrives, and reported rather than assumed.
    const judged = await aiApi.evaluateScenario(rule, scenario, reasoningEffort);
    const answer = JUDGED_ANSWER[judged.applies] ?? JUDGED_ANSWER.uncertain;
    // The judge reads whether the rule applies, not whether the case complies, so
    // it never returns a breach: an applying rule settles the case, a standing-
    // aside rule does not bear, and anything else is the rule borne-but-unsettled.
    const settlement: CaseSettlement =
      judged.applies === "yes"
        ? "settles"
        : judged.applies === "no"
          ? "stands_aside"
          : "unsettled";
    return {
      ...base,
      decidedBy: "judge",
      label: answer.label,
      color: answer.color,
      account: judged.reasoning ?? "",
      missing: judged.missing_facts ?? [],
      unanswered: null,
      settlement,
      adverse: false,
    };
  } catch (caught) {
    return {
      ...base,
      decidedBy: "nobody",
      label: null,
      color: "default",
      account: "",
      missing: [],
      unanswered: refusal(caught),
      settlement: "unanswered",
      adverse: false,
    };
  }
}

/** What the Tests pane can ask for, and what it is told while it waits. */
export interface PolicyTesting {
  /**
   * Propose scenarios for these rules, or null when there is nothing to
   * propose them against.
   *
   * Null, rather than a function that returns a refusal, because the batch
   * endpoint takes a published version and builds its rule list from that
   * version's assembled package. Without one there is no request to make — not
   * a request that would be turned down. A reviewer on an unpublished set was
   * previously offered this control, pressed it, and was told the set "has no
   * active approved version to propose tests against": a true sentence
   * describing a door that should never have been drawn.
   *
   * This is the *only* thing here that needs a version. Putting a case to a
   * rule never did; that it appeared to was the defect. Writing a batch of
   * scenarios in advance is an optimisation over asking one at a time, and an
   * optimisation being unavailable is not a rule being unavailable.
   */
  generate: ((ruleIds: readonly string[]) => Promise<void>) | null;
  /** Run these tests against the version on screen. */
  run: (testIds: readonly string[]) => Promise<void>;
  /**
   * What these verbs act against: the draft, or a named published version.
   *
   * Carried out of the hook rather than passed separately to the pane, so that
   * the pane's account of what can be asked and the hook's account of what it
   * will actually call come from one value. It is a fact about the record — the
   * version it is being read at — not a permission.
   */
  target: TestTarget;
  /** Which rules or tests are mid-flight, so the pane can say which row is busy. */
  busy: ReadonlySet<string>;
  /** Whether anything at all is in flight. */
  working: boolean;
  /** The last refusal, in the server's own words, or null. */
  error: string | null;
  /** Clear the last refusal. */
  dismissError: () => void;
}

/**
 * Turn a thrown error into something a reviewer can act on.
 *
 * The server's `detail` is the specific part — which rule got how many
 * scenarios, or that AI is not configured — and it is what gets shown. A
 * generic "generation failed" would leave the reviewer with no idea whether to
 * retry, reword their guidance, or call an administrator.
 */
function refusal(error: unknown): string {
  if (error instanceof PolicyPlatformApiError) {
    return error.detail || `The server refused the request (${error.status}).`;
  }
  if (error instanceof Error && error.message) return error.message;
  return "The request did not complete, and the reason was not reported.";
}

export function usePolicyTesting(options: {
  policySetKey: string | null | undefined;
  /** The version to run against, when the surface is looking at one. */
  policyVersionId?: string | null;
  /** That version's number, so a result can name it rather than print a uuid. */
  policyVersionNumber?: number | null;
  /** Who is asking. Recorded on the batch and on every run. */
  actor: string;
  /** Called after anything succeeds, so the surface can re-read the tests. */
  onChanged: () => void;
}): PolicyTesting {
  const { policySetKey, policyVersionId, policyVersionNumber, actor, onChanged } = options;
  const [busy, setBusy] = useState<ReadonlySet<string>>(() => new Set());
  const [error, setError] = useState<string | null>(null);

  const track = useCallback(async (keys: readonly string[], work: () => Promise<unknown>) => {
    setError(null);
    setBusy((current) => {
      const next = new Set(current);
      for (const key of keys) next.add(key);
      return next;
    });
    try {
      await work();
      onChanged();
    } catch (caught) {
      setError(refusal(caught));
    } finally {
      setBusy((current) => {
        const next = new Set(current);
        for (const key of keys) next.delete(key);
        return next;
      });
    }
  }, [onChanged]);

  const generate = useCallback(
    async (ruleIds: readonly string[]) => {
      if (!policySetKey || !policyVersionId || ruleIds.length === 0) return;
      await track(ruleIds, () =>
        policyTestApi.generateBatch(policySetKey, {
          rule_ids: [...ruleIds],
          tests_per_policy: SCENARIOS_PER_RULE,
          policy_version_id: policyVersionId,
          grounding_mode: "json_only",
          reasoning_effort: "medium",
          guidance: "",
          created_by: actor,
        }),
      );
    },
    [policySetKey, policyVersionId, actor, track],
  );

  const run = useCallback(
    async (testIds: readonly string[]) => {
      if (testIds.length === 0) return;
      await track(testIds, async () => {
        // Sequentially, not in parallel: each run is a model call, and firing
        // a policy's worth of them at once is the difference between a slow
        // action and a rate-limit refusal that loses the ones already paid for.
        for (const testId of testIds) {
          await policyTestApi.run(testId, actor, policyVersionId ?? undefined);
        }
      });
    },
    [actor, policyVersionId, track],
  );

  const dismissError = useCallback(() => setError(null), []);

  const target = useMemo(
    () => testTarget(policyVersionId, policyVersionNumber),
    [policyVersionId, policyVersionNumber],
  );

  return useMemo(
    () => ({
      // The batch door is drawn only where it opens. See `PolicyTesting.generate`.
      generate: target.kind === "published_version" ? generate : null,
      run,
      target,
      busy,
      working: busy.size > 0,
      error,
      dismissError,
    }),
    [generate, run, target, busy, error, dismissError],
  );
}
