import { CaretRightOutlined } from "@ant-design/icons";

interface PolicyGroupHeaderProps {
  label: string;
  count: number;
  collapsed: boolean;
  onToggle: () => void;
  style?: React.CSSProperties;
}

/**
 * Sticky-ish group divider inside the virtualized policy list (e.g. "Rule
 * Type: Approval Requirement — 12"). Collapsible so large sets can be
 * scanned at the group level without losing the row-level detail.
 */
export function PolicyGroupHeader({ label, count, collapsed, onToggle, style }: PolicyGroupHeaderProps) {
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onToggle();
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      aria-expanded={!collapsed}
      className="policy-group-header"
      style={style}
      onClick={onToggle}
      onKeyDown={handleKeyDown}
    >
      <CaretRightOutlined className={`policy-group-caret${collapsed ? "" : " policy-group-caret-open"}`} />
      <span className="policy-group-label">{label}</span>
      <span className="policy-group-count">{count}</span>
    </div>
  );
}
