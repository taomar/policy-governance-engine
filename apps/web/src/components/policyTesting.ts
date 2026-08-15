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
import { PolicyPlatformApiError, policyTestApi } from "../api";

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

/** What the Tests pane can ask for, and what it is told while it waits. */
export interface PolicyTesting {
  /** Propose scenarios for these rules. Costs model time. */
  generate: (ruleIds: readonly string[]) => Promise<void>;
  /** Run these tests against the version on screen. */
  run: (testIds: readonly string[]) => Promise<void>;
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
      if (!policySetKey || ruleIds.length === 0) return;
      await track(ruleIds, () =>
        policyTestApi.generateBatch(policySetKey, {
          rule_ids: [...ruleIds],
          tests_per_policy: SCENARIOS_PER_RULE,
          policy_version_id: policyVersionId ?? undefined,
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

  return useMemo(
    () => ({ generate, run, busy, working: busy.size > 0, error, dismissError }),
    [generate, run, busy, error, dismissError],
  );
}
