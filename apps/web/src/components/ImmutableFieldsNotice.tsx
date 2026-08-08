import { Alert, Space, Tag, Typography } from "antd";
import { LockOutlined } from "@ant-design/icons";

const { Text } = Typography;

/** Fields the server owns, by form context.
 *
 * These are listed in one place rather than written into each form's copy so
 * the disclaimer cannot drift away from what the API actually enforces in
 * `candidate_rules.draft_candidate_rule` / `revise_candidate_rule`. */
const SERVER_OWNED: Record<"draft" | "edit", { field: string; why: string }[]> = {
  draft: [
    { field: "policy_set_id", why: "assigned from the policy set you are drafting into" },
    { field: "policy_version_id", why: "stays 'draft' until a manager publishes a version" },
    { field: "rule_revision", why: "starts at 1 and is incremented by the platform" },
  ],
  edit: [
    { field: "rule_id", why: "the rule's permanent identity — editing it would orphan its review history" },
    { field: "policy_set_id", why: "fixed by the policy set this candidate belongs to" },
    { field: "policy_version_id", why: "stays 'draft' until a manager publishes a version" },
    { field: "evidence", why: "the source clauses this rule was extracted from; changing them would break traceability" },
    { field: "lineage", why: "records which model and prompt produced the rule" },
  ],
};

/**
 * Tells the user, before they start typing, which fields the server will
 * overwrite regardless of what the form sends.
 *
 * Both endpoints silently `model_copy(update=...)` these fields. Silently is
 * the problem: a user who edits `rule_id` in raw-JSON mode gets a 200 back and
 * reasonably assumes it took effect. Stating the contract up front is cheaper
 * than explaining the surprise afterwards.
 */
export function ImmutableFieldsNotice({
  mode = "draft",
  ruleId,
}: {
  mode?: "draft" | "edit";
  ruleId?: string;
}) {
  const fields = SERVER_OWNED[mode];
  return (
    <Alert
      type="info"
      showIcon
      icon={<LockOutlined />}
      style={{ marginBottom: 16 }}
      message={
        <Space size={8} wrap>
          <Text strong style={{ fontSize: 13 }}>
            Some fields are set by the platform, not by you
          </Text>
          {mode === "draft" && ruleId?.trim() ? (
            <Text type="secondary" style={{ fontSize: 12 }}>
              — your rule ID <Tag style={{ marginInlineEnd: 0 }}>{ruleId.trim()}</Tag> is permanent once submitted
            </Text>
          ) : null}
        </Space>
      }
      description={
        <div style={{ fontSize: 12 }}>
          <ul style={{ margin: "4px 0 0", paddingInlineStart: 18 }}>
            {fields.map((f) => (
              <li key={f.field} style={{ marginBottom: 2 }}>
                <Text code style={{ fontSize: 11 }}>
                  {f.field}
                </Text>{" "}
                <Text type="secondary">— {f.why}</Text>
              </li>
            ))}
          </ul>
          <Text type="secondary" style={{ display: "block", marginTop: 6 }}>
            Anything you enter in these fields (including in raw-JSON mode) is replaced on save.
          </Text>
        </div>
      }
    />
  );
}
