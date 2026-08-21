import { useEffect, useState } from "react";
import { Button, Divider, Input, Popover, Space, Tag, Typography } from "antd";
import { LogoutOutlined, UserOutlined } from "@ant-design/icons";
import { useActor, toRbacRole } from "../ActorContext";
import { clearSession, getSession } from "../auth";
import { ROLE_LABELS, ROLE_DESCRIPTIONS, type Role } from "../rbac";

const { Text } = Typography;

const ROLE_TAG_COLOUR: Record<Role, string> = {
  viewer: "default",
  policy_author: "blue",
  admin: "purple",
};

/**
 * Shows the actor's display name, role badge, and role description.
 *
 * The role is read-only — a user must not be able to grant themselves a role.
 * The name remains editable: it is a display-name convenience that autofills
 * author/reviewer fields, not a privilege.
 */
export function IdentityBadge() {
  const { actor, setActor } = useActor();
  const [open, setOpen] = useState(false);
  const [draftName, setDraftName] = useState(actor.name);

  useEffect(() => setDraftName(actor.name), [actor.name]);

  const rbacRole = toRbacRole(actor.role);
  const roleLabel = ROLE_LABELS[rbacRole] ?? actor.role;
  const roleDesc = ROLE_DESCRIPTIONS[rbacRole] ?? "";
  const tagColour = ROLE_TAG_COLOUR[rbacRole] ?? "default";

  const content = (
    <Space direction="vertical" size={12} className="actor-switcher-popover">
      <div>
        <Text type="secondary" className="actor-field-label">
          Your name
        </Text>
        <Input
          value={draftName}
          onChange={(e) => setDraftName(e.target.value)}
          onBlur={() => setActor({ ...actor, name: draftName.trim() })}
          onPressEnter={() => setActor({ ...actor, name: draftName.trim() })}
          placeholder="jane.doe"
        />
      </div>
      <div>
        <Text type="secondary" className="actor-field-label">
          Role
        </Text>
        <div>
          <Tag color={tagColour}>{roleLabel}</Tag>
        </div>
        <Text type="secondary" className="actor-role-description">
          {roleDesc}
        </Text>
      </div>
      {getSession() && (
        <>
          <Divider style={{ margin: 0 }} />
          <Button
            icon={<LogoutOutlined />}
            block
            onClick={() => {
              clearSession();
              // Force a full reload so the App-level session gate
              // re-evaluates and shows the login screen.
              window.location.reload();
            }}
          >
            Sign out
          </Button>
        </>
      )}
    </Space>
  );

  return (
    <Popover
      content={content}
      title="Identity"
      trigger="click"
      open={open}
      onOpenChange={setOpen}
      placement="bottomRight"
    >
      <Button
        icon={<UserOutlined />}
        className="actor-switcher-btn"
        aria-label={`Identity: ${actor.name || "unnamed"}, ${roleLabel}`}
      >
        {actor.name || "Set name"}{" "}
        <Tag color={tagColour} className="identity-role-tag">
          {roleLabel}
        </Tag>
      </Button>
    </Popover>
  );
}
