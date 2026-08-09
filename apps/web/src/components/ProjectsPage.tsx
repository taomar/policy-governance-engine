import { useEffect, useState } from "react";
import { Alert, AutoComplete, Button, Empty, Form, Input, Modal, Select, Tag, Typography } from "antd";
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
  PlusOutlined,
  RightOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { api, PolicyPlatformApiError, type PolicySet } from "../api";
import { colorForCategory, POLICY_CATEGORIES } from "../policyCategories";
import { ProjectWorkspace } from "./ProjectWorkspace";

const { Title, Text } = Typography;

interface ProjectStats {
  documentCount: number;
  activeRuleCount: number;
  pendingCount: number;
}

function projectInitials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
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
  const [policySets, setPolicySets] = useState<PolicySet[]>([]);
  const [stats, setStats] = useState<Record<string, ProjectStats>>({});
  const [selected, setSelected] = useState<PolicySet | null>(null);
  const [loading, setLoading] = useState(false);
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
      const entries = await Promise.all(
        sets.map(async (ps) => {
          try {
            const [documents, versions, candidates] = await Promise.all([
              api.listDocuments(ps.key),
              api.listPolicyVersions(ps.key),
              api.listCandidateRules(ps.key, "candidate"),
            ]);
            const active = versions.find((v) => v.is_active);
            return [
              ps.key,
              {
                documentCount: documents.length,
                activeRuleCount: active?.rule_count ?? 0,
                pendingCount: candidates.length,
              },
            ] as const;
          } catch {
            return [ps.key, { documentCount: 0, activeRuleCount: 0, pendingCount: 0 }] as const;
          }
        })
      );
      setStats(Object.fromEntries(entries));
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
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
      acc.documents += current?.documentCount ?? 0;
      acc.published += current?.activeRuleCount ?? 0;
      acc.pending += current?.pendingCount ?? 0;
      return acc;
    },
    { documents: 0, published: 0, pending: 0 },
  );

  return (
    <div className="projects-page">
      <header className="page-header-row projects-page-header">
        <div>
          <Title level={3}>Project register</Title>
          <Text type="secondary">Source documents, review work, and published policy versions by project.</Text>
        </div>
        <div className="projects-page-actions">
          <Text type="secondary">{policySets.length} projects</Text>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            New project
          </Button>
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
            <dt>Source documents</dt>
            <dd>{totals.documents}</dd>
          </div>
          <div>
            <dt>Published rules</dt>
            <dd>{totals.published}</dd>
          </div>
          <div className={totals.pending > 0 ? "project-register-summary-attention" : undefined}>
            <dt>Awaiting review</dt>
            <dd>{totals.pending}</dd>
          </div>
        </dl>
      )}

      {loading ? (
        <div className="project-register-loading">
          <Text type="secondary">Loading project register…</Text>
        </div>
      ) : policySets.length === 0 ? (
        <div className="project-register-empty">
          <Empty
            description={
              <span className="project-register-empty-copy">
                <Text>No projects yet.</Text>
                <Text type="secondary">Create one to start uploading policy documents and extracting rules.</Text>
              </span>
            }
          >
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              New project
            </Button>
          </Empty>
        </div>
      ) : (
        <div className="project-register" role="list" aria-label="Projects">
          <div className="project-register-columns" aria-hidden="true">
            <span>Project</span>
            <span>Documents</span>
            <span>Published</span>
            <span>Review queue</span>
            <span>Status</span>
            <span />
          </div>
          {policySets.map((ps) => {
            const s = stats[ps.key];
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
                        <Tag bordered={false} color={colorForCategory(ps.category)}>
                          {ps.category}
                        </Tag>
                      )}
                    </span>
                    <span className="project-register-meta">
                      <code>{ps.key}</code>
                      <span>Owned by {ps.owner}</span>
                    </span>
                    {ps.description && <span className="project-register-description">{ps.description}</span>}
                  </span>
                </span>
                <span className="project-register-stat" title="Documents uploaded">
                  <FileTextOutlined />
                  <strong>{s?.documentCount ?? "—"}</strong>
                  <small>Documents</small>
                </span>
                <span className="project-register-stat" title="Published rules in the active version">
                  <CheckCircleOutlined />
                  <strong>{s?.activeRuleCount ?? "—"}</strong>
                  <small>Published</small>
                </span>
                <span
                  className={`project-register-stat${s && s.pendingCount > 0 ? " project-register-stat-attention" : ""}`}
                  title="Candidate rules awaiting review"
                >
                  <ClockCircleOutlined />
                  <strong>{s?.pendingCount ?? "—"}</strong>
                  <small>Awaiting</small>
                </span>
                <span className="project-register-health">
                  {ps.is_review_overdue ? (
                    <Tag color="error" icon={<WarningOutlined />}>
                      Review overdue
                    </Tag>
                  ) : s && s.pendingCount > 0 ? (
                    <Tag color="gold">Review in progress</Tag>
                  ) : (
                    <Tag color="green">No pending review</Tag>
                  )}
                </span>
                <RightOutlined className="project-register-open" aria-hidden="true" />
              </button>
            );
          })}
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
        destroyOnClose
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
