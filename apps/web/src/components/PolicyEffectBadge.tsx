import { Tag } from "antd";
import type { Effect } from "../api";
import { effectMeta } from "../ruleDisplay";

/**
 * Small, always-labeled effect indicator (never color-only) — reused by the
 * compact policy row and the inspector header so a rule's effect reads the
 * same everywhere. Color is semantic-only: green=allow, amber=require
 * action, red=deny.
 *
 * A record whose effect states no kind is said rather than skipped or blanked.
 * The type says the kind is always there and every record measured carries one,
 * but this badge is drawn from data the app did not produce, and a record that
 * arrives without one used to take the whole card down with it. Naming the gap
 * keeps the rule readable and keeps the gap visible, which is the only way it
 * gets fixed where it belongs — in the extraction, not here.
 */
export function PolicyEffectBadge({ effect, size }: { effect: Effect; size?: "small" | "default" }) {
  const type = (effect as { type?: string | null } | null | undefined)?.type;
  const meta =
    typeof type === "string" && type.length > 0
      ? effectMeta(type)
      : { label: "Effect kind not recorded", color: "default" };
  return (
    <Tag color={meta.color} className={`policy-effect-badge${size === "small" ? " policy-effect-badge-sm" : ""}`}>
      {meta.label}
    </Tag>
  );
}
