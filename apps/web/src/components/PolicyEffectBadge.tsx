import { Tag } from "antd";
import type { Effect } from "../api";
import { effectMeta } from "../ruleDisplay";

/**
 * Small, always-labeled effect indicator (never color-only) — reused by the
 * compact policy row and the inspector header so a rule's effect reads the
 * same everywhere. Color is semantic-only: green=allow, amber=require
 * action, red=deny.
 */
export function PolicyEffectBadge({ effect, size }: { effect: Effect; size?: "small" | "default" }) {
  const meta = effectMeta(effect.type);
  return (
    <Tag color={meta.color} className={`policy-effect-badge${size === "small" ? " policy-effect-badge-sm" : ""}`}>
      {meta.label}
    </Tag>
  );
}
