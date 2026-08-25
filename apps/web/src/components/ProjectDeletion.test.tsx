import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ActorProvider } from "../ActorContext";
import { api, aiApi, type DeletePolicySetResponse, type PolicySet, type WorkspaceCounts } from "../api";
import type { Role } from "../rbac";
import { ProjectOverviewTab } from "./ProjectOverviewTab";

vi.mock("./ActivityPanel", () => ({ ActivityPanel: () => <div>Activity panel</div> }));
vi.mock("./NotesPanel", () => ({ NotesPanel: () => <div>Notes panel</div> }));
vi.mock("./PolicySetSummaryPanel", () => ({ PolicySetSummaryPanel: () => <div>Summary panel</div> }));
vi.mock("./ExtractionProgressPanel", () => ({ default: () => <div>Extraction progress</div> }));

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

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  vi.spyOn(api, "listDocuments").mockResolvedValue([]);
  vi.spyOn(api, "listPolicyVersions").mockResolvedValue([]);
  vi.spyOn(api, "listCandidateRules").mockResolvedValue([]);
  vi.spyOn(api, "getVersionRules").mockResolvedValue([]);
  vi.spyOn(api, "getPolicyIndexState").mockResolvedValue({
    policy_set_key: "scratch-delete",
    index_name: "policy-scratch-delete",
    last_attempt: "never_attempted",
    freshness: "unknown",
    active_version_number: null,
    indexed_version_number: null,
    attempted_version_number: null,
    document_count: 0,
    built_at: null,
    attempted_at: null,
    error: null,
    source: "recorded_build_state",
    live_probe: false,
  });
  vi.spyOn(aiApi, "getQualityHistory").mockResolvedValue({ runs: [], count: 0, truncated: false });
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  sessionStorage.clear();
  vi.restoreAllMocks();
});

function signInAs(role: Role): void {
  sessionStorage.setItem(
    "policy-platform.session",
    JSON.stringify({
      accessToken: "test-token",
      expiresAt: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
      role,
      name: role,
    }),
  );
}

function policySet(): PolicySet {
  return {
    id: "set-id",
    key: "scratch-delete",
    name: "Scratch delete",
    owner: "ops",
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

function counts(): WorkspaceCounts {
  return {
    documents: 1,
    review_pending: 0,
    review_pending_policies: 0,
    policy_rules: 280,
    published_policies: 38,
    versions: 1,
    tests: 0,
    regression_tests: 0,
    exceptions_open: 0,
    correlation_findings: 0,
    decisions: 0,
  };
}

function renderOverview(role: Role) {
  signInAs(role);
  render(
    <ActorProvider>
      <ProjectOverviewTab
        policySet={policySet()}
        onNavigate={() => undefined}
        counts={counts()}
      />
    </ActorProvider>,
  );
}

describe("project deletion", () => {
  it("does not offer the delete affordance to a non-admin", () => {
    renderOverview("policy_author");
    expect(screen.queryByRole("button", { name: /delete project/i })).toBeNull();
  });

  it("requires the typed confirmation to exactly match the project key", async () => {
    renderOverview("admin");
    const deletePolicySet = vi.spyOn(api, "deletePolicySet").mockRejectedValue(new Error("should not be called"));

    fireEvent.click(screen.getByRole("button", { name: /delete project/i }));
    fireEvent.change(screen.getByLabelText(/project key confirmation/i), { target: { value: "scratch-delete " } });
    fireEvent.click(screen.getAllByRole("button", { name: /delete project/i }).at(-1)!);

    await screen.findByText("Confirmation must exactly match scratch-delete.");
    expect(deletePolicySet).not.toHaveBeenCalled();
  });

  it("surfaces an orphaned search-index outcome from the delete response", async () => {
    renderOverview("admin");
    const outcome: DeletePolicySetResponse = {
      key: "scratch-delete",
      name: "Scratch delete",
      rows_deleted: { policy_sets: 1 },
      total_rows_deleted: 322,
      search_index: "orphaned",
      search_documents_identified: 7,
      search_documents_deleted: null,
      search_index_error: "Azure Search was unavailable",
      policy_index: "clean",
      policy_index_name: "policy-scratch-delete",
      policy_index_deleted: true,
      policy_index_error: null,
      retained: {},
    };
    const deletePolicySet = vi.spyOn(api, "deletePolicySet").mockResolvedValue(outcome);

    fireEvent.click(screen.getByRole("button", { name: /delete project/i }));
    expect(screen.getAllByText(/38 published policies and 280 live rules/i).length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText(/project key confirmation/i), { target: { value: "scratch-delete" } });
    fireEvent.click(screen.getAllByRole("button", { name: /delete project/i }).at(-1)!);

    await screen.findByText(/search index cleanup was orphaned/i);
    expect(screen.getByText("orphaned")).toBeTruthy();
    expect(screen.getByText("Azure Search was unavailable")).toBeTruthy();
    await waitFor(() => {
      expect(deletePolicySet).toHaveBeenCalledWith("scratch-delete", "admin", "scratch-delete");
    });
  });
});
