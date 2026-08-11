import { useMemo, useState } from "react";
import {
  Alert,
  Button,
  Checkbox,
  Col,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Tabs,
  Tag,
  Typography,
} from "antd";
import { BranchesOutlined, EditOutlined, PlusOutlined, ThunderboltOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import {
  aiApi,
  api,
  PolicyPlatformApiError,
  type CandidateRule,
  type CanonicalRule,
  type ConditionNode,
  type PolicyScope,
  type ScenarioEvaluation,
} from "../api";
import { machineExecutableFor } from "../ruleExecutability";
import { RuleCard } from "./RuleCard";
import { ScopeFieldsEditor } from "./ScopeEditor";
import { normalizeScope } from "../scopeUtils";
import { useActor } from "../ActorContext";
import { RULE_TYPES } from "../ruleTypes";
import { ImmutableFieldsNotice } from "./ImmutableFieldsNotice";
import {
  buildCondition,
  conditionToRows,
  CONDITION_OPERATORS,
  type ConditionRow,
} from "../conditionRows";

const { TextArea } = Input;
const { Text, Paragraph } = Typography;

const OPERATORS = CONDITION_OPERATORS;

type EditRuleModalProps =
  | {
      mode?: "edit";
      policySetKey: string;
      candidate: CandidateRule;
      onClose: () => void;
      onApplied: () => void;
      /** Other rules in this policy set, offered as pickable options for "Supersedes rule
       * IDs" (the rule being edited is excluded automatically). Optional — omitting it just
       * falls back to a free-type-only field, same as before this was wired up. */
      allRules?: CanonicalRule[];
    }
  | {
      mode: "revise";
      policySetKey: string;
      sourceRule: CanonicalRule;
      onClose: () => void;
      onApplied: () => void;
      allRules?: CanonicalRule[];
    };

/**
 * Direct, manual edit of a candidate rule — the human-typed counterpart to
 * "Suggest Rewrite" (which asks the AI to draft a change). Lets a composer or
 * manager correct wording, thresholds, dates, tags/category, or the condition
 * itself, with a live before/after preview, and records why the edit was made
 * (surfaced afterwards in the rule's Notes/discussion trail).
 *
 * Also doubles as the "Revise this rule" flow: pass `mode="revise"` with a
 * *published* `sourceRule` instead of `candidate`, and the same form is used
 * to pre-fill a brand-new candidate (same `rule_id`, next `rule_revision`)
 * that goes through the normal draft → review → approve → publish pipeline.
 * `publish_approved_candidates` merges newly-approved candidates into the
 * carried-forward rule set by `rule_id`, so publishing a revision safely
 * replaces just that one rule and leaves every other published rule intact.
 */
export function EditRuleModal(props: EditRuleModalProps) {
  const { policySetKey, onClose, onApplied } = props;
  const isRevise = props.mode === "revise";
  const { actor } = useActor();
  const rule = isRevise ? props.sourceRule : props.candidate.rule;
  const rowsFromCondition = useMemo(() => conditionToRows(rule.condition), [rule]);
  // A rule can't supersede itself — exclude it from the picker options.
  const supersedeCandidates = useMemo(
    () => (props.allRules ?? []).filter((r) => r.rule_id !== rule.rule_id).map((r) => ({ rule_id: r.rule_id, title: r.title })),
    [props.allRules, rule.rule_id]
  );

  const [advancedMode, setAdvancedMode] = useState(rowsFromCondition === null);
  const [advancedJson, setAdvancedJson] = useState(() => JSON.stringify(rule, null, 2));
  // Once the raw JSON holds condition logic the simple row editor can't represent (e.g. after
  // "Populate with AI" proposes an OR/NOT condition), unchecking Advanced mode would silently
  // rebuild the condition from the stale, unrelated `conditionRows` state and discard it. Lock the
  // checkbox in that case instead of allowing a silent loss.
  const advancedJsonRows = useMemo(() => {
    if (!advancedMode) return undefined;
    try {
      return conditionToRows((JSON.parse(advancedJson) as CanonicalRule).condition);
    } catch {
      return null;
    }
  }, [advancedMode, advancedJson]);
  const mustStayInAdvancedMode = advancedMode && advancedJsonRows === null;
  const [title, setTitle] = useState(rule.title);
  const [description, setDescription] = useState(rule.description);
  const [ruleType, setRuleType] = useState(rule.rule_type);
  const [effectType, setEffectType] = useState<"allow" | "deny" | "require_action" | "informational">(rule.effect.type);
  const [effectAction, setEffectAction] = useState(rule.effect.action);
  const [priority, setPriority] = useState(rule.priority);
  const [effectiveFrom, setEffectiveFrom] = useState(rule.effective_from);
  const [effectiveTo, setEffectiveTo] = useState(rule.effective_to ?? "");
  const [category, setCategory] = useState(rule.category ?? "");
  const [tagsText, setTagsText] = useState((rule.tags ?? []).join(", "));
  const [scope, setScope] = useState<PolicyScope>(normalizeScope(rule.scope));
  const [isExplicitOverride, setIsExplicitOverride] = useState(rule.is_explicit_override ?? false);
  const [supersedesRuleIds, setSupersedesRuleIds] = useState<string[]>(rule.supersedes_rule_ids ?? []);
  const [groupLabel, setGroupLabel] = useState(rule.group_label ?? "");
  const [relatedRuleIds, setRelatedRuleIds] = useState<string[]>(rule.related_rule_ids ?? []);
  const existingGroupLabels = useMemo(
    () => (props.allRules ?? []).map((r) => r.group_label).filter((label): label is string => !!label),
    [props.allRules]
  );
  const [conditionRows, setConditionRows] = useState<ConditionRow[]>(
    rowsFromCondition ?? [{ fact: "", operator: "greaterThan", value: "" }]
  );
  const [editNote, setEditNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"fields" | "evaluate">("fields");

  // "Populate with AI" (revise mode only): the user edits the description
  // field (pre-filled with the currently published wording) to describe what
  // should change, and AI proposes updated values for every relevant field.
  const [populatingAi, setPopulatingAi] = useState(false);
  const [populateError, setPopulateError] = useState<string | null>(null);
  const [populateExplanation, setPopulateExplanation] = useState<string | null>(null);

  // "AI Evaluate" tab: advisory-only scenario reasoning, never the real
  // deterministic engine (see ai_scenario_eval.py).
  const [scenario, setScenario] = useState("");
  const [reasoningEffort, setReasoningEffort] = useState<"low" | "medium" | "high">("medium");
  const [evaluating, setEvaluating] = useState(false);
  const [evalError, setEvalError] = useState<string | null>(null);
  const [evalResult, setEvalResult] = useState<ScenarioEvaluation | null>(null);

  const addConditionRow = () => setConditionRows((rows) => [...rows, { fact: "", operator: "greaterThan", value: "" }]);
  const updateConditionRow = (i: number, patch: Partial<ConditionRow>) =>
    setConditionRows((rows) => rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  const removeConditionRow = (i: number) => setConditionRows((rows) => rows.filter((_, idx) => idx !== i));

  const previewRule: CanonicalRule | null = useMemo(() => {
    if (advancedMode) {
      try {
        return JSON.parse(advancedJson) as CanonicalRule;
      } catch {
        return null;
      }
    }
    const filteredRows = conditionRows.filter((r) => r.fact.trim() !== "");
    // Clearing every row must actually clear the condition. Falling back to
    // `rule.condition` whenever the list was empty made that impossible: the
    // rows vanished from the form, the save succeeded, and the old condition
    // came back with nothing to explain it. The fallback still applies when
    // `rowsFromCondition` is null — that means the stored condition is richer
    // than the row editor can show (OR/NOT/nesting) and the modal is in raw
    // JSON mode, so an empty list there means "never editable here", not
    // "cleared".
    const nextCondition: ConditionNode =
      filteredRows.length > 0
        ? buildCondition(filteredRows)
        : rowsFromCondition === null
          ? rule.condition
          : { type: "all", all: [] };
    return {
      ...rule,
      rule_revision: isRevise ? rule.rule_revision + 1 : rule.rule_revision,
      title,
      description,
      rule_type: ruleType,
      effect: { type: effectType, action: effectAction },
      priority,
      effective_from: effectiveFrom,
      effective_to: effectiveTo || null,
      category,
      tags: tagsText
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
      scope,
      is_explicit_override: isExplicitOverride,
      supersedes_rule_ids: supersedesRuleIds,
      group_label: groupLabel,
      related_rule_ids: relatedRuleIds,
      condition: nextCondition,
      // Derived, never carried over. Spreading `...rule` kept the extracted
      // `false` even after a reviewer had supplied a real condition, so the
      // engine short-circuited to NOT_APPLICABLE and the edit never ran.
      machine_executable: machineExecutableFor(nextCondition),
      required_facts:
        filteredRows.length > 0
          ? filteredRows.map((r) => ({
              name: r.fact,
              data_type: isNaN(Number(r.value)) ? "string" : "number",
              required: true,
            }))
          : rowsFromCondition === null
            ? rule.required_facts
            : [],
    };
  }, [advancedMode, advancedJson, rule, rowsFromCondition, isRevise, title, description, ruleType, effectType, effectAction, priority, effectiveFrom, effectiveTo, category, tagsText, scope, isExplicitOverride, supersedesRuleIds, groupLabel, relatedRuleIds, conditionRows]);

  const handleSave = async () => {
    setError(null);
    if (!actor.name.trim()) {
      setError(`Set your name in the actor switcher before ${isRevise ? "revising" : "editing"} a rule.`);
      return;
    }
    if (!previewRule) {
      setError("The advanced JSON is not valid — fix it before saving.");
      return;
    }
    setSaving(true);
    try {
      if (isRevise) {
        await api.draftCandidateRule(policySetKey, {
          rule: previewRule as unknown as Record<string, unknown>,
        });
      } else {
        await api.editCandidateRule(policySetKey, props.candidate.id, {
          rule: previewRule as unknown as Record<string, unknown>,
          editor: editNote.trim() ? `${actor.name} — ${editNote.trim()}` : actor.name,
        });
      }
      onApplied();
      onClose();
    } catch (err) {
      setError(err instanceof PolicyPlatformApiError ? err.detail : String(err));
    } finally {
      setSaving(false);
    }
  };

  // Applies an AI-suggested rule payload onto the form's editable state —
  // shared by the "Populate with AI" description flow. Mirrors the same
  // fields this component seeds from `rule` on mount.
  const applyAiSuggestion = (suggested: CanonicalRule) => {
    setTitle(suggested.title);
    setDescription(suggested.description);
    setRuleType(suggested.rule_type);
    setEffectType(suggested.effect.type);
    setEffectAction(suggested.effect.action);
    setPriority(suggested.priority);
    setEffectiveFrom(suggested.effective_from);
    setEffectiveTo(suggested.effective_to ?? "");
    setCategory(suggested.category ?? "");
    setTagsText((suggested.tags ?? []).join(", "));
    setScope(normalizeScope(suggested.scope));
    setIsExplicitOverride(suggested.is_explicit_override ?? false);
    setSupersedesRuleIds(suggested.supersedes_rule_ids ?? []);
    const rows = conditionToRows(suggested.condition);
    if (rows) {
      setConditionRows(rows);
      setAdvancedMode(false);
    } else {
      setAdvancedMode(true);
      setAdvancedJson(JSON.stringify(suggested, null, 2));
    }
  };

  const handlePopulateWithAi = async () => {
    if (!previewRule) {
      setPopulateError("Fix the form (or Advanced JSON) first — the rule must be valid before using AI.");
      return;
    }
    setPopulatingAi(true);
    setPopulateError(null);
    setPopulateExplanation(null);
    try {
      // The AI endpoint treats whatever `rule_revision` it receives as the current
      // (published) one and always returns current+1. In revise mode, `previewRule`
      // has already been bumped to `rule.rule_revision + 1` for the eventual Save
      // payload — sending it as-is would double-increment (e.g. rev 1 -> preview
      // rev 2 -> AI returns rev 3, silently skipping rev 2). Send the true current
      // revision instead so the AI's response lines up with what Save will submit.
      const payloadForAi = isRevise ? { ...previewRule, rule_revision: rule.rule_revision } : previewRule;
      const result = await aiApi.rewritePreview(payloadForAi, description);
      applyAiSuggestion(result.suggested);
      setPopulateExplanation(result.explanation);
    } catch (err) {
      setPopulateError(err instanceof PolicyPlatformApiError ? err.detail : String(err));
    } finally {
      setPopulatingAi(false);
    }
  };

  const handleEvaluateScenario = async () => {
    if (!previewRule) {
      setEvalError("Fix the form (or Advanced JSON) first — the rule must be valid to evaluate.");
      return;
    }
    if (!scenario.trim()) return;
    setEvaluating(true);
    setEvalError(null);
    setEvalResult(null);
    try {
      const result = await aiApi.evaluateScenario(previewRule, scenario, reasoningEffort);
      setEvalResult(result);
    } catch (err) {
      setEvalError(err instanceof PolicyPlatformApiError ? err.detail : String(err));
    } finally {
      setEvaluating(false);
    }
  };

  return (
    <Modal
      title={
        <Space>
          {isRevise ? <BranchesOutlined style={{ color: "#2563eb" }} /> : <EditOutlined style={{ color: "#2563eb" }} />}
          <span>
            {isRevise ? `Revise Rule — ${rule.rule_id}` : `Edit Rule — ${rule.rule_id}`}
          </span>
        </Space>
      }
      open
      onCancel={onClose}
      width={1040}
      footer={[
        <Button key="cancel" onClick={onClose}>
          Cancel
        </Button>,
        <Button key="save" type="primary" onClick={handleSave} loading={saving}>
          {saving ? "Saving…" : isRevise ? "Submit Revision for Review" : "Save Edit"}
        </Button>,
      ]}
    >
      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}

      {isRevise && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message={`Creating revision ${rule.rule_revision + 1} of ${rule.rule_id}`}
          description={
            <>
              This starts pre-filled with the currently published rule (revision {rule.rule_revision}). It's saved as
              a new <strong>candidate</strong> in the Review queue — nothing changes for the live policy until it's
              approved and published. Publishing keeps every other published rule as-is and only replaces this one,
              because rules are merged by rule ID.
            </>
          }
        />
      )}

      <ImmutableFieldsNotice mode="edit" />

      <Checkbox
        checked={advancedMode}
        onChange={(e) => setAdvancedMode(e.target.checked)}
        disabled={mustStayInAdvancedMode}
        style={{ marginBottom: 16 }}
      >
        Advanced (raw JSON) mode{" "}
        {(mustStayInAdvancedMode || (!advancedMode && rowsFromCondition === null)) &&
          "— required: this rule's condition has nested logic"}
      </Checkbox>

      <Row gutter={24}>
        <Col span={12}>
          <Tabs
            className="tabs-segmented"
            activeKey={activeTab}
            onChange={(k) => setActiveTab(k as "fields" | "evaluate")}
            items={[
              {
                key: "fields",
                label: "Edit Fields",
                children: (
                  <>
          {/* Description + "Populate with AI" always render here, regardless of Simple/Advanced
              mode, so the trigger and its success/error feedback stay reachable even after the AI
              proposes a compound condition that forces Advanced (raw JSON) mode below. */}
          <Form layout="vertical">
            {isRevise && (
              <Form.Item label="Current description (published, read-only)">
                <TextArea rows={2} value={rule.description} disabled />
              </Form.Item>
            )}
            <Form.Item
              label={
                isRevise
                  ? "Updated description — starts from the current wording; edit it to describe the change"
                  : "Description"
              }
            >
              <TextArea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
            </Form.Item>
            {isRevise && (
              <div style={{ marginTop: -12, marginBottom: 16 }}>
                <Button
                  size="small"
                  icon={<ThunderboltOutlined />}
                  onClick={handlePopulateWithAi}
                  loading={populatingAi}
                  disabled={!description.trim()}
                >
                  {populatingAi ? "Populating…" : "Populate with AI"}
                </Button>
                {populateError && (
                  <Alert
                    type="error"
                    showIcon
                    message={populateError}
                    style={{ marginTop: 8 }}
                    closable
                    onClose={() => setPopulateError(null)}
                  />
                )}
                {populateExplanation && (
                  <Alert
                    type="success"
                    showIcon
                    message={
                      <>
                        <strong>AI updated:</strong> {populateExplanation}
                      </>
                    }
                    style={{ marginTop: 8 }}
                    closable
                    onClose={() => setPopulateExplanation(null)}
                  />
                )}
                {advancedMode && (
                  <div style={{ marginTop: 8, fontSize: 12, color: "rgba(0,0,0,0.45)" }}>
                    This rule's condition has nested (OR/NOT) logic, so it's shown as raw JSON below — the AI's
                    other field changes (title, effect, scope, etc.) are included there too.
                  </div>
                )}
              </div>
            )}
          </Form>
          {advancedMode ? (
            <Form.Item label="Candidate rule (canonical rule JSON)">
              <TextArea rows={20} value={advancedJson} onChange={(e) => setAdvancedJson(e.target.value)} spellCheck={false} />
            </Form.Item>
          ) : (
            <Form layout="vertical">
              <Form.Item label="Title" required>
                <Input value={title} onChange={(e) => setTitle(e.target.value)} />
              </Form.Item>
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item label="Rule type">
                    <Select value={ruleType} onChange={setRuleType} options={RULE_TYPES.map((t) => ({ value: t, label: t }))} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="Category">
                    <Input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="HR, Finance, IT…" />
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
                <Col span={10}>
                  <Form.Item label="Effect action" required>
                    <Input value={effectAction} onChange={(e) => setEffectAction(e.target.value)} />
                  </Form.Item>
                </Col>
                <Col span={6}>
                  <Form.Item label="Priority">
                    <InputNumber style={{ width: "100%" }} value={priority} onChange={(v) => setPriority(Number(v ?? 0))} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="Effective from" required>
                    <DatePicker
                      style={{ width: "100%" }}
                      value={effectiveFrom ? dayjs(effectiveFrom) : null}
                      onChange={(d) => setEffectiveFrom(d ? d.format("YYYY-MM-DD") : "")}
                    />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="Effective to">
                    <DatePicker
                      style={{ width: "100%" }}
                      value={effectiveTo ? dayjs(effectiveTo) : null}
                      onChange={(d) => setEffectiveTo(d ? d.format("YYYY-MM-DD") : "")}
                      allowClear
                    />
                  </Form.Item>
                </Col>
                <Col span={24}>
                  <Form.Item label="Tags (comma-separated)">
                    <Input value={tagsText} onChange={(e) => setTagsText(e.target.value)} placeholder="leave, pregnancy, annual-cap" />
                  </Form.Item>
                </Col>
              </Row>

              <ScopeFieldsEditor
                scope={scope}
                onScopeChange={setScope}
                isExplicitOverride={isExplicitOverride}
                onIsExplicitOverrideChange={setIsExplicitOverride}
                supersedesRuleIds={supersedesRuleIds}
                onSupersedesRuleIdsChange={setSupersedesRuleIds}
                supersedeCandidates={supersedeCandidates}
                groupLabel={groupLabel}
                onGroupLabelChange={setGroupLabel}
                existingGroupLabels={existingGroupLabels}
                relatedRuleIds={relatedRuleIds}
                onRelatedRuleIdsChange={setRelatedRuleIds}
              />

              <Form.Item label="Condition (AND of comparisons — switch to Advanced mode for OR/NOT/nested logic)">
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
                      {conditionRows.length > 1 && <Button onClick={() => removeConditionRow(i)}>✕</Button>}
                    </Space.Compact>
                  ))}
                  <Button icon={<PlusOutlined />} onClick={addConditionRow}>
                    Add condition
                  </Button>
                </Space>
              </Form.Item>
            </Form>
          )}

          {!isRevise && (
            <Form.Item label="Reason for this edit (optional, recorded on the rule's discussion trail)">
              <Input
                value={editNote}
                onChange={(e) => setEditNote(e.target.value)}
                placeholder="e.g. corrected the cap from 60 to 70 days per Finance"
              />
            </Form.Item>
          )}
                  </>
                ),
              },
              {
                key: "evaluate",
                label: "AI Evaluate",
                children: (
                  <div>
                    <Alert
                      type="warning"
                      showIcon
                      message="AI advisory only — not a real evaluation"
                      description="This uses AI reasoning to sanity-check wording against a scenario. It does not run the deterministic evaluation engine and its verdict isn't authoritative — use the Evaluate page for production-grade results."
                      style={{ marginBottom: 16 }}
                    />
                    <Form layout="vertical">
                      <Form.Item label="Describe a scenario in plain English">
                        <TextArea
                          rows={3}
                          value={scenario}
                          onChange={(e) => setScenario(e.target.value)}
                          placeholder="e.g. A contractor with 15 working days requests a permanent device"
                        />
                      </Form.Item>
                    </Form>
                    <Space style={{ marginBottom: 16 }}>
                      <Text type="secondary">Reasoning effort</Text>
                      <Select
                        value={reasoningEffort}
                        onChange={(v) => setReasoningEffort(v as typeof reasoningEffort)}
                        style={{ width: 120 }}
                        options={[
                          { value: "low", label: "Low" },
                          { value: "medium", label: "Medium" },
                          { value: "high", label: "High" },
                        ]}
                      />
                      <Button
                        type="primary"
                        icon={<ThunderboltOutlined />}
                        onClick={handleEvaluateScenario}
                        loading={evaluating}
                        disabled={!scenario.trim()}
                      >
                        {evaluating ? "Reasoning…" : "Evaluate with AI"}
                      </Button>
                    </Space>
                    {evalError && <Alert type="error" showIcon message={evalError} style={{ marginBottom: 16 }} />}
                    {evalResult && (
                      <div>
                        <Space style={{ marginBottom: 8 }}>
                          <Tag
                            color={
                              evalResult.applies === "yes" ? "green" : evalResult.applies === "no" ? "red" : "gold"
                            }
                          >
                            {evalResult.applies.toUpperCase()}
                          </Tag>
                          <Tag>Reasoning effort: {evalResult.reasoning_effort}</Tag>
                        </Space>
                        <Paragraph>{evalResult.reasoning}</Paragraph>
                        <Paragraph>
                          <Text strong>Predicted outcome: </Text>
                          {evalResult.predicted_outcome}
                        </Paragraph>
                        {evalResult.missing_facts.length > 0 && (
                          <Paragraph>
                            <Text strong>Missing facts: </Text>
                            <Space wrap>
                              {evalResult.missing_facts.map((f) => (
                                <Tag key={f}>{f}</Tag>
                              ))}
                            </Space>
                          </Paragraph>
                        )}
                      </div>
                    )}
                  </div>
                ),
              },
            ]}
          />
        </Col>

        <Col span={12}>
          <Paragraph type="secondary" style={{ marginBottom: 6 }}>
            <Text strong>Live preview</Text>
          </Paragraph>
          {previewRule ? (
            <RuleCard rule={previewRule} defaultExpanded hideNotes />
          ) : (
            <Alert type="warning" showIcon message="Fix the JSON above to see a preview." />
          )}
        </Col>
      </Row>
    </Modal>
  );
}
