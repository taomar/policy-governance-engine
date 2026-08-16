import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Button, Collapse, Descriptions, Empty, Space, Tabs, Tag, Tooltip, Typography } from "antd";
import {
  ApartmentOutlined,
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
} from "@ant-design/icons";
import type { AggregateLimit, ApprovedPolicyVersion, CanonicalRule, Clause, NoteEntityType } from "../api";
import { resolveClausesById } from "../clauseCache";
import { resolveDocumentMetaByVersionId, type DocumentMeta } from "../documentMetaCache";
import { ambiguityNote } from "../ambiguityNote";
import { AmbiguityNoteView } from "./AmbiguityNoteView";
import { EvidenceHeadingContext } from "./EvidenceHeadingContext";
import { DecisionReadinessView } from "./DecisionReadinessView";
import { JsonView } from "./JsonView";
import { withRuleIdentity } from "../ruleIdentity";
import { NotesPanel } from "./NotesPanel";
import { DocumentBodyDrawer } from "./DocumentBodyDrawer";
import { PolicyEffectBadge } from "./PolicyEffectBadge";
import { PARTIES_AND_ROUTES_TAB_LABEL } from "./policyTabPanes";
import { RuleScenarioTester } from "./RuleScenarioTester";
import { PublishedRuleAskAiButton } from "./PublishedRuleAskAiButton";
import { RuleVersionHistory } from "./RuleVersionHistory";
import {
  RuleJsonPane,
  RuleLogicPane,
  RuleScopePane,
  RuleTechnicalMetadata,
} from "./ruleTabPanes";
import { DirectionalText } from "./DirectionalText";
import { ruleTypeLabel } from "../ruleTypes";
import { colorForCategory } from "../policyCategories";
import {
  ambiguityMeta,
  findRuleVariations,
  formatConditionValue,
  hasAmbiguityFlag,
  readableDescription,
  ruleDecisionSummary,
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
  /**
   * Which question is open, where the surrounding surface holds that state.
   *
   * Optional, because this component has two placements and only one of them
   * has anywhere to keep it. As the destination panel the workspace owns the
   * tab, so arriving at a rule from its History leaves the reader on History.
   * Embedded under a row's `Details` there is no workspace state to own it —
   * several rows can be open at once and each is its own reading — so it keeps
   * its own. Uncontrolled is the *absence* of an owner, not a default: passing
   * `activeTabKey` without `onTabChange` would freeze the strip, so the two
   * travel together.
   */
  activeTabKey?: string;
  onTabChange?: (key: string) => void;
  /**
   * Where this inspector is drawn.
   *
   * `panel` is the destination column or drawer, which owns its own height and
   * scrolls. `embedded` is the same reading opened in place under the row it
   * belongs to — inside a card or a list — so it drops the window chrome and
   * lets the page it sits in do the scrolling.
   *
   * It is a placement, not a permission. Nothing here reads it to decide what a
   * reader may do; what a rule offers is read from the rule.
   */
  variant?: "panel" | "embedded";
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
  /**
   * This inspector is embedded as a citation inside another workflow, not as
   * the place the reader came to act on the rule.
   *
   * WHY THIS IS NOT AN EDITABILITY FLAG, AND MUST NOT BECOME ONE
   *
   * Whether a record may be changed is a property of the record, answered by
   * `candidateEditability` from its review status, and no caller is entitled to
   * a second opinion on it. This says something a record cannot: the *same*
   * published rule is the subject of the page on one surface and a reference
   * pulled in beside a quality finding on another. Only the caller knows which,
   * because it is a fact about the surrounding surface rather than about the
   * rule.
   *
   * What it suppresses is therefore limited to acting *on* a rule you arrived
   * at by way of something else — running a scenario against it, writing a note
   * on it. It does not, and must not, gate anything whose answer is already
   * carried by the record or by the presence of a handler: a caller that does
   * not want Revise offered simply does not pass `onRevise`.
   */
  shownAsReference?: boolean;
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
  variant = "panel",
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
  shownAsReference = false,
}: PolicyInspectorProps) {
  /** Held only for the placement that has no owner for it. Initialised to the
   *  first question rather than to whatever a controlled caller last chose, so
   *  an embedded reading always opens where every other one does. */
  const [ownTabKey, setOwnTabKey] = useState("overview");
  const tabKey = activeTabKey ?? ownTabKey;
  const changeTab = onTabChange ?? setOwnTabKey;
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
              <DirectionalText>{target.title}</DirectionalText>
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
        {/* THREE IDENTIFIERS, THREE DIFFERENT THINGS
         *
         * A reader tracing a record was offered "Rule ID" and "Policy ID (set)"
         * side by side and reasonably read the second as the identifier of the
         * policy this rule belongs to. It is not. It is the identifier of the
         * whole set — every policy of the document at once — and the policy is
         * a first-class record with an identity of its own, its `provision_key`,
         * which is what carries across versions and what History is grouped by.
         *
         * So each label now names its scope rather than leaving the reader to
         * infer it, widest first, and the policy's own key is on the policy's
         * Overview where the policy is what is being shown. Nothing here
         * invents a policy identifier for a rule: a rule states which policy it
         * belongs to, and that is a different pane's answer. */}
        <Descriptions.Item label="This rule">
          <Text code copyable={{ text: rule.rule_id }}>
            {rule.rule_id}
          </Text>
        </Descriptions.Item>
        <Descriptions.Item label="The policy set it belongs to">
          <Text code copyable={{ text: rule.policy_set_id }}>
            {rule.policy_set_id}
          </Text>
        </Descriptions.Item>
        {recordKind === "published" && (
          <Descriptions.Item label="The published version it was read at">
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
                <Tag color="purple" icon={<CrownOutlined />} variant="filled">
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
                    <Tag variant="filled">{sibling.review_status}</Tag>
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
                    {ev.page !== null ? `, p.${ev.page}` : ""}
                    {clause ? ` · clause ${clause.clause_ref}` : ""}
                  </Text>
                  {/* Was appended to the line above as ` · {section}`, which read as part
                      of the document's title and disappeared entirely when absent. It has
                      its own row now so that both of its states are visible. */}
                  <EvidenceHeadingContext section={ev.section} />
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

  // The logic, scope and JSON panes live in `ruleTabPanes` because they are
  // now rendered in two places: here, on the full-record surface, and inside
  // the row the rule stands in. One definition, so the two cannot drift into
  // two readings of one record.
  const logic = (
    <RuleLogicPane
      rule={rule}
      allRules={allRules}
      onSelectRule={onSelectRule}
      aggregateLimits={aggregateLimits}
    />
  );

  const scope = <RuleScopePane rule={rule} allRules={allRules} onSelectRule={onSelectRule} />;

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

      <RuleTechnicalMetadata rule={rule} />
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
  // simply don't get this tab rather than showing a broken one. Withheld from a
  // reference view for the same reason Notes is: running a scenario is acting on
  // a rule, and this one was arrived at by way of something else.
  const testScenario =
    policySetKey && !shownAsReference ? <RuleScenarioTester policySetKey={policySetKey} rule={rule} /> : null;

  const json = <RuleJsonPane rule={rule} sourceLabels={sourceLabels} />;

  return (
    <div className={`policy-inspector${variant === "embedded" ? " policy-inspector--embedded" : ""}`}>
      <div className="policy-inspector-header">
        {/* Which of the two records this panel is answering about.
         *
         * The page beside it lists policies, and a policy and one of its rules
         * are two different selections that used to open the same rule-shaped
         * panel. Naming the kind is what lets a reader tell, without counting
         * identifiers, whether they are looking at the thing they pointed at. */}
        <p className="record-kind-eyebrow" data-testid="record-kind">
          Rule
        </p>
        <div className="policy-inspector-title-row">
          <Title level={5} className="policy-inspector-title">
            <DirectionalText>{rule.title}</DirectionalText>
          </Title>
          <span className="policy-row-flags">
            {rule.is_explicit_override && (
              <Tooltip title="Explicit override — outranks otherwise-applicable rules">
                <CrownOutlined className="policy-row-flag policy-row-flag-override" />
              </Tooltip>
            )}
            {hasAmbiguityFlag(rule.ambiguity_status) && (
              <Tooltip title={ambiguityNote(rule.ambiguity_status).reason}>
                <ExclamationCircleOutlined
                  className={`policy-row-flag policy-row-flag-ambiguity policy-row-flag-ambiguity--${ambiguityMeta(rule.ambiguity_status).color}`}
                />
              </Tooltip>
            )}
            {!rule.machine_executable && (
              <Tooltip title="The source states this rule's test in words rather than as a comparison, so a reviewer settles a case by reading it. It is reviewable and publishable as it stands.">
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
        {/* What the source's wording admits, in text, immediately above the
            review actions. This was previously reachable only by hovering the
            warning glyph in the title row, which a keyboard user never sees.
            Renders only for a status worth interrupting for; the complete
            field, including "reads one way", is on the parties and routes
            tab so it is never invisible. */}
        <AmbiguityNoteView status={rule.ambiguity_status} variant="banner" />
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
          {/* Asking a question about a rule is a read, so nothing about who is
              looking gates it. What gates it is whether the rule can be named
              to the server: a rule id alone does not identify a published
              record, because the draft row that produced it carries the same id.
              Both parts of the identity present, or no button.
              This used to live on the published page's own card, which is the
              only reason a reader on any other surface could not ask. */}
          {policySetKey && publishedVersion?.id && (
            <PublishedRuleAskAiButton
              rule={rule}
              policySetKey={policySetKey}
              policyVersionId={publishedVersion.id}
            />
          )}
          {additionalActions}
        </Space>
      </div>

      <Tabs
        activeKey={tabKey}
        onChange={changeTab}
        className="policy-inspector-tabs"
        items={[
          { key: "overview", label: "Overview", children: overview },
          { key: "logic", label: "Logic", children: logic },
          {
            key: "readiness",
            label: (
              <span>
                {PARTIES_AND_ROUTES_TAB_LABEL}
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
          ...(!shownAsReference ? [{ key: "notes", label: "Notes", children: notes }] : []),
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
