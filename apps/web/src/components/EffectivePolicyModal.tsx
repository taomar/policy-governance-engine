import { Alert, Modal, Space, Table, Tag, Typography } from "antd";
import { ApartmentOutlined, EyeOutlined } from "@ant-design/icons";
import type { CanonicalRule } from "../api";
import { effectivePolicy, type EffectiveCase } from "../familyComposite";
import { clusterLabel, type RuleVariationGroup } from "../ruleDisplay";
import { ConditionView } from "./ConditionView";

const { Text, Paragraph } = Typography;

/**
 * A family of rules shown as the one policy they collectively state.
 *
 * Read only, and deliberately so. The platform still decides on the individual
 * rules — this exists so a reviewer can see what those rules add up to before
 * deciding them, which the row list cannot show: eight rows of a severity
 * matrix are one policy with eight cases, and reconstructing that from the
 * rows is work the reviewer should not have to do.
 *
 * Nothing here is authored. Shared parts are established by agreement across
 * every member, cases are copied from members verbatim, and where the source
 * gave no executable condition the stated wording is shown as stated wording.
 * There is no summarisation step, because a summary of a policy is a new claim
 * about the policy.
 */
export function EffectivePolicyModal({
  open,
  onClose,
  cluster,
  members,
}: {
  open: boolean;
  onClose: () => void;
  cluster: RuleVariationGroup;
  members: CanonicalRule[];
}) {
  const policy = effectivePolicy(members);

  const columns = [
    {
      title: "Case",
      dataIndex: "label",
      key: "label",
      width: "26%",
      render: (label: string, row: EffectiveCase) => (
        <Space orientation="vertical" size={2}>
          <Text strong>{label}</Text>
          <Text type="secondary" className="effective-policy-ruleid">
            {row.ruleId}
          </Text>
        </Space>
      ),
    },
    {
      title: "When",
      key: "when",
      width: "36%",
      render: (_: unknown, row: EffectiveCase) => {
        if (row.when.kind === "executable") {
          return <ConditionView node={row.when.node} />;
        }
        if (row.when.kind === "stated") {
          return (
            <Space orientation="vertical" size={2}>
              {row.when.lines.map((line) => (
                <Text key={line}>{line}</Text>
              ))}
              <Tag variant="filled" className="effective-policy-flag">
                AI Ready
              </Tag>
            </Space>
          );
        }
        return (
          <Text type="secondary">
            No condition derived — a reviewer must decide whether it is unconditional
          </Text>
        );
      },
    },
    {
      title: "Then",
      key: "then",
      width: "26%",
      render: (_: unknown, row: EffectiveCase) => (
        <Space orientation="vertical" size={2}>
          <Text>{row.then || "—"}</Text>
          {row.effectType && (
            <Tag variant="filled" className="effective-policy-flag">
              {row.effectType}
            </Tag>
          )}
        </Space>
      ),
    },
    {
      title: "Status",
      key: "status",
      width: "12%",
      render: (_: unknown, row: EffectiveCase) => (
        <Space orientation="vertical" size={2}>
          <Tag variant="filled">{row.reviewStatus}</Tag>
        </Space>
      ),
    },
  ];

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={1000}
      title={
        <Space size={8}>
          <ApartmentOutlined />
          <span>Effective policy</span>
          <Tag variant="filled">
            {policy.cases.length} rule{policy.cases.length === 1 ? "" : "s"} · 1 policy
          </Tag>
        </Space>
      }
    >
      <Alert
        type="info"
        showIcon
        icon={<EyeOutlined />}
        className="effective-policy-banner"
        title="View only"
        description="Assembled from the rules below to show what they state together. It is not itself a rule: nothing here is stored, published or evaluated, and decisions are still made on the individual rules."
      />

      <div className="effective-policy-statement">
        <Text strong className="effective-policy-label">
          {clusterLabel(cluster)}
        </Text>
        {(policy.subject || policy.predicate) && (
          <Paragraph className="effective-policy-spo">
            {policy.subject && <Text strong>{policy.subject}</Text>}{" "}
            {policy.predicate && <Text>{policy.predicate}</Text>}{" "}
            <Text type="secondary">
              — one of {policy.cases.length} case{policy.cases.length === 1 ? "" : "s"} below
            </Text>
          </Paragraph>
        )}
        {!policy.subject && !policy.predicate && (
          <Paragraph type="secondary" className="effective-policy-spo">
            These rules state no subject and predicate identically, so no shared statement can be
            shown without asserting one the source did not make. The cases are listed as extracted.
          </Paragraph>
        )}
      </div>

      {policy.duplicateLabels.length > 0 && (
        <Alert
          type="warning"
          showIcon
          className="effective-policy-banner"
          title="The same case is stated more than once"
          description={`${policy.duplicateLabels.join(", ")} — either the source repeats itself, or extraction produced a duplicate. Both need a decision before this policy can be relied on.`}
        />
      )}

      {policy.reviewStatuses.length > 1 && (
        <Alert
          type="warning"
          showIcon
          className="effective-policy-banner"
          title="Cases are in different review states"
          description="Approving only what is visible would leave this policy partly decided."
        />
      )}

      {policy.sharedConditions.length > 0 && (
        <div className="effective-policy-shared">
          <Text type="secondary" className="effective-policy-shared-label">
            Conditions the source states for this policy
          </Text>
          <ul className="effective-policy-shared-list">
            {policy.sharedConditions.map((condition) => (
              <li key={condition}>{condition}</li>
            ))}
          </ul>
          <Text type="secondary" className="effective-policy-shared-note">
            Every rule carries this same list, so it describes the policy rather than any one case.
            Which condition selects which case is not stated as a comparison, so a reviewer decides
            that by reading.
          </Text>
        </div>
      )}

      <Table
        size="small"
        rowKey="ruleId"
        pagination={false}
        dataSource={policy.cases}
        columns={columns}
        className="effective-policy-table"
      />

      <div className="effective-policy-footer">
        <Text type="secondary">
          Source document{policy.documentVersionIds.length === 1 ? "" : "s"}:{" "}
          {policy.documentVersionIds.join(", ") || "unknown"}
        </Text>
      </div>
    </Modal>
  );
}
