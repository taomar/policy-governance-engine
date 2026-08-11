import { Alert, Empty, Space, Table, Tag, Tooltip, Typography } from "antd";
import { AuditOutlined, TeamOutlined } from "@ant-design/icons";
import type { CanonicalRule, DecisionReadiness, RuleParty } from "../api";
import { XACML_NOTE } from "../xacml";

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
    label: "Decomposition damaged",
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
  // Keyed on an authority party rather than on the verdict: a rule can state a
  // testable limit *and* need a human to approve it. "not exceeding 5% ... and
  // subject to the judgment and approval of the Board of Trustees" is both, and
  // grouping only the rules with nothing else stated would leave out the one
  // that most needs a person in the loop.
  const deciders = readiness.parties.filter((party) => party.role === "authority");

  return (
    <div className="decision-readiness">
      <Alert
        type={readiness.evaluability === "malformed" ? "error" : "info"}
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
          <>
            <Paragraph type="secondary" className="decision-readiness-gloss">
              {verdict.gloss}
            </Paragraph>
            <Text type="secondary" className="decision-readiness-reason">
              {readiness.reason}
            </Text>
          </>
        }
      />

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
