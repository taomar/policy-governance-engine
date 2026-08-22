import { Fragment, useEffect, useState } from "react";
import { Alert, AutoComplete, Button, Empty, Form, Input, Modal, Select, Tag, Typography } from "antd";
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  PlusOutlined,
  ReloadOutlined,
  RightOutlined,
  SafetyCertificateOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import {
  api,
  PolicyPlatformApiError,
  type PolicySet,
  type ProjectPortfolioInsight,
} from "../api";
import { colorForCategory, POLICY_CATEGORIES } from "../policyCategories";
import { describeApiFailure, UNKNOWN_COUNT, type LoadState } from "../loadState";
import { routeCell } from "../projectRegisterRow";
import { recordScaleLabel, reviewBacklogBadge } from "../policyRecordFacts";
import { groupProjectsByDocument, groupSubtitle } from "../projectRegisterGroups";
import { qualityScopeLabel } from "../qualityTrend";
import { ProjectWorkspace } from "./ProjectWorkspace";
import { useActor } from "../ActorContext";
import { canAuthor } from "../rbac";

const { Title, Text } = Typography;

function projectInitials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function qualityFindingCount(insight: ProjectPortfolioInsight): number {
  return (
    (insight.latest_quality_high ?? 0) +
    (insight.latest_quality_medium ?? 0) +
    (insight.latest_quality_low ?? 0)
  );
}

function projectStatus(
  project: PolicySet,
  insight: ProjectPortfolioInsight,
): { color: string; label: string } {
  if (project.is_review_overdue) return { color: "error", label: "Review overdue" };
  if (insight.active_rule_count === 0) return { color: "default", label: "Not published" };
  if ((insight.latest_quality_high ?? 0) > 0) return { color: "error", label: "Quality action needed" };
  if (insight.review_pending > 0) return { color: "gold", label: "Review in progress" };
  return { color: "green", label: "Operational" };
}

/**
 * Top-level "Projects" page — the entry point for the whole journey. A user starts
 * here: create a project, then open it to add documents, review AI-extracted
 * candidates, and publish policies. Each card shows live counts (documents, published
 * rules, pending review) so the user can tell what needs attention before opening one.
 */
export function ProjectsPage({
  onActiveProjectChange,
  onOpenAskAi,
  openRequest,
}: {
  /** Reports which project (if any) is currently open, so the app can scope Ask AI to it. */
  onActiveProjectChange?: (ps: PolicySet | null) => void;
  onOpenAskAi?: () => void;
  /**
   * A request from elsewhere in the shell (the sider) to open one project.
   * Deliberately an intent rather than a controlled value: selection stays owned
   * by this page, which is the only place that knows whether the project list has
   * loaded yet. The nonce lets the same project be re-opened after the user has
   * navigated back to the list.
   */
  openRequest?: { key: string | null; nonce: number };
}) {
  const { role } = useActor();
  const mayAuthor = canAuthor(role);
  const [policySets, setPolicySets] = useState<PolicySet[]>([]);
  const [stats, setStats] = useState<Record<string, ProjectPortfolioInsight>>({});
  const [selected, setSelected] = useState<PolicySet | null>(null);
  const [loading, setLoading] = useState(false);
  // Whether we have an answer about the project list at all. `policySets` being
  // empty cannot carry this: an empty array means both "there are no projects"
  // and "we never found out", and those must show a reader different things.
  const [listState, setListState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [form] = Form.useForm();

  const refreshList = async () => {
    setLoading(true);
    setError(null);
    try {
      const sets = await api.listPolicySets();
      setPolicySets(sets);
      setListState("ready");
      try {
        const portfolio = await api.getProjectPortfolioSummary();
        setStats(Object.fromEntries(portfolio.map((insight) => [insight.key, insight])));
      } catch (caught) {
        setStats({});
        setError(`Projects loaded, but operational insights are unavailable: ${describeApiFailure(caught)}`);
      }
    } catch (e) {
      // We did not get an answer, so we do not have one. Leaving `policySets`
      // at [] while rendering the "no projects yet" prompt told a reader with
      // nine projects that they had none, and invited them to create a tenth.
      setListState("unavailable");
      setError(describeApiFailure(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refreshList();
  }, []);

  const openProject = (ps: PolicySet) => {
    setSelected(ps);
    onActiveProjectChange?.(ps);
  };

  // Resolves an open request once the list is available, so a request that
  // arrives during the initial load is honoured rather than dropped.
  const requestedKey = openRequest?.key;
  const requestedNonce = openRequest?.nonce;
  useEffect(() => {
    if (requestedKey === undefined) return;
    if (requestedKey === null) {
      setSelected(null);
      onActiveProjectChange?.(null);
      return;
    }
    const match = policySets.find((ps) => ps.key === requestedKey);
    if (match) openProject(match);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedKey, requestedNonce, policySets]);

  const backToList = () => {
    setSelected(null);
    onActiveProjectChange?.(null);
    void refreshList(); // counts may have changed while working inside the project
  };

  const handleProjectUpdated = (updated: PolicySet) => {
    setSelected(updated);
    onActiveProjectChange?.(updated);
    setPolicySets((prev) => prev.map((ps) => (ps.key === updated.key ? updated : ps)));
  };

  const handleCreate = async () => {
    setCreateError(null);
    let values: { key: string; name: string; owner: string; description?: string; category?: string; tags?: string[] };
    try {
      values = await form.validateFields();
    } catch {
      return; // inline field validation errors already shown by the form
    }
    try {
      const created = await api.createPolicySet(values);
      setCreateOpen(false);
      form.resetFields();
      await refreshList();
      openProject(created);
    } catch (e) {
      setCreateError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    }
  };

  if (selected) {
    return (
      <ProjectWorkspace
        policySet={selected}
        onBack={backToList}
        onOpenAskAi={onOpenAskAi}
        onUpdated={handleProjectUpdated}
      />
    );
  }

  const totals = policySets.reduce(
    (acc, ps) => {
      const current = stats[ps.key];
      acc.published += current?.active_rule_count ?? 0;
      acc.regression += current?.regression_test_count ?? 0;
      acc.pending += current?.review_pending ?? 0;
      // The same queue in the unit it is decided in. A policy is what gets
      // reviewed, approved and published; rules are its contents, and one
      // policy commonly holds several -- so the two answer different questions
      // and are joined rather than summed.
      //
      // Absent is not zero. A server that does not serve the policy figure yet
      // leaves the key undefined, and adding 0 for it would silently report a
      // portfolio holding hundreds of rules as holding no policies. One missing
      // figure makes the whole total unknown, and the surface then says what it
      // does have, in rules, and names that unit.
      if (current && typeof current.review_pending_policies !== "number") {
        acc.pendingPoliciesKnown = false;
      }
      acc.pendingPolicies += current?.review_pending_policies ?? 0;
      acc.highFindings += current?.latest_quality_high ?? 0;
      // Route counts, each summed from what the records carry. Neither is
      // derived from the other or from the total -- see `projectRegisterRow`.
      acc.live += current?.live_candidate_count ?? 0;
      acc.direct += current?.candidate_direct_count ?? 0;
      acc.reading += current?.candidate_reading_count ?? 0;
      return acc;
    },
    {
      published: 0,
      regression: 0,
      pending: 0,
      pendingPolicies: 0,
      pendingPoliciesKnown: true,
      highFindings: 0,
      live: 0,
      direct: 0,
      reading: 0,
    },
  );
  const pendingPolicies = totals.pendingPoliciesKnown ? totals.pendingPolicies : null;
  const totalRoutes = routeCell(totals.live, totals.direct, totals.reading);

  return (
    <div className="projects-page">
      <header className="page-header-row projects-page-header">
        <div>
          <Title level={3}>Project register</Title>
          <Text type="secondary">Source documents, review work, and published policy versions by project.</Text>
        </div>
        <div className="projects-page-actions">
          <Text type="secondary">
            {listState === "unavailable" ? `${UNKNOWN_COUNT} projects` : `${policySets.length} projects`}
          </Text>
          {mayAuthor && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              New project
            </Button>
          )}
        </div>
      </header>

      {error && <Alert type="error" showIcon message={error} />}

      {policySets.length > 0 && (
        <dl className="project-register-summary" aria-label="Project portfolio totals">
          <div>
            <dt>Projects</dt>
            <dd>{policySets.length}</dd>
          </div>
          <div>
            <dt>Published rules</dt>
            <dd>{totals.published}</dd>
          </div>
          <div>
            {/* Was `<dt>Deterministic</dt><dd>0</dd>`. A route name sitting bare
                over a numeral, in a row of counters, reads as a score: in this
                company "Deterministic 0" is a nought out of six. How a source
                states its own test is the source's property, not a mark this
                system earns against it, and most policy prose states it in
                words. The wording comes from `routeCell`, the same function the
                dashboard tile and each register row use, so the three cannot
                drift into describing one fact three ways. */}
            <dt>Decision routes</dt>
            <dd>{totalRoutes.headline}</dd>
            <small>{totalRoutes.detail}</small>
          </div>
          <div>
            <dt>Regression guards</dt>
            <dd>{totals.regression}</dd>
          </div>
          <div className={totals.pending > 0 ? "project-register-summary-attention" : undefined}>
            <dt>Awaiting review</dt>
            {/* Policies lead because a policy is what a reviewer decides. The
                rule count stays beside it: it is what a policy is made of, and
                a reviewer sizing the job wants both. When the policy figure has
                not been served the number shown is the rule count and the line
                below says so, rather than badging a nought nobody measured. */}
            <dd>{pendingPolicies ?? totals.pending}</dd>
            <small>{recordScaleLabel(pendingPolicies, totals.pending)}</small>
          </div>
          <div className={totals.highFindings > 0 ? "project-register-summary-risk" : undefined}>
            <dt>High findings</dt>
            <dd>{totals.highFindings}</dd>
          </div>
        </dl>
      )}

      {loading || listState === "loading" ? (
        <div className="project-register-loading">
          <Text type="secondary">Loading project register…</Text>
        </div>
      ) : listState === "unavailable" ? (
        <div className="project-register-empty">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <span className="project-register-empty-copy">
                <Text>Project register unavailable.</Text>
                <Text type="secondary">
                  Your projects have not been loaded, so this list is not showing them. Nothing has been lost — try
                  again once the server responds.
                </Text>
              </span>
            }
          >
            <Button icon={<ReloadOutlined />} onClick={() => void refreshList()}>
              Try again
            </Button>
          </Empty>
        </div>
      ) : policySets.length === 0 ? (
        <div className="project-register-empty">
          <Empty
            description={
              <span className="project-register-empty-copy">
                <Text>No projects yet.</Text>
                <Text type="secondary">
                  {mayAuthor
                    ? "Create one to start uploading policy documents and extracting rules."
                    : "A Policy Author creates projects. Once one exists you will see it here."}
                </Text>
              </span>
            }
          >
            {mayAuthor && (
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
                New project
              </Button>
            )}
          </Empty>
        </div>
      ) : (
        <div className="project-register" role="list" aria-label="Projects">
          <div className="project-register-columns" aria-hidden="true">
            <span>Project</span>
            <span>Published package</span>
            <span>How decided</span>
            <span>Quality</span>
            <span>Validation</span>
            <span>Review</span>
            <span />
          </div>
          {groupProjectsByDocument(
            policySets.map((ps) => ({
              key: ps.key,
              document_content_hash: stats[ps.key]?.document_content_hash ?? null,
              document_title: stats[ps.key]?.document_title ?? null,
              run_count: stats[ps.key]?.run_count ?? null,
              ps,
            })),
          ).map((group) => (
            <Fragment key={group.documentHash ?? "__no_document__"}>
              <div className="project-register-group">
                <FileTextOutlined aria-hidden="true" />
                <strong>{group.label}</strong>
                <small>{groupSubtitle(group)}</small>
              </div>
              {group.projects.map(({ ps }) => {
            const s = stats[ps.key];
            const route = s
              ? routeCell(s.live_candidate_count, s.candidate_direct_count, s.candidate_reading_count)
              : null;
            const health = s ? projectStatus(ps, s) : null;
            return (
              <button key={ps.id} type="button" role="listitem" className="project-register-row" onClick={() => openProject(ps)}>
                <span className="project-register-identity">
                  <span className="project-register-glyph" aria-hidden="true">
                    {projectInitials(ps.name)}
                  </span>
                  <span className="project-register-copy">
                    <span className="project-register-title-line">
                      <strong>{ps.name}</strong>
                      {ps.category && ps.category.trim().toLowerCase() !== ps.name.trim().toLowerCase() && (
                        <Tag variant="filled" color={colorForCategory(ps.category)}>
                          {ps.category}
                        </Tag>
                      )}
                    </span>
                    <span className="project-register-meta">
                      <code>{ps.key}</code>
                      <span>Owned by {ps.owner}</span>
                      {s && <span>{s.document_count} source document{s.document_count === 1 ? "" : "s"}</span>}
                    </span>
                    {ps.description && <span className="project-register-description">{ps.description}</span>}
                  </span>
                </span>
                <span className="project-register-insight" title="Active published policy package">
                  <FileTextOutlined />
                  <span>
                    <strong>{s?.active_version_number ? `v${s.active_version_number} · ${s.active_rule_count} rules` : "Not published"}</strong>
                    <small>{s ? `${s.version_count} version${s.version_count === 1 ? "" : "s"} retained` : "Loading package"}</small>
                  </span>
                </span>
                <span
                  className="project-register-insight"
                  title="Policies whose test the source states as a comparison take the Deterministic route, where the engine computes the answer. The rest take the AI Ready route, where a judge reads the rule against the case."
                >
                  <CheckCircleOutlined />
                  <span>
                    {/* Counts of the live generation, not a share of the published
                        one. This cell used to read "0 of 0" and "0% deterministic"
                        for every project, because it divided published-rule counts
                        that are zero until a version is approved. */}
                    <strong>{route ? route.headline : "—"}</strong>
                    <small>{route ? route.detail : "Loading routes"}</small>
                  </span>
                </span>
                <span className="project-register-insight" title="Latest quality evaluation, on whichever population was checked most recently">
                  <SafetyCertificateOutlined />
                  <span>
                    <strong className={s && (s.latest_quality_high ?? 0) > 0 ? "is-risk" : undefined}>
                      {!s || s.latest_quality_at === null
                        ? "Not evaluated"
                        : `${s.latest_quality_high ?? 0} high · ${qualityFindingCount(s)} total`}
                    </strong>
                    <small>
                      {s?.latest_quality_at
                        ? `${qualityScopeLabel(s.latest_quality_scope)}${
                            s.latest_quality_rule_count ? `, ${s.latest_quality_rule_count} checked` : ""
                          } · ${new Date(s.latest_quality_at).toLocaleDateString()}`
                        : "Run Quality to establish a baseline"}
                    </small>
                  </span>
                </span>
                <span className="project-register-insight" title="Saved validation evidence and active regression guards">
                  <ExperimentOutlined />
                  <span>
                    <strong>{s ? `${s.regression_test_count} guard${s.regression_test_count === 1 ? "" : "s"}` : "—"}</strong>
                    <small>{s ? `${s.test_count} validation scenario${s.test_count === 1 ? "" : "s"}` : "Loading validation"}</small>
                  </span>
                </span>
                <span
                  className="project-register-review"
                  title={reviewBacklogBadge(s?.review_pending, s?.review_pending_policies).hint}
                >
                  <span className={s && s.review_pending > 0 ? "is-attention" : undefined}>
                    <ClockCircleOutlined />
                    <strong>
                      {s
                        ? `${recordScaleLabel(s.review_pending_policies ?? null, s.review_pending)} awaiting`
                        : "— awaiting"}
                    </strong>
                  </span>
                  {health && (
                    <Tag color={health.color} icon={ps.is_review_overdue ? <WarningOutlined /> : undefined}>
                      {health.label}
                    </Tag>
                  )}
                </span>
                <RightOutlined className="project-register-open" aria-hidden="true" />
              </button>
            );
              })}
            </Fragment>
          ))}
        </div>
      )}

      <Modal
        title="New Project"
        open={createOpen}
        onCancel={() => {
          setCreateOpen(false);
          setCreateError(null);
          form.resetFields();
        }}
        onOk={handleCreate}
        okText="Create Project"
        destroyOnHidden
      >
        {createError && <Alert type="error" showIcon message={createError} style={{ marginBottom: 12 }} />}
        <Form layout="vertical" form={form}>
          <Form.Item label="Key" name="key" rules={[{ required: true, message: "Enter a unique key" }]}>
            <Input placeholder="expense-policy" />
          </Form.Item>
          <Form.Item label="Name" name="name" rules={[{ required: true, message: "Enter a name" }]}>
            <Input placeholder="Expense Approval Policy" />
          </Form.Item>
          <Form.Item label="Owner" name="owner" rules={[{ required: true, message: "Enter an owner" }]}>
            <Input placeholder="finance-team" />
          </Form.Item>
          <Form.Item
            label="Category"
            name="category"
            tooltip="Business domain this project belongs to — pick a suggestion or type your own."
          >
            <AutoComplete
              options={POLICY_CATEGORIES.map((c) => ({ value: c }))}
              placeholder="HR, Finance, IT…"
              filterOption={(input, option) => (option?.value ?? "").toLowerCase().includes(input.toLowerCase())}
            />
          </Form.Item>
          <Form.Item label="Tags" name="tags" tooltip="Free-form labels for filtering across projects.">
            <Select mode="tags" placeholder="leave, onboarding, q3-2025…" tokenSeparators={[","]} />
          </Form.Item>
          <Form.Item label="Description" name="description">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
