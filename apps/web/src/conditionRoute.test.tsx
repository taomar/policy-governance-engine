import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { CanonicalRule, ConditionProvenance } from "./api";
import { CONDITION_ROUTE, UNKNOWN_CONDITION_ROUTE, conditionRoute } from "./conditionRoute";
import { ConditionRouteNote } from "./components/ConditionRouteNote";
import { PolicyInspector } from "./components/PolicyInspector";

/**
 * The routing reason reaches a reviewer, in words, whatever the code says.
 *
 * Which codes exist is checked from the other side of the boundary, by
 * `tests/unit/test_condition_route_wording.py` — it imports the declared set
 * out of `contracts/policy.py` and fails when one of them has no entry here.
 * That direction cannot be run from this side: the declaration is Python, and
 * reading it from a browser test would mean parsing a language this project
 * has a parser for one directory over.
 *
 * What is checked here is everything that stays true whatever the set is: that
 * the entries are real sentences rather than placeholders, that a code nobody
 * has heard of still produces something a reviewer can read, that no reader is
 * ever shown an internal identifier, and — the one that actually failed before
 * — that the panel is mounted where a reviewer will meet it. Wording that
 * exists and is rendered by nothing is the state this work found the codebase
 * in: two helpers with wording for these codes, styled and unused, and a
 * comment promising a panel that had been deleted.
 */

const KNOWN_CODES = Object.keys(CONDITION_ROUTE);

/** A code no build has wording for. Deliberately shaped like a real one. */
const UNSEEN_CODE = "conditions_deferred_to_a_later_reading";

function provenance(code: string, unsupported_expression = ""): ConditionProvenance {
  return { code, unsupported_expression };
}

/**
 * A record with nothing on it but what the inspector needs to draw.
 *
 * No evidence, so the panel resolves no clauses and no document metadata and
 * the test needs no server. Everything about the routing note is passed in.
 */
function ruleWith(condition_provenance: ConditionProvenance | null): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "set-under-test",
    policy_version_id: "version-under-test",
    rule_id: "rule-under-test",
    rule_revision: 1,
    title: "Rule under test",
    description: "",
    rule_type: "eligibility",
    authority: { level: "policy", owner: "Owner", rank: 1 },
    scope: { jurisdictions: [], organizational_units: [], personas: [], processes: [] },
    condition: { type: "all", all: [] },
    condition_provenance,
    effect: { type: "allow", action: "grant" },
    required_facts: [],
    exceptions: [],
    priority: 0,
    effective_from: "2024-01-01",
    effective_to: null,
    machine_executable: false,
    ambiguity_status: "none",
    review_status: "approved",
    evidence: [],
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
  };
}

beforeEach(() => {
  // antd measures the viewport; jsdom provides neither of these.
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
    }))
  );
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("condition route wording", () => {
  it("has a code to check in the first place", () => {
    // A mapping that emptied out would let every test below pass by iterating
    // nothing, which is the failure mode of a guard rather than of a feature.
    expect(KNOWN_CODES.length).toBeGreaterThan(0);
  });

  it("says something for every code it knows, and never the code itself", () => {
    for (const code of KNOWN_CODES) {
      const entry = CONDITION_ROUTE[code];
      expect(entry.route.length, code).toBeGreaterThan(0);
      // Long enough to be a statement about the source rather than a label
      // repeated in sentence position.
      expect(entry.reason.split(" ").length, code).toBeGreaterThan(10);
      for (const other of KNOWN_CODES) {
        expect(`${entry.route} ${entry.reason}`, code).not.toContain(other);
      }
    }
  });

  it("answers for a code it has never seen, without printing it", () => {
    const route = conditionRoute(provenance(UNSEEN_CODE));

    expect(route).toBe(UNKNOWN_CONDITION_ROUTE);
    expect(route?.reason.length).toBeGreaterThan(0);
    expect(route?.reason).not.toContain(UNSEEN_CODE);
    // No route is claimed. Which of the two an unknown code means is not
    // knowable from the code, and guessing would be the interface inventing a
    // fact about the record.
    expect(route?.route).toBe("");
  });

  it("says nothing about a record that carries no provenance", () => {
    // Hand-authored rules never went through the formulator. An explanation
    // for one would have to be made up.
    expect(conditionRoute(null)).toBeNull();
    expect(conditionRoute(undefined)).toBeNull();
  });
});

describe("ConditionRouteNote", () => {
  it("renders the reason for every code, and shows no identifier", () => {
    for (const code of KNOWN_CODES) {
      const { unmount } = render(<ConditionRouteNote provenance={provenance(code)} />);
      expect(screen.getByText(CONDITION_ROUTE[code].reason)).toBeTruthy();
      expect(document.body.textContent).not.toContain(code);
      unmount();
    }
  });

  it("still tells a reviewer a reason exists when it cannot name it", () => {
    render(<ConditionRouteNote provenance={provenance(UNSEEN_CODE)} />);

    // The failure being guarded against is silence: an unrecognised code that
    // rendered nothing would leave the reviewer unable to tell the record was
    // routed for a reason at all.
    expect(screen.getByText(UNKNOWN_CONDITION_ROUTE.reason)).toBeTruthy();
    expect(document.body.textContent).not.toContain(UNSEEN_CODE);
  });

  it("shows the extracted expression when there is one, and nothing when there is not", () => {
    const expression = "amount <= 0.1 * salary";
    const { unmount } = render(
      <ConditionRouteNote provenance={provenance(KNOWN_CODES[0], expression)} />
    );
    expect(screen.getByText(expression)).toBeTruthy();
    unmount();

    render(<ConditionRouteNote provenance={provenance(KNOWN_CODES[0])} />);
    // Keyed on content, so the common case carries no empty block.
    expect(document.querySelector(".condition-route-expression")).toBeNull();
  });

  it("says nothing at all for a record with no provenance", () => {
    const { container } = render(<ConditionRouteNote provenance={null} />);
    expect(container.textContent).toBe("");
  });
});

describe("the record detail view", () => {
  it("shows the routing reason beside the condition it explains", () => {
    // The point of the whole exercise. Wording nothing renders is what the
    // codebase already had.
    const code = "no_scope_derived" in CONDITION_ROUTE ? "no_scope_derived" : KNOWN_CODES[0];
    render(
      <PolicyInspector
        rule={ruleWith(provenance(code))}
        activeTabKey="logic"
        onTabChange={() => {}}
      />
    );

    expect(screen.getByText(CONDITION_ROUTE[code].reason)).toBeTruthy();
  });

  it("leaves the panel alone for a record that carries no provenance", () => {
    render(
      <PolicyInspector rule={ruleWith(null)} activeTabKey="logic" onTabChange={() => {}} />
    );

    expect(document.querySelector(".condition-route")).toBeNull();
  });
});
