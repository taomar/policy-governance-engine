import { useMemo, useState, type ReactNode } from "react";
import { Collapse, Descriptions, List, Segmented, Space, Tag, Tooltip, Typography } from "antd";
import {
  ApartmentOutlined,
  BarChartOutlined,
  BranchesOutlined,
  CrownOutlined,
  FileTextOutlined,
  UserOutlined,
} from "@ant-design/icons";
import type { AggregateLimit, CanonicalRule } from "../api";
import { ConditionView } from "./ConditionView";
import { ConditionRouteNote } from "./ConditionRouteNote";
import { SemanticProjectionView, hasSemanticProjection } from "./SemanticProjectionView";
import { JsonView } from "./JsonView";
import { PolicyEffectBadge } from "./PolicyEffectBadge";
import { DirectionalText } from "./DirectionalText";
import { withRuleIdentity } from "../ruleIdentity";
import { isEmptyCondition, scopeEntries } from "../ruleDisplay";

const { Text } = Typography;

/**
 * One rule's tab bodies, in one place, so the two surfaces that show them
 * cannot drift.
 *
 * These were written inside `PolicyInspector` and rendered only there — the
 * separate destination a reviewer reached by leaving the queue. They are now
 * also rendered inside the row the rule stands in, and the whole value of that
 * depends on the two being the same thing rather than two readings of it. A
 * reviewer who checks a rule in place and then opens the full record must see
 * the same tree, the same groups, the same chips; anything else means one of
 * the two is lying about the record.
 *
 * So this is a move, not a rewrite. The markup and class names below are the
 * inspector's, unchanged, and the inspector now calls these instead of holding
 * its own copy. Both callers get corrections to either at the same moment.
 *
 * Everything here reads the record already in hand. There is no fetch in this
 * file, so no pane it renders can sit on "Loading…" — which is what makes them
 * safe to put inside a row of a queue that can hold dozens of rules.
 */

/**
 * Rule IDs as jump-to-rule tags where the target is resolvable, and as a plain
 * copyable ID otherwise (a dangling or out-of-version reference).
 */
export function RuleRefTags({
  ids,
  allRules = [],
  onSelectRule,
}: {
  ids: string[];
  allRules?: CanonicalRule[];
  onSelectRule?: (rule: CanonicalRule) => void;
}) {
  const rulesById = useMemo(() => new Map(allRules.map((r) => [r.rule_id, r])), [allRules]);
  return (
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
}

/**
 * What goes inside the bordered condition box, or null when there is nothing
 * to put there. Nothing is the case where the source states its test in
 * words and the record carries no attribute table: an empty bordered box
 * reads as a rendering failure, and the routing note under it already says
 * what happened. The note is what replaces the old "may genuinely be
 * unconditional, or its scope may have been missed" line, which asked the
 * reviewer to choose between two readings the record had already settled.
 */
function ConditionBox({ rule }: { rule: CanonicalRule }) {
  if (!isEmptyCondition(rule.condition)) return <ConditionView node={rule.condition} />;
  if (hasSemanticProjection(rule)) return <SemanticProjectionView rule={rule} />;
  if (!rule.condition_provenance) {
    return (
      <Text type="secondary">
        No conditions were derived. The rule may genuinely be unconditional, or its scope
        may have been missed during extraction — a reviewer must decide which.
      </Text>
    );
  }
  return null;
}

/** Whether `ConditionBox` would draw anything for this rule. */
function hasConditionBox(rule: CanonicalRule): boolean {
  return !isEmptyCondition(rule.condition) || hasSemanticProjection(rule) || !rule.condition_provenance;
}

/**
 * The rule as logic: what makes it fire, what it needs to be told, what is
 * carved out of it, and what it shares a cap with.
 */
export function RuleLogicPane({
  rule,
  aggregateLimits,
  allRules,
  onSelectRule,
}: {
  rule: CanonicalRule;
  aggregateLimits?: AggregateLimit[];
  allRules?: CanonicalRule[];
  onSelectRule?: (rule: CanonicalRule) => void;
}) {
  const contributions = useMemo(
    () =>
      (aggregateLimits ?? []).filter((agg) =>
        agg.contributing_rules.some((c) => c.rule_id === rule.rule_id),
      ),
    [rule, aggregateLimits],
  );

  return (
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
                <Text type="secondary">Supersedes:</Text>{" "}
                <RuleRefTags ids={rule.supersedes_rule_ids} allRules={allRules} onSelectRule={onSelectRule} />
              </div>
            )}
          </Space>
        </div>
      )}

      <div className="rule-card-section">
        <Text strong className="rule-card-section-title">
          Condition — when this rule fires
        </Text>
        {hasConditionBox(rule) && (
          <div className="cond-box">
            <ConditionBox rule={rule} />
          </div>
        )}
        <ConditionRouteNote provenance={rule.condition_provenance} />
      </div>

      {rule.required_facts.length > 0 && (
        <div className="rule-card-section">
          <Text strong className="rule-card-section-title">
            Required facts
          </Text>
          <Space size={6} wrap>
            {rule.required_facts.map((f) => (
              <Tag key={f.name} variant="filled" className="fact-tag">
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
            <BranchesOutlined /> Exceptions — carve-outs, escalation &amp; special-case routes
          </Text>
          <List
            size="small"
            dataSource={rule.exceptions}
            renderItem={(exc) => (
              <List.Item key={exc.exception_id}>
                <div className="exception-item">
                  <div className="exception-item-headline">
                    <Text>
                      <DirectionalText>{exc.description}</DirectionalText>
                    </Text>
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
}

/** Who and what the rule reaches, and how it is classified. */
export function RuleScopePane({
  rule,
  allRules,
  onSelectRule,
}: {
  rule: CanonicalRule;
  allRules?: CanonicalRule[];
  onSelectRule?: (rule: CanonicalRule) => void;
}) {
  return (
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
              <Text className={entry.isDefault ? "inspector-scope-value-default" : undefined}>
                <DirectionalText>{entry.value}</DirectionalText>
              </Text>
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
                  <Tag key={t} variant="filled" className="fact-tag">
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
                <RuleRefTags ids={rule.related_rule_ids} allRules={allRules} onSelectRule={onSelectRule} />
              </div>
            )}
          </Space>
        </div>
      )}
    </div>
  );
}

/**
 * The stored forms of the record, side by side.
 *
 * The evaluator record and both formulation artifacts are peers. They used
 * to be stacked vertically, which meant the two original AI artifacts sat
 * below a 100+ line JSON viewer and appeared to have disappeared.
 */
export function RuleJsonPane({
  rule,
  /** "Extracted from" labels, resolved by whoever already fetched document
   *  metadata. Empty where nobody has — the provenance line then says so rather
   *  than waiting on a request this pane never makes. */
  sourceLabels = [],
}: {
  rule: CanonicalRule;
  sourceLabels?: string[];
}) {
  const [jsonVariant, setJsonVariant] = useState<"evaluator" | "canonical" | "dmn">("evaluator");
  const activeJsonVariant = rule.formulation ? jsonVariant : "evaluator";

  const jsonVariants = {
    evaluator: {
      title: "Evaluator record",
      description: (
        <>
          The stored <Text code>CanonicalRule</Text> consumed by the deterministic evaluator. Nothing is inferred at
          evaluation time.
        </>
      ),
      value: withRuleIdentity(rule, rule),
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
      // The attribute table travels with the decomposition it describes.
      // Reading `canonical.rule` alone means pairing each attribute with its
      // fact by hand, which is the work `attributes` already did — and doing it
      // twice is how two readings of one record start to disagree.
      value: rule.formulation?.canonical
        ? withRuleIdentity({ ...rule.formulation.canonical, attributes: rule.attributes ?? null }, rule)
        : null,
      downloadName: `${rule.rule_id}-canonical.json`,
    },
    dmn: {
      title: "DMN / FEEL projection",
      description: (
        <>The paired OMG DMN 1.5 decision projection and FEEL mapping produced by the formulator.</>
      ),
      value: rule.formulation
        ? withRuleIdentity({ attributes: rule.attributes ?? null, dmn_decisions: rule.formulation.dmn_decisions }, rule)
        : null,
      downloadName: `${rule.rule_id}-dmn.json`,
    },
  } satisfies Record<string, { title: string; description: ReactNode; value: unknown; downloadName: string }>;
  const selectedJson = jsonVariants[activeJsonVariant];

  return (
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
                <Tag key={label}>
                  <DirectionalText>{label}</DirectionalText>
                </Tag>
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
}

/** The identifiers that name this record, collapsed where the inspector puts them. */
export function RuleTechnicalMetadata({ rule }: { rule: CanonicalRule }) {
  return (
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
  );
}
