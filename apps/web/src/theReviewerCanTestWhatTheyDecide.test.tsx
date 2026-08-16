/**
 * The reviewer can test the record they are being asked to decide.
 *
 * WHAT IS AT STAKE
 *
 * Two surfaces show a rule: the review queue, where a candidate is decided, and
 * the policies page, where a published version is read. Both mount the same
 * inspector, and the inspector draws its "Test scenario" tab only when it is
 * given the key of the policy set the engine should load. The policies page
 * passed the key. The review queue did not, at the one mount bound to the
 * selected candidate — so the tab was absent exactly where a decision is made,
 * and the reviewer had no way to try a rule before approving it.
 *
 * The omission was invisible because nothing failed: a missing optional prop
 * renders a smaller tab strip, not an error. Seven tabs looked like a design.
 *
 * WHAT IS ASSERTED
 *
 * First, that the key is what draws the tab, so the prop is load-bearing rather
 * than decorative and removing it again fails here.
 *
 * Second, that the record under test is the candidate as it stands. A candidate
 * has no version, so there is nothing published to test it against; the tester
 * is mounted without a target precisely so its draft default applies. A future
 * change that aims it at a published version would test a different record from
 * the one being decided, which is the misreading the reviewer named.
 *
 * Third, over the whole of the queue's source rather than the one mount that
 * was wrong: every inspector the queue mounts is accounted for, and the one
 * bound to the selected candidate carries the key. A second mount added later
 * fails the count and has to be considered rather than silently inheriting
 * whichever behaviour it happens to get.
 *
 * Nothing here is a phrase from any document, and no number in it is a
 * measurement of one.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { CanonicalRule } from "./api";
import { PolicyInspector } from "./components/PolicyInspector";

beforeAll(() => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

afterEach(() => {
  cleanup();
});

/** The control the reviewer was missing, named once so a rename in the
 *  component fails here rather than passing on a substring of something else. */
const THE_TESTING_TAB = /test scenario/i;

function aCandidateRule(): CanonicalRule {
  return {
    rule_id: "a-rule",
    title: "A title",
    description: "A description.",
    rule_type: "obligation",
    evaluation_mode: "ai_ready",
    condition: { type: "all", all: [] },
    effect: { type: "requirement", description: "An effect." },
    scope: {
      jurisdictions: [],
      organizational_units: [],
      processes: [],
      personas: [],
      channels: [],
      systems: [],
    },
    authority: { owner: "An owner", level: "A level", reference: "" },
    required_facts: [],
    decision_readiness: null,
    source_refs: [],
    ambiguity_status: "clear",
    review_status: "candidate",
    lineage: {
      extraction_run_id: null,
      deployment_name: null,
      prompt_version: null,
      parser_version: null,
      schema_version: "1.0",
    },
    category: "",
    tags: [],
    group_label: "",
    related_rule_ids: [],
    is_explicit_override: false,
    supersedes_rule_ids: [],
    advice: [],
    evidence: [],
    rule_revision: 1,
  } as unknown as CanonicalRule;
}

function renderInspector(policySetKey: string | undefined) {
  render(
    <PolicyInspector
      rule={aCandidateRule()}
      policySetKey={policySetKey}
      recordKind="candidate"
      recordLabel="candidate"
      activeTabKey="overview"
      onTabChange={() => {}}
    />,
  );
}

describe("the reviewer can test the record they are deciding", () => {
  it("offers the testing tab on a candidate once the queue names the policy set", () => {
    renderInspector("a-set");
    expect(screen.queryAllByText(THE_TESTING_TAB).length).toBeGreaterThan(0);
  });

  it("draws no testing tab when the key is withheld, so the prop is what carries it", () => {
    renderInspector(undefined);
    expect(screen.queryAllByText(THE_TESTING_TAB)).toHaveLength(0);
  });
});

/** The queue's own source. Read rather than rendered, because the defect was a
 *  prop absent at one call site and no rendering of that component can show a
 *  prop the caller never passed. */
const QUEUE = import.meta.glob("./components/ReviewQueue.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

describe("every inspector the queue mounts is accounted for", () => {
  /** A glob that matches nothing passes every assertion made about it, so the
   *  file has to be proved present before anything is read from it. */
  const source = (() => {
    const found = Object.values(QUEUE);
    expect(found).toHaveLength(1);
    return found[0];
  })();

  /** Each mount, from its opening tag through enough of its props to read them.
   *  Sliced by distance rather than by matching the closing tag, because a mount
   *  whose props contain their own elements has more than one closing tag in it. */
  const mounts = [...source.matchAll(/<PolicyInspector\b/g)].map((match) =>
    source.slice(match.index ?? 0, (match.index ?? 0) + 2500),
  );

  it("mounts the inspector exactly where this file knows about", () => {
    // Not a measurement of anything in a document: it is the number of call
    // sites this file has read and reasoned about. A new one must be considered
    // rather than inherit whichever behaviour it happens to get.
    expect(mounts).toHaveLength(2);
  });

  it("names the policy set on the mount bound to the record being decided", () => {
    const deciding = mounts.filter((mount) => mount.slice(0, 300).includes("selectedCandidate"));
    expect(deciding).toHaveLength(1);
    expect(deciding[0]).toContain("policySetKey=");
  });

  it("puts the case to the candidate, never to a published version", () => {
    const deciding = mounts.filter((mount) => mount.slice(0, 300).includes("selectedCandidate"))[0];
    // The tester takes an optional target and defaults to the draft. The queue
    // must not aim it anywhere: the record being decided is the one on screen.
    expect(deciding).not.toMatch(/\btarget=/);
    expect(deciding).not.toMatch(/policyVersionId=/);
  });
});
