import { useState } from "react";
import { Alert, AutoComplete, Button, Form, Input, Modal, Select, Space, Tabs, Tag, Typography } from "antd";
import { ArrowLeftOutlined, EditOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { api, PolicyPlatformApiError, type PolicySet } from "../api";
import { colorForCategory, POLICY_CATEGORIES } from "../policyCategories";
import { ProjectOverviewTab } from "./ProjectOverviewTab";
import { DocumentsPage } from "./DocumentsPage";
import { PoliciesTab } from "./PoliciesTab";
import { ReviewQueue } from "./ReviewQueue";
import { ComparePage } from "./ComparePage";
import { QualityPage } from "./QualityPage";
import { CorrelationPage } from "./CorrelationPage";
import { PolicyTestsPage } from "./PolicyTestsPage";
import { AggregateLimitsPage } from "./AggregateLimitsPage";

const { Title, Text, Paragraph } = Typography;

type WorkspaceTabKey =
  | "overview"
  | "documents"
  | "policies"
  | "limits"
  | "review"
  | "compare"
  | "quality"
  | "correlation"
  | "tests";

const TAB_KEYS: WorkspaceTabKey[] = [
  "overview",
  "documents",
  "policies",
  "limits",
  "review",
  "compare",
  "quality",
  "correlation",
  "tests",
];

/**
 * The single home for working on one project end to end: bring files in, see them
 * categorized into policies, draft/approve/publish rules, and check quality — all
 * scoped to this project so nothing the user does here can leak into another one.
 * Every embedded tab shares the same `policySetKey` scope and can hop to any other
 * tab via `onNavigate`, e.g. "extracted 4 candidates → jump to Review" or "no
 * policies yet → jump to Documents".
 */
export function ProjectWorkspace({
  policySet,
  onBack,
  onOpenAskAi,
  onUpdated,
}: {
  policySet: PolicySet;
  onBack: () => void;
  /** Opens the app-level Ask AI drawer, pre-scoped to this project. Omitted when AI is disabled. */
  onOpenAskAi?: () => void;
  /** Reports a successful metadata edit so the parent (ProjectsPage) can refresh its list/selection. */
  onUpdated?: (ps: PolicySet) => void;
}) {
  const [activeTab, setActiveTab] = useState<WorkspaceTabKey>("overview");
  const [editOpen, setEditOpen] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [editSaving, setEditSaving] = useState(false);
  const [form] = Form.useForm();

  const handleNavigate = (page: string) => {
    if ((TAB_KEYS as string[]).includes(page)) setActiveTab(page as WorkspaceTabKey);
  };

  const openEdit = () => {
    setEditError(null);
    form.setFieldsValue({
      name: policySet.name,
      description: policySet.description,
      category: policySet.category,
      tags: policySet.tags,
    });
    setEditOpen(true);
  };

  const handleSaveEdit = async () => {
    setEditError(null);
    let values: { name: string; description?: string; category?: string; tags?: string[] };
    try {
      values = await form.validateFields();
    } catch {
      return; // inline field validation errors already shown by the form
    }
    setEditSaving(true);
    try {
      const updated = await api.updatePolicySet(policySet.key, values);
      setEditOpen(false);
      onUpdated?.(updated);
    } catch (e) {
      setEditError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setEditSaving(false);
    }
  };

  return (
    <>
      <Button icon={<ArrowLeftOutlined />} onClick={onBack} className="back-btn">
        Back to Projects
      </Button>

      <div className="page-header-row">
        <div>
          <Space size={8} align="center" wrap>
            <Title level={3} style={{ marginBottom: 4 }}>
              {policySet.name}
            </Title>
            {policySet.category && (
              <Tag color={colorForCategory(policySet.category)} style={{ marginBottom: 4 }}>
                {policySet.category}
              </Tag>
            )}
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={openEdit}
              style={{ marginBottom: 4 }}
              aria-label="Edit project details"
            >
              Edit
            </Button>
          </Space>
          <br />
          <Space size={10} wrap>
            <Text type="secondary" className="entity-id-row" copyable={{ text: policySet.key }}>
              {policySet.key}
            </Text>
            <Text type="secondary">owner: {policySet.owner}</Text>
            {policySet.tags.length > 0 && (
              <Space size={4} wrap>
                {policySet.tags.map((t) => (
                  <Tag key={t} bordered={false} className="fact-tag">
                    {t}
                  </Tag>
                ))}
              </Space>
            )}
          </Space>
        </div>
        {onOpenAskAi && (
          <Button type="primary" icon={<ThunderboltOutlined />} onClick={onOpenAskAi}>
            Ask AI about this project
          </Button>
        )}
      </div>
      {policySet.description && <Paragraph type="secondary">{policySet.description}</Paragraph>}

      <Tabs
        className="workspace-tabs"
        activeKey={activeTab}
        onChange={(k) => setActiveTab(k as WorkspaceTabKey)}
        items={[
          {
            key: "overview",
            label: "Overview",
            children: <ProjectOverviewTab policySet={policySet} onNavigate={handleNavigate} />,
          },
          {
            key: "documents",
            label: "Documents",
            children: (
              <DocumentsPage policySetKey={policySet.key} policySetName={policySet.name} onNavigate={handleNavigate} />
            ),
          },
          {
            key: "policies",
            label: "Policies",
            children: <PoliciesTab policySetKey={policySet.key} onNavigate={handleNavigate} />,
          },
          {
            key: "limits",
            label: "Aggregate Limits",
            children: <AggregateLimitsPage policySetKey={policySet.key} />,
          },
          {
            key: "review",
            label: "Review",
            children: <ReviewQueue policySetKey={policySet.key} />,
          },
          {
            key: "compare",
            label: "Compare",
            children: <ComparePage policySetKey={policySet.key} />,
          },
          {
            key: "quality",
            label: "Quality",
            children: <QualityPage policySetKey={policySet.key} />,
          },
          {
            key: "correlation",
            label: "Correlation",
            children: <CorrelationPage policySetKey={policySet.key} />,
          },
          {
            key: "tests",
            label: "Tests",
            children: <PolicyTestsPage policySetKey={policySet.key} />,
          },
        ]}
      />

      <Modal
        title="Edit Project"
        open={editOpen}
        onCancel={() => {
          setEditOpen(false);
          setEditError(null);
        }}
        onOk={handleSaveEdit}
        okText="Save Changes"
        confirmLoading={editSaving}
        destroyOnClose
      >
        {editError && <Alert type="error" showIcon message={editError} style={{ marginBottom: 12 }} />}
        <Form layout="vertical" form={form}>
          <Form.Item label="Name" name="name" rules={[{ required: true, message: "Enter a name" }]}>
            <Input />
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
