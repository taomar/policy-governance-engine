import { Button, Dropdown, message, Tooltip } from "antd";
import type { MenuProps } from "antd";
import { ClockCircleOutlined, CopyOutlined, EditOutlined, MoreOutlined } from "@ant-design/icons";
import type { CanonicalRule } from "../api";
import { candidateEditability } from "../candidateEditability";

/**
 * The actions a record offers when nobody may change it in place.
 *
 * WHY THE MENU IS DERIVED AND NOT PASSED IN
 *
 * The entries here are decided by `candidateEditability(status)` — the same
 * table the server enforces and the review surfaces read. A caller that handed
 * this component a "you may edit" flag would be a second opinion on the same
 * question, and two opinions on it is how the published page came to offer a
 * different set of controls from the review page in the first place.
 *
 * A published record answers `canEdit: false`, and it says why: a published
 * version is an immutable snapshot, so the way to change it is to start a
 * revision, not to overwrite it. That is what `Revise` is, and it is why
 * `Revise` belongs here while `Edit` does not. The two are not the same act
 * wearing different words — one writes a new record and leaves the published
 * one standing, the other would rewrite what a version already promised.
 *
 * `Revise` is still conditional on the caller supplying a handler, because
 * whether a revision can be *started* is a fact about the version (only the
 * active one may be revised) rather than about the record. That is a different
 * question from whether this record may be edited, and it is the caller's to
 * answer.
 */
export function PublishedRecordActions({
  rule,
  status = "published",
  onRevise,
  onViewHistory,
  size = "small",
}: {
  rule: CanonicalRule;
  /** The record's own review state. Defaults to the state every rule of a
   *  published version is in; passed explicitly by anything that holds a
   *  record in another state. */
  status?: string;
  /** Present only when this record's version is the one a revision may be
   *  started from. */
  onRevise?: (rule: CanonicalRule) => void;
  /** Opens this record with its history in view. */
  onViewHistory?: (rule: CanonicalRule) => void;
  size?: "small" | "middle";
}) {
  const editability = candidateEditability(status);

  const copyId = async () => {
    try {
      await navigator.clipboard.writeText(rule.rule_id);
      message.success(`Copied ${rule.rule_id}`);
    } catch {
      message.error("Couldn't copy — clipboard unavailable");
    }
  };

  const items: MenuProps["items"] = [
    onRevise && {
      key: "revise",
      label: "Revise",
      icon: <EditOutlined />,
      title: editability.editBlockedReason ?? undefined,
    },
    { key: "copy", label: "Copy ID", icon: <CopyOutlined /> },
    onViewHistory && { key: "history", label: "View history", icon: <ClockCircleOutlined /> },
  ].filter(Boolean) as MenuProps["items"];

  const onClick: MenuProps["onClick"] = ({ key, domEvent }) => {
    domEvent.stopPropagation();
    if (key === "revise") onRevise?.(rule);
    else if (key === "copy") void copyId();
    else if (key === "history") onViewHistory?.(rule);
  };

  return (
    <Dropdown menu={{ items, onClick }} trigger={["click"]} placement="bottomRight">
      <Tooltip title="More actions for this record">
        <Button
          type="text"
          size={size}
          icon={<MoreOutlined />}
          onClick={(e) => e.stopPropagation()}
          aria-label={`More actions for ${rule.rule_id}`}
          data-testid="record-actions"
        />
      </Tooltip>
    </Dropdown>
  );
}
