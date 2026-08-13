import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { CanonicalRule } from "./api";
import {
  AMBIGUITY_NOTE,
  AMBIGUITY_UNNAMED,
  UNKNOWN_AMBIGUITY_NOTE,
  ambiguityNote,
} from "./ambiguityNote";
import { AmbiguityNoteView } from "./components/AmbiguityNoteView";
import { DecisionReadinessView } from "./components/DecisionReadinessView";
import { PolicyInspector } from "./components/PolicyInspector";

/**
 * What the source's wording admits reaches a reviewer, in words, on the record.
 *
 * Which statuses exist is checked from the other side of the boundary by
 * `tests/unit/test_ambiguity_note_wording.py`, which reads the members off
 * `AmbiguityStatus` and fails when one has no entry here. That direction cannot
 * run from this side: the enum is Python.
 *
 * What is checked here is everything true whatever the set is — that entries are
 * sentences rather than placeholders, that a status nobody has heard of still
 * produces something readable, that no reader is shown an internal identifier,
 * and, the one that actually failed before, that the note is mounted where a
 * reviewer decides. The status was already stored on every record and already
 * reached the DOM: as a glyph whose hover text was the enum member with the
 * underscores taken out. A reviewer who did not hover, or who arrived by
 * keyboard, approved the record without being told.
 */

const KNOWN_STATUSES = Object.keys(AMBIGUITY_NOTE);

/**
 * What the mapping held when this was written.
 *
 * A floor, not an equality. Adding a status is ordinary and the Python guard
 * already insists a new one gets wording; losing the lot is not ordinary, and
 * every loop below over `KNOWN_STATUSES` would pass by running zero times.
 */
const STATUSES_AT_WRITING = 4;

/** A status no build has wording for. Deliberately shaped like a real one. */
const UNSEEN_STATUS = "reads_more_than_one_way_pending_counsel";

function ruleWith(ambiguity_status: string): CanonicalRule {
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
    condition_provenance: null,
    effect: { type: "allow", action: "grant" },
    required_facts: [],
    exceptions: [],
    priority: 0,
    effective_from: "2024-01-01",
    effective_to: null,
    machine_executable: false,
    ambiguity_status,
    review_status: "candidate",
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
    decision_readiness: {
      evaluability: "decidable",
      required_attributes: [{ phrase: "the employee", role: "subject" }],
      parties: [],
    },
  } as unknown as CanonicalRule;
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

describe("ambiguity wording", () => {
  it("has a status to check in the first place", () => {
    // A mapping that emptied out would let every test below pass by iterating
    // nothing, which is the failure mode of a guard rather than of a feature.
    expect(KNOWN_STATUSES.length).toBeGreaterThanOrEqual(STATUSES_AT_WRITING);
  });

  it("says something for every status it knows, and never the status itself", () => {
    let checked = 0;
    for (const status of KNOWN_STATUSES) {
      const entry = AMBIGUITY_NOTE[status];
      expect(entry.label.length, status).toBeGreaterThan(0);
      // Long enough to be a sentence about the source rather than a restated
      // identifier. The Python guard checks the vocabulary; this checks there
      // is something there to check.
      expect(entry.reason.length, status).toBeGreaterThan(40);
      expect(entry.label, status).not.toContain(status);
      expect(entry.reason, status).not.toContain(status);
      checked += 1;
    }
    // The loop must have run. An emptied mapping makes every expect above
    // vacuously true by never reaching one.
    expect(checked).toBe(KNOWN_STATUSES.length);
    expect(checked).toBeGreaterThanOrEqual(STATUSES_AT_WRITING);
  });

  it("falls back for a status it has never seen, rather than guessing", () => {
    expect(ambiguityNote(UNSEEN_STATUS)).toBe(UNKNOWN_AMBIGUITY_NOTE);
    expect(ambiguityNote(null)).toBe(UNKNOWN_AMBIGUITY_NOTE);
    expect(ambiguityNote(undefined)).toBe(UNKNOWN_AMBIGUITY_NOTE);
    // Positive control: a known status must NOT take the fallback, or the
    // assertions above would hold for a lookup that always fell back.
    expect(ambiguityNote(KNOWN_STATUSES[0])).not.toBe(UNKNOWN_AMBIGUITY_NOTE);
  });
});

describe("what a reviewer is shown", () => {
  it("states what the source's wording admits, for every status", () => {
    let rendered = 0;
    for (const status of KNOWN_STATUSES) {
      const view = render(<AmbiguityNoteView status={status} variant="section" />);
      // The sentence itself, not a tag or a colour.
      expect(screen.getByText(AMBIGUITY_NOTE[status].reason), status).toBeTruthy();
      rendered += 1;
      view.unmount();
    }
    expect(rendered).toBe(KNOWN_STATUSES.length);
    expect(rendered).toBeGreaterThanOrEqual(STATUSES_AT_WRITING);
  });

  it("admits it does not know WHICH words read more than one way", () => {
    // The record stores a status and no field naming the open phrase. Saying so
    // is the difference between reporting what the system knows and implying it
    // knows more. Shown for a plain status and for an unknown one alike.
    render(<AmbiguityNoteView status="human_judgment_required" variant="section" />);
    expect(screen.getByText(AMBIGUITY_UNNAMED)).toBeTruthy();
    cleanup();

    render(<AmbiguityNoteView status={UNSEEN_STATUS} variant="section" />);
    expect(screen.getByText(AMBIGUITY_UNNAMED)).toBeTruthy();
  });

  it("shows an unknown status as a stored identifier, never as a sentence", () => {
    render(<AmbiguityNoteView status={UNSEEN_STATUS} variant="section" />);

    // It says something readable...
    expect(screen.getByText(UNKNOWN_AMBIGUITY_NOTE.reason)).toBeTruthy();
    // ...and it does show the stored value, because that is the one thing that
    // lets a reviewer report what they saw...
    const raw = screen.getByText(UNSEEN_STATUS);
    expect(raw).toBeTruthy();
    // ...but labelled as a stored value, in a <code>, so it is never mistaken
    // for wording written for them.
    expect(raw.tagName.toLowerCase()).toBe("code");
    // Exact match: a loose regex here also matches the wrapping element and
    // fails on "multiple elements found", which looks like a defect and is not.
    expect(screen.getByText("Stored value:")).toBeTruthy();
  });

  it("never leaves a reviewer with nothing when the status is absent", () => {
    // Absent is a state a reviewer must be able to tell apart from "reads one
    // way". Rendering nothing would make the two identical on screen.
    render(<AmbiguityNoteView status={null} variant="section" />);
    expect(screen.getByText(UNKNOWN_AMBIGUITY_NOTE.reason)).toBeTruthy();
    expect(screen.getByText("(nothing recorded)")).toBeTruthy();
  });
});

describe("where the note is mounted", () => {
  it("interrupts beside the review actions when the source reads more than one way", () => {
    const rule = ruleWith("human_judgment_required");
    render(
      <PolicyInspector
        rule={rule}
        activeTabKey="overview"
        onTabChange={() => {}}
        additionalActions={<button type="button">Approve</button>}
      />
    );

    // Positive control: the panel mounted at all. Without this, a failure to
    // render the whole inspector is indistinguishable from a missing note.
    expect(screen.getByText("Rule under test")).toBeTruthy();
    expect(screen.getByText("Approve")).toBeTruthy();

    // The claim: the reason is on screen as text, next to the review action,
    // with nobody hovering anything.
    expect(screen.getByText(AMBIGUITY_NOTE.human_judgment_required.reason)).toBeTruthy();
  });

  it("does not interrupt when the source's wording reads one way", () => {
    const rule = ruleWith("none");
    render(
      <PolicyInspector
        rule={rule}
        activeTabKey="overview"
        onTabChange={() => {}}
        additionalActions={<button type="button">Approve</button>}
      />
    );

    // Positive control: same mount, so an empty query below means the banner is
    // absent rather than the inspector being.
    expect(screen.getByText("Rule under test")).toBeTruthy();
    expect(screen.queryByText(AMBIGUITY_NOTE.none.reason)).toBeNull();
  });

  it("still states the plain case on the readiness tab, so the field is never invisible", () => {
    // The banner is suppressed for "none" to keep it meaningful. That must not
    // mean a reviewer cannot find out: the tab carries every status.
    render(<DecisionReadinessView rule={ruleWith("none")} />);

    // Positive control: the tab rendered its own content.
    expect(screen.getByText("Attributes the evaluator must find")).toBeTruthy();
    expect(screen.getByText(AMBIGUITY_NOTE.none.reason)).toBeTruthy();
  });
});
