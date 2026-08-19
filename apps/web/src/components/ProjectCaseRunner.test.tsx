import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ProjectCaseRunner } from "./ProjectCaseRunner";
import { api, type ApprovedPolicyVersion, type AssembledPolicy, type PolicySet } from "../api";
import { ProjectWorkspace } from "./ProjectWorkspace";

vi.mock("./ProjectOverviewTab", () => ({ ProjectOverviewTab: () => <div>Overview tab</div> }));
vi.mock("./DocumentsPage", () => ({ DocumentsPage: () => <div>Documents tab</div> }));
vi.mock("./PoliciesTab", () => ({ PoliciesTab: () => <div>Policies tab</div> }));
vi.mock("./ReviewQueue", () => ({ ReviewQueue: () => <div>Review tab</div> }));
vi.mock("./ComparePage", () => ({ ComparePage: () => <div>Compare tab</div> }));
vi.mock("./QualityPage", () => ({ QualityPage: () => <div>Quality tab</div> }));
vi.mock("./CorrelationPage", () => ({ CorrelationPage: () => <div>Correlation tab</div> }));
vi.mock("./PolicyValidationLab", () => ({ PolicyValidationLab: () => <div>Validation tab</div> }));
vi.mock("./PolicyExceptionsPage", () => ({ PolicyExceptionsPage: () => <div>Exceptions tab</div> }));
vi.mock("./PolicyAttestationsPage", () => ({ PolicyAttestationsPage: () => <div>Attestations tab</div> }));
vi.mock("./DecisionLogPage", () => ({ DecisionLogPage: () => <div>Decision tab</div> }));

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
  vi.restoreAllMocks();
});

function policySet(): PolicySet {
  return {
    id: "set-id",
    key: "a-set",
    name: "A project",
    owner: "owner",
    description: "",
    category: "",
    tags: [],
    review_due_date: null,
    last_reviewed_at: null,
    is_review_overdue: false,
    accountable_owner: "",
    delegate_approver: "",
    escalation_contact: "",
    consulted_parties: [],
    informed_parties: [],
  };
}

function activeVersion(): ApprovedPolicyVersion {
  return {
    id: "version-id",
    policy_set_id: "set-id",
    version_number: 1,
    effective_from: "2026-01-01",
    effective_to: null,
    is_active: true,
    approved_by: "approver",
    approved_at: "2026-01-01T00:00:00Z",
    rule_count: 2,
  };
}

function assembledPolicy(key: string, provisionId: string): AssembledPolicy {
  return {
    key,
    heading: `Heading ${key}`,
    heading_path: ["Published", `Heading ${key}`],
    topic_label: null,
    persisted: true,
    provision_id: provisionId,
    document_version_id: "doc-version",
    source_elements: "",
    page: 1,
    rule_count: 1,
    passage_count: 1,
    route: "ai_ready",
    passages: [],
    rules: [{ rule_id: `${key}-rule`, title: "Rule title", evaluation_mode: "ai_ready" }],
  };
}

function mockPublishedPolicyList() {
  vi.spyOn(api, "getActiveVersion").mockResolvedValue(activeVersion());
  vi.spyOn(api, "listVersionPolicies").mockResolvedValue([
    assembledPolicy("kept-policy", "provision-kept"),
    assembledPolicy("discarded-policy", "provision-discarded"),
  ]);
}

describe("project-wide case runner", () => {
  it("is reachable from the project strip, not only as an imported component", async () => {
    mockPublishedPolicyList();
    vi.spyOn(api, "getWorkspaceCounts").mockResolvedValue({
      documents: 0,
      review_pending: 0,
      policy_rules: 0,
      versions: 0,
      tests: 0,
      regression_tests: 0,
      exceptions_open: 0,
      correlation_findings: 0,
      decisions: 0,
    });

    render(<ProjectWorkspace policySet={policySet()} />);
    fireEvent.click(screen.getByRole("button", { name: /test a case/i }));

    expect(await screen.findByText(/Put a case to this project's published policies/i)).toBeTruthy();
  });

  it("posts without a provision id for project scope and shows retained and discarded policies", async () => {
    mockPublishedPolicyList();
    const answer = vi.spyOn(api, "answerProjectCase").mockResolvedValue({
      scope: "project",
      policy_set_key: "a-set",
      retrieval: {
        status: "narrowed",
        policies_considered: 2,
        policies_retained: 1,
        policies_discarded: 1,
        policy_budget: 5,
        policy_scan: 40,
      },
      considered: [
        {
          provision_id: "provision-kept",
          provision_key: "kept-policy",
          heading_path: ["Published", "Kept"],
          rules: 1,
          retained: true,
          best_rank: 1,
          best_score: 0.82,
          matched_clauses: 2,
        },
        {
          provision_id: "provision-discarded",
          provision_key: "discarded-policy",
          heading_path: ["Published", "Discarded"],
          rules: 1,
          retained: false,
          best_rank: 6,
          best_score: 0.31,
          matched_clauses: 1,
          discard_reason: "outside_budget",
        },
      ],
      excluded: [],
      evaluation: {
        intent: "informational",
        informational: {
          status: "answered",
          answer: "A composed answer. [rule-kept]",
          citations: [
            {
              rule_id: "rule-kept",
              policy: { provision_key: "kept-policy", heading_path: ["Published", "Kept"] },
              source: { state: "quoted", text: "The document's own working-hours words.", page: 11, section: "7.8. WORKING HOURS" },
            },
          ],
          grounding: { rules_available: 2, rules_cited: 1, policies_grounded: 1, fabricated_citations: [] },
        },
      },
      size: { combined_chars: 1000, budget_chars: 200000, oversize: false },
    });

    render(<ProjectCaseRunner policySetKey="a-set" open onClose={() => {}} />);
    fireEvent.change(screen.getByTestId("project-case-scenario"), { target: { value: "What applies?" } });
    fireEvent.click(screen.getByTestId("project-case-run"));

    await waitFor(() => expect(answer).toHaveBeenCalled());
    expect(answer.mock.calls[0][1]).not.toHaveProperty("provision_id");
    expect(await screen.findByTestId("project-case-status-narrowed")).toBeTruthy();
    expect(screen.getByText("Retained")).toBeTruthy();
    expect(screen.getByText("Discarded")).toBeTruthy();
    expect(screen.getByText("Outside Budget")).toBeTruthy();
    expect(screen.getByText("A composed answer. [rule-kept]")).toBeTruthy();
    expect(screen.getAllByText("Published › Kept").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/document's own working-hours words/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/No refused citations were reported/i)).toBeTruthy();
    expect(screen.getByText("Show raw response")).toBeTruthy();
  });

  it("posts a provision id for single-policy scope and states retrieval was bypassed", async () => {
    mockPublishedPolicyList();
    const answer = vi.spyOn(api, "answerProjectCase").mockResolvedValue({
      scope: "single",
      policy_set_key: "a-set",
      provision: {
        provision_id: "provision-kept",
        provision_key: "kept-policy",
        heading_path: ["Published", "Kept"],
        rules: 1,
      },
      retrieval: { status: "bypassed", reason: "single policy chosen" },
      evaluation: {
        intent: "decision",
        informational: null,
        decision: {
          status: "not_settled_by_rules",
          verdict: "",
          answer: "The retained rules bear on the case but do not decide it. [rule-kept]",
          missing_required_facts: [],
          citations: [
            {
              rule_id: "rule-kept",
              policy: { provision_key: "kept-policy", heading_path: ["Published", "Kept"] },
              source: { state: "quoted", text: "A quoted sentence from the retained policy.", page: 2, section: "A section" },
            },
          ],
          grounding: { rules_available: 1, rules_cited: 1, policies_grounded: 1, fabricated_citations: [] },
        },
      },
      size: { combined_chars: 500, budget_chars: 200000, oversize: false },
    });

    render(<ProjectCaseRunner policySetKey="a-set" open onClose={() => {}} />);
    fireEvent.click(screen.getByLabelText(/One published policy/i));
    fireEvent.change(screen.getByTestId("project-case-scenario"), { target: { value: "May this happen?" } });
    await waitFor(() => expect(screen.getByText(/Published › Heading kept-policy/i)).toBeTruthy());
    fireEvent.click(screen.getByTestId("project-case-run"));

    await waitFor(() => expect(answer).toHaveBeenCalled());
    expect(answer.mock.calls[0][1]).toMatchObject({ provision_id: "provision-kept" });
    expect(await screen.findByTestId("project-case-status-bypassed")).toBeTruthy();
    expect(screen.getByText("Not settled by rules")).toBeTruthy();
    expect(screen.queryByTestId("project-case-verdict")).toBeNull();
    expect(screen.getByText("The retained rules bear on the case but do not decide it. [rule-kept]")).toBeTruthy();
    expect(screen.getAllByText(/quoted sentence from the retained policy/i).length).toBeGreaterThan(0);
  });

  it("shows an answered decision verdict, missing facts, and refused citations without making raw JSON primary", async () => {
    mockPublishedPolicyList();
    vi.spyOn(api, "answerProjectCase").mockResolvedValue({
      scope: "project",
      policy_set_key: "a-set",
      retrieval: { status: "narrowed", policies_considered: 1, policies_retained: 1, policies_discarded: 0 },
      considered: [
        {
          provision_id: "provision-kept",
          provision_key: "kept-policy",
          heading_path: ["Published", "Kept"],
          rules: 1,
          retained: true,
        },
      ],
      excluded: [],
      evaluation: {
        intent: "decision",
        decision: {
          status: "answered",
          verdict: "not compliant",
          answer: "The retained rule prohibits the case as described. [rule-kept]",
          missing_required_facts: ["employee category"],
          citations: [
            {
              rule_id: "rule-kept",
              policy: { provision_key: "kept-policy", heading_path: ["Published", "Kept"] },
              source: { state: "quoted", text: "Employees must not do that.", page: 4, section: "Conduct" },
            },
          ],
          grounding: {
            rules_available: 1,
            rules_cited: 1,
            policies_grounded: 1,
            fabricated_citations: ["AI-made-up"],
          },
        },
      },
      size: { combined_chars: 100, budget_chars: 200000, oversize: false },
    });

    render(<ProjectCaseRunner policySetKey="a-set" open onClose={() => {}} />);
    fireEvent.change(screen.getByTestId("project-case-scenario"), { target: { value: "Is this allowed?" } });
    fireEvent.click(screen.getByTestId("project-case-run"));

    expect((await screen.findByTestId("project-case-verdict")).textContent).toContain("not compliant");
    expect(screen.getByText("The retained rule prohibits the case as described. [rule-kept]")).toBeTruthy();
    expect(screen.getByTestId("project-case-missing-facts").textContent).toContain("employee category");
    expect(screen.getByText(/fabricated citation was refused/i)).toBeTruthy();
    expect(screen.getByText("Show raw response")).toBeTruthy();
  });

  it("keeps no published version distinct from no match", async () => {
    mockPublishedPolicyList();
    vi.spyOn(api, "answerProjectCase").mockResolvedValue({
      scope: "project",
      policy_set_key: "xx",
      retrieval: { status: "no_published_version" },
      considered: [],
      excluded: [],
      evaluation: null,
      size: { combined_chars: 0, budget_chars: 200000, oversize: false },
    });

    render(<ProjectCaseRunner policySetKey="xx" open onClose={() => {}} />);
    fireEvent.change(screen.getByTestId("project-case-scenario"), { target: { value: "Anything published?" } });
    fireEvent.click(screen.getByTestId("project-case-run"));

    expect(await screen.findByTestId("project-case-status-no_published_version")).toBeTruthy();
    expect(screen.getByText(/has no published policies yet/i)).toBeTruthy();
    expect(screen.queryByText(/none matched this case/i)).toBeNull();
  });

  it("links an unbuilt project index refusal to the Overview repair surface", async () => {
    mockPublishedPolicyList();
    vi.spyOn(api, "getWorkspaceCounts").mockResolvedValue({
      documents: 0,
      review_pending: 0,
      policy_rules: 0,
      versions: 0,
      tests: 0,
      regression_tests: 0,
      exceptions_open: 0,
      correlation_findings: 0,
      decisions: 0,
    });
    vi.spyOn(api, "answerProjectCase").mockResolvedValue({
      scope: "project",
      policy_set_key: "gmu",
      retrieval: {
        status: "index_not_built",
        reason: "Republish or rebuild the policy index.",
        policies_considered: 0,
        policies_retained: 0,
        policies_discarded: 0,
      },
      considered: [],
      excluded: [],
      evaluation: null,
      size: { combined_chars: 0, budget_chars: 200000, oversize: false },
    });

    render(<ProjectWorkspace policySet={{ ...policySet(), key: "gmu" }} />);
    fireEvent.click(screen.getByRole("tab", { name: /Validation/i }));
    expect(await screen.findByText("Validation tab")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /test a case/i }));
    fireEvent.change(await screen.findByTestId("project-case-scenario"), { target: { value: "Can the project answer?" } });
    fireEvent.click(screen.getByTestId("project-case-run"));

    expect(await screen.findByTestId("project-case-status-index_not_built")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /open index repair/i }));

    await waitFor(() => expect(screen.getByText("Overview tab")).toBeTruthy());
  });
});
