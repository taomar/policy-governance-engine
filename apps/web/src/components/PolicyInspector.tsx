import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Button, Collapse, Descriptions, Empty, List, Segmented, Space, Tabs, Tag, Tooltip, Typography } from "antd";
import {
  ApartmentOutlined,
  BarChartOutlined,
  BranchesOutlined,
  CodeOutlined,
  CrownOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  ExpandOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  FullscreenExitOutlined,
  FullscreenOutlined,
  MenuFoldOutlined,
  NodeIndexOutlined,
  ReadOutlined,
  ToolOutlined,
  UserOutlined,
} from "@ant-design/icons";
import type { AggregateLimit, ApprovedPolicyVersion, CanonicalRule, Clause, NoteEntityType } from "../api";
import { resolveClausesById } from "../clauseCache";
import { resolveDocumentMetaByVersionId, type DocumentMeta } from "../documentMetaCache";
import { ConditionView } from "./ConditionView";
import { SemanticProjectionView, hasSemanticProjection } from "./SemanticProjectionView";
import { DecisionReadinessView } from "./DecisionReadinessView";
import { JsonView } from "./JsonView";
import { withRuleIdentity } from "../ruleIdentity";
import { NotesPanel } from "./NotesPanel";
import { DocumentBodyDrawer } from "./DocumentBodyDrawer";
import { PolicyEffectBadge } from "./PolicyEffectBadge";
import { RuleScenarioTester } from "./RuleScenarioTester";
import { RuleVersionHistory } from "./RuleVersionHistory";
import { ruleTypeLabel } from "../ruleTypes";
import { colorForCategory } from "../policyCategories";
import {
  ambiguityMeta,
  findRuleVariations,
  formatConditionValue,
  hasAmbiguityFlag,
  isEmptyCondition,
  readableDescription,
  ruleDecisionSummary,
  scopeEntries,
} from "../ruleDisplay";

const { Text, Paragraph, Title } = Typography;

interface PolicyInspectorProps {
  rule: CanonicalRule | null;
  /** Every rule in the current version (unfiltered by search/facets) — used
   * to resolve `related_rule_ids`/`supersedes_rule_ids` into clickable links
   * and to compute the heuristic "variations" cluster. Defaults to empty so
   * existing callers keep working without it (the relationship UI simply
   * falls back to plain, non-clickable IDs in that case). */
  allRules?: CanonicalRule[];
  aggregateLimits?: AggregateLimit[];
  /** The published version this rule belongs to — supplies the History
   * tab's approval/publish record. Omit if not yet loaded. */
  publishedVersion?: ApprovedPolicyVersion | null;
  /** Every published version of this policy set (any order) — lets the
   * History tab find the version immediately prior to `publishedVersion`
   * and show what changed for this specific rule since then. Omit to hide
   * that section (falls back to just the existing publish-record display). */
  versions?: ApprovedPolicyVersion[];
  /** The owning policy set's key — required by the "Test scenario" tab to
   * call the real-engine-backed scenario endpoint. Omit only if that tab
   * should be hidden (e.g. no policy set context is available yet). */
  policySetKey?: string;
  activeTabKey: string;
  onTabChange: (key: string) => void;
  onRevise?: (rule: CanonicalRule) => void;
  /** Jump the master/detail view to another rule — wired to clickable
   * relationship/variation references so "linked to other policy" is an
   * actual navigation, not just an ID to copy and search for by hand. */
  onSelectRule?: (rule: CanonicalRule) => void;
  /** Shown only in narrower (drawer/full-screen) layouts to dismiss the inspector. */
  onClose?: () => void;
  /** Desktop workspace action: hide the inspector and give the full width to the policy list. */
  onHide?: () => void;
  /** Desktop workspace action: promote the inspector to a viewport-sized focus surface. */
  onToggleFullscreen?: () => void;
  isFullscreen?: boolean;
  /** Review-specific metadata rendered beside the rule's immutable identity. */
  contextMeta?: ReactNode;
  /** Review workflow actions (AI, edit, approve/reject) rendered after source actions. */
  additionalActions?: ReactNode;
  /** Extra review record content placed at the top of Overview. */
  overviewSupplement?: ReactNode;
  /** Override the default published-rule discussion target for candidate review. */
  notesTarget?: { entityType: NoteEntityType; entityId: string; title: string };
  recordKind?: "published" | "candidate";
  recordLabel?: string;
  readOnly?: boolean;
}

/**
 * The "detail" half of the master/detail workspace: everything RuleCard used
 * to show inline, reorganized into Overview / Logic / Scope / History /
 * Notes tabs so a single rule's full depth is available without forcing
 * every other row in the list to grow to accommodate it.
 */
export function PolicyInspector({
  rule,
  allRules = [],
  aggregateLimits,
  publishedVersion,
  versions,
  policySetKey,
  activeTabKey,
  onTabChange,
  onRevise,
  onSelectRule,
  onClose,
  onHide,
  onToggleFullscreen,
  isFullscreen = false,
  contextMeta,
  additionalActions,
  overviewSupplement,
  notesTarget,
  recordKind = "published",
  recordLabel = "policy",
  readOnly = false,
}: PolicyInspectorProps) {
  const [clausesById, setClausesById] = useState<Map<string, Clause>>(new Map());
  const [docMetaByVersionId, setDocMetaByVersionId] = useState<Map<string, DocumentMeta>>(new Map());
  const [bodyViewer, setBodyViewer] = useState<{ documentVersionId: string; clauseId: string | null; page: number | null } | null>(null);
  const [jsonVariant, setJsonVariant] = useState<"evaluator" | "canonical" | "dmn">("evaluator");

  useEffect(() => {
    setBodyViewer(null);
    if (!rule) return;
    const docVersionIds = rule.evidence.map((ev) => ev.document_version_id).filter(Boolean);
    if (docVersionIds.length === 0) return;
    let cancelled = false;
    resolveClausesById(docVersionIds).then((byId) => {
      if (!cancelled) setClausesById(byId);
    });
    resolveDocumentMetaByVersionId(docVersionIds).then((byId) => {
      if (!cancelled) setDocMetaByVersionId(byId);
    });
    return () => {
      cancelled = true;
    };
    // rule_revision (not evidence.length) is the correct re-fetch trigger: a rule's evidence
    // is immutable within a revision and only ever changes together with a revision bump, so
    // this correctly re-resolves clauses/doc-meta even when a new revision happens to carry
    // the same evidence *count* but different citations.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rule?.rule_id, rule?.rule_revision]);

  const primaryEvidence = useMemo(() => {
    if (!rule) return undefined;
    const withClause = rule.evidence.find((ev) => ev.clause_id && clausesById.has(ev.clause_id));
    if (withClause) return withClause;
    return rule.evidence.find((ev) => ev.document_version_id);
  }, [rule, clausesById]);
  const evidenceStillResolving = !!rule && rule.evidence.length > 0 && !primaryEvidence;
  const activeDocMeta = bodyViewer ? docMetaByVersionId.get(bodyViewer.documentVersionId) : undefined;

  const contributions = useMemo(() => {
    if (!rule) return [];
    return (aggregateLimits ?? []).filter((agg) => agg.contributing_rules.some((c) => c.rule_id === rule.rule_id));
  }, [rule, aggregateLimits]);

  const rulesById = useMemo(() => new Map(allRules.map((r) => [r.rule_id, r])), [allRules]);

  // Heuristic "other rules that look like variations of this same decision" cluster — see
  // findRuleVariations' doc comment for exactly what it does and does not do (display-only,
  // never touches group_label/related_rule_ids).
  const variations = useMemo(() => (rule ? findRuleVariations(rule, allRules) : null), [rule, allRules]);

  // Deduped "which source document(s)" labels for this rule's evidence, shared by the JSON
  // tab's extraction-record banner below. Source text extracted verbatim from a document (e.g.
  // "this Law", "this policy", "this Agreement") is meaningless on its own once it is lifted out
  // of that document into an AI extraction record — so every place that shows the raw formulator
  // output must restate which source document it came from, not just the Evidence tab. Generic
  // ("source document"), never "law" — a rule here can equally come from an HR handbook, an IT
  // policy, or a procurement manual.
  const sourceLabels = useMemo(() => {
    if (!rule) return [];
    const seen = new Set<string>();
    const labels: string[] = [];
    for (const ev of rule.evidence) {
      const docMeta = docMetaByVersionId.get(ev.document_version_id);
      const clause = ev.clause_id ? clausesById.get(ev.clause_id) : undefined;
      const label = `${docMeta ? `${docMeta.documentTitle} (${docMeta.versionLabel})` : "Document"}${
        ev.section ? ` · ${ev.section}` : ""
      }${ev.page !== null ? `, p.${ev.page}` : ""}${clause ? ` · clause ${clause.clause_ref}` : ""}`;
      if (!seen.has(label)) {
        seen.add(label);
        labels.push(label);
      }
    }
    return labels;
  }, [rule, docMetaByVersionId, clausesById]);

  /** Renders a list of rule IDs (from `related_rule_ids`/`supersedes_rule_ids`) as clickable
   * jump-to-rule tags when the target is resolvable in the current version's rule set,
   * falling back to a plain copyable ID otherwise (e.g. a dangling/out-of-version reference). */
  const renderRuleRefs = (ids: string[]) => (
    <Space size={4} wrap>
      {ids.map((rid) => {
        const target = rulesById.get(rid);
        if (target && onSelectRule) {
          return (
            <Tag
              key={rid}
              className="rule-ref-tag"
              onClick={() => onSelectRule(target)}
              title={`${rid} — jump to this rule`}
            >
              {target.title}
            </Tag>
          );
        }
        return (
          <Text key={rid} code copyable={{ text: rid }} type="secondary">
            <Tooltip title="Referenced rule not found in this version (renamed, superseded, or from a different policy set)">
              {rid}
            </Tooltip>
          </Text>
        );
      })}
    </Space>
  );

  if (!rule) {
    return (
      <div className="policy-inspector policy-inspector-empty">
        <Empty description="Select a policy from the list to see its full details" />
      </div>
    );
  }

  const decision = ruleDecisionSummary(rule);

  // Rendered in two places on purpose: collapsed at the foot of Overview so
  // the machine-readable form is reachable without leaving the summary, and
  // uncapped in its own tab for actually reading a long rule in this narrow
  // panel. Same component, so they can never drift apart.
  //
  // Carries the same `_identity` block as the canonical and DMN views so all
  // three downloads name the rule, its documents, and its Search keys
  // identically — the rule body alone never mentioned Search at all.
  const ruleJson = withRuleIdentity(rule, rule);
  const overviewJsonBlock = <JsonView value={ruleJson} downloadName={`${rule.rule_id}.json`} maxHeight={420} />;

  const overview = (
    <div className="inspector-pane">
      {rule.description && (
        <Paragraph type="secondary">{readableDescription(rule.description)}</Paragraph>
      )}
      {overviewSupplement}
      <Descriptions column={1} size="small" bordered className="inspector-descriptions">
        <Descriptions.Item label="Rule ID">
          <Text code copyable={{ text: rule.rule_id }}>
            {rule.rule_id}
          </Text>
        </Descriptions.Item>
        <Descriptions.Item label="Policy ID (set)">
          <Text code copyable={{ text: rule.policy_set_id }}>
            {rule.policy_set_id}
          </Text>
        </Descriptions.Item>
        {recordKind === "published" && (
          <Descriptions.Item label="Published version ID">
            <Text code copyable={{ text: rule.policy_version_id }}>
              {rule.policy_version_id}
            </Text>
          </Descriptions.Item>
        )}
        <Descriptions.Item label="Priority">{rule.priority}</Descriptions.Item>
        <Descriptions.Item label="Set by">
          {rule.authority.owner} <Text type="secondary">({rule.authority.level}, rank {rule.authority.rank})</Text>
        </Descriptions.Item>
        <Descriptions.Item label="Effective from">{rule.effective_from}</Descriptions.Item>
        <Descriptions.Item label="Effective to">{rule.effective_to ?? "—"}</Descriptions.Item>
        {(rule.is_explicit_override ||
          rule.supersedes_rule_ids.length > 0 ||
          rule.related_rule_ids.length > 0 ||
          rule.group_label) && (
          <Descriptions.Item label="Relationships">
            <Space direction="vertical" size={4} style={{ width: "100%" }}>
              {rule.is_explicit_override && (
                <Tag color="purple" icon={<CrownOutlined />} bordered={false}>
                  Explicit override
                </Tag>
              )}
              {rule.supersedes_rule_ids.length > 0 && (
                <div className="inspector-relationship-line">
                  <Text type="secondary">Supersedes:</Text> {renderRuleRefs(rule.supersedes_rule_ids)}
                </div>
              )}
              {rule.related_rule_ids.length > 0 && (
                <div className="inspector-relationship-line">
                  <Text type="secondary">Related to:</Text> {renderRuleRefs(rule.related_rule_ids)}
                </div>
              )}
              {rule.group_label && (
                <Text type="secondary" className="inspector-relationship-line">
                  <ApartmentOutlined /> Variation group: <Text strong>{rule.group_label}</Text>
                </Text>
              )}
            </Space>
          </Descriptions.Item>
        )}
      </Descriptions>

      {rule.related_rule_ids.length > 0 && (
        <div className="rule-card-section">
          <Text strong className="rule-card-section-title">
            <ApartmentOutlined /> Decided together with
          </Text>
          <Paragraph type="secondary" className="inspector-decided-with-intro">
            {rule.related_rule_ids.length + 1} rules state this topic
            {rule.group_label ? ` — “${rule.group_label}”` : ""}. They come from the same document
            and are reviewed as one set, so approving this one alone can leave the topic
            half-decided.
          </Paragraph>
          <div className="inspector-decided-with">
            {rule.related_rule_ids.map((rid) => {
              const sibling = rulesById.get(rid);
              if (!sibling) {
                return (
                  <div key={rid} className="inspector-decided-with-row">
                    <Text code copyable={{ text: rid }} type="secondary">
                      {rid}
                    </Text>
                    <Text type="secondary">not in this version</Text>
                  </div>
                );
              }
              return (
                <div key={rid} className="inspector-decided-with-row">
                  <button
                    type="button"
                    className="inspector-decided-with-link"
                    onClick={() => onSelectRule?.(sibling)}
                    disabled={!onSelectRule}
                  >
                    {sibling.title}
                  </button>
                  <Space size={4} wrap>
                    <Tag bordered={false}>{sibling.review_status}</Tag>
                  </Space>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="rule-card-section">
        <Text strong className="rule-card-section-title">
          <ReadOutlined /> Original source text — the exact words from the source document
        </Text>
        {rule.evidence.length === 0 ? (
          <div className="evidence-empty-block">
            <Text type="secondary">
              No source citation on this rule — it was manually authored or drafted without a linked source
              document, so there is no original wording to quote.
            </Text>
          </div>
        ) : (
          <Space direction="vertical" size={10} style={{ width: "100%" }}>
            {rule.evidence.map((ev, idx) => {
              const clause = ev.clause_id ? clausesById.get(ev.clause_id) : undefined;
              const docMeta = docMetaByVersionId.get(ev.document_version_id);
              return (
                <div key={idx} className="evidence-block">
                  <Text type="secondary" className="evidence-line">
                    <FileTextOutlined />{" "}
                    {docMeta ? `${docMeta.documentTitle} (${docMeta.versionLabel})` : "Document"}
                    {ev.section ? ` · ${ev.section}` : ""}
                    {ev.page !== null ? `, p.${ev.page}` : ""}
                    {clause ? ` · clause ${clause.clause_ref}` : ""}
                  </Text>
                  <div className="evidence-provenance-grid">
                    <div>
                      <span>Document version ID</span>
                      <Text code copyable={{ text: ev.document_version_id }}>
                        {ev.document_version_id}
                      </Text>
                    </div>
                    {ev.clause_id && (
                      <div>
                        <span>Clause ID</span>
                        <Text code copyable={{ text: ev.clause_id }}>
                          {ev.clause_id}
                        </Text>
                      </div>
                    )}
                    {clause?.element_id && (
                      <div>
                        <span>Source element</span>
                        <Text code>{clause.element_id}</Text>
                      </div>
                    )}
                    {clause?.search_document_id && (
                      <div className="evidence-provenance-search">
                        <span>Azure AI Search ID · {clause.search_index}</span>
                        <Text code copyable={{ text: clause.search_document_id }}>
                          {clause.search_document_id}
                        </Text>
                      </div>
                    )}
                  </div>
                  {clause ? (
                    <div className="evidence-quote-box">
                      <Paragraph
                        className="evidence-quote-text"
                        ellipsis={{ rows: 3, expandable: true, symbol: "show full text" }}
                      >
                        “{clause.text}”
                      </Paragraph>
                      <Button
                        type="link"
                        size="small"
                        className="evidence-context-link"
                        icon={<ExpandOutlined />}
                        onClick={() =>
                          setBodyViewer({ documentVersionId: ev.document_version_id, clauseId: clause.id, page: ev.page ?? null })
                        }
                      >
                        View in full document
                      </Button>
                    </div>
                  ) : (
                    <div className="evidence-quote-missing-block">
                      <Text type="secondary" className="evidence-quote-missing">
                        {ev.clause_id
                          ? "Loading original text…"
                          : "No highlighted excerpt for this citation — the document and page reference below are still accurate."}
                      </Text>
                      {!ev.clause_id && (
                        <Button
                          type="link"
                          size="small"
                          className="evidence-context-link"
                          icon={<ExpandOutlined />}
                          onClick={() =>
                            setBodyViewer({ documentVersionId: ev.document_version_id, clauseId: null, page: ev.page ?? null })
                          }
                        >
                          View source document
                        </Button>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </Space>
        )}
      </div>

      <Collapse
        className="inspector-technical-collapse inspector-json-collapse"
        items={[
          {
            key: "json",
            label: (
              <span className="inspector-json-collapse-label">
                <CodeOutlined /> Canonical rule JSON — exactly what the evaluator reads
              </span>
            ),
            children: overviewJsonBlock,
          },
        ]}
      />
    </div>
  );

  const logic = (
    <div className="inspector-pane">
      {(rule.is_explicit_override || rule.supersedes_rule_ids.length > 0) && (
        <div className="rule-card-section precedence-band">
          <Text strong className="rule-card-section-title">
            <CrownOutlined /> Precedence
          </Text>
          <Space direction="vertical" size={6} style={{ width: "100%" }}>
            {rule.is_explicit_override && <Tag color="purple">Explicit override — outranks otherwise-applicable rules</Tag>}
            {rule.supersedes_rule_ids.length > 0 && (
              <div className="rule-card-scope">
                <Text type="secondary">Supersedes:</Text> {renderRuleRefs(rule.supersedes_rule_ids)}
              </div>
            )}
          </Space>
        </div>
      )}

      <div className="rule-card-section">
        <Text strong className="rule-card-section-title">
          Condition — when this rule fires
        </Text>
        <div className="cond-box">
          {isEmptyCondition(rule.condition) ? (
            hasSemanticProjection(rule) ? (
              <SemanticProjectionView rule={rule} />
            ) : (
              <Text type="secondary">
                No conditions were derived. The rule may genuinely be unconditional, or its scope
                may have been missed during extraction — a reviewer must decide which.
              </Text>
            )
          ) : (
            <ConditionView node={rule.condition} />
          )}
        </div>
      </div>

      {rule.required_facts.length > 0 && (
        <div className="rule-card-section">
          <Text strong className="rule-card-section-title">
            Required facts
          </Text>
          <Space size={6} wrap>
            {rule.required_facts.map((f) => (
              <Tag key={f.name} bordered={false} className="fact-tag">
                {f.name}
                <span className="fact-type">{f.data_type}</span>
                {!f.required && <span className="fact-optional">optional</span>}
              </Tag>
            ))}
          </Space>
        </div>
      )}

      {rule.exceptions.length > 0 && (
        <div className="rule-card-section">
          <Text strong className="rule-card-section-title">
            <BranchesOutlined /> Exceptions — carve-outs, escalation & special-case routes
          </Text>
          <List
            size="small"
            dataSource={rule.exceptions}
            renderItem={(exc) => (
              <List.Item key={exc.exception_id}>
                <div className="exception-item">
                  <div className="exception-item-headline">
                    <Text>{exc.description}</Text>
                    {exc.limit_value !== null && exc.limit_value !== undefined && (
                      <Tag color="blue" className="exception-limit-tag">
                        limit: {exc.limit_value} {exc.limit_unit ?? ""}
                      </Tag>
                    )}
                  </div>
                  {exc.condition && (
                    <div className="cond-box cond-box-nested">
                      <Text type="secondary" className="exception-condition-label">
                        Applies when:
                      </Text>
                      <ConditionView node={exc.condition} />
                    </div>
                  )}
                  {exc.effect_override && <PolicyEffectBadge effect={exc.effect_override} />}
                </div>
              </List.Item>
            )}
          />
        </div>
      )}

      {contributions.length > 0 && (
        <div className="rule-card-section">
          <Text strong className="rule-card-section-title">
            <BarChartOutlined /> Counts toward a combined cap
          </Text>
          <Space direction="vertical" size={8} style={{ width: "100%" }}>
            {contributions.map((agg) => (
              <div key={agg.aggregate_id} className="aggregate-contribution-box">
                <Text>{agg.description || agg.aggregate_id}</Text>
                <div>
                  <Tag color="geekblue">
                    combined max {agg.max_value}
                    {agg.period ? ` / ${agg.period}` : ""}
                  </Tag>
                  <Text type="secondary" className="rule-card-scope">
                    shared with{" "}
                    {agg.contributing_rules
                      .filter((c) => c.rule_id !== rule.rule_id)
                      .map((c, i) => (
                        <Text key={c.rule_id} code copyable={{ text: c.rule_id }}>
                          {i > 0 ? ", " : ""}
                          {c.rule_id}
                        </Text>
                      ))}
                  </Text>
                </div>
              </div>
            ))}
          </Space>
        </div>
      )}
    </div>
  );

  const scope = (
    <div className="inspector-pane">
      <div className="rule-card-section">
        <Text strong className="rule-card-section-title">
          <UserOutlined /> Applies to
        </Text>
        <div className="inspector-scope-grid">
          {scopeEntries(rule.scope).map((entry) => (
            <div key={entry.label} className="inspector-scope-item">
              <Text type="secondary" className="inspector-scope-label">
                {entry.label}
              </Text>
              <Text className={entry.isDefault ? "inspector-scope-value-default" : undefined}>{entry.value}</Text>
            </div>
          ))}
        </div>
      </div>

      {(rule.tags.length > 0 || rule.group_label || rule.related_rule_ids.length > 0) && (
        <div className="rule-card-section">
          <Text strong className="rule-card-section-title">
            Classification
          </Text>
          <Space direction="vertical" size={6} style={{ width: "100%" }}>
            {rule.tags.length > 0 && (
              <Space size={4} wrap>
                {rule.tags.map((t) => (
                  <Tag key={t} bordered={false} className="fact-tag">
                    {t}
                  </Tag>
                ))}
              </Space>
            )}
            {rule.group_label && (
              <Text type="secondary" className="rule-card-scope">
                <ApartmentOutlined /> Variation group: <Text strong>{rule.group_label}</Text>
              </Text>
            )}
            {rule.related_rule_ids.length > 0 && (
              <div className="rule-card-scope">
                <Text type="secondary">
                  <ApartmentOutlined /> Related rules:
                </Text>{" "}
                {renderRuleRefs(rule.related_rule_ids)}
              </div>
            )}
          </Space>
        </div>
      )}
    </div>
  );

  const history = (
    <div className="inspector-pane">
      {policySetKey && versions && versions.length > 0 && (
        <div className="rule-card-section">
          <Text strong className="rule-card-section-title">
            <BranchesOutlined /> Version history — what changed for this rule
          </Text>
          <RuleVersionHistory
            policySetKey={policySetKey}
            rule={rule}
            versions={versions}
            currentVersionNumber={publishedVersion?.version_number ?? null}
          />
        </div>
      )}

      <Descriptions column={1} size="small" bordered className="inspector-descriptions">
        <Descriptions.Item label="Current revision">rev {rule.rule_revision}</Descriptions.Item>
        {publishedVersion && (
          <>
            <Descriptions.Item label="Published version">v{publishedVersion.version_number}</Descriptions.Item>
            <Descriptions.Item label="Approved by">{publishedVersion.approved_by}</Descriptions.Item>
            <Descriptions.Item label="Approved at">
              {new Date(publishedVersion.approved_at).toLocaleString()}
            </Descriptions.Item>
            <Descriptions.Item label="Version effective">
              {publishedVersion.effective_from} → {publishedVersion.effective_to ?? "open-ended"}
            </Descriptions.Item>
          </>
        )}
      </Descriptions>

      <Collapse
        className="inspector-technical-collapse"
        items={[
          {
            key: "technical",
            label: "Technical metadata",
            children: (
              <Descriptions size="small" column={1} bordered className="rule-card-descriptions">
                <Descriptions.Item label="Policy set ID">
                  <Text className="entity-id-row" copyable={{ text: rule.policy_set_id }}>
                    {rule.policy_set_id}
                  </Text>
                </Descriptions.Item>
                <Descriptions.Item label="Policy version ID">
                  <Text className="entity-id-row" copyable={{ text: rule.policy_version_id }}>
                    {rule.policy_version_id}
                  </Text>
                </Descriptions.Item>
                <Descriptions.Item label="Rule ID">
                  <Text className="entity-id-row" copyable={{ text: rule.rule_id }}>
                    {rule.rule_id}
                  </Text>
                </Descriptions.Item>
                {rule.lineage.extraction_run_id && (
                  <Descriptions.Item label="AI extraction run ID">
                    <Text className="entity-id-row" copyable={{ text: rule.lineage.extraction_run_id }}>
                      {rule.lineage.extraction_run_id}
                    </Text>
                  </Descriptions.Item>
                )}
              </Descriptions>
            ),
          },
        ]}
      />
    </div>
  );

  const notes = (
    <div className="inspector-pane">
      <NotesPanel
        entityType={notesTarget?.entityType ?? "rule"}
        entityId={notesTarget?.entityId ?? rule.rule_id}
        title={notesTarget?.title ?? "Notes on this rule"}
      />
    </div>
  );

  // Only renderable with a policySetKey (needed for the real-engine lookup) —
  // callers that don't yet have one (rare; mainly narrower/legacy call sites)
  // simply don't get this tab rather than showing a broken one.
  const testScenario = policySetKey && !readOnly ? <RuleScenarioTester policySetKey={policySetKey} rule={rule} /> : null;

  const activeJsonVariant = rule.formulation ? jsonVariant : "evaluator";
  const jsonVariants = {
    complete: {
      title: "Complete record",
      description: (
        <>
          Everything extracted from this clause in one place — the source text, the canonical
          decomposition with every attribute the document supported, the derived logic, and the DMN
          projection.
        </>
      ),
      value: {
        rule_id: rule.rule_id,
        title: rule.title,
        // The document's own words, first, because everything below is a
        // reading of them.
        source_text: rule.formulation?.canonical?.source_text ?? rule.description,
        rule_type: rule.rule_type,
        effect: rule.effect,
        // The full attribute set: subject, parties, trigger, condition,
        // thresholds, deadlines, exceptions and the rest, exactly as extracted.
        canonical: rule.formulation?.canonical ?? null,
        // How those attributes were read as logic.
        logic: {
          condition: rule.condition,
          required_facts: rule.required_facts,
          exceptions: rule.exceptions,
        },
        // The decision projection, as the formulator produced it.
        dmn: rule.formulation?.dmn_decisions ?? [],
        parties_and_readiness: rule.decision_readiness ?? null,
        scope: rule.scope,
        evidence: rule.evidence,
        relationships: {
          related_rule_ids: rule.related_rule_ids,
          group_label: rule.group_label,
        },
        lineage: rule.lineage,
      },
      downloadName: `${rule.rule_id}-complete.json`,
    },
    evaluator: {
      title: "Evaluator record",
      description: (
        <>
          The stored <Text code>CanonicalRule</Text> consumed by the deterministic evaluator. Nothing is inferred at
          evaluation time.
        </>
      ),
      value: ruleJson,
      downloadName: `${rule.rule_id}.json`,
    },
    canonical: {
      title: "Canonical formulation",
      description: (
        <>
          The source-grounded decomposition: subject, predicate, object and every qualifying
          attribute the document supplied.
        </>
      ),
      value: rule.formulation?.canonical ? withRuleIdentity(rule.formulation.canonical, rule) : null,
      downloadName: `${rule.rule_id}-canonical.json`,
    },
    dmn: {
      title: "DMN / FEEL projection",
      description: (
        <>
          The paired OMG DMN 1.5 decision projection and FEEL mapping produced by the formulator.
        </>
      ),
      value: rule.formulation
        ? withRuleIdentity({ dmn_decisions: rule.formulation.dmn_decisions }, rule)
        : null,
      downloadName: `${rule.rule_id}-dmn.json`,
    },
  } satisfies Record<string, { title: string; description: ReactNode; value: unknown; downloadName: string }>;
  const selectedJson = jsonVariants[activeJsonVariant];

  // The evaluator record and both formulation artifacts are peers. They used
  // to be stacked vertically, which meant the two original AI artifacts sat
  // below a 100+ line JSON viewer and appeared to have disappeared.
  const json = (
    <div className="inspector-pane inspector-pane--json">
      <div className="json-variant-switcher">
        <Segmented
          block
          value={activeJsonVariant}
          onChange={(value) => setJsonVariant(value as typeof jsonVariant)}
          options={[
            { value: "evaluator", label: "Evaluator JSON" },
            { value: "canonical", label: "Canonical formulation", disabled: !rule.formulation },
            { value: "dmn", label: "DMN / FEEL", disabled: !rule.formulation },
          ]}
        />
      </div>
      {/* One compact line of chrome. The heading repeated the label already on
          the selected segment, and the sentence beneath it explained a record
          the reader is looking straight at — together they cost more height
          than the JSON was given. Provenance stays, because it is the one
          thing here that is not visible in the record itself, but on the same
          row and behind a tooltip rather than a paragraph. */}
      {activeJsonVariant !== "evaluator" && rule.formulation && (
        <div className="json-view-provenance">
          <Tooltip title={selectedJson.description}>
            <Text type="secondary" className="json-view-provenance-label">
              <FileTextOutlined /> Extracted from
            </Text>
          </Tooltip>
          {sourceLabels.length > 0 ? (
            <Space size={4} wrap className="json-view-provenance-list">
              {sourceLabels.map((label) => (
                <Tag key={label}>{label}</Tag>
              ))}
            </Space>
          ) : (
            <Tooltip title="This rule has no linked evidence, so any self-referential wording below (e.g. 'this Law', 'this policy') cannot be resolved to a specific source document.">
              <Text type="secondary">source document unknown — see Evidence tab</Text>
            </Tooltip>
          )}
        </div>
      )}
      {!rule.formulation && (
        <Text type="secondary">
          No AI extraction record stored for this rule. Rules drafted by hand carry no formulator
          output. Rules approved before this record was persisted lost it at publish time and cannot
          have it reconstructed here.
        </Text>
      )}
      <JsonView value={selectedJson.value} downloadName={selectedJson.downloadName} />
    </div>
  );

  return (
    <div className="policy-inspector">
      <div className="policy-inspector-header">
        <div className="policy-inspector-title-row">
          <Title level={5} className="policy-inspector-title">
            {rule.title}
          </Title>
          <span className="policy-row-flags">
            {rule.is_explicit_override && (
              <Tooltip title="Explicit override — outranks otherwise-applicable rules">
                <CrownOutlined className="policy-row-flag policy-row-flag-override" />
              </Tooltip>
            )}
            {hasAmbiguityFlag(rule.ambiguity_status) && (
              <Tooltip title={`Ambiguity: ${ambiguityMeta(rule.ambiguity_status).label}`}>
                <ExclamationCircleOutlined
                  className={`policy-row-flag policy-row-flag-ambiguity policy-row-flag-ambiguity--${ambiguityMeta(rule.ambiguity_status).color}`}
                />
              </Tooltip>
            )}
            {!rule.machine_executable && (
              <Tooltip title="Manual rule — not machine-executable">
                <ToolOutlined className="policy-row-flag" />
              </Tooltip>
            )}
          </span>
          <div className="policy-inspector-window-actions">
            {onHide && (
              <Tooltip title={`Hide details and expand the ${recordLabel} list`}>
                <Button
                  type="text"
                  size="small"
                  icon={<MenuFoldOutlined />}
                  onClick={onHide}
                  aria-label={`Hide ${recordLabel} details`}
                />
              </Tooltip>
            )}
            {onToggleFullscreen && (
              <Tooltip title={isFullscreen ? "Restore workspace view" : `Open ${recordLabel} details full screen`}>
                <Button
                  type="text"
                  size="small"
                  icon={isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
                  onClick={onToggleFullscreen}
                  aria-label={isFullscreen ? "Restore workspace view" : `Open ${recordLabel} details full screen`}
                />
              </Tooltip>
            )}
            {onClose && (
              <Button type="text" size="small" className="policy-inspector-close" onClick={onClose} aria-label="Close details">
                ✕
              </Button>
            )}
          </div>
        </div>
        <Space size={8} wrap className="policy-inspector-subtitle">
          <PolicyEffectBadge effect={rule.effect} />
          <Tag title={rule.rule_type}>{ruleTypeLabel(rule.rule_type)}</Tag>
          {rule.category && <Tag color={colorForCategory(rule.category)}>{rule.category}</Tag>}
          {contextMeta}
          <Text type="secondary" className="rule-card-id" copyable={{ text: rule.rule_id, tooltips: ["Copy rule ID", "Copied!"] }}>
            {rule.rule_id} · rev {rule.rule_revision}
          </Text>
        </Space>
        <div className="policy-inspector-decision" title={decision.text}>
          <span className="policy-decision-key">When</span>
          <span className="policy-decision-value">{decision.condition}</span>
          <span className="policy-decision-arrow">→</span>
          <span className="policy-decision-key">Then</span>
          <span className="policy-decision-result">{decision.action}</span>
        </div>
        {variations && (
          <div className="policy-inspector-variations">
            <Text type="secondary" className="policy-inspector-variations-label">
              <NodeIndexOutlined />{" "}
              {variations.kind === "group" ? (
                <>
                  {variations.members.length} rules in group <Text code>{variations.key}</Text>:
                </>
              ) : (
                <>
                  {variations.members.length} rules decide by <Text code>{variations.key}</Text>:
                </>
              )}
            </Text>
            <Space size={4} wrap className="policy-inspector-variations-list">
              {variations.members.map((m) => {
                const isCurrent = m.rule_id === rule.rule_id;
                const label =
                  variations.kind === "group"
                    ? m.title
                    : formatConditionValue((m.condition as Extract<typeof m.condition, { type: "factComparison" }>).value);
                return (
                  <Tag
                    key={m.rule_id}
                    className={`variation-pill${isCurrent ? " variation-pill--current" : ""}`}
                    onClick={isCurrent || !onSelectRule ? undefined : () => onSelectRule(m)}
                    title={isCurrent ? `${m.title} (currently viewing)` : `${m.title} — jump to this variation`}
                  >
                    {label}
                  </Tag>
                );
              })}
            </Space>
          </div>
        )}
        <Space size={8} className="policy-inspector-actions">
          {rule.evidence.length > 0 && (
            <Button
              size="small"
              icon={<ReadOutlined />}
              onClick={() => {
                if (primaryEvidence) {
                  setBodyViewer({
                    documentVersionId: primaryEvidence.document_version_id,
                    clauseId: primaryEvidence.clause_id ?? null,
                    page: primaryEvidence.page ?? null,
                  });
                }
              }}
              disabled={!primaryEvidence}
              title={
                !primaryEvidence
                  ? evidenceStillResolving
                    ? "Loading source…"
                    : "Source unavailable"
                  : primaryEvidence.clause_id && clausesById.has(primaryEvidence.clause_id)
                    ? "Open the original source document at this rule's clause"
                    : "Open the original source document (no highlighted clause for this citation)"
              }
            >
              View source
            </Button>
          )}
          {onRevise && !readOnly && (
            <Button size="small" icon={<EditOutlined />} onClick={() => onRevise(rule)} title="Draft the next revision of this rule for review">
              Revise
            </Button>
          )}
          {!readOnly && additionalActions}
        </Space>
      </div>

      <Tabs
        activeKey={activeTabKey}
        onChange={onTabChange}
        className="policy-inspector-tabs"
        items={[
          { key: "overview", label: "Overview", children: overview },
          { key: "logic", label: "Logic", children: logic },
          {
            key: "readiness",
            label: (
              <span>
                Parties &amp; readiness
                {(rule.decision_readiness?.parties.length ?? 0) > 0 && (
                  <Tag className="inspector-tab-count">
                    {rule.decision_readiness?.parties.length}
                  </Tag>
                )}
              </span>
            ),
            children: (
              <div className="inspector-pane">
                <DecisionReadinessView rule={rule} />
              </div>
            ),
          },
          { key: "scope", label: "Scope", children: scope },
          ...(testScenario
            ? [
                {
                  key: "test-scenario",
                  label: (
                    <span>
                      <ExperimentOutlined /> Test scenario
                    </span>
                  ),
                  children: testScenario,
                },
              ]
            : []),
          { key: "history", label: "History", children: history },
          ...(!readOnly ? [{ key: "notes", label: "Notes", children: notes }] : []),
          { key: "json", label: "JSON", children: json },
        ]}
      />

      <DocumentBodyDrawer
        open={bodyViewer !== null}
        onClose={() => setBodyViewer(null)}
        documentVersionId={bodyViewer?.documentVersionId ?? null}
        focusClauseId={bodyViewer?.clauseId ?? null}
        focusPage={bodyViewer?.page ?? null}
        documentTitle={activeDocMeta?.documentTitle}
        versionLabel={activeDocMeta?.versionLabel}
      />
    </div>
  );
}
