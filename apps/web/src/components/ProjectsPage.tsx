import { useEffect, useState } from "react";
import { Alert, AutoComplete, Button, Card, Col, Empty, Form, Input, Modal, Row, Select, Space, Tag, Typography } from "antd";
import { CheckCircleOutlined, ClockCircleOutlined, FileTextOutlined, PlusOutlined, WarningOutlined } from "@ant-design/icons";
import { api, PolicyPlatformApiError, type PolicySet } from "../api";
import { colorForCategory, POLICY_CATEGORIES } from "../policyCategories";
import { ProjectWorkspace } from "./ProjectWorkspace";

const { Title, Text, Paragraph } = Typography;

interface ProjectStats {
  documentCount: number;
  activeRuleCount: number;
  pendingCount: number;
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
}: {
  /** Reports which project (if any) is currently open, so the app can scope Ask AI to it. */
  onActiveProjectChange?: (ps: PolicySet | null) => void;
  onOpenAskAi?: () => void;
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

  return (
    <>
      <div className="page-header-row">
        <div>
          <Title level={3} style={{ margin: 0 }}>
            Projects
          </Title>
          <Text type="secondary">Each project holds its own documents, policies, and version history.</Text>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
          New Project
        </Button>
      </div>

      {error && <Alert type="error" showIcon message={error} />}

      {loading ? (
        <Text type="secondary">Loading…</Text>
      ) : policySets.length === 0 ? (
        <Card>
          <Empty
            description={
              <Space direction="vertical" size={4}>
                <Text>No projects yet.</Text>
                <Text type="secondary">Create one to start uploading policy documents and extracting rules.</Text>
              </Space>
            }
          >
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
              New Project
            </Button>
          </Empty>
        </Card>
      ) : (
        <Row gutter={[16, 16]}>
          {policySets.map((ps) => {
            const s = stats[ps.key];
            return (
              <Col xs={24} sm={12} lg={8} key={ps.id}>
                <Card hoverable onClick={() => openProject(ps)} className="policy-set-card">
                  <div className="policy-set-card-title-row">
                    <Title level={5} style={{ marginBottom: 4 }}>
                      {ps.name}
                    </Title>
                    <Space size={4} wrap style={{ flexShrink: 0 }}>
                      {ps.category && <Tag color={colorForCategory(ps.category)}>{ps.category}</Tag>}
                      {ps.is_review_overdue && (
                        <Tag color="error" icon={<WarningOutlined />}>
                          Review overdue
                        </Tag>
                      )}
                    </Space>
                  </div>
                  <Text
                    type="secondary"
                    className="entity-id-row"
                    onClick={(e) => e.stopPropagation()}
                    copyable={{ text: ps.key }}
                  >
                    {ps.key}
                  </Text>
                  <br />
                  <Text type="secondary">owner: {ps.owner}</Text>
                  {ps.description && <Paragraph className="policy-set-card-desc">{ps.description}</Paragraph>}
                  {ps.tags.length > 0 && (
                    <Space size={4} wrap className="policy-set-card-tags">
                      {ps.tags.map((t) => (
                        <Tag key={t} bordered={false} className="fact-tag">
                          {t}
                        </Tag>
                      ))}
                    </Space>
                  )}
                  <div className="project-card-stats">
                    <span title="Documents uploaded">
                      <FileTextOutlined /> {s?.documentCount ?? "…"}
                    </span>
                    <span title="Published rules (active version)">
                      <CheckCircleOutlined /> {s?.activeRuleCount ?? "…"}
                    </span>
                    <span
                      title="Candidate rules awaiting review"
                      className={s && s.pendingCount > 0 ? "project-card-stat-attn" : ""}
                    >
                      <ClockCircleOutlined /> {s?.pendingCount ?? "…"}
                    </span>
                  </div>
                </Card>
              </Col>
            );
          })}
        </Row>
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
    </>
  );
}
