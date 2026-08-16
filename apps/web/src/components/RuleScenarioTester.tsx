/**
 * "Put a case to this rule" — one rule, one case, whichever decider its route
 * calls for, against whichever record the surface is reading.
 *
 * TWO ROUTES, TWO DECIDERS, ONE WAY IN
 *
 * A rule states its test either as a comparison between named quantities or in
 * words. The first is computed by `evaluator.engine.evaluate_policy` against
 * facts an AI conservatively infers from a plain-English case. The second is
 * read by a judge against that same case — which is the reason the route
 * exists, and the route most policy text arrives on.
 *
 * This component asks whichever decider the record calls for, and the record
 * alone chooses: a rule whose comparison the engine can compute goes to the
 * engine, and everything else goes to the judge. It is not a preference a
 * caller can pass in, because a caller that guessed wrong would send a rule to
 * a decider that refuses it — `ai_scenario_engine.py` short-circuits before it
 * reads any case, and the reader would see a refusal where they asked a
 * question.
 *
 * AND SEPARATELY, WHAT IT IS ASKED ABOUT
 *
 * Who decides is one axis; what they decide about is another. A reviewer is
 * asking about the candidate in front of them, which is not versioned and may
 * belong to a set that has never published anything. A policy admin is asking
 * about what is in force, at a version they chose. `target` says which, it
 * defaults to the draft, and the answer states it — because a verdict whose
 * target the reader has to infer is not evidence.
 *
 * These were previously one axis, and the engine route was made to depend on a
 * publication it never needed. A reviewer testing a draft was silently answered
 * about the active published version instead, or — on a set with no published
 * version — told the set had none, which read as the rule being untestable.
 *
 * WHY THE JUDGED ANSWER CARRIES NO NUMBER
 *
 * A judged answer has three states: it applies, it does not, or the case as
 * described does not settle it. That third state is what a confidence figure
 * is reaching for, said in a form a reviewer can act on — describe more of the
 * case. A number would be worse than useless here: `contracts/correlation.py`
 * records why the specification bans them (a model asked for a probability
 * supplies one, and `0.91` reads as measurement when it is invention), and
 * beside a computed answer a percentage would read as the judged route
 * apologising for itself. Both routes decide. They decide differently.
 *
 * Results are deliberately NOT written to the evaluation audit trail on either
 * route: this is an exploratory check by a reviewer, not a production calling
 * -system event. See `ai_scenario_engine.py` and `ai_scenario_eval.py`.
 */
import { useEffect, useState } from "react";
import { Alert, Button, Descriptions, Input, Select, Space, Tag, Tooltip, Typography } from "antd";
import { ExperimentOutlined, FileTextOutlined, InfoCircleOutlined, ReadOutlined } from "@ant-design/icons";
import {
  aiApi,
  PolicyPlatformApiError,
  type CanonicalRule,
  type Clause,
  type EvidenceReference,
  type RuleScenarioTestResult,
  type ScenarioEvaluation,
} from "../api";
import { resolveClausesById } from "../clauseCache";
import { DETERMINISTIC_LABEL, engineDecidesRule } from "../ruleExecutability";
import { MarkedQuotation } from "./MarkedQuotation";
import {
  COMPUTED_ANSWER,
  JUDGED_ANSWER,
  DRAFT_TARGET,
  RESULT_DOES_NOT_CARRY_OVER,
  targetLabel,
  type TestTarget,
} from "./policyTesting";

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

type ReasoningEffort = "low" | "medium" | "high";

interface RuleScenarioTesterProps {
  policySetKey: string;
  rule: CanonicalRule;
  /**
   * What the case is put to. Defaults to the draft, because a surface that has
   * not named a published version is reading the record as it stands — which is
   * the honest answer for a reviewer and the only possible one for a set that
   * has never published.
   */
  target?: TestTarget;
}

export function RuleScenarioTester({
  policySetKey,
  rule,
  target = DRAFT_TARGET,
}: RuleScenarioTesterProps) {
  const [scenario, setScenario] = useState("");
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>("low");
  const [result, setResult] = useState<RuleScenarioTestResult | null>(null);
  const [judged, setJudged] = useState<ScenarioEvaluation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  // The rule's source clauses, resolved from evidence offsets to real verbatim
  // text through the shared cache (see `resolveClausesById`) so the sentence the
  // judge reads is on the card, not behind "View source". `resolving` keeps the
  // in-flight state distinct from text that was never stored (constraint 5).
  const [clausesById, setClausesById] = useState<Map<string, Clause>>(new Map());
  const [sourceResolving, setSourceResolving] = useState(false);

  // One derivation of who decides, taken from the record and shared with every
  // other surface that asks (see `engineDecidesRule`). Two copies of this
  // question is what let a rule be offered a decider that would refuse it.
  const engineDecides = engineDecidesRule(rule);

  // Switching rules while this tab is open should not show a stale answer
  // from a different rule under the new title/condition.
  useEffect(() => {
    setResult(null);
    setJudged(null);
    setError(null);
    setScenario("");
  }, [rule.rule_id]);

  // Resolve this rule's cited clauses to their stored text. Keyed on the
  // revision, not `evidence.length`, because evidence only changes together
  // with a revision bump — the same trigger RuleCard's identical effect uses.
  useEffect(() => {
    const docVersionIds = (rule.evidence ?? [])
      .map((ev) => ev.document_version_id)
      .filter(Boolean);
    if (docVersionIds.length === 0) {
      setClausesById(new Map());
      setSourceResolving(false);
      return;
    }
    let cancelled = false;
    setSourceResolving(true);
    resolveClausesById(docVersionIds)
      .then((byId) => {
        if (!cancelled) setClausesById(byId);
      })
      .catch(() => {
        if (!cancelled) setClausesById(new Map());
      })
      .finally(() => {
        if (!cancelled) setSourceResolving(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rule.rule_id, rule.rule_revision]);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      if (engineDecides) {
        setJudged(null);
        setResult(
          target.kind === "published_version" && policySetKey
            ? await aiApi.testRuleScenario(
                policySetKey,
                rule.rule_id,
                scenario.trim(),
                reasoningEffort,
                target.policyVersionId,
              )
            : await aiApi.computeScenario(rule, scenario.trim(), reasoningEffort),
        );
      } else {
        setResult(null);
        setJudged(await aiApi.evaluateScenario(rule, scenario.trim(), reasoningEffort));
      }
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setLoading(false);
    }
  };

  const factEntries = result ? Object.entries(result.inferred_facts) : [];
  const rr = result?.rule_result ?? null;

  return (
    <div className="inspector-pane">
      <Alert
        type="info"
        showIcon
        message={
          engineDecides
            ? "The engine computes this rule's comparison"
            : "A judge reads this rule against your case"
        }
        description={
          engineDecides ? (
            <span>
              The rule states its test as a comparison between named quantities. AI translates your
              case into those quantities, taking only what you stated, and the same evaluator that
              production evaluations use settles the outcome from them.
            </span>
          ) : (
            <span>
              The rule states what it requires in words rather than as a comparison between named
              quantities, so it is served as <Text code>ai_ready</Text> and settled by a judge
              reading the record — the source sentence, the facts it names, and the outcome it
              states — against the case you describe.
            </span>
          )
        }
        style={{ marginBottom: 16 }}
      />
      <Paragraph type="secondary" data-testid="scenario-target">
        The case is put to <Text strong>{targetLabel(target)}</Text>.
        {target.kind === "draft" ? ` ${RESULT_DOES_NOT_CARRY_OVER}` : ""}
      </Paragraph>
      <RuleSourceText
        evidence={rule.evidence ?? []}
        clausesById={clausesById}
        resolving={sourceResolving}
      />
      <Paragraph>
        <Text strong>Describe a case in plain English</Text>
      </Paragraph>
      <TextArea
        rows={3}
        value={scenario}
        onChange={(e) => setScenario(e.target.value)}
        placeholder="e.g. An employee in the US submits an expense of $75 for a client dinner"
      />
      <Space style={{ marginTop: 12, marginBottom: 16 }}>
        <Text type="secondary">Reasoning effort</Text>
        <Select<ReasoningEffort>
          value={reasoningEffort}
          onChange={setReasoningEffort}
          style={{ width: 120 }}
          options={[
            { value: "low", label: "Low" },
            { value: "medium", label: "Medium" },
            { value: "high", label: "High" },
          ]}
        />
        <Button
          type="primary"
          icon={engineDecides ? <ExperimentOutlined /> : <ReadOutlined />}
          onClick={run}
          loading={loading}
          disabled={!scenario.trim()}
          data-testid="scenario-run"
        >
          {loading
            ? engineDecides
              ? "Computing…"
              : "Reading…"
            : engineDecides
              ? "Run the engine on this case"
              : "Put this case to the judge"}
        </Button>
      </Space>

      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}

      {judged && (
        <div className="scenario-test-result" data-testid="scenario-answer">
          <Space style={{ marginBottom: 12 }} wrap>
            <Tag
              color={JUDGED_ANSWER[judged.applies].color}
              className="scenario-test-verdict-tag"
              data-testid="scenario-verdict"
            >
              {JUDGED_ANSWER[judged.applies].label}
            </Tag>
            <Tag>Reasoning effort: {judged.reasoning_effort}</Tag>
          </Space>

          {judged.predicted_outcome && (
            <Paragraph>
              <Text strong>What the rule requires here: </Text>
              {judged.predicted_outcome}
            </Paragraph>
          )}

          <Paragraph>{judged.reasoning}</Paragraph>

          {judged.missing_facts.length > 0 && (
            <Paragraph>
              <Text strong>What the case would have to state for this to be settled: </Text>
              <Space wrap>
                {judged.missing_facts.map((f) => (
                  <Tag key={f} color="gold">
                    {f}
                  </Tag>
                ))}
              </Space>
            </Paragraph>
          )}

          <Text type="secondary" style={{ fontSize: 12 }} data-testid="scenario-decided-by">
            Read by a judge against the record on screen · not saved to the audit trail
            (exploratory check only)
          </Text>
        </div>
      )}

      {result && (
        <div className="scenario-test-result" data-testid="scenario-answer">
          <Space style={{ marginBottom: 12 }} wrap>
            <Tag
              color={rr ? COMPUTED_ANSWER[rr.status].color : "default"}
              className="scenario-test-verdict-tag"
              data-testid="scenario-verdict"
            >
              {rr ? COMPUTED_ANSWER[rr.status].label : COMPUTED_ANSWER.ERROR.label}
            </Tag>
            {rr?.effect_action && (
              <Tag
                color={
                  rr.effect_type === "deny"
                    ? "red"
                    : rr.effect_type === "allow"
                      ? "green"
                      : rr.effect_type === "informational"
                        ? "default"
                        : "blue"
                }
              >
                {rr.effect_action}
              </Tag>
            )}
            {result.not_in_effect && (
              <Tooltip title="This rule exists in the active approved version, but its effective date window doesn't include today (not yet effective, or expired) — the real engine skips it entirely, so no verdict is available.">
                <Tag color="default">
                  <InfoCircleOutlined /> Outside effective date range
                </Tag>
              </Tooltip>
            )}
            <Tag>Reasoning effort: {result.reasoning_effort}</Tag>
            {result.testability_reason && <Tag>{DETERMINISTIC_LABEL.no}</Tag>}
          </Space>

          <Paragraph>{result.explanation}</Paragraph>

          {result.missing_facts.length > 0 && (
            <Paragraph>
              <Text strong>What the case would have to state for this to be settled: </Text>
              <Space wrap>
                {result.missing_facts.map((f) => (
                  <Tag key={f} color="gold">
                    {f}
                  </Tag>
                ))}
              </Space>
            </Paragraph>
          )}

          {factEntries.length > 0 && (
            <>
              <Text type="secondary" className="section-eyebrow">
                Quantities the AI read out of your case (used as-is by the engine)
              </Text>
              <Descriptions size="small" column={1} bordered style={{ marginTop: 8, marginBottom: 12 }}>
                {factEntries.map(([k, v]) => (
                  <Descriptions.Item key={k} label={k}>
                    {typeof v === "object" ? JSON.stringify(v) : String(v)}
                  </Descriptions.Item>
                ))}
              </Descriptions>
            </>
          )}

          {result.assumptions.length > 0 && (
            <Paragraph>
              <Text strong>Assumptions made: </Text>
              <ul style={{ marginTop: 4, marginBottom: 0 }}>
                {result.assumptions.map((a, i) => (
                  <li key={i}>
                    <Text type="secondary">{a}</Text>
                  </li>
                ))}
              </ul>
            </Paragraph>
          )}

          {/* The engine's own account of the answer. The timestamp and the hash
              are its audit handles, and each is written only if the engine sent
              one: an answer that arrives without them is still an answer, and a
              missing handle must not cost the reader the verdict it belongs to.
              Reading them unguarded threw during render and took the whole
              panel — and the deterministic route is the smaller of the two, so
              nobody would have seen it for a while. */}
          <Text type="secondary" style={{ fontSize: 12 }} data-testid="scenario-decided-by">
            Computed by the engine
            {result.evaluation_timestamp
              ? ` ${new Date(result.evaluation_timestamp).toLocaleString()}`
              : ""}
            {result.result_hash ? (
              <>
                {" "}
                · result hash{" "}
                <Text code copyable={{ text: result.result_hash }} style={{ fontSize: 12 }}>
                  {result.result_hash.slice(0, 12)}…
                </Text>
              </>
            ) : null}{" "}
            · not saved to the audit trail (exploratory check only)
          </Text>
        </div>
      )}
    </div>
  );
}

/**
 * The rule as the document states it, shown on the test card itself.
 *
 * A reviewer here is deciding whether the judge's verdict is right, and cannot
 * do that without the sentence the verdict was read from — so the source is
 * evidence, and evidence does not sit behind "View source" (constraint 6). It
 * is quoted whole and unaltered through the same `MarkedQuotation` every other
 * card uses (constraint 4), its direction carried per run for the corpus's
 * Arabic clauses (constraint 7).
 *
 * Four states are kept apart (constraint 5), and none is an empty box: a rule
 * with no citation was authored by hand and has no words to quote; a citation
 * whose text is still resolving is loading; a citation whose text was never
 * stored says exactly that; and a resolved citation is shown verbatim.
 */
function RuleSourceText({
  evidence,
  clausesById,
  resolving,
}: {
  evidence: readonly EvidenceReference[];
  clausesById: Map<string, Clause>;
  resolving: boolean;
}) {
  return (
    <div className="scenario-source" data-testid="scenario-source" style={{ marginBottom: 16 }}>
      <Text type="secondary" className="section-eyebrow">
        <ReadOutlined /> The rule in the document&apos;s own words — quoted exactly
      </Text>
      {evidence.length === 0 ? (
        <Paragraph
          type="secondary"
          data-testid="scenario-source-none"
          style={{ marginTop: 8, marginBottom: 0 }}
        >
          No source citation on this rule — it was authored by hand or drafted without a linked
          source document, so there is no original wording to quote.
        </Paragraph>
      ) : (
        <Space direction="vertical" size={10} style={{ width: "100%", marginTop: 8 }}>
          {evidence.map((ev, idx) => {
            const clause = ev.clause_id ? clausesById.get(ev.clause_id) : undefined;
            if (clause) {
              const locator = [
                clause.section,
                clause.page !== null ? `p.${clause.page}` : null,
                clause.clause_ref ? `clause ${clause.clause_ref}` : null,
              ]
                .filter(Boolean)
                .join(" · ");
              return (
                <div key={idx} className="scenario-source-block">
                  <MarkedQuotation
                    text={clause.text}
                    marks={[]}
                    className="policy-card__passage"
                    testId="scenario-source-quotation"
                  />
                  {locator ? (
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      <FileTextOutlined /> {locator}
                    </Text>
                  ) : null}
                </div>
              );
            }
            if (ev.clause_id && resolving) {
              return (
                <Text key={idx} type="secondary" data-testid="scenario-source-loading">
                  Loading the source text…
                </Text>
              );
            }
            // A citation whose text was never stored is a different answer from a
            // rule that says nothing (constraint 5): the reference exists here,
            // its wording does not.
            return (
              <Text key={idx} type="secondary" data-testid="scenario-source-absent">
                The source text for this passage was not stored with its rules.
              </Text>
            );
          })}
        </Space>
      )}
    </div>
  );
}