import { useEffect, useMemo, useState } from "react";
import { Button, Collapse, Descriptions, Space, Tag, Typography, List } from "antd";
import {
  FileTextOutlined,
  ApartmentOutlined,
  ExpandOutlined,
  UserOutlined,
  CrownOutlined,
  BranchesOutlined,
  BarChartOutlined,
  ReadOutlined,
  EditOutlined,
} from "@ant-design/icons";
import type { AggregateLimit, CanonicalRule, Clause } from "../api";
import { resolveClausesById } from "../clauseCache";
import { resolveDocumentMetaByVersionId, type DocumentMeta } from "../documentMetaCache";
import { ConditionView } from "./ConditionView";
import { NotesPanel } from "./NotesPanel";
import { DocumentBodyDrawer } from "./DocumentBodyDrawer";
import { ruleTypeLabel } from "../ruleTypes";
import { colorForCategory } from "../policyCategories";
import { ambiguityMeta, describeScope, hasAmbiguityFlag } from "../ruleDisplay";

const { Text, Paragraph } = Typography;

const EFFECT_COLOR: Record<string, string> = {
  allow: "green",
  deny: "red",
  require_action: "gold",
};

interface RuleCardProps {
  rule: CanonicalRule;
  defaultExpanded?: boolean;
  headerActions?: React.ReactNode;
  /** Suppress the Notes sub-panel (e.g. inside a dense bulk list). Defaults to shown. */
  hideNotes?: boolean;
  /** Aggregate limits in scope (usually the whole published version's list) —
   * used only to show, on this rule, which combined caps it feeds into. Pass
   * the full list; RuleCard filters to the ones naming this rule_id. */
  aggregateLimits?: AggregateLimit[];
  /** When set, shows a "Revise" header action that hands the *published*
   * canonical rule back to the caller — used by PoliciesTab to open a
   * pre-filled "create the next revision" form. Omit to hide the action
   * (e.g. when rendering a candidate/draft rule, which is already editable
   * a different way). */
  onRevise?: (rule: CanonicalRule) => void;
}

export function RuleCard({ rule, defaultExpanded, headerActions, hideNotes, aggregateLimits, onRevise }: RuleCardProps) {
  const [clausesById, setClausesById] = useState<Map<string, Clause>>(new Map());
  const [docMetaByVersionId, setDocMetaByVersionId] = useState<Map<string, DocumentMeta>>(new Map());
  const [bodyViewer, setBodyViewer] = useState<{ documentVersionId: string; clauseId: string | null; page: number | null } | null>(null);

  useEffect(() => {
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
    // rule_revision (not evidence.length) is the correct re-fetch trigger — see PolicyInspector's
    // identical effect for the rationale (evidence only changes together with a revision bump).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rule.rule_id, rule.rule_revision]);

  // The evidence item the always-visible "View source" header action jumps
  // to. Prefer one with a resolvable clause (jumps straight to the
  // highlighted excerpt); fall back to any evidence with just a document
  // reference (opens the source document at the right page, without a
  // highlight) rather than leaving the button permanently disabled — a
  // clause link can go stale (source re-processed after the rule was
  // drafted) while the document/page citation itself is still valid.
  const primaryEvidence = useMemo(() => {
    const withClause = rule.evidence.find((ev) => ev.clause_id && clausesById.has(ev.clause_id));
    if (withClause) return withClause;
    return rule.evidence.find((ev) => ev.document_version_id);
  }, [rule.evidence, clausesById]);
  // True only while evidence exists but we haven't yet resolved *any* usable
  // target for it (clause lookup in flight) — distinct from "no evidence",
  // so the header button's tooltip doesn't claim to be loading forever.
  const evidenceStillResolving = rule.evidence.length > 0 && !primaryEvidence;
  const activeDocMeta = bodyViewer ? docMetaByVersionId.get(bodyViewer.documentVersionId) : undefined;

  const header = (
    <Space size={10} wrap className="rule-card-header">
      {headerActions}
      <Text strong>{rule.title}</Text>
      <Tag color={EFFECT_COLOR[rule.effect.type] ?? "default"}>{rule.effect.type}</Tag>
      <Tag title={rule.rule_type}>{ruleTypeLabel(rule.rule_type)}</Tag>
      {rule.category && <Tag color={colorForCategory(rule.category)}>{rule.category}</Tag>}
      {!rule.machine_executable && <Tag color="orange">manual</Tag>}
      {hasAmbiguityFlag(rule.ambiguity_status) && (
        <Tag color={ambiguityMeta(rule.ambiguity_status).color}>{ambiguityMeta(rule.ambiguity_status).label}</Tag>
      )}
      <Text
        type="secondary"
        className="rule-card-id"
        copyable={{ text: rule.rule_id, tooltips: ["Copy rule ID", "Copied!"] }}
        onClick={(e) => e.stopPropagation()}
      >
        {rule.rule_id} · rev {rule.rule_revision}
      </Text>
      <span className="rule-card-header-spacer" />
      {rule.evidence.length > 0 && (
        <Button
          size="small"
          icon={<ReadOutlined />}
          className="rule-card-header-action"
          onClick={(e) => {
            e.stopPropagation();
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
        <Button
          size="small"
          icon={<EditOutlined />}
          className="rule-card-header-action"
          onClick={(e) => {
            e.stopPropagation();
            onRevise(rule);
          }}
          title="Draft the next revision of this rule for review"
        >
          Revise
        </Button>
      )}
    </Space>
  );

  return (
    <>
      <Collapse
        className="rule-card"
        defaultActiveKey={defaultExpanded ? ["body"] : []}
        items={[
        {
          key: "body",
          label: header,
          children: (
            <div className="rule-card-body">
              {rule.description && <Paragraph type="secondary">{rule.description}</Paragraph>}

              <div className="entity-band">
                <div className="entity-band-row">
                  <UserOutlined className="entity-band-icon" />
                  <span className="entity-band-label">Set by</span>
                  <span className="entity-band-value">
                    {rule.authority.owner} <Text type="secondary">({rule.authority.level}, rank {rule.authority.rank})</Text>
                  </span>
                </div>
                <div className="entity-band-row">
                  <UserOutlined className="entity-band-icon" />
                  <span className="entity-band-label">Applies to</span>
                  <span className="entity-band-value">{describeScope(rule.scope)}</span>
                </div>
                <div className="entity-band-row entity-band-row-action">
                  <Tag color={EFFECT_COLOR[rule.effect.type] ?? "default"} className="entity-band-effect-tag">
                    {rule.effect.type}
                  </Tag>
                  <span className="entity-band-value entity-band-action-text">{rule.effect.action}</span>
                  <Text type="secondary" className="entity-band-priority">
                    priority {rule.priority}
                  </Text>
                </div>
              </div>

              {(rule.is_explicit_override || rule.supersedes_rule_ids.length > 0) && (
                <div className="rule-card-section precedence-band">
                  <Text strong className="rule-card-section-title">
                    <CrownOutlined /> Precedence
                  </Text>
                  <Space direction="vertical" size={6} style={{ width: "100%" }}>
                    {rule.is_explicit_override && (
                      <Tag color="purple">Explicit override — outranks otherwise-applicable rules</Tag>
                    )}
                    {rule.supersedes_rule_ids.length > 0 && (
                      <Text type="secondary" className="rule-card-scope">
                        Supersedes:{" "}
                        {rule.supersedes_rule_ids.map((rid, i) => (
                          <Text key={rid} code copyable={{ text: rid }}>
                            {i > 0 ? ", " : ""}
                            {rid}
                          </Text>
                        ))}
                      </Text>
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
                          {exc.effect_override && (
                            <Tag color={EFFECT_COLOR[exc.effect_override.type] ?? "default"}>
                              override → {exc.effect_override.type}: {exc.effect_override.action}
                            </Tag>
                          )}
                        </div>
                      </List.Item>
                    )}
                  />
                </div>
              )}

              {(() => {
                const contributions = (aggregateLimits ?? []).filter((agg) =>
                  agg.contributing_rules.some((c) => c.rule_id === rule.rule_id)
                );
                if (contributions.length === 0) return null;
                return (
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
                );
              })()}

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
                      <Text type="secondary" className="rule-card-scope">
                        <ApartmentOutlined /> Related rules:{" "}
                        {rule.related_rule_ids.map((rid, i) => (
                          <Text key={rid} code copyable={{ text: rid }}>
                            {i > 0 ? ", " : ""}
                            {rid}
                          </Text>
                        ))}
                      </Text>
                    )}
                  </Space>
                </div>
              )}

              <div className="rule-card-section record-details">
                <Text strong className="rule-card-section-title">
                  Record details
                </Text>
                <Descriptions size="small" column={2} bordered className="rule-card-descriptions">
                  <Descriptions.Item label="Effective from">{rule.effective_from}</Descriptions.Item>
                  <Descriptions.Item label="Effective to">{rule.effective_to ?? "—"}</Descriptions.Item>
                  <Descriptions.Item label="Policy set ID" span={2}>
                    <Text className="entity-id-row" copyable={{ text: rule.policy_set_id }}>
                      {rule.policy_set_id}
                    </Text>
                  </Descriptions.Item>
                  <Descriptions.Item label="Policy version ID" span={2}>
                    <Text className="entity-id-row" copyable={{ text: rule.policy_version_id }}>
                      {rule.policy_version_id}
                    </Text>
                  </Descriptions.Item>
                </Descriptions>
              </div>

              <div className="rule-card-section">
                <Text strong className="rule-card-section-title">
                  <ReadOutlined /> Original source text — the exact words from the source document
                </Text>
                {rule.evidence.length === 0 ? (
                  <div className="evidence-empty-block">
                    <Text type="secondary">
                      No source citation on this rule — it was manually authored or drafted without a linked
                      source document, so there is no original wording to quote.
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

              {!hideNotes && (
                <div className="rule-card-section">
                  <NotesPanel entityType="rule" entityId={rule.rule_id} title="Notes on this rule" compact />
                </div>
              )}
            </div>
          ),
        },
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
    </>
  );
}
