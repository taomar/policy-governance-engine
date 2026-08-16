/**
 * Putting one case to a whole policy.
 *
 * WHY A POLICY SCOPE AT ALL
 *
 * A policy is what the document states and what a person approves; its rules
 * are how it decides. So the question a reviewer actually has — "what does this
 * policy say about this situation?" — is a question about the policy, and
 * answering it one rule at a time makes the reviewer do the assembly the record
 * already did for them. Worse, it hides the case that matters most: two rules
 * of one policy reaching answers that do not sit together.
 *
 * WHAT THIS IS NOT
 *
 * It is not a second decider. Every rule here is asked through
 * `putCaseToRule`, the same single routing the rule-scope tester uses, so a
 * rule asked on its own and the same rule asked as part of its policy reach the
 * same instrument. Two copies of that routing would drift, and the drift would
 * be invisible until two surfaces disagreed about one rule.
 *
 * WHY THE ANSWERS ARE NOT ADDED UP
 *
 * The engine computes whether a case *satisfies* a rule. The judge reads
 * whether a rule *applies* to a case. Those are different questions, so their
 * answers are not points on one scale and there is no honest way to total them
 * into "9 passed". What is counted instead is what was asked and what came
 * back — which decider answered, and what was left unanswered — and every
 * answer is shown in the words of whoever gave it.
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
import { putCaseToRule, targetLabel, RESULT_DOES_NOT_CARRY_OVER, type CaseAnswer, type TestTarget } from "./policyTesting";

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

type ReasoningEffort = "low" | "medium" | "high";

/** How a decider is named where a reviewer reads which one answered. */
const DECIDED_BY: Record<CaseAnswer["decidedBy"], { label: string; color: string }> = {
  engine: { label: "Computed", color: "geekblue" },
  judge: { label: "Read", color: "purple" },
  nobody: { label: "Not asked", color: "default" },
};

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

  const run = async () => {
    setRunning(true);
    setAnswers([]);
    setAsked(0);
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

  const answeredByEngine = (answers ?? []).filter((a) => a.decidedBy === "engine").length;
  const answeredByJudge = (answers ?? []).filter((a) => a.decidedBy === "judge").length;
  const unanswered = (answers ?? []).filter((a) => a.decidedBy === "nobody").length;

  return (
    <div className="policy-pane" data-testid="policy-case-runner">
      <Alert
        type="info"
        showIcon
        message="One case, put to every rule this policy states"
        description={
          <span>
            Each rule is decided by the instrument its own route calls for: a rule stating a
            comparison between named quantities is computed, and a rule stating what it requires in
            words is read against your case. Both settle the rule. They settle it differently, and
            each answer below is shown in the words of whichever settled it.
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
            ? `Putting the case… ${asked} of ${rules.length}`
            : rules.length === 1
              ? "Put this case to the rule"
              : `Put this case to all ${rules.length} rules`}
        </Button>
      </Space>

      {running ? (
        <Progress percent={Math.round((asked / Math.max(rules.length, 1)) * 100)} size="small" />
      ) : null}

      {answers && answers.length > 0 && !running ? (
        <Paragraph data-testid="policy-case-rollup">
          <Text strong>What came back: </Text>
          {[
            answeredByEngine > 0
              ? `${answeredByEngine} ${answeredByEngine === 1 ? "rule was" : "rules were"} computed`
              : null,
            answeredByJudge > 0
              ? `${answeredByJudge} ${answeredByJudge === 1 ? "rule was" : "rules were"} read`
              : null,
            unanswered > 0
              ? `${unanswered} ${unanswered === 1 ? "was" : "were"} not answered`
              : null,
          ]
            .filter(Boolean)
            .join(", ")}
          . Each answer stands on its own — the two routes answer different questions, so nothing
          here is added up into a single verdict for the policy.
        </Paragraph>
      ) : null}

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
                  : "Describe a case above, and every rule of this policy will answer it."
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

      {answers && answers.length > 0 ? (
        <Text type="secondary" style={{ fontSize: 12 }} data-testid="policy-case-not-saved">
          Answers read here are yours to look at. Nothing is written to this policy's tests or to
          the evaluation audit trail, which records what calling systems asked.
        </Text>
      ) : null}
    </div>
  );
}
