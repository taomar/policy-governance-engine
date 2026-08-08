import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Col,
  DatePicker,
  Empty,
  Form,
  Input,
  InputNumber,
  Pagination,
  Progress,
  Row,
  Select,
  Space,
  Statistic,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  BulbOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  SendOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import {
  aiApi,
  api,
  PolicyPlatformApiError,
  type ApprovedPolicyVersion,
  type CandidateRule,
  type CanonicalRule,
  type ConditionNode,
  type ConditionOperator,
  type PolicySet,
  type PolicyScope,
  type QualityFinding,
} from "../api";
import { RuleCard } from "./RuleCard";
import { RewriteModal } from "./RewriteModal";
import { EditRuleModal } from "./EditRuleModal";
import { ManagerActionModal } from "./ManagerActionModal";
import { AskAboutRuleModal } from "./AskAboutRuleModal";
import { NotesPanel } from "./NotesPanel";
import { ExportMenu } from "./ExportMenu";
import { ScopeFieldsEditor } from "./ScopeEditor";
import { EMPTY_SCOPE } from "../scopeUtils";
import { useActor } from "../ActorContext";
import { RULE_TYPES } from "../ruleTypes";
import { CandidateRow } from "./CandidateRow";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

const STATUS_FILTERS = ["all", "candidate", "changes_requested", "approved", "rejected", "published"] as const;

const STATUS_COLOR: Record<string, string> = {
  candidate: "blue",
  changes_requested: "orange",
  approved: "green",
  rejected: "red",
  published: "purple",
};

const STATUS_LABEL: Record<string, string> = {
  all: "All",
  candidate: "Candidate",
  changes_requested: "Changes requested",
  approved: "Approved",
  rejected: "Rejected",
  published: "Published",
};

const OPERATORS = [
  "equals",
  "notEquals",
  "greaterThan",
  "greaterThanOrEqual",
  "lessThan",
  "lessThanOrEqual",
  "in",
  "notIn",
  "contains",
  "startsWith",
  "endsWith",
  "exists",
  "isNull",
];

interface ConditionRow {
  fact: string;
  operator: string;
  value: string;
}

function buildCondition(rows: ConditionRow[]): ConditionNode {
  const leaves: ConditionNode[] = rows.map((r) => {
    let value: unknown = r.value;
    if (value !== "" && !isNaN(Number(value))) value = Number(value);
    else if (value === "true") value = true;
    else if (value === "false") value = false;
    return { type: "factComparison", fact: r.fact, operator: r.operator as ConditionOperator, value };
  }) as ConditionNode[];
  if (leaves.length === 1) return leaves[0];
  return { type: "all", all: leaves };
}

export function ReviewQueue({ policySetKey }: { policySetKey?: string } = {}) {
  const scoped = Boolean(policySetKey);
  const { actor } = useActor();
  const { message } = App.useApp();
  const [policySets, setPolicySets] = useState<PolicySet[]>([]);
  const [selectedKey, setSelectedKey] = useState<string>(policySetKey ?? "");
  const [candidates, setCandidates] = useState<CandidateRule[]>([]);
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_FILTERS)[number]>("all");
  const [searchText, setSearchText] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [publishedBy, setPublishedBy] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState(() => new Date().toISOString().slice(0, 10));
  const [publishResult, setPublishResult] = useState<ApprovedPolicyVersion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showDraftForm, setShowDraftForm] = useState(false);
  const [advancedMode, setAdvancedMode] = useState(false);
  const [rewriteTarget, setRewriteTarget] = useState<CandidateRule | null>(null);
  const [editTarget, setEditTarget] = useState<CandidateRule | null>(null);
  const [managerAction, setManagerAction] = useState<{ candidate: CandidateRule; mode: "request-changes" | "override-approve" | "override-reject" } | null>(null);
  const [askTarget, setAskTarget] = useState<CandidateRule | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  // Candidate list rendering — each row starts collapsed (RuleCard's own
  // detail body, its per-evidence resolution effect, and the discussion
  // NotesPanel all only mount for rows the reviewer actually opens), plus
  // client-side pagination so at most PAGE_SIZE rows exist in the DOM at
  // once. Without this, a queue the size of a real extracted document (300+
  // pending candidates) rendered every row fully expanded on load — a
  // confirmed live scalability bug (346 candidates × full detail + a
  // separate notes fetch each, all mounted simultaneously).
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 20;

  // Readiness/quality findings — lazy-loaded on demand (triggers a real AI call),
  // grouped client-side by affected rule_id so each candidate can show a small badge.
  const [qualityFindings, setQualityFindings] = useState<Map<string, QualityFinding[]> | null>(null);
  const [qualityLoading, setQualityLoading] = useState(false);
  const [qualityError, setQualityError] = useState<string | null>(null);

  // Active-version rules — fetched to compute a pre-publish diff summary
  // (net-new / superseding / carried-forward-unchanged) before the manager commits.
  const [activeVersionRules, setActiveVersionRules] = useState<CanonicalRule[] | null>(null);

  // structured draft form state
  const [ruleId, setRuleId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [ruleType, setRuleType] = useState("approval_requirement");
  const [effectType, setEffectType] = useState<"allow" | "deny" | "require_action" | "informational">("require_action");
  const [effectAction, setEffectAction] = useState("");
  const [authorityOwner, setAuthorityOwner] = useState("");
  const [authorityLevel, setAuthorityLevel] = useState("corporate");
  const [authorityRank, setAuthorityRank] = useState(10);
  const [priority, setPriority] = useState(0);
  const [draftEffectiveFrom, setDraftEffectiveFrom] = useState(() => new Date().toISOString().slice(0, 10));
  const [conditionRows, setConditionRows] = useState<ConditionRow[]>([{ fact: "", operator: "greaterThan", value: "" }]);
  const [draftScope, setDraftScope] = useState<PolicyScope>(EMPTY_SCOPE);
  const [draftIsExplicitOverride, setDraftIsExplicitOverride] = useState(false);
  const [draftSupersedesRuleIds, setDraftSupersedesRuleIds] = useState<string[]>([]);
  const [draftGroupLabel, setDraftGroupLabel] = useState("");
  const [draftRelatedRuleIds, setDraftRelatedRuleIds] = useState<string[]>([]);
  const [advancedJson, setAdvancedJson] = useState("{}");
  const [draftError, setDraftError] = useState<string | null>(null);

  useEffect(() => {
    if (scoped) return; // scope is fixed by the embedding project; no picker/list needed
    api
      .listPolicySets()
      .then((sets) => {
        setPolicySets(sets);
        if (sets.length > 0) setSelectedKey(sets[0].key);
      })
      .catch((e) => setError(e instanceof PolicyPlatformApiError ? e.detail : String(e)));
  }, [scoped]);

  // Autofill reviewer/publisher name from the active actor identity — the user can
  // still override either field before submitting a review or publish action.
  useEffect(() => {
    if (actor.name.trim()) {
      setReviewer((prev) => (prev.trim() ? prev : actor.name));
      setPublishedBy((prev) => (prev.trim() ? prev : actor.name));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [actor.name]);

  const loadCandidates = async () => {
    if (!selectedKey) return;
    setError(null);
    setLoading(true);
    try {
      const status = statusFilter === "all" ? undefined : statusFilter;
      const list = await api.listCandidateRules(selectedKey, status);
      setCandidates(list);
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadCandidates();
    setQualityFindings(null); // stale once the policy set/filter changes — re-run on demand
    setExpandedIds(new Set());
    setPage(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedKey, statusFilter]);

  // Load the current active version's rules once per policy set, purely to compute the
  // pre-publish diff summary below — a plain deterministic DB read, safe to fetch eagerly
  // (unlike the AI-backed quality check, which stays behind a manual trigger).
  useEffect(() => {
    setActiveVersionRules(null);
    if (!selectedKey) return;
    let cancelled = false;
    api
      .getActiveVersion(selectedKey)
      .then((version) => api.getVersionRules(selectedKey, version.id))
      .then((rules) => {
        if (!cancelled) setActiveVersionRules(rules);
      })
      .catch(() => {
        if (!cancelled) setActiveVersionRules([]); // no active version yet (first publish) — treat as empty baseline
      });
    return () => {
      cancelled = true;
    };
  }, [selectedKey]);

  const runQualityCheck = async () => {
    if (!selectedKey) return;
    setQualityError(null);
    setQualityLoading(true);
    try {
      const report = await aiApi.getCandidateQuality(selectedKey);
      const byRule = new Map<string, QualityFinding[]>();
      for (const finding of report.findings) {
        for (const ruleId of finding.affected_rule_ids) {
          const list = byRule.get(ruleId) ?? [];
          list.push(finding);
          byRule.set(ruleId, list);
        }
      }
      setQualityFindings(byRule);
    } catch (e) {
      setQualityError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setQualityLoading(false);
    }
  };

  const handleReview = async (candidateId: string, decision: "approve" | "reject") => {
    setError(null);
    // The reviewer name is required because an approval with no attributable
    // author is not an audit trail. Reported through `message` rather than the
    // page-top Alert: the buttons are in a long scrolling list, and an error
    // rendered off-screen is indistinguishable from the button not working —
    // which is exactly how this was reported.
    if (!reviewer.trim()) {
      message.warning("Enter a reviewer name before approving or rejecting.");
      return;
    }
    try {
      await api.reviewCandidateRule(selectedKey, candidateId, { decision, reviewer });
      message.success(decision === "approve" ? "Rule approved" : "Rule rejected");
      await loadCandidates();
    } catch (e) {
      const detail = e instanceof PolicyPlatformApiError ? e.detail : String(e);
      setError(detail);
      message.error(detail);
    }
  };

  const toggleSelected = (candidateId: string) =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(candidateId)) next.delete(candidateId);
      else next.add(candidateId);
      return next;
    });

  const toggleExpanded = (candidateId: string) =>
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(candidateId)) next.delete(candidateId);
      else next.add(candidateId);
      return next;
    });

  const REVIEWABLE_STATUSES = new Set(["candidate", "rejected", "changes_requested"]);

  const filteredCandidates = useMemo(() => {
    const q = searchText.trim().toLowerCase();
    if (!q) return candidates;
    return candidates.filter((c) => {
      const r = c.rule;
      return (
        r.title.toLowerCase().includes(q) ||
        r.description.toLowerCase().includes(q) ||
        r.rule_id.toLowerCase().includes(q) ||
        r.effect.action.toLowerCase().includes(q) ||
        (r.category ?? "").toLowerCase().includes(q) ||
        (r.tags ?? []).some((t) => t.toLowerCase().includes(q)) ||
        (r.group_label ?? "").toLowerCase().includes(q)
      );
    });
  }, [candidates, searchText]);

  // Reset to page 1 whenever the search narrows/widens the filtered set, so
  // the reviewer never lands on a now-empty trailing page.
  useEffect(() => {
    setPage(1);
  }, [searchText]);

  const pagedCandidates = useMemo(
    () => filteredCandidates.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [filteredCandidates, page]
  );

  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const c of candidates) counts[c.review_status] = (counts[c.review_status] ?? 0) + 1;
    return counts;
  }, [candidates]);

  const selectableIds = filteredCandidates.filter((c) => REVIEWABLE_STATUSES.has(c.review_status)).map((c) => c.id);

  const toggleSelectAllVisible = () =>
    setSelectedIds((prev) => (prev.size === selectableIds.length ? new Set() : new Set(selectableIds)));

  const handleBulkReview = async (decision: "approve" | "reject") => {
    setError(null);
    if (!reviewer.trim()) {
      message.warning("Enter a reviewer name before approving or rejecting.");
      return;
    }
    if (selectedIds.size === 0) {
      message.warning("Select at least one candidate rule first.");
      return;
    }
    setBulkBusy(true);
    try {
      const result = await api.bulkReviewCandidateRules(selectedKey, {
        candidate_ids: Array.from(selectedIds),
        decision,
        reviewer,
        notes: "bulk review",
      });
      setSelectedIds(new Set());
      await loadCandidates();
      if (result.skipped.length > 0) {
        // A partial result is not an error: the reviewed rules were reviewed.
        // Reporting it as one made reviewers re-run the action.
        message.warning(
          `${result.reviewed} reviewed; ${result.skipped.length} skipped (already reviewed or published).`
        );
      } else {
        message.success(`${result.reviewed} rule${result.reviewed === 1 ? "" : "s"} ${decision}d`);
      }
    } catch (e) {
      const detail = e instanceof PolicyPlatformApiError ? e.detail : String(e);
      setError(detail);
      message.error(detail);
    } finally {
      setBulkBusy(false);
    }
  };

  const handlePublish = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setPublishResult(null);
    try {
      const version = await api.publishCandidates(selectedKey, {
        approved_by: publishedBy,
        effective_from: effectiveFrom,
        is_active: true,
      });
      setPublishResult(version);
      await loadCandidates();
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    }
  };

  const handleDraft = async (e: React.FormEvent) => {
    e.preventDefault();
    setDraftError(null);
    try {
      let rule: Record<string, unknown>;
      if (advancedMode) {
        rule = JSON.parse(advancedJson);
      } else {
        rule = {
          policy_set_id: "placeholder",
          policy_version_id: "placeholder",
          rule_id: ruleId,
          rule_revision: 1,
          title,
          description,
          rule_type: ruleType,
          authority: { level: authorityLevel, owner: authorityOwner, rank: authorityRank },
          scope: draftScope,
          is_explicit_override: draftIsExplicitOverride,
          supersedes_rule_ids: draftSupersedesRuleIds,
          group_label: draftGroupLabel,
          related_rule_ids: draftRelatedRuleIds,
          condition: buildCondition(conditionRows.filter((r) => r.fact.trim() !== "")),
          effect: { type: effectType, action: effectAction },
          required_facts: conditionRows
            .filter((r) => r.fact.trim() !== "")
            .map((r) => ({ name: r.fact, data_type: isNaN(Number(r.value)) ? "string" : "number", required: true })),
          priority,
          effective_from: draftEffectiveFrom,
        };
      }
      await api.draftCandidateRule(selectedKey, { rule });
      setShowDraftForm(false);
      setRuleId("");
      setTitle("");
      setDescription("");
      setEffectAction("");
      setAuthorityOwner("");
      setConditionRows([{ fact: "", operator: "greaterThan", value: "" }]);
      setDraftScope(EMPTY_SCOPE);
      setDraftIsExplicitOverride(false);
      setDraftSupersedesRuleIds([]);
      setDraftGroupLabel("");
      setDraftRelatedRuleIds([]);
      await loadCandidates();
    } catch (e) {
      setDraftError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    }
  };

  const addConditionRow = () => setConditionRows((rows) => [...rows, { fact: "", operator: "greaterThan", value: "" }]);
  const updateConditionRow = (i: number, patch: Partial<ConditionRow>) =>
    setConditionRows((rows) => rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  const removeConditionRow = (i: number) => setConditionRows((rows) => rows.filter((_, idx) => idx !== i));

  const approvedUnpublished = candidates.filter((c) => c.review_status === "approved");
  const totalCandidates = candidates.length;
  const publishedPct = totalCandidates ? Math.round(((statusCounts.published ?? 0) / totalCandidates) * 100) : 0;
  const isManager = actor.role === "policy_manager";

  const publishDiff = useMemo(() => {
    if (activeVersionRules === null) return null;
    const activeIds = new Set(activeVersionRules.map((r) => r.rule_id));
    const approvedIds = new Set(approvedUnpublished.map((c) => c.rule.rule_id));
    const netNew = approvedUnpublished.filter((c) => !activeIds.has(c.rule.rule_id));
    const superseding = approvedUnpublished.filter((c) => activeIds.has(c.rule.rule_id));
    const unchangedCount = activeVersionRules.filter((r) => !approvedIds.has(r.rule_id)).length;
    return { netNew, superseding, unchangedCount };
  }, [activeVersionRules, approvedUnpublished]);

  return (
    <>
      <div className="page-header-row">
        <Title level={3} style={{ margin: 0 }}>
          Review Queue
        </Title>
        {!scoped && (
          <Select
            value={selectedKey}
            onChange={setSelectedKey}
            style={{ minWidth: 220 }}
            options={policySets.map((ps) => ({ value: ps.key, label: ps.name }))}
          />
        )}
      </div>

      {error && <Alert type="error" showIcon message={error} closable onClose={() => setError(null)} />}
      {!scoped && policySets.length === 0 && (
        <Text type="secondary">Create a policy set first (Policy Sets page).</Text>
      )}

      {selectedKey && totalCandidates > 0 && (
        <Card size="small" className="progress-stats-bar" style={{ marginBottom: 16 }}>
          <Row gutter={24} align="middle">
            <Col flex="220px">
              <Statistic title="Total rules" value={totalCandidates} />
            </Col>
            <Col flex="auto">
              <Progress
                percent={publishedPct}
                success={{ percent: publishedPct }}
                format={() => `${statusCounts.published ?? 0} published`}
              />
            </Col>
            <Col>
              <Space size={[6, 6]} wrap>
                {STATUS_FILTERS.filter((s) => s !== "all").map((s) => (
                  <Tag key={s} color={STATUS_COLOR[s]} style={{ margin: 0 }}>
                    {STATUS_LABEL[s]}: {statusCounts[s] ?? 0}
                  </Tag>
                ))}
              </Space>
            </Col>
          </Row>
        </Card>
      )}

      {selectedKey && (
        <>
          <Card
            title="Candidate Rules"
            className="modern-card"
            extra={
              <Button
                type={showDraftForm ? "default" : "primary"}
                icon={!showDraftForm && <PlusOutlined />}
                onClick={() => setShowDraftForm((v) => !v)}
              >
                {showDraftForm ? "Cancel" : "Draft Candidate Rule"}
              </Button>
            }
          >
            {showDraftForm && (
              <Form layout="vertical" onSubmitCapture={handleDraft} style={{ marginBottom: 8 }}>
                {draftError && <Alert type="error" showIcon message={draftError} style={{ marginBottom: 16 }} />}
                <Checkbox checked={advancedMode} onChange={(e) => setAdvancedMode(e.target.checked)} style={{ marginBottom: 16 }}>
                  Advanced (raw JSON) mode
                </Checkbox>

                {advancedMode ? (
                  <Form.Item label="Candidate rule (canonical rule JSON)">
                    <TextArea rows={14} value={advancedJson} onChange={(e) => setAdvancedJson(e.target.value)} spellCheck={false} />
                  </Form.Item>
                ) : (
                  <>
                    <Row gutter={16}>
                      <Col span={8}>
                        <Form.Item label="Rule ID" required>
                          <Input value={ruleId} onChange={(e) => setRuleId(e.target.value)} placeholder="RULE-DRAFT-001" />
                        </Form.Item>
                      </Col>
                      <Col span={16}>
                        <Form.Item label="Title" required>
                          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Require manager approval" />
                        </Form.Item>
                      </Col>
                      <Col span={24}>
                        <Form.Item label="Description">
                          <Input value={description} onChange={(e) => setDescription(e.target.value)} />
                        </Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item label="Rule type">
                          <Select
                            value={ruleType}
                            onChange={setRuleType}
                            options={RULE_TYPES.map((t) => ({ value: t, label: t }))}
                          />
                        </Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item label="Effect">
                          <Select
                            value={effectType}
                            onChange={(v) => setEffectType(v as typeof effectType)}
                            options={[
                              { value: "allow", label: "allow" },
                              { value: "deny", label: "deny" },
                              { value: "require_action", label: "require_action" },
                              { value: "informational", label: "informational" },
                            ]}
                          />
                        </Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item label="Effect action" required>
                          <Input value={effectAction} onChange={(e) => setEffectAction(e.target.value)} placeholder="manager_approval" />
                        </Form.Item>
                      </Col>
                      <Col span={6}>
                        <Form.Item label="Priority">
                          <InputNumber style={{ width: "100%" }} value={priority} onChange={(v) => setPriority(Number(v ?? 0))} />
                        </Form.Item>
                      </Col>
                      <Col span={6}>
                        <Form.Item label="Authority owner" required>
                          <Input value={authorityOwner} onChange={(e) => setAuthorityOwner(e.target.value)} placeholder="finance-controls" />
                        </Form.Item>
                      </Col>
                      <Col span={6}>
                        <Form.Item label="Authority level">
                          <Input value={authorityLevel} onChange={(e) => setAuthorityLevel(e.target.value)} placeholder="corporate" />
                        </Form.Item>
                      </Col>
                      <Col span={6}>
                        <Form.Item label="Authority rank">
                          <InputNumber
                            style={{ width: "100%" }}
                            value={authorityRank}
                            onChange={(v) => setAuthorityRank(Number(v ?? 0))}
                          />
                        </Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item label="Effective from" required>
                          <DatePicker
                            style={{ width: "100%" }}
                            value={dayjs(draftEffectiveFrom)}
                            onChange={(d) => setDraftEffectiveFrom(d ? d.format("YYYY-MM-DD") : "")}
                          />
                        </Form.Item>
                      </Col>
                    </Row>

                    <ScopeFieldsEditor
                      scope={draftScope}
                      onScopeChange={setDraftScope}
                      isExplicitOverride={draftIsExplicitOverride}
                      onIsExplicitOverrideChange={setDraftIsExplicitOverride}
                      supersedesRuleIds={draftSupersedesRuleIds}
                      onSupersedesRuleIdsChange={setDraftSupersedesRuleIds}
                      supersedeCandidates={(activeVersionRules ?? []).map((r) => ({ rule_id: r.rule_id, title: r.title }))}
                      groupLabel={draftGroupLabel}
                      onGroupLabelChange={setDraftGroupLabel}
                      existingGroupLabels={(activeVersionRules ?? []).map((r) => r.group_label).filter(Boolean)}
                      relatedRuleIds={draftRelatedRuleIds}
                      onRelatedRuleIdsChange={setDraftRelatedRuleIds}
                    />

                    <Form.Item label="Condition (AND of comparisons — use Advanced mode for OR/NOT/nested logic)">
                      <Space direction="vertical" style={{ width: "100%" }} size={8}>
                        {conditionRows.map((row, i) => (
                          <Space.Compact key={i} style={{ width: "100%" }}>
                            <Input
                              placeholder="fact name"
                              value={row.fact}
                              onChange={(e) => updateConditionRow(i, { fact: e.target.value })}
                              style={{ width: "30%" }}
                            />
                            <Select
                              value={row.operator}
                              onChange={(v) => updateConditionRow(i, { operator: v })}
                              style={{ width: "30%" }}
                              options={OPERATORS.map((op) => ({ value: op, label: op }))}
                            />
                            <Input
                              placeholder="value"
                              value={row.value}
                              onChange={(e) => updateConditionRow(i, { value: e.target.value })}
                              style={{ width: "30%" }}
                            />
                            {conditionRows.length > 1 && (
                              <Button onClick={() => removeConditionRow(i)}>✕</Button>
                            )}
                          </Space.Compact>
                        ))}
                        <Button icon={<PlusOutlined />} onClick={addConditionRow}>
                          Add condition
                        </Button>
                      </Space>
                    </Form.Item>
                  </>
                )}

                <Button type="primary" htmlType="submit">
                  Submit for Review
                </Button>
              </Form>
            )}

            <Space size={16} wrap className="review-controls-bar" style={{ marginBottom: 16 }}>
              <Select
                value={statusFilter}
                onChange={(v) => setStatusFilter(v as typeof statusFilter)}
                style={{ width: 190 }}
                options={STATUS_FILTERS.map((s) => ({ value: s, label: STATUS_LABEL[s] }))}
              />
              <Input
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                placeholder="Search title, description, action, rule ID, tag…"
                prefix={<SearchOutlined />}
                allowClear
                style={{ width: 300 }}
              />
              <Space>
                <Text>Reviewer name</Text>
                <Input value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="jane.doe" style={{ width: 160 }} />
              </Space>
              <Tooltip title="Run an AI + deterministic quality scan over unpublished candidates (findings appear as badges below)">
                <Button icon={<SafetyCertificateOutlined />} onClick={runQualityCheck} loading={qualityLoading}>
                  {qualityFindings ? "Re-run quality check" : "Run quality check"}
                </Button>
              </Tooltip>
              <ExportMenu
                label="Export this filter"
                size="middle"
                onExport={(format) =>
                  api.exportCandidateRules(selectedKey, format, statusFilter === "all" ? undefined : statusFilter)
                }
              />
            </Space>

            {qualityError && <Alert type="warning" showIcon message={qualityError} style={{ marginBottom: 16 }} closable onClose={() => setQualityError(null)} />}

            {selectableIds.length > 0 && (
              <Card size="small" className="bulk-bar" style={{ marginBottom: 16 }}>
                <Space size={16} wrap style={{ width: "100%", justifyContent: "space-between" }}>
                  <Checkbox
                    checked={selectedIds.size === selectableIds.length && selectableIds.length > 0}
                    onChange={toggleSelectAllVisible}
                  >
                    {selectedIds.size > 0 ? `${selectedIds.size} selected` : `Select all ${selectableIds.length} in this filter`}
                  </Checkbox>
                  <Space>
                    <Button
                      type="primary"
                      disabled={selectedIds.size === 0 || bulkBusy}
                      loading={bulkBusy}
                      onClick={() => handleBulkReview("approve")}
                    >
                      Approve selected ({selectedIds.size})
                    </Button>
                    <Button danger disabled={selectedIds.size === 0 || bulkBusy} onClick={() => handleBulkReview("reject")}>
                      Reject selected
                    </Button>
                  </Space>
                </Space>
              </Card>
            )}

            {loading ? (
              <Text type="secondary">Loading…</Text>
            ) : (
              <>
                <Space direction="vertical" style={{ width: "100%" }} size={8} className="candidate-list">
                  {pagedCandidates.map((c) => {
                    const findings = qualityFindings?.get(c.rule.rule_id) ?? [];
                    const isReviewable = REVIEWABLE_STATUSES.has(c.review_status);
                    const isExpanded = expandedIds.has(c.id);
                    return (
                      <div key={c.id} className="candidate-item">
                        <CandidateRow
                          candidate={c}
                          expanded={isExpanded}
                          selected={selectedIds.has(c.id)}
                          selectable={isReviewable}
                          findingsCount={findings.length}
                          statusColor={STATUS_COLOR[c.review_status] ?? "default"}
                          statusLabel={STATUS_LABEL[c.review_status] ?? c.review_status}
                          onToggleExpand={() => toggleExpanded(c.id)}
                          onToggleSelect={() => toggleSelected(c.id)}
                          onApprove={isReviewable ? () => handleReview(c.id, "approve") : undefined}
                          onReject={isReviewable ? () => handleReview(c.id, "reject") : undefined}
                        />
                        {isExpanded && (
                          <div className="candidate-item-detail">
                            <RuleCard rule={c.rule} defaultExpanded hideNotes />
                            {findings.length > 0 && (
                              <div className="readiness-badges">
                                {findings.map((f, fi) => (
                                  <Tooltip key={fi} title={f.recommendation}>
                                    <Tag
                                      icon={<ExclamationCircleOutlined />}
                                      color={f.severity === "high" ? "red" : f.severity === "medium" ? "gold" : "default"}
                                    >
                                      {f.category}: {f.finding}
                                    </Tag>
                                  </Tooltip>
                                ))}
                              </div>
                            )}
                            <div className="candidate-item-footer">
                              <Space size={10} wrap>
                                <Text type="secondary" className="entity-id-row" copyable={{ text: c.id }}>
                                  {c.id}
                                </Text>
                                {c.reviewed_by && <Text type="secondary">reviewed by {c.reviewed_by}</Text>}
                                {c.review_notes && <Text type="secondary">— {c.review_notes}</Text>}
                              </Space>
                              <Space size={8} wrap>
                                <Button size="small" icon={<BulbOutlined />} onClick={() => setAskTarget(c)}>
                                  Ask AI about this rule
                                </Button>
                                {isReviewable && (
                                  <>
                                    <Button size="small" icon={<EditOutlined />} onClick={() => setEditTarget(c)}>
                                      Edit
                                    </Button>
                                    <Button size="small" icon={<ThunderboltOutlined />} onClick={() => setRewriteTarget(c)}>
                                      Suggest Rewrite
                                    </Button>
                                    <Button size="small" type="primary" onClick={() => handleReview(c.id, "approve")}>
                                      Approve
                                    </Button>
                                    <Button size="small" danger onClick={() => handleReview(c.id, "reject")}>
                                      Reject
                                    </Button>
                                  </>
                                )}
                                {c.review_status === "approved" && (
                                  <>
                                    <Tooltip title={isManager ? "Send back to the composer for rework" : "Manager role required"}>
                                      <Button
                                        size="small"
                                        icon={<SendOutlined />}
                                        disabled={!isManager}
                                        onClick={() => setManagerAction({ candidate: c, mode: "request-changes" })}
                                      >
                                        Send back for changes
                                      </Button>
                                    </Tooltip>
                                    <Tooltip title={isManager ? "Override this decision to Rejected" : "Manager role required"}>
                                      <Button
                                        size="small"
                                        danger
                                        disabled={!isManager}
                                        onClick={() => setManagerAction({ candidate: c, mode: "override-reject" })}
                                      >
                                        Override & Reject
                                      </Button>
                                    </Tooltip>
                                  </>
                                )}
                                {c.review_status === "rejected" && isManager && (
                                  <Tooltip title="Override this decision to Approved">
                                    <Button
                                      size="small"
                                      onClick={() => setManagerAction({ candidate: c, mode: "override-approve" })}
                                    >
                                      Override & Approve
                                    </Button>
                                  </Tooltip>
                                )}
                              </Space>
                            </div>
                            <NotesPanel entityType="candidate_rule" entityId={c.id} title="Review discussion" compact />
                          </div>
                        )}
                      </div>
                    );
                  })}
                  {filteredCandidates.length === 0 && (
                    <Empty
                      description={searchText ? "No candidate rules match your search." : "No candidate rules found for this filter."}
                    />
                  )}
                </Space>
                {filteredCandidates.length > PAGE_SIZE && (
                  <div className="candidate-pagination">
                    <Pagination
                      current={page}
                      pageSize={PAGE_SIZE}
                      total={filteredCandidates.length}
                      onChange={setPage}
                      showSizeChanger={false}
                      showTotal={(total, range) => `${range[0]}–${range[1]} of ${total} candidates`}
                    />
                  </div>
                )}
              </>
            )}
          </Card>

          <Card title="Publish Approved Candidates" className="modern-card">
            <Paragraph type="secondary">
              {approvedUnpublished.length} approved candidate(s) ready to publish into a new version, carrying forward
              all rules from the current active version.
            </Paragraph>
            {publishDiff && approvedUnpublished.length > 0 && (
              <Space wrap style={{ marginBottom: 16 }}>
                <Tag color="green">{publishDiff.netNew.length} net-new rule(s)</Tag>
                <Tag color="gold">{publishDiff.superseding.length} superseding existing rule(s)</Tag>
                <Tag>{publishDiff.unchangedCount} unchanged carried forward</Tag>
              </Space>
            )}
            <Form layout="vertical" onSubmitCapture={handlePublish}>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item label="Approved by" required>
                    <Input value={publishedBy} onChange={(e) => setPublishedBy(e.target.value)} placeholder="jane.doe" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="Effective from" required>
                    <DatePicker
                      style={{ width: "100%" }}
                      value={dayjs(effectiveFrom)}
                      onChange={(d) => setEffectiveFrom(d ? d.format("YYYY-MM-DD") : "")}
                    />
                  </Form.Item>
                </Col>
              </Row>
              <Button type="primary" htmlType="submit" disabled={approvedUnpublished.length === 0}>
                Publish New Version
              </Button>
            </Form>
            {publishResult && (
              <Alert
                type="success"
                showIcon
                style={{ marginTop: 16 }}
                message={`Published: version ${publishResult.version_number}, ${publishResult.rule_count} rule(s)`}
              />
            )}
          </Card>
        </>
      )}

      {rewriteTarget && (
        <RewriteModal candidate={rewriteTarget} onClose={() => setRewriteTarget(null)} onApplied={() => void loadCandidates()} />
      )}
      {editTarget && (
        <EditRuleModal
          policySetKey={selectedKey}
          candidate={editTarget}
          allRules={activeVersionRules ?? []}
          onClose={() => setEditTarget(null)}
          onApplied={() => void loadCandidates()}
        />
      )}
      {managerAction && (
        <ManagerActionModal
          policySetKey={selectedKey}
          candidate={managerAction.candidate}
          mode={managerAction.mode}
          onClose={() => setManagerAction(null)}
          onApplied={() => void loadCandidates()}
        />
      )}
      {askTarget && <AskAboutRuleModal candidate={askTarget} onClose={() => setAskTarget(null)} />}
    </>
  );
}
