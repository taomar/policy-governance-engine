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
 * Nothing here is saved. This is a reviewer looking, not a calling system
 * evaluating, and the audit trail records the second only.
 */
import { useState } from "react";
import { Alert, Button, Empty, Progress, Select, Space, Table, Tag, Typography } from "antd";
import { ReadOutlined } from "@ant-design/icons";
import { Input } from "antd";
import type { CanonicalRule } from "../api";
import { DirectionalText } from "./DirectionalText";
import { RuleName } from "./RuleName";
import { putCaseToRule, targetLabel, RESULT_DOES_NOT_CARRY_OVER, type CaseAnswer, type TestTarget } from "./policyTesting";
import { answerPolicyCase, type CaseIntent, type InformationalAnswer } from "./policyCaseIntent";
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
 * Every rule of the policy, listed so leading with a few never leaves a reviewer
 * believing those few were all there were.
 *
 * It is not behind a disclosure: what a reviewer needs to judge what they were
 * shown does not sit behind a click. It says how many rules were read and shows
 * each — its finding aids, and its own title verbatim — marking the ones the
 * answer above already rested on so the reader can tell cited from merely read
 * without either being hidden.
 */
function AllRulesReference({
  rules,
  policySetKey,
  citedIds,
  heading,
}: {
  rules: readonly CanonicalRule[];
  policySetKey: string | null | undefined;
  citedIds: ReadonlySet<string>;
  heading: string;
}) {
  if (rules.length === 0) return null;
  return (
    <div data-testid="policy-case-all-rules" style={{ marginTop: 16 }}>
      <Paragraph type="secondary" style={{ marginBottom: 6 }}>
        <Text strong>{heading}.</Text> Each is listed here; none is hidden.
      </Paragraph>
      <Space direction="vertical" size={8} style={{ width: "100%" }}>
        {rules.map((rule) => (
          <div key={rule.rule_id} className="policy-case-reading__rule">
            <NamedRule policySetKey={policySetKey} ruleId={rule.rule_id} variant="block" />
            <Space wrap size={6} align="start">
              <DirectionalText>{rule.title}</DirectionalText>
              {citedIds.has(rule.rule_id) ? <Tag color="purple">the answer rests on this</Tag> : null}
            </Space>
          </div>
        ))}
      </Space>
    </div>
  );
}

/**
 * The answer to a case that asks what the policy provides.
 *
 * The four states are kept apart, because a stated answer, a policy that holds
 * nothing on the subject, a model that would not compose one, and a request that
 * did not complete are four different replies and a reviewer shown one dressed as
 * another is misled. Only the first carries composed words, and those are marked
 * as the app's — the ✦ and "by this app" the generated rule name already uses —
 * over the rules they were drawn from, each named and quoted verbatim so the
 * reader can go from the answer to the exact sentence and check it.
 */
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
      {citations.map((c) => (
        <div key={c.rule_id} className="policy-case-citation" data-testid="policy-case-citation">
          <NamedRule policySetKey={policySetKey} ruleId={c.rule_id} variant="block" />
          <div>
            <Text strong>
              <DirectionalText>{c.title}</DirectionalText>
            </Text>
          </div>
          <Paragraph style={{ marginBottom: 0 }}>
            “<DirectionalText align>{c.quote}</DirectionalText>”
          </Paragraph>
        </div>
      ))}

      <AllRulesReference
        rules={rules}
        policySetKey={policySetKey}
        citedIds={citedIds}
        heading={`All ${rules.length} ${rules.length === 1 ? "rule" : "rules"} of this policy were read`}
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

export function PolicyCaseRunner({
  policySetKey,
  target,
  rules,
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
    // Fail closed. If the classification cannot be reached or is refused, put the
    // case to the rules rather than answer a different question than the one
    // asked — a classification that did not arrive must not masquerade as one
    // that did. This path never says so in words that read as an error: nothing
    // failed for the reviewer, the case is simply decided rule by rule.
    let classified: Awaited<ReturnType<typeof answerPolicyCase>> | null = null;
    try {
      classified = await answerPolicyCase(rules, { scenario: scenario.trim(), reasoningEffort });
    } catch {
      classified = null;
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
    <div className="policy-pane" data-testid="policy-case-runner">
      <Alert
        type="info"
        showIcon
        message="One case, one answer from this policy"
        description={
          <span>
            Describe a situation and this policy answers it as a whole, leading with the rule or
            rules the answer rests on and naming them so you can read each yourself. A question of
            what the policy says is answered from the rules that state it; a case that describes a
            situation for a determination is decided by each rule through its own route — a
            comparison between named quantities is computed, what a rule requires in words is read —
            and where those routes point different ways you are told, not handed one answer that hid
            it.
          </span>
        }
        style={{ marginBottom: 16 }}
      />

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
          Answers read here are yours to look at. Nothing is written to this policy's tests or to
          the evaluation audit trail, which records what calling systems asked.
        </Text>
      ) : null}
    </div>
  );
}
