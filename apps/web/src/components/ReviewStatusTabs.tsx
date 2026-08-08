import {
  AppstoreOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  CloudUploadOutlined,
  EditOutlined,
  FileSearchOutlined,
} from "@ant-design/icons";
import type { ReactNode } from "react";

/**
 * Sub-tabs for the review queue, keyed on review_status.
 *
 * Deliberately NOT antd `<Tabs>`: the review queue already sits inside the
 * app's project-level `<Tabs>`, and nesting them makes `.ant-tabs-tab` match
 * both levels — which has repeatedly confused both styling and automation.
 * A purpose-built strip also lets each tab carry its own count and accent,
 * which a dropdown (the previous control) could not show at all: the reviewer
 * had to open the filter to discover there was nothing in it.
 */

export interface ReviewStatusTab {
  value: string;
  label: string;
  /** One-line explanation of what lands in this tab and what to do about it. */
  help: string;
  color: string;
  icon: ReactNode;
}

export const REVIEW_STATUS_TABS: ReviewStatusTab[] = [
  {
    value: "all",
    label: "All",
    help: "Every rule in this policy set that has not been replaced by a later extraction run.",
    color: "#4b5563",
    icon: <AppstoreOutlined />,
  },
  {
    value: "candidate",
    label: "Needs review",
    help: "Extracted or drafted, not yet decided. This is the working queue.",
    color: "#1677ff",
    icon: <FileSearchOutlined />,
  },
  {
    value: "changes_requested",
    label: "Changes requested",
    help: "Sent back for rework. Edit the rule, then approve it.",
    color: "#fa8c16",
    icon: <EditOutlined />,
  },
  {
    value: "approved",
    label: "Approved",
    help: "Signed off and waiting to be published into a version.",
    color: "#52c41a",
    icon: <CheckCircleOutlined />,
  },
  {
    value: "rejected",
    label: "Rejected",
    help: "Declined. Kept for audit — rejections are evidence, not deletions.",
    color: "#ff4d4f",
    icon: <CloseCircleOutlined />,
  },
  {
    value: "published",
    label: "Published",
    help: "Already part of an approved policy version. Read-only.",
    color: "#722ed1",
    icon: <CloudUploadOutlined />,
  },
];

interface ReviewStatusTabsProps {
  value: string;
  onChange: (value: string) => void;
  /** Per-status totals for the whole policy set (server-side, not the current page). */
  counts: Record<string, number>;
  total: number;
}

export function ReviewStatusTabs({ value, onChange, counts, total }: ReviewStatusTabsProps) {
  return (
    <div className="review-status-tabs" role="tablist" aria-label="Review status">
      {REVIEW_STATUS_TABS.map((tab) => {
        const count = tab.value === "all" ? total : (counts[tab.value] ?? 0);
        const active = value === tab.value;
        return (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={active}
            title={tab.help}
            className={
              "review-status-tab" +
              (active ? " review-status-tab-active" : "") +
              (count === 0 ? " review-status-tab-empty" : "")
            }
            style={
              {
                "--tab-accent": tab.color,
              } as React.CSSProperties
            }
            onClick={() => onChange(tab.value)}
          >
            <span className="review-status-tab-icon">{tab.icon}</span>
            <span className="review-status-tab-body">
              <span className="review-status-tab-count">{count}</span>
              <span className="review-status-tab-label">{tab.label}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
