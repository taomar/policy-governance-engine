import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Empty, Spin, Tag, Timeline, Tooltip, Typography } from "antd";
import { AuditOutlined } from "@ant-design/icons";
import { auditApi, PolicyPlatformApiError, type AuditEvent } from "../api";

const { Text } = Typography;

/**
 * Recent governance activity for a project.
 *
 * The audit trail is the platform's record of who exercised authority and
 * when. It was previously written to a table nothing read, which meant an
 * approval left no trace a person could actually see. This surfaces it in the
 * one place someone asks the question — "what has happened to this project
 * lately?" — rather than adding a whole tab for a small team to remember.
 */

/** Human wording per event type. Keeping the map here rather than storing
 * prose in the audit row keeps the record itself machine-readable and stable
 * even if the phrasing changes. */
const EVENT_LABEL: Record<string, string> = {
  "candidate_rule.reviewed": "Rule reviewed",
  "candidate_rule.review_overridden": "Review overridden by manager",
  "candidate_rule.bulk_reviewed": "Bulk review",
  "policy_version.published": "Version published",
  "correlation_finding.disposed": "Contradiction finding decided",
};

const EVENT_COLOR: Record<string, string> = {
  "candidate_rule.reviewed": "blue",
  "candidate_rule.review_overridden": "orange",
  "candidate_rule.bulk_reviewed": "blue",
  "policy_version.published": "green",
  "correlation_finding.disposed": "purple",
};

function summarise(event: AuditEvent): string {
  const d = event.details ?? {};
  switch (event.event_type) {
    case "candidate_rule.reviewed":
      return `${d.decision === "approve" ? "Approved" : "Rejected"} — ${d.from_status} → ${d.to_status}`;
    case "candidate_rule.review_overridden":
      return `Forced to ${d.to_status}${d.reason ? ` — ${d.reason}` : ""}`;
    case "candidate_rule.bulk_reviewed":
      return `${d.reviewed_count} rule(s) ${d.decision === "approve" ? "approved" : "rejected"}${
        d.skipped_count ? `, ${d.skipped_count} skipped` : ""
      }`;
    case "policy_version.published":
      return `v${d.version_number} — ${d.rules_in_version} rules, ${d.candidates_published} newly published`;
    case "correlation_finding.disposed":
      return `${d.classification} marked ${d.disposition}`;
    default:
      return "";
  }
}

interface Props {
  policySetKey: string;
  limit?: number;
}

export function ActivityPanel({ policySetKey, limit = 25 }: Props) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // The trail is polymorphic and not keyed by policy set, so the set is
      // recorded in the detail payload instead. Filtering client-side keeps the
      // audit table's shape honest — it records entities, not projects — at the
      // cost of over-fetching, which is acceptable at this volume.
      const page = await auditApi.list({ limit: 200 });
      setEvents(page.events);
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = useMemo(
    () =>
      events
        .filter((e) => (e.details?.policy_set_key ?? null) === policySetKey)
        .slice(0, limit),
    [events, policySetKey, limit]
  );

  return (
    <section className="project-overview-panel activity-panel">
      <div className="project-overview-panel__header">
        <div>
          <Text strong>
            <AuditOutlined /> Recent governance activity
          </Text>
          <Text type="secondary">Latest immutable review and publication events</Text>
        </div>
        <Tooltip title="Every approval, override, publication and finding decision is written to an immutable audit trail. This shows the most recent for this project.">
          <Tag bordered={false}>Audit trail</Tag>
        </Tooltip>
      </div>
      <div className="project-overview-panel__body">
      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} />}
      {loading && <Spin />}
      {!loading && visible.length === 0 && (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="No approvals, publications or decisions recorded for this project yet."
        />
      )}
      {!loading && visible.length > 0 && (
        <Timeline
          items={visible.map((event) => ({
            color: EVENT_COLOR[event.event_type] ?? "gray",
            children: (
              <div className="activity-item">
                <div className="activity-item-head">
                  <Tag color={EVENT_COLOR[event.event_type] ?? "default"}>
                    {EVENT_LABEL[event.event_type] ?? event.event_type}
                  </Tag>
                  <Text strong>{event.actor}</Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {event.created_at ? new Date(event.created_at).toLocaleString() : ""}
                  </Text>
                </div>
                <Text type="secondary">{summarise(event)}</Text>
                {typeof event.details?.notes === "string" && event.details.notes && (
                  <div>
                    <Text italic style={{ fontSize: 12 }}>
                      “{event.details.notes as string}”
                    </Text>
                  </div>
                )}
              </div>
            ),
          }))}
        />
      )}
      </div>
    </section>
  );
}

export default ActivityPanel;
