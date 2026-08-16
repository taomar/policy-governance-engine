import { Alert, Empty, Space, Table, Tag, Tooltip, Typography } from "antd";
import { AuditOutlined, TeamOutlined } from "@ant-design/icons";
import type { CanonicalRule, DecisionReadiness, RuleParty } from "../api";
import { XACML_NOTE } from "../xacml";
import { splitDefectFinding } from "../ruleExecutability";
import { AmbiguityNoteView } from "./AmbiguityNoteView";

const { Text, Paragraph } = Typography;

/**
 * What an LLM evaluating this rule against a customer's case needs, and
 * whether it can.
 *
 * This exists because `machine_executable` answers a different question and
 * the product only ever showed that one. It asks whether the *FEEL* evaluator
 * can decide the rule, which needs a fact model mapping "the employee's
 * current basic salary" to a path in the customer's schema — so it reads false
 * for every AI-extracted rule, and the product reported "0 of 45 executable"
 * about a document whose rules are mostly decidable.
 *
 * The shipped JSON is evaluated by an LLM that performs that binding from the
 * case in front of it. Nothing here is evaluated by the deterministic engine
 * and nothing is written into `rule.condition`.
 */

const VERDICT: Record<
  DecisionReadiness["evaluability"],
  { color: string; label: string; gloss: string }
> = {
  decidable: {
    color: "green",
    label: "Decidable",
    gloss: "The source states a test and its terms. An evaluator has everything the document offers.",
  },
  discretionary: {
    color: "blue",
    label: "Delegated",
    gloss:
      "The source states no test because it delegated the decision. DMN models this as an authority requirement; XACML as a Permit carrying an Obligation to obtain approval. A delegated decision is still a decision.",
  },
  underspecified: {
    color: "orange",
    label: "Underspecified",
    gloss:
      "The source names a subject and a verb and nothing else — no value, condition, time, place or authority. The gap belongs to the document, not the extraction.",
  },
  not_a_decision: {
    color: "default",
    label: "States meaning only",
    gloss: "A definition or classification. It grants and refuses nothing, so there is nothing to decide.",
  },
  malformed: {
    color: "red",
    label: "Split in the wrong place",
    gloss:
      "The sentence was mis-split, so every claim derived from it inherits the error. This one is ours to fix, not the document's.",
  },
};

/** XACML §B.2 subject categories, and the one role the standard has no category for. */
const PARTY_ROLE: Record<RuleParty["role"], { label: string; note: string }> = {
  access_subject: {
    label: "Governs",
    note: "XACML access-subject — the party whose conduct this rule governs.",
  },
  recipient_subject: {
    label: "Receives",
    note: "XACML recipient-subject — the party that receives the result. Not the same as the party whose conduct is governed.",
  },
  authority: {
    label: "Decides",
    note: "XACML has no subject category for an approver: it models required approval as an Obligation the decision point must discharge. DMN models it as an authority requirement on a knowledge source.",
  },
};

export function DecisionReadinessView({ rule }: { rule: CanonicalRule }) {
  const readiness = rule.decision_readiness;
  if (!readiness) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="No readiness assessment stored. Rules authored by hand never went through the formulator, so there is no canonical decomposition to assess."
      />
    );
  }

  const verdict = VERDICT[readiness.evaluability];
  // `malformed` is the one value that is not a reading of the document. The
  // other four describe how the source states its test; this one says the app
  // divided the source's sentence wrongly, which invalidates the parties and
  // attributes below rather than describing them. So it is lifted out of the
  // verdict row and stated as a finding, in its own words, with the consequence
  // and the next step a reviewer needs. Leaving it as a red tag among four
  // neutral ones is what made it read as a crash.
  const splitDefect =
    readiness.evaluability === "malformed" ? splitDefectFinding(rule.review_status) : null;
  // Keyed on an authority party rather than on the verdict: a rule can state a
  // testable limit *and* need a human to approve it. "not exceeding 5% ... and
  // subject to the judgment and approval of the Board of Trustees" is both, and
  // grouping only the rules with nothing else stated would leave out the one
  // that most needs a person in the loop.
  const deciders = readiness.parties.filter((party) => party.role === "authority");

  return (
    <div className="decision-readiness">
      {splitDefect ? (
        <Alert
          type="warning"
          showIcon
          data-testid="split-defect-finding"
          message={splitDefect.heading}
          description={
            <div className="decision-readiness-defect">
              <Paragraph type="secondary" className="decision-readiness-gloss">
                {splitDefect.consequence}
              </Paragraph>
              <Paragraph className="decision-readiness-gloss">
                <Text strong data-testid="split-defect-approval">
                  {splitDefect.blocksApproval
                    ? "Do not approve this rule while it reads this way."
                    : "This does not stand in the way of approving the rule."}
                </Text>
              </Paragraph>
              <Paragraph type="secondary" className="decision-readiness-gloss">
                <Text data-testid="split-defect-next-step">{splitDefect.nextStep}</Text>
              </Paragraph>
            </div>
          }
        />
      ) : (
        <Alert
          type="info"
          showIcon
          message={
            <Space size={8} wrap>
              <Tag color={verdict.color}>{verdict.label}</Tag>
              {deciders.length > 0 && (
                <Tag icon={<AuditOutlined />} color="purple">
                  Bounded by human judgement
                </Tag>
              )}
            </Space>
          }
          description={
            <Paragraph type="secondary" className="decision-readiness-gloss">
              {verdict.gloss}
            </Paragraph>
          }
        />
      )}

      {deciders.length > 0 && (
        <div className="decision-readiness-section">
          <Text strong>
            <AuditOutlined /> Who decides
          </Text>
          <Paragraph type="secondary" className="decision-readiness-hint">
            Named in the source. The decision point must obtain this approval before acting —
            no evaluator, deterministic or otherwise, can substitute for it.
          </Paragraph>
          <Space size={6} wrap>
            {deciders.map((party) => (
              <Tooltip key={`${party.name}-${party.source}`} title={`read from "${party.source}"`}>
                <Tag color="purple">{party.name}</Tag>
              </Tooltip>
            ))}
          </Space>
        </div>
      )}

      <div className="decision-readiness-section">
        <Text strong>
          <TeamOutlined /> Parties
        </Text>
        {readiness.parties.length === 0 ? (
          <Paragraph type="secondary" className="decision-readiness-hint">
            The source names no party. Absent is not the same as missing — a rule about an
            amount ("Annual increase shall not exceed 10%") legitimately names nobody, and
            the grammatical subject is not treated as a person.
          </Paragraph>
        ) : (
          <Table
            size="small"
            pagination={false}
            rowKey={(party) => `${party.role}-${party.name}`}
            dataSource={readiness.parties}
            columns={[
              {
                title: "Party",
                dataIndex: "name",
                render: (name: string) => <Text>{name}</Text>,
              },
              {
                title: "Role",
                dataIndex: "role",
                width: 130,
                render: (role: RuleParty["role"]) => (
                  <Tooltip title={PARTY_ROLE[role].note}>
                    <Tag color={role === "authority" ? "purple" : "blue"}>
                      {PARTY_ROLE[role].label}
                    </Tag>
                  </Tooltip>
                ),
              },
              {
                title: "Read from",
                dataIndex: "source",
                render: (source: string) => (
                  <Text code className="decision-readiness-source">
                    {source}
                  </Text>
                ),
              },
            ]}
          />
        )}
      </div>

      {/* What the source's wording admits. Rendered for every status,
          including "none", so the field is never invisible on the tab a
          reviewer opens to see what the system holds about deciding this. */}
      <AmbiguityNoteView status={rule.ambiguity_status} variant="section" />

      <div className="decision-readiness-section">
        <Text strong>Attributes the evaluator must find</Text>
        <Paragraph type="secondary" className="decision-readiness-hint">
          Quoted from the source, never a fact path. This is the target list for the
          extraction pass: without it the evaluating model decides for itself what is
          relevant, which is where non-determinism enters — at extraction, before any
          evaluation happens. An attribute the case never mentions is then detectably
          absent rather than silently estimated.
        </Paragraph>
        {readiness.required_attributes.length === 0 ? (
          <Text type="secondary">The rule named nothing to look for.</Text>
        ) : (
          <Space size={6} wrap>
            {readiness.required_attributes.map((attribute) => (
              <Tooltip
                key={`${attribute.role}-${attribute.phrase}`}
                title={`canonical "${attribute.role}"`}
              >
                <Tag>{attribute.phrase}</Tag>
              </Tooltip>
            ))}
          </Space>
        )}
      </div>

      <Text type="secondary" className="decision-readiness-standard">
        {XACML_NOTE}
      </Text>
    </div>
  );
}
