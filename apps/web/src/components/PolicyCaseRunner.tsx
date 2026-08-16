/**
 * Putting one case to a whole policy.
 *
 * WHY A POLICY SCOPE AT ALL
 *
 * A policy is what the document states and what a person approves; its rules
 * are how it decides. So the question a reviewer actually has — "what does this
 * policy say about this situation?" — is a question about the policy. Answering
 * it one rule at a time hands the reviewer a table of separate verdicts and
 * makes them do the assembly the record can do for them, and it buries the case
 * that matters most: two rules of one policy reaching answers that do not sit
 * together. So this leads with one answer at the policy level and names the rule
 * or rules it rests on, with every rule consulted kept reachable beneath it.
 *
 * WHAT THIS IS NOT
 *
 * It is not a second decider. Every rule here is asked through
 * `putCaseToRule`, the same single routing the rule-scope tester uses, so a
 * rule asked on its own and the same rule asked as part of its policy reach the
 * same instrument. Two copies of that routing would drift, and the drift would
 * be invisible until two surfaces disagreed about one rule.
 *
 * LEADING WITH AN ANSWER IS NOT ADDING UP VERDICTS
 *
 * The engine computes whether a case *satisfies* a rule. The judge reads
 * whether a rule *applies* to a case. Those are different questions, so their
 * answers are not points on one scale and must never be totalled into one
 * "the policy says yes". The reading below never does that: it re-presents each
 * rule's own verdict, in the words of whoever gave it, and when the rules that
 * bear on the case point different ways it says so plainly rather than picking a
 * winner. Citing the rule that settles a case is naming a source, not summing.
 *
 * An informational question — one that only asks what the policy says — is
 * answered on its own path: the rules that state the answer are gathered and the
 * answer is composed by this app, marked as ours and citing each rule it read.
 * That synthesis is our words about the document, never a verdict on a case.
 *
 * Reading a case saves nothing on its own. A reviewer may take one further,
 * deliberate step — keeping a settled determination as a guard, which writes to
 * this policy's tests so it re-runs on every future publish — but asking is a
 * reviewer looking, not a calling system evaluating, and the evaluation audit
 * trail records the second only, never either of these.
 */
import { useState } from "react";
import { Alert, Button, Empty, Progress, Select, Space, Table, Tag, Typography } from "antd";
import { ReadOutlined, SaveOutlined } from "@ant-design/icons";
import { Input } from "antd";
import {
  policyTestApi,
  PolicyPlatformApiError,
  type CanonicalRule,
  type CreatePolicyTestRequest,
  type EvaluationStatus,
} from "../api";
import { DirectionalText } from "./DirectionalText";
import { baseDirection } from "../directionalText";
import { RuleName } from "./RuleName";
import { putCaseToRule, targetLabel, RESULT_DOES_NOT_CARRY_OVER, type CaseAnswer, type CaseGuardSeed, type TestTarget } from "./policyTesting";
import { answerPolicyCase, type CaseIntent, type InformationalAnswer, type InformationalGrounding } from "./policyCaseIntent";
import { readPolicyCase, type PolicyCaseReading } from "./policyCaseSummary";
import "./policyCaseRunner.css";

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

type ReasoningEffort = "low" | "medium" | "high";

/** How a decider is named where a reviewer reads which one answered. */
const DECIDED_BY: Record<CaseAnswer["decidedBy"], { label: string; color: string }> = {
  engine: { label: "Computed", color: "geekblue" },
  judge: { label: "Read", color: "purple" },
  nobody: { label: "Not asked", color: "default" },
};

/**
 * `RuleName` only accepts a concrete `policySetKey`; here it may be absent (a
 * draft grouping with no persisted set has none). When it is, there is no
 * generated name to show, so this renders nothing — the caller always prints the
 * rule's own title beside it, which never depends on our naming.
 */
function NamedRule({
  policySetKey,
  ruleId,
  variant,
}: {
  policySetKey: string | null | undefined;
  ruleId: string;
  variant?: "inline" | "block";
}) {
  if (!policySetKey) return null;
  return <RuleName policySetKey={policySetKey} ruleId={ruleId} variant={variant} />;
}

/**
 * Every rule of the policy, accounted for, so leading with a few never leaves a
 * reviewer believing those few were all there were.
 *
 * The completeness claim — how many rules were read — always stays visible. What
 * sits with it depends on whether an answer was composed:
 *
 *  - Beneath a composed answer, the rules it rests on are already shown in full
 *    above, with their quotes. Repeating them here would be a second copy of one
 *    fact, not a second fact, so this carries only the remainder — the rules not
 *    cited above — and puts that enumeration behind a disclosure. That is
 *    legitimate because the enumeration is provenance, not the evidence a
 *    reviewer needs to judge a record (constraint 6); the claim that every rule
 *    was read stays open, and the count still adds up.
 *  - When no answer was composed, this list is the thing to read directly, so
 *    every rule stays open with nothing behind a click.
 */
function AllRulesReference({
  rules,
  policySetKey,
  citedIds,
  heading,
  collapsible = false,
}: {
  rules: readonly CanonicalRule[];
  policySetKey: string | null | undefined;
  citedIds: ReadonlySet<string>;
  heading: string;
  collapsible?: boolean;
}) {
  if (rules.length === 0) return null;

  // The rules the answer already cited in full above are not repeated here:
  // printing one rule twice is a second copy of one fact, not a second fact.
  const remainder = rules.filter((rule) => !citedIds.has(rule.rule_id));

  const list = (shown: readonly CanonicalRule[]) => (
    <Space direction="vertical" size={8} style={{ width: "100%" }}>
      {shown.map((rule) => (
        <div key={rule.rule_id} className="policy-case-reading__rule">
          <NamedRule policySetKey={policySetKey} ruleId={rule.rule_id} variant="block" />
          <DirectionalText>{rule.title}</DirectionalText>
        </div>
      ))}
    </Space>
  );

  // Beneath a composed answer: the completeness claim is provenance, not the
  // evidence, so the enumeration may sit behind a disclosure (constraint 6) —
  // but the claim itself stays open, and the disclosure holds only the rules
  // not already shown above.
  if (collapsible) {
    if (remainder.length === 0) {
      return (
        <div data-testid="policy-case-all-rules" style={{ marginTop: 16 }}>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            <Text strong>{heading}.</Text> Every one is cited above.
          </Paragraph>
        </div>
      );
    }
    return (
      <details
        data-testid="policy-case-all-rules"
        className="policy-case-all-rules"
        style={{ marginTop: 16 }}
      >
        <summary className="policy-case-all-rules__summary">
          <Text strong>{heading}.</Text>{" "}
          <Text type="secondary">
            The {remainder.length} not cited above {remainder.length === 1 ? "is" : "are"} kept here.
          </Text>
        </summary>
        <div className="policy-case-all-rules__body">{list(remainder)}</div>
      </details>
    );
  }

  // No answer was composed: the list is the thing to read directly, so every
  // rule stays open with nothing behind a click.
  return (
    <div data-testid="policy-case-all-rules" style={{ marginTop: 16 }}>
      <Paragraph type="secondary" style={{ marginBottom: 6 }}>
        <Text strong>{heading}.</Text> Each is listed here; none is hidden.
      </Paragraph>
      {list(rules)}
    </div>
  );
}

/**
 * What the answer was grounded on, reported to the reader so the grounding is
 * something seen rather than merely asserted.
 *
 * Its load-bearing job is the refusal: when the model cited a rule that is not
 * in this policy, that citation was dropped by the server and named here, so a
 * reviewer watches the check reject a fabrication instead of trusting that it
 * would. It also states how large the set read was — and, when the policy was
 * too large to read in one pass, that no single answer was composed from it, so
 * a partial reading can never pass for the whole policy's.
 *
 * This is the app's own reporting about the gather, not the document's words.
 */
function GroundingLine({ grounding }: { grounding: InformationalGrounding | undefined }) {
  if (!grounding) return null;
  const { rules_available, rules_cited, fabricated_citations, oversize } = grounding;
  const refused = fabricated_citations.length > 0;
  return (
    <div data-testid="policy-case-grounding" style={{ marginTop: 12 }}>
      <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: refused || oversize ? 6 : 0 }}>
        Grounded on the {rules_available} {rules_available === 1 ? "rule" : "rules"} of this policy
        {rules_cited > 0
          ? `; the answer rests on ${rules_cited} of ${rules_available === 1 ? "it" : "them"}.`
          : "."}{" "}
        Every cited rule is checked against this policy before it is shown.
      </Paragraph>
      {refused ? (
        <Alert
          type="warning"
          showIcon
          data-testid="policy-case-grounding-refused"
          message={
            fabricated_citations.length === 1
              ? "A citation naming no rule in this policy was refused"
              : `${fabricated_citations.length} citations naming no rule in this policy were refused`
          }
          description={`The model cited ${fabricated_citations.join(", ")}, which ${
            fabricated_citations.length === 1 ? "is not a rule" : "are not rules"
          } of this policy. ${
            fabricated_citations.length === 1 ? "It was" : "They were"
          } dropped and are reported here rather than shown as part of the answer.`}
        />
      ) : null}
      {oversize ? (
        <Alert
          type="warning"
          showIcon
          data-testid="policy-case-grounding-oversize"
          message="This policy was too large to read in one grounded pass"
          description="No single answer was composed from it, so no rule was silently left unread. The rules are listed below to read directly."
        />
      ) : null}
    </div>
  );
}


function InformationalPanel({
  informational,
  rules,
  policySetKey,
}: {
  informational: InformationalAnswer;
  rules: readonly CanonicalRule[];
  policySetKey: string | null | undefined;
}) {
  const { status, answer, citations, note } = informational;

  if (status !== "answered") {
    return (
      <div data-testid="policy-case-answer">
        <Alert
          type={status === "no_rule_bears" ? "info" : "warning"}
          showIcon
          message={
            status === "no_rule_bears"
              ? "No rule in this policy bears on your question"
              : status === "declined"
                ? "No answer was composed"
                : "The answer could not be composed"
          }
          description={
            status === "no_rule_bears"
              ? "No rule in this policy speaks to what you asked, so there is nothing here to answer it from."
              : status === "declined"
                ? "The model was asked to compose an answer from this policy's rules and returned none. The rules are listed below to read directly."
                : "The request to compose an answer did not complete. The rules are listed below to read directly, or ask again."
          }
        />
        <GroundingLine grounding={informational.grounding} />
        <AllRulesReference
          rules={rules}
          policySetKey={policySetKey}
          citedIds={new Set()}
          heading={`All ${rules.length} ${rules.length === 1 ? "rule" : "rules"} of this policy`}
        />
      </div>
    );
  }

  const citedIds = new Set(citations.map((c) => c.rule_id));
  // The answer cites rules by id; their title and verbatim sentence are the
  // record's own, held here already. Resolve them from the id rather than trust
  // a second copy over the wire — and a generated name never travels at all,
  // `NamedRule` looks it up from the id at render (constraint 8). The sentence
  // shown is the document's, uncut and untranslated (constraint 4).
  const ruleById = new Map(rules.map((r) => [r.rule_id, r] as const));
  return (
    <div data-testid="policy-case-answer">
      <div className="app-synthesis" data-generated="true" data-testid="policy-case-answer-text">
        <div>
          <span className="app-synthesis__mark" aria-hidden>
            ✦
          </span>{" "}
          <span className="app-synthesis__caption">Answer composed by this app from the rules below</span>
        </div>
        <Paragraph className="app-synthesis__body" style={{ marginBottom: 0 }}>
          <DirectionalText align>{answer}</DirectionalText>
        </Paragraph>
      </div>

      {note ? (
        <Paragraph type="secondary" style={{ fontSize: 12 }}>
          <DirectionalText>{note}</DirectionalText>
        </Paragraph>
      ) : null}

      <Paragraph type="secondary" style={{ marginBottom: 8 }}>
        This is one policy's answer. A question can bear on more than one policy; this does not reach
        past the policy in front of you.
      </Paragraph>

      <Paragraph style={{ marginBottom: 4 }}>
        <Text strong>
          {citations.length === 1
            ? "The answer rests on this rule:"
            : `The answer rests on these ${citations.length} rules:`}
        </Text>
      </Paragraph>
      {citations.map((c) => {
        const cited = ruleById.get(c.rule_id);
        const quote = cited?.formulation?.canonical?.source_text ?? "";
        return (
          <div key={c.rule_id} className="policy-case-citation" data-testid="policy-case-citation">
            <NamedRule policySetKey={policySetKey} ruleId={c.rule_id} variant="block" />
            {cited?.title ? (
              <div>
                <Text strong>
                  <DirectionalText>{cited.title}</DirectionalText>
                </Text>
              </div>
            ) : null}
            {quote ? (
              <p
                className="policy-case-citation__quote directional-text--block"
                dir={baseDirection(quote)}
                style={{ marginBottom: 0 }}
              >
                “<DirectionalText>{quote}</DirectionalText>”
              </p>
            ) : null}
          </div>
        );
      })}

      <GroundingLine grounding={informational.grounding} />

      <AllRulesReference
        rules={rules}
        policySetKey={policySetKey}
        citedIds={citedIds}
        heading={`All ${rules.length} ${rules.length === 1 ? "rule" : "rules"} of this policy were read`}
        collapsible
      />
    </div>
  );
}

/**
 * One reading of a case put to a policy for a determination: the answer the rules
 * give, above the per-rule detail rather than instead of it.
 *
 * It leads with the rules that settle the case and names them, so the reviewer
 * reads the answer and the rule it rests on together rather than reducing a table
 * themselves. It never totals the routes: each settling rule is shown in the
 * words its own decider gave, and where the settling rules do not all point the
 * same way that is said plainly, not resolved into one verdict. The four
 * policy-level states are kept apart for the same reason the per-rule ones are.
 */
function DecisionReading({
  reading,
  policySetKey,
}: {
  reading: PolicyCaseReading;
  policySetKey: string | null | undefined;
}) {
  const { state, settling, unsettled, divergent, rulesRead } = reading;
  const readAcross = `Read across ${rulesRead} ${rulesRead === 1 ? "rule" : "rules"}; every one is listed below.`;

  if (state === "settled") {
    return (
      <div className="policy-case-reading">
        <Paragraph style={{ marginBottom: 8 }}>
          <Text strong>
            {divergent
              ? "The rules that settle this case do not all point the same way."
              : settling.length === 1
                ? "One rule of this policy settles this case."
                : `${settling.length} rules of this policy settle this case.`}
          </Text>{" "}
          {divergent
            ? "Each is shown as its decider gave it; neither is resolved into a single answer for you."
            : "The answer rests on what these rules gave, shown in the words of whichever settled each."}
        </Paragraph>
        {settling.map((a) => (
          <div key={a.ruleId} className="policy-case-reading__rule">
            <NamedRule policySetKey={policySetKey} ruleId={a.ruleId} variant="block" />
            <Space wrap size={6} align="start">
              <Text strong>
                <DirectionalText>{a.title}</DirectionalText>
              </Text>
              {a.label ? <Tag color={a.color}>{a.label}</Tag> : null}
            </Space>
            {a.account ? (
              <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0 }}>
                <DirectionalText>{a.account}</DirectionalText>
              </Paragraph>
            ) : null}
          </div>
        ))}
        <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 8, marginBottom: 0 }}>
          {readAcross}
        </Paragraph>
      </div>
    );
  }

  if (state === "bears_unsettled") {
    return (
      <div className="policy-case-reading">
        <Paragraph style={{ marginBottom: 8 }}>
          <Text strong>The rules that bear on this case do not settle it as described.</Text> Each is
          shown below, with what it would need to settle.
        </Paragraph>
        {unsettled.map((a) => (
          <div key={a.ruleId} className="policy-case-reading__rule">
            <NamedRule policySetKey={policySetKey} ruleId={a.ruleId} variant="block" />
            <Text strong>
              <DirectionalText>{a.title}</DirectionalText>
            </Text>
          </div>
        ))}
        <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 8, marginBottom: 0 }}>
          {readAcross}
        </Paragraph>
      </div>
    );
  }

  if (state === "no_rule_bears") {
    return (
      <div className="policy-case-reading">
        <Paragraph style={{ marginBottom: 0 }}>
          <Text strong>No rule in this policy bears on this case.</Text> Every rule read stands aside
          from it; each is listed below.
        </Paragraph>
      </div>
    );
  }

  return (
    <div className="policy-case-reading">
      <Paragraph style={{ marginBottom: 0 }}>
        <Text strong>This case has no policy-level answer to show.</Text> The requests to the rules did
        not complete, so none reached the case. Each rule is listed below; putting the case again may
        reach them.
      </Paragraph>
    </div>
  );
}

/**
 * A guard's name is the reviewer's own case text, trimmed only for legibility in
 * a list — never a document quotation, so trimming it breaks no verbatim rule.
 * It is what a reviewer recognizes when this guard later surfaces a failure under
 * Quality.
 */
function guardName(scenario: string): string {
  const oneLine = scenario.trim().replace(/\s+/g, " ");
  const clipped = oneLine.length > 80 ? `${oneLine.slice(0, 79)}…` : oneLine;
  return `Case: ${clipped}`;
}

/**
 * The guard's description is ours, not the document's, so it says plainly what
 * the guard protects. `expected_rule_id` (stored on the test) names which rule;
 * this states the verdict that rule must keep returning.
 */
function guardDescription(status: EvaluationStatus): string {
  const verdict = status === "SATISFIED" ? "satisfied" : "not satisfied";
  return (
    "Kept from the case dialog. On every version published from now on, the deterministic " +
    `evaluator must still read this case as "${verdict}" for this rule, or Quality flags it.`
  );
}

/**
 * Keeping a settled determination as a regression guard — a deliberate step, and
 * the only thing on this whole surface that writes anything.
 *
 * WHY KEEPING SEVERAL IS NOT THE AGGREGATION THE READING REFUSES
 *
 * Each seed is one rule's reproducible verdict on this case: the facts the engine
 * read from it, and the status that rule must keep returning. Keeping several is
 * keeping several separate deterministic checks, never a policy-level ruling
 * summed from them. Every guard re-runs on each future publish (Section 4.1) with
 * no model in the loop — which is exactly why only an engine-settled
 * determination can become one, and an informational or judged answer cannot.
 *
 * WHAT IT DOES NOT TOUCH
 *
 * It writes to this policy's tests. It never writes to the evaluation audit
 * trail, which records what calling systems asked: a reviewer keeping a guard is
 * not a calling system, and the meaning of that trail must not blur.
 */
function KeepAsGuard({
  policySetKey,
  seeds,
}: {
  policySetKey: string;
  seeds: readonly CaseGuardSeed[];
}) {
  const [saving, setSaving] = useState(false);
  const [keptCount, setKeptCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const keep = async () => {
    setSaving(true);
    setError(null);
    try {
      for (const seed of seeds) {
        const status = seed.expectedRuleStatus;
        const body: CreatePolicyTestRequest = {
          name: guardName(seed.scenario),
          description: guardDescription(status),
          test_kind: status === "SATISFIED" ? "positive" : "negative",
          input_facts: seed.inferredFacts,
          expected_overall_status: seed.expectedOverallStatus,
          expected_rule_id: seed.ruleId,
          expected_rule_status: status,
        };
        await policyTestApi.create(policySetKey, body);
      }
      setKeptCount(seeds.length);
    } catch (caught) {
      setError(caught instanceof PolicyPlatformApiError ? caught.detail : String(caught));
    } finally {
      setSaving(false);
    }
  };

  if (keptCount !== null) {
    // Constraint 5: name the state precisely. A guard now EXISTS and has NOT yet
    // run — it runs first on the next publish, not now — which is a different
    // state from one that has run and passed or failed.
    return (
      <Alert
        type="success"
        showIcon
        style={{ marginTop: 16 }}
        data-testid="policy-case-guard-kept"
        message={keptCount === 1 ? "Kept as a guard." : `Kept as ${keptCount} guards.`}
        description="It has not run yet. It runs first on the next version you publish, and on every publish after, flagging this case under Quality if the determination ever changes."
      />
    );
  }

  return (
    <div style={{ marginTop: 16 }} data-testid="policy-case-guard-offer">
      <Paragraph style={{ marginBottom: 8 }}>
        <Text strong>Is this answer right? Keep it as a guard.</Text> A guard re-runs this exact case
        against every version you publish from now on and flags it under Quality if the determination
        ever changes. It writes to this policy&apos;s tests — never to the evaluation audit trail.
      </Paragraph>
      <Button
        icon={<SaveOutlined />}
        onClick={() => {
          void keep();
        }}
        loading={saving}
        data-testid="policy-case-guard-keep"
      >
        {seeds.length === 1 ? "Keep as a guard" : `Keep as ${seeds.length} guards`}
      </Button>
      {error ? (
        <Alert
          type="error"
          showIcon
          style={{ marginTop: 8 }}
          message={error}
          data-testid="policy-case-guard-error"
        />
      ) : null}
    </div>
  );
}

/**
 * Whether — and how — a case just answered can be kept as a guard, decided in one
 * place so every not-guardable answer states WHY rather than silently offering
 * nothing (a greyed control with no reason is exactly what constraint 5 forbids).
 *
 * The outcomes are kept apart: an engine-settled determination is keepable; an
 * informational answer and a judge-settled one are each not, for their own named
 * reason; and an un-persisted grouping has no policy to attach a guard to.
 */
function GuardFromCase({
  showInformational,
  reading,
  policySetKey,
  target,
}: {
  showInformational: boolean;
  reading: PolicyCaseReading | null;
  policySetKey: string | null | undefined;
  target: TestTarget;
}) {
  // An informational answer is our synthesis across several rules, not one rule's
  // verdict. Named, never greyed out in silence.
  if (showInformational) {
    return (
      <Alert
        type="info"
        showIcon
        style={{ marginTop: 16 }}
        data-testid="policy-case-not-guardable"
        message="This informational answer cannot be kept as a guard."
        description="A guard re-runs one rule's determination on a set of facts. This answer is composed by this app from several rules and states no single rule's verdict, so there is nothing deterministic for a guard to re-run."
      />
    );
  }

  if (!reading) return null;

  // Only a settled case is a determination at all. The other states explain
  // themselves in the reading above, and carry no verdict to keep.
  if (reading.state !== "settled") return null;

  // Settled, but by a judge reading words: it states no facts, so nothing
  // deterministic could re-run. Named for the same reason.
  if (reading.guardSeeds.length === 0) {
    return (
      <Alert
        type="info"
        showIcon
        style={{ marginTop: 16 }}
        data-testid="policy-case-not-guardable"
        message="This determination cannot be kept as a guard."
        description="It is settled by a rule the judge read in words, which states no facts. A guard re-runs deterministic facts, so there is nothing here for one to re-run."
      />
    );
  }

  // Guardable — but a guard attaches to a persisted policy (the policy is the
  // currency). A grouping inferred at read time has none.
  if (!policySetKey) {
    return (
      <Alert
        type="info"
        showIcon
        style={{ marginTop: 16 }}
        data-testid="policy-case-not-guardable"
        message="A guard needs a published policy to attach to."
        description="This grouping is read from the draft and is not persisted as a policy set, so there is nothing for a guard to re-run against yet."
      />
    );
  }

  // Guardable and persisted — but a guard re-runs against future *published*
  // versions (that is when run_active_tests_for_version fires). A case put to
  // the draft was computed against a single rule in isolation and against words
  // that may still change before they are published, so its reading does not
  // carry over into a faithful guard. Keep it once the policy is published.
  if (target.kind !== "published_version") {
    return (
      <Alert
        type="info"
        showIcon
        style={{ marginTop: 16 }}
        data-testid="policy-case-not-guardable"
        message="Keep this as a guard once the policy is published."
        description="A guard re-runs on every future published version. This case was put to the draft, whose rules may still change before they are published, so there is no published version yet for a guard to protect."
      />
    );
  }

  return <KeepAsGuard policySetKey={policySetKey} seeds={reading.guardSeeds} />;
}

export function PolicyCaseRunner({
  policySetKey,
  target,
  rules,
  provisionId,
}: {
  policySetKey: string | null | undefined;
  /**
   * What the case is put to: the policy as it is drafted, or a named published
   * version of it.
   *
   * Passed down rather than guessed, and reported in the answer rather than
   * left for the reader to infer from which page they are on. It is a fact
   * about the record, not a permission granted by the caller.
   */
  target: TestTarget;
  rules: readonly CanonicalRule[];
  /**
   * The persisted provision this policy is, when it has one. The policy-level
   * grounded answer is built server-side from this id, so it is what the one
   * model call needs and all it needs.
   *
   * Absent — `null` or `undefined` — for a policy whose boundary was inferred at
   * read time rather than persisted: there is no provision to name, so no record
   * to ground on, and the case falls to the per-rule deciders below. That is the
   * honest reading of an un-persisted grouping, not a failure, so nothing here
   * reports it as one.
   */
  provisionId?: string | null;
}) {
  const [scenario, setScenario] = useState("");
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>("low");
  const [answers, setAnswers] = useState<CaseAnswer[] | null>(null);
  const [asked, setAsked] = useState(0);
  const [running, setRunning] = useState(false);
  /**
   * Which of the two kinds the case was read as, and — when it asked what the
   * policy provides — the gathered answer. Both are `null` until a run resolves
   * the intent. A run whose classification does not arrive leaves the intent
   * `decision`, so the case is put to the rules rather than answered as something
   * it is not.
   */
  const [intent, setIntent] = useState<CaseIntent | null>(null);
  const [informational, setInformational] = useState<InformationalAnswer | null>(null);

  const run = async () => {
    setRunning(true);
    setIntent(null);
    setInformational(null);
    setAnswers(null);
    setAsked(0);

    // Classify first, and let the server gather the answer when the case asks
    // what the policy provides. Such a case must never be run through the
    // per-rule deciders: a rule that states the answer would be reported as
    // unsettled for want of the very quantity being asked about.
    //
    // Only a persisted provision can be asked: the grounded answer is built from
    // the record the server holds under that id. Without one there is nothing to
    // ground on, so the case goes to the per-rule deciders — the same path a
    // classification that did not arrive takes, and for the same reason: a
    // policy-level answer that was never composed must not be invented here.
    //
    // Fail closed. If the classification cannot be reached or is refused, put the
    // case to the rules rather than answer a different question than the one
    // asked — a classification that did not arrive must not masquerade as one
    // that did. This path never says so in words that read as an error: nothing
    // failed for the reviewer, the case is simply decided rule by rule.
    let classified: Awaited<ReturnType<typeof answerPolicyCase>> | null = null;
    if (provisionId) {
      try {
        classified = await answerPolicyCase(provisionId, { scenario: scenario.trim(), reasoningEffort });
      } catch {
        classified = null;
      }
    }

    if (classified && classified.intent === "informational" && classified.informational) {
      setIntent("informational");
      setInformational(classified.informational);
      setRunning(false);
      return;
    }

    setIntent("decision");
    setAnswers([]);
    const collected: CaseAnswer[] = [];
    // Sequentially, not in parallel: each is a model call, and a policy's worth
    // of them fired at once is the difference between a slow answer and a
    // rate-limit refusal that loses the ones already paid for.
    for (const rule of rules) {
      const answer = await putCaseToRule(rule, {
        scenario: scenario.trim(),
        reasoningEffort,
        policySetKey,
        target,
      });
      collected.push(answer);
      setAnswers([...collected]);
      setAsked(collected.length);
    }
    setRunning(false);
  };

  const showInformational = intent === "informational" && informational !== null;
  // The policy-level reading is drawn only once the run is complete: a reading of
  // half the rules would lead with a "settling" rule that a later one contradicts.
  const reading: PolicyCaseReading | null =
    !showInformational && !running && answers && answers.length > 0 ? readPolicyCase(answers) : null;

  return (
    <div className="policy-pane policy-case-runner" data-testid="policy-case-runner">
      <Paragraph type="secondary" data-testid="policy-case-intro" style={{ marginBottom: 16 }}>
        Describe a situation and this policy answers it as a whole, naming the rule or rules the
        answer rests on so you can read each yourself.
      </Paragraph>

      <Paragraph type="secondary" data-testid="policy-case-target">
        The case is put to <Text strong>{targetLabel(target)}</Text>.
        {target.kind === "draft" ? ` ${RESULT_DOES_NOT_CARRY_OVER}` : ""}
      </Paragraph>

      <Paragraph>
        <Text strong>Describe a case in plain English</Text>
      </Paragraph>
      <TextArea
        rows={3}
        value={scenario}
        onChange={(e) => setScenario(e.target.value)}
        placeholder="e.g. Someone in the situation this policy governs asks whether they may proceed"
        data-testid="policy-case-scenario"
      />
      <Space style={{ marginTop: 12, marginBottom: 16 }} wrap>
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
          icon={<ReadOutlined />}
          onClick={() => {
            void run();
          }}
          loading={running}
          disabled={!scenario.trim() || rules.length === 0}
          data-testid="policy-case-run"
        >
          {running
            ? intent === "decision"
              ? `Putting the case to each rule… ${asked} of ${rules.length}`
              : "Reading the case…"
            : "Put this case to this policy"}
        </Button>
      </Space>

      {running && intent === "decision" ? (
        <Progress percent={Math.round((asked / Math.max(rules.length, 1)) * 100)} size="small" />
      ) : null}

      {showInformational && informational ? (
        <InformationalPanel informational={informational} rules={rules} policySetKey={policySetKey} />
      ) : reading ? (
        <div data-testid="policy-case-rollup">
          <DecisionReading reading={reading} policySetKey={policySetKey} />
        </div>
      ) : null}

      <GuardFromCase
        showInformational={showInformational && informational !== null}
        reading={reading}
        policySetKey={policySetKey}
        target={target}
      />

      {!showInformational && reading ? (
        <Paragraph
          type="secondary"
          style={{ fontSize: 12, marginTop: 16, marginBottom: 0 }}
          data-testid="policy-case-detail-heading"
        >
          <Text strong>Behind the reading — each rule on its own.</Text> The reading above rests on
          these; every rule read is kept here, in the words its own decider gave, so the detail is
          present to check rather than the thing you meet first. None is hidden.
        </Paragraph>
      ) : null}

      {!showInformational ? (
        <Table<CaseAnswer>
        size="small"
        rowKey="ruleId"
        dataSource={answers ?? []}
        pagination={false}
        style={{ marginTop: 12 }}
        locale={{
          emptyText: (
            <Empty
              description={
                rules.length === 0
                  ? "This policy states no rules to put a case to."
                  : "Describe a case above, and this policy will answer it."
              }
            />
          ),
        }}
        columns={[
          {
            title: "Rule",
            dataIndex: "title",
            render: (title: string) => <DirectionalText>{title}</DirectionalText>,
          },
          {
            title: "Decided by",
            dataIndex: "decidedBy",
            width: 130,
            render: (decidedBy: CaseAnswer["decidedBy"]) => (
              <Tag color={DECIDED_BY[decidedBy].color}>{DECIDED_BY[decidedBy].label}</Tag>
            ),
          },
          {
            title: "Answer",
            key: "answer",
            render: (_: unknown, row: CaseAnswer) => (
              <Space direction="vertical" size={2}>
                {row.label ? (
                  <Tag color={row.color}>{row.label}</Tag>
                ) : (
                  <Text type="secondary">{row.unanswered}</Text>
                )}
                {row.account ? (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    <DirectionalText>{row.account}</DirectionalText>
                  </Text>
                ) : null}
                {row.missing.length > 0 ? (
                  <Space wrap size={4}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      The case would have to state:
                    </Text>
                    {row.missing.map((fact) => (
                      <Tag key={fact} color="gold">
                        {fact}
                      </Tag>
                    ))}
                  </Space>
                ) : null}
              </Space>
            ),
          },
        ]}
      />
      ) : null}

      {(showInformational && informational) || (answers && answers.length > 0) ? (
        <Text type="secondary" style={{ fontSize: 12 }} data-testid="policy-case-not-saved">
          Reading a case here writes nothing. The one thing that does is deliberately keeping a
          guard, which writes to this policy&apos;s tests — never to the evaluation audit trail,
          which records what calling systems asked.
        </Text>
      ) : null}
    </div>
  );
}
