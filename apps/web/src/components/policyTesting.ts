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
 * Which door a rule can be tested through, here, now.
 *
 * TWO ROUTES DECIDE, AND ONE OF THEM NEEDS SOMETHING PUBLISHED
 *
 * A rule states its test either as a comparison between named quantities or in
 * words. The first is computed by the deterministic engine; the second is read
 * by a judge. That much is a property of the rule and nothing else.
 *
 * But the engine computes against a *published version* — it resolves the set's
 * active approved version and evaluates the rule as it stands there. Before
 * anything is published there is no such version, so there is nothing for it to
 * compute against. The judge is handed the rule itself and needs no version at
 * all, which is why a rule stated in words can be tested from the moment it is
 * drafted.
 *
 * So availability is derived from two facts about the record — how it states
 * its test, and whether a version of it has been published — and from nothing
 * about which page is rendering. Both are properties of the record. A caller
 * cannot pass a flag that opens a door the server will slam.
 *
 * `engine-awaits-publication` is not a defect and must never be worded as one.
 * The rule is fine; the instrument that checks it has not been given the thing
 * it checks against yet.
 */
export type TestingDoor = "engine-scenario" | "judge-case" | "engine-awaits-publication";

export function testingDoor(
  rule: CanonicalRule,
  publishedVersionId: string | null | undefined,
): TestingDoor {
  if (!engineDecidesRule(rule)) return "judge-case";
  return publishedVersionId ? "engine-scenario" : "engine-awaits-publication";
}

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
}

/**
 * Put one case to one rule, through whichever door the rule's route opens.
 *
 * The single implementation of "ask about this rule". Rule scope and policy
 * scope both call it, so a rule put to a case on its own and the same rule put
 * to a case as part of its policy cannot reach different deciders — which is
 * exactly the drift that two copies of this routing would produce, and it would
 * be invisible until two surfaces disagreed about one rule.
 */
export async function putCaseToRule(
  rule: CanonicalRule,
  options: {
    scenario: string;
    reasoningEffort: string;
    policySetKey: string | null | undefined;
    publishedVersionId: string | null | undefined;
  },
): Promise<CaseAnswer> {
  const { scenario, reasoningEffort, policySetKey, publishedVersionId } = options;
  const door = testingDoor(rule, publishedVersionId);
  const base = { ruleId: rule.rule_id, title: rule.title };

  if (door === "engine-awaits-publication" || (door === "engine-scenario" && !policySetKey)) {
    return {
      ...base,
      decidedBy: "nobody",
      label: null,
      color: "default",
      account: "",
      missing: [],
      unanswered:
        "This rule states its test as a comparison, and the engine computes that comparison against a published version. Nothing has been published for it to compute against yet.",
    };
  }

  try {
    if (door === "engine-scenario") {
      const result = await aiApi.testRuleScenario(
        policySetKey as string,
        rule.rule_id,
        scenario,
        reasoningEffort,
      );
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
      };
    }

    const judged = await aiApi.evaluateScenario(rule, scenario, reasoningEffort);
    const answer = JUDGED_ANSWER[judged.applies] ?? JUDGED_ANSWER.uncertain;
    return {
      ...base,
      decidedBy: "judge",
      label: answer.label,
      color: answer.color,
      account: judged.reasoning ?? "",
      missing: judged.missing_facts ?? [],
      unanswered: null,
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
   * version's package. Without one there is no request to make — not a request
   * that would be turned down. A reviewer on an unpublished set was previously
   * offered this control, pressed it, and was told the set "has no active
   * approved version to propose tests against": a true sentence describing a
   * door that should never have been drawn.
   */
  generate: ((ruleIds: readonly string[]) => Promise<void>) | null;
  /** Run these tests against the version on screen. */
  run: (testIds: readonly string[]) => Promise<void>;
  /**
   * The published version these verbs act against, or null when the record on
   * screen is not published.
   *
   * Carried out of the hook rather than passed separately to the pane, so that
   * the pane's account of what can be asked and the hook's account of what it
   * will actually call come from one value. It is a fact about the record — the
   * version it is being read at — not a permission.
   */
  publishedVersionId: string | null;
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
  /** Who is asking. Recorded on the batch and on every run. */
  actor: string;
  /** Called after anything succeeds, so the surface can re-read the tests. */
  onChanged: () => void;
}): PolicyTesting {
  const { policySetKey, policyVersionId, actor, onChanged } = options;
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

  const publishedVersionId = policyVersionId ?? null;

  return useMemo(
    () => ({
      // The batch door is drawn only where it opens. See `PolicyTesting.generate`.
      generate: publishedVersionId ? generate : null,
      run,
      publishedVersionId,
      busy,
      working: busy.size > 0,
      error,
      dismissError,
    }),
    [generate, run, publishedVersionId, busy, error, dismissError],
  );
}
