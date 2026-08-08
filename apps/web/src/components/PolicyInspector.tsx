import { useEffect, useMemo, useState } from "react";
import { Button, Collapse, Descriptions, Empty, List, Space, Tabs, Tag, Tooltip, Typography } from "antd";
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
  NodeIndexOutlined,
  ReadOutlined,
  ToolOutlined,
  UserOutlined,
} from "@ant-design/icons";
import type { AggregateLimit, ApprovedPolicyVersion, CanonicalRule, Clause } from "../api";
import { resolveClausesById } from "../clauseCache";
import { resolveDocumentMetaByVersionId, type DocumentMeta } from "../documentMetaCache";
import { ConditionView } from "./ConditionView";
import { JsonView } from "./JsonView";
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
  humanizeAction,
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
}: PolicyInspectorProps) {
  const [clausesById, setClausesById] = useState<Map<string, Clause>>(new Map());
  const [docMetaByVersionId, setDocMetaByVersionId] = useState<Map<string, DocumentMeta>>(new Map());
  const [bodyViewer, setBodyViewer] = useState<{ documentVersionId: string; clauseId: string | null; page: number | null } | null>(null);

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

  // Rendered in two places on purpose: collapsed at the foot of Overview so
  // the machine-readable form is reachable without leaving the summary, and
  // uncapped in its own tab for actually reading a long rule in this narrow
  // panel. Same component, so they can never drift apart.
  const jsonBlock = <JsonView value={rule} downloadName={`${rule.rule_id}.json`} />;
  const overviewJsonBlock = <JsonView value={rule} downloadName={`${rule.rule_id}.json`} maxHeight={420} />;

  const overview = (
    <div className="inspector-pane">
      {rule.description && <Paragraph type="secondary">{rule.description}</Paragraph>}
      <Descriptions column={1} size="small" bordered className="inspector-descriptions">
        <Descriptions.Item label="Effect">
          <PolicyEffectBadge effect={rule.effect} /> {humanizeAction(rule.effect.action)}
        </Descriptions.Item>
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
          <ConditionView node={rule.condition} />
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
              </Descriptions>
            ),
          },
        ]}
      />
    </div>
  );

  const notes = (
    <div className="inspector-pane">
      <NotesPanel entityType="rule" entityId={rule.rule_id} title="Notes on this rule" />
    </div>
  );

  // Only renderable with a policySetKey (needed for the real-engine lookup) —
  // callers that don't yet have one (rare; mainly narrower/legacy call sites)
  // simply don't get this tab rather than showing a broken one.
  const testScenario = policySetKey ? <RuleScenarioTester policySetKey={policySetKey} rule={rule} /> : null;

  // The canonical machine-executable form. This platform's whole premise is
  // that a policy is a structured rule rather than prose, so exposing the
  // exact object the evaluator consumes is the most direct way to see what a
  // rule actually *is* — and makes it copy-pasteable into a test fixture.
  const json = (
    <div className="inspector-pane">
      <div className="json-view-caption">
        <div className="section-eyebrow">
          <CodeOutlined /> Canonical rule JSON — exactly what the evaluator reads
        </div>
        <Text type="secondary" className="json-view-caption-text">
          This is the stored <Text code>CanonicalRule</Text> for this policy, verbatim. Every decision the evaluator
          makes about this rule comes from these fields — nothing is inferred at evaluation time.
        </Text>
      </div>
      {jsonBlock}

      <div className="json-view-caption" style={{ marginTop: 20 }}>
        <div className="section-eyebrow">
          <CodeOutlined /> AI extraction record — both stages, preserved verbatim
        </div>
        <Text type="secondary" className="json-view-caption-text">
          The formulator agent always produces two paired outputs (spec Section 8, "canonical before executable"):
          the subject/predicate/object <Text code>Canonical JSON</Text> decomposed straight from the source text,
          and a <Text code>DMN JSON</Text> decision projection. The executable form above is a lossy mapping of the
          first — this section shows both originals so you can check the mapping against what the AI actually said.
        </Text>
      </div>
      {rule.formulation && (
        <div className="extraction-source-banner">
          <Text type="secondary" className="extraction-source-banner-label">
            <FileTextOutlined /> Extracted from:
          </Text>
          {sourceLabels.length > 0 ? (
            <Space size={4} wrap>
              {sourceLabels.map((label) => (
                <Tag key={label}>{label}</Tag>
              ))}
            </Space>
          ) : (
            <Tooltip title="This rule has no linked evidence, so any self-referential wording below (e.g. 'this Law', 'this policy') cannot be resolved to a specific source document.">
              <Text type="warning">source document unknown — see Evidence tab</Text>
            </Tooltip>
          )}
        </div>
      )}
      {rule.formulation ? (
        <Collapse
          className="inspector-technical-collapse"
          items={[
            {
              key: "extraction-canonical",
              label: "Canonical JSON — verbatim subject/predicate/object",
              children: (
                <JsonView
                  value={rule.formulation.canonical ?? null}
                  downloadName={`${rule.rule_id}-canonical.json`}
                  maxHeight={420}
                />
              ),
            },
            {
              key: "extraction-dmn",
              label: "DMN JSON — OMG DMN 1.5 / FEEL decision projection",
              children: (
                <JsonView
                  value={rule.formulation.dmn_decisions}
                  downloadName={`${rule.rule_id}-dmn.json`}
                  maxHeight={420}
                />
              ),
            },
          ]}
        />
      ) : (
        <Text type="secondary">
          No AI extraction record — this rule was hand-authored or drafted before the formulator agent existed.
        </Text>
      )}
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
          {onClose && (
            <Button type="text" size="small" className="policy-inspector-close" onClick={onClose} aria-label="Close details">
              ✕
            </Button>
          )}
        </div>
        <Space size={8} wrap className="policy-inspector-subtitle">
          <PolicyEffectBadge effect={rule.effect} />
          <Tag title={rule.rule_type}>{ruleTypeLabel(rule.rule_type)}</Tag>
          {rule.category && <Tag color={colorForCategory(rule.category)}>{rule.category}</Tag>}
          <Text type="secondary" className="rule-card-id" copyable={{ text: rule.rule_id, tooltips: ["Copy rule ID", "Copied!"] }}>
            {rule.rule_id} · rev {rule.rule_revision}
          </Text>
        </Space>
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
            <Space size={4} wrap>
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
          {onRevise && (
            <Button size="small" icon={<EditOutlined />} onClick={() => onRevise(rule)} title="Draft the next revision of this rule for review">
              Revise
            </Button>
          )}
        </Space>
      </div>

      <Tabs
        activeKey={activeTabKey}
        onChange={onTabChange}
        className="policy-inspector-tabs"
        items={[
          { key: "overview", label: "Overview", children: overview },
          { key: "logic", label: "Logic", children: logic },
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
          { key: "notes", label: "Notes", children: notes },
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
