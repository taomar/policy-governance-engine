import { useState } from "react";
import {
  Alert,
  AutoComplete,
  Button,
  DatePicker,
  Divider,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { ArrowLeftOutlined, CheckCircleOutlined, EditOutlined, ThunderboltOutlined, WarningOutlined } from "@ant-design/icons";
import dayjs, { type Dayjs } from "dayjs";
import { api, PolicyPlatformApiError, type PolicySet, type UpdatePolicySetRequest } from "../api";
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
import { PolicyExceptionsPage } from "./PolicyExceptionsPage";
import { PolicyAttestationsPage } from "./PolicyAttestationsPage";
import { DecisionLogPage } from "./DecisionLogPage";

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
  | "tests"
  | "exceptions"
  | "attestations"
  | "decision-log";

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
  "exceptions",
  "attestations",
  "decision-log",
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

  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [reviewSaving, setReviewSaving] = useState(false);
  const [reviewForm] = Form.useForm();

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
      review_due_date: policySet.review_due_date ? dayjs(policySet.review_due_date) : undefined,
      accountable_owner: policySet.accountable_owner,
      delegate_approver: policySet.delegate_approver,
      escalation_contact: policySet.escalation_contact,
      consulted_parties: policySet.consulted_parties,
      informed_parties: policySet.informed_parties,
    });
    setEditOpen(true);
  };

  const handleSaveEdit = async () => {
    setEditError(null);
    let raw: {
      name: string;
      description?: string;
      category?: string;
      tags?: string[];
      review_due_date?: Dayjs | null;
      accountable_owner?: string;
      delegate_approver?: string;
      escalation_contact?: string;
      consulted_parties?: string[];
      informed_parties?: string[];
    };
    try {
      raw = await form.validateFields();
    } catch {
      return; // inline field validation errors already shown by the form
    }
    setEditSaving(true);
    try {
      const { review_due_date, ...rest } = raw;
      const body: UpdatePolicySetRequest = { ...rest };
      if (review_due_date) {
        body.review_due_date = review_due_date.format("YYYY-MM-DD");
      } else if (policySet.review_due_date) {
        // field was cleared by the user — distinguish "not provided" from "explicitly cleared"
        body.clear_review_due_date = true;
      }
      const updated = await api.updatePolicySet(policySet.key, body);
      setEditOpen(false);
      onUpdated?.(updated);
    } catch (e) {
      setEditError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setEditSaving(false);
    }
  };

  const openReview = () => {
    setReviewError(null);
    reviewForm.setFieldsValue({ next_due_date: undefined });
    setReviewOpen(true);
  };

  const handleMarkReviewed = async () => {
    setReviewError(null);
    let values: { next_due_date?: Dayjs | null };
    try {
      values = await reviewForm.validateFields();
    } catch {
      return;
    }
    setReviewSaving(true);
    try {
      const updated = await api.markPolicySetReviewed(policySet.key, {
        next_due_date: values.next_due_date ? values.next_due_date.format("YYYY-MM-DD") : null,
      });
      setReviewOpen(false);
      onUpdated?.(updated);
    } catch (e) {
      setReviewError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setReviewSaving(false);
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
            {policySet.review_due_date && (
              <Tag
                color={policySet.is_review_overdue ? "error" : "default"}
                icon={policySet.is_review_overdue ? <WarningOutlined /> : <CheckCircleOutlined />}
                style={{ marginBottom: 4 }}
              >
                {policySet.is_review_overdue ? "Review overdue · due " : "Review due "}
                {dayjs(policySet.review_due_date).format("MMM D, YYYY")}
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
            <Button type="text" size="small" onClick={openReview} style={{ marginBottom: 4 }}>
              Mark Reviewed
            </Button>
          </Space>
          <br />
          <Space size={10} wrap>
            <Text type="secondary" className="entity-id-row" copyable={{ text: policySet.key }}>
              {policySet.key}
            </Text>
            <Text type="secondary">owner: {policySet.owner}</Text>
            {policySet.last_reviewed_at && (
              <Text type="secondary">last reviewed: {dayjs(policySet.last_reviewed_at).format("MMM D, YYYY")}</Text>
            )}
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
            children: <ProjectOverviewTab policySet={policySet} onNavigate={handleNavigate} onEditProject={openEdit} />,
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
          {
            key: "exceptions",
            label: "Exceptions",
            children: <PolicyExceptionsPage policySetKey={policySet.key} />,
          },
          {
            key: "attestations",
            label: "Attestations",
            children: <PolicyAttestationsPage policySetKey={policySet.key} />,
          },
          {
            key: "decision-log",
            label: "Decision Log",
            children: <DecisionLogPage policySetKey={policySet.key} />,
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
          <Form.Item
            label="Review due date"
            name="review_due_date"
            tooltip="Periodic recertification date (ISO 37301 §9.3) — when this policy set should next be reviewed. Clear it to stop tracking a due date."
          >
            <DatePicker style={{ width: "100%" }} allowClear format="YYYY-MM-DD" />
          </Form.Item>

          <Divider style={{ margin: "8px 0 16px" }}>Governance &amp; ownership (RACI)</Divider>
          <Form.Item
            label="Accountable owner"
            name="accountable_owner"
            tooltip="The single named person or role ultimately answerable for this policy — distinct from the owning department above."
          >
            <Input placeholder="Jane Doe, VP People Ops" />
          </Form.Item>
          <Form.Item
            label="Delegate approver"
            name="delegate_approver"
            tooltip="Backup who can approve on the accountable owner's behalf, e.g. while they're out."
          >
            <Input placeholder="Alex Kim, Director" />
          </Form.Item>
          <Form.Item
            label="Escalation contact"
            name="escalation_contact"
            tooltip="Who overdue reviews or exception requests should be routed to if the accountable owner is unresponsive."
          >
            <Input placeholder="compliance-office@company.com" />
          </Form.Item>
          <Form.Item
            label="Consulted parties"
            name="consulted_parties"
            tooltip="Subject-matter experts or stakeholders consulted before this policy changes (RACI 'C')."
          >
            <Select mode="tags" placeholder="Legal, Internal Audit…" tokenSeparators={[","]} />
          </Form.Item>
          <Form.Item
            label="Informed parties"
            name="informed_parties"
            tooltip="Stakeholders who should be notified once this policy changes (RACI 'I')."
          >
            <Select mode="tags" placeholder="All people managers, Finance ops…" tokenSeparators={[","]} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Mark as Reviewed"
        open={reviewOpen}
        onCancel={() => {
          setReviewOpen(false);
          setReviewError(null);
        }}
        onOk={handleMarkReviewed}
        okText="Mark Reviewed"
        confirmLoading={reviewSaving}
        destroyOnClose
      >
        {reviewError && <Alert type="error" showIcon message={reviewError} style={{ marginBottom: 12 }} />}
        <Paragraph type="secondary">
          Records that this policy set was reviewed today. Optionally set the next review due date.
        </Paragraph>
        <Form layout="vertical" form={reviewForm}>
          <Form.Item label="Next review due date (optional)" name="next_due_date">
            <DatePicker style={{ width: "100%" }} allowClear format="YYYY-MM-DD" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
