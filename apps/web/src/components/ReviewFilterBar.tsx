/**
 * The review queue's filter surface.
 *
 * A reviewer arriving at several hundred candidate rules has no way in without
 * a way to narrow. The dimensions here are the ones the work is actually
 * organised by:
 *
 *  - **document** — which source this came from, when a policy set covers more
 *    than one;
 *  - **extraction run** — a specific attempt, so a reviewer can pivot from run
 *    history into exactly what that run produced (including runs a later one
 *    has since superseded);
 *  - **what changed** — the point of re-extracting a document. A run of 190
 *    rules where 188 are identical to last time is two rules of work, and this
 *    is what makes that visible instead of burying it.
 *
 * `Unchanged` is offered but is deliberately not the default: the default view
 * is everything, so nothing is ever hidden from someone who has not opted in.
 */
import { Badge, Button, Empty, Segmented, Select, Space, Tag, Tooltip, Typography } from "antd";
import {
  ClockCircleOutlined,
  DeleteOutlined,
  FileTextOutlined,
  FilterOutlined,
  PlusCircleOutlined,
  ReloadOutlined,
  SwapOutlined,
} from "@ant-design/icons";
import type { ReviewFacets } from "../api";

const { Text } = Typography;

export const DELTA_META: Record<
  string,
  { label: string; color: string; help: string }
> = {
  new: {
    label: "New",
    color: "green",
    help: "Not present in the previous extraction of this document.",
  },
  changed: {
    label: "Changed",
    color: "orange",
    help: "Continues a rule from the previous extraction, but its logic differs.",
  },
  unchanged: {
    label: "Unchanged",
    color: "default",
    help: "Identical to the previous extraction. Nothing to review.",
  },
  baseline: {
    label: "First extraction",
    color: "blue",
    help: "From the first extraction of this document — there was nothing to compare against.",
  },
};

interface Props {
  facets: ReviewFacets | null;
  documentFilter: string;
  runFilter: string;
  deltaFilter: string;
  showRemoved: boolean;
  onDocument: (value: string) => void;
  onRun: (value: string) => void;
  onDelta: (value: string) => void;
  onToggleRemoved: () => void;
  onRefresh: () => void;
}

export function ReviewFilterBar({
  facets,
  documentFilter,
  runFilter,
  deltaFilter,
  showRemoved,
  onDocument,
  onRun,
  onDelta,
  onToggleRemoved,
  onRefresh,
}: Props) {
  if (!facets) return null;

  const totals = facets.delta_totals;
  const changeCount = totals.new + totals.changed;
  // Runs are filtered by the chosen document so the run list cannot offer a run
  // that would produce an empty queue under the current document filter.
  const runs = documentFilter
    ? facets.runs.filter((r) => r.document_id === documentFilter)
    : facets.runs;
  const removed = facets.removed;

  const deltaOptions = [
    { value: "all", label: "Everything" },
    ...(["new", "changed", "unchanged", "baseline"] as const)
      .filter((k) => totals[k] > 0)
      .map((k) => ({
        value: k,
        label: (
          <Tooltip title={DELTA_META[k].help}>
            <span>
              {DELTA_META[k].label} <Text type="secondary">{totals[k]}</Text>
            </span>
          </Tooltip>
        ),
      })),
  ];

  return (
    <div className="review-filter-bar">
      <Space direction="vertical" size={10} style={{ width: "100%" }}>
        <Space wrap size={10} align="center">
          <FilterOutlined style={{ color: "#8c8c8c" }} />
          <Text strong style={{ fontSize: 13 }}>
            Narrow the queue
          </Text>

          <Select
            size="small"
            style={{ minWidth: 200 }}
            value={documentFilter || "all"}
            onChange={(v) => {
              onDocument(v === "all" ? "" : v);
              onRun(""); // a run from the previous document would filter to nothing
            }}
            options={[
              { value: "all", label: "All documents" },
              ...facets.documents.map((d) => ({
                value: d.id,
                label: `${d.title} (${d.rule_count})`,
              })),
            ]}
            suffixIcon={<FileTextOutlined />}
          />

          <Select
            size="small"
            style={{ minWidth: 260 }}
            value={runFilter || "all"}
            onChange={(v) => onRun(v === "all" ? "" : v)}
            popupMatchSelectWidth={360}
            options={[
              { value: "all", label: "All extraction runs" },
              ...runs.map((r) => ({
                value: r.id,
                label: (
                  <Space size={6}>
                    <Text code style={{ fontSize: 11 }}>
                      {r.reference ?? "run"}
                    </Text>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {r.document_title} {r.version_label}
                    </Text>
                    <Text style={{ fontSize: 11 }}>{r.total} rules</Text>
                    {r.pending > 0 && (
                      <Tag color="blue" style={{ margin: 0, fontSize: 10, lineHeight: "16px" }}>
                        {r.pending} pending
                      </Tag>
                    )}
                  </Space>
                ),
              })),
            ]}
            suffixIcon={<ClockCircleOutlined />}
          />

          <Segmented
            size="small"
            value={deltaFilter}
            onChange={(v) => onDelta(String(v))}
            options={deltaOptions}
          />

          <Button size="small" icon={<ReloadOutlined />} onClick={onRefresh}>
            Refresh
          </Button>
        </Space>

        <Space wrap size={8} align="center">
          {changeCount === 0 && totals.unchanged > 0 ? (
            <Tag color="success" style={{ margin: 0 }}>
              No changes since the previous extraction — {totals.unchanged} rule(s) matched exactly
            </Tag>
          ) : (
            <>
              {totals.new > 0 && (
                <Tag color="green" icon={<PlusCircleOutlined />} style={{ margin: 0 }}>
                  {totals.new} new
                </Tag>
              )}
              {totals.changed > 0 && (
                <Tag color="orange" icon={<SwapOutlined />} style={{ margin: 0 }}>
                  {totals.changed} changed
                </Tag>
              )}
              {totals.unchanged > 0 && (
                <Tag style={{ margin: 0 }}>{totals.unchanged} unchanged</Tag>
              )}
            </>
          )}
          {totals.unclassified > 0 && (
            <Tooltip title="Drafted before change tracking existed, or written by hand — there is no previous run to compare them against.">
              <Tag style={{ margin: 0 }}>{totals.unclassified} not compared</Tag>
            </Tooltip>
          )}
          {removed.length > 0 && (
            <Badge count={removed.length} size="small" offset={[4, -2]}>
              <Button
                size="small"
                type={showRemoved ? "primary" : "default"}
                danger={!showRemoved}
                icon={<DeleteOutlined />}
                onClick={onToggleRemoved}
              >
                No longer found
              </Button>
            </Badge>
          )}
        </Space>

        {showRemoved && (
          <section className="review-removed-panel">
            <div className="review-removed-panel__header">
              <Space size={6}>
                <DeleteOutlined />
                <span>Rules the latest extraction no longer produces</span>
              </Space>
            </div>
            <div className="review-removed-panel__body">
            <Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 10 }}>
              A previous run found these; the most recent one did not. Either the clause was removed
              from the document, or the extractor missed it. They create no row in the queue, so this
              is the only place they appear.
            </Text>
            {removed.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Nothing was dropped" />
            ) : (
              <Space direction="vertical" size={8} style={{ width: "100%" }}>
                {removed.map((r) => (
                  <div key={r.id} className="review-removed-row">
                    <Space size={6} wrap>
                      <Text strong style={{ fontSize: 13 }}>
                        {r.title}
                      </Text>
                      <Tag style={{ margin: 0, fontSize: 10 }}>{r.rule_type}</Tag>
                      {r.review_status !== "candidate" && (
                        <Tag color="blue" style={{ margin: 0, fontSize: 10 }}>
                          was {r.review_status}
                        </Tag>
                      )}
                      {r.superseded_by_reference && (
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          dropped by <Text code style={{ fontSize: 10 }}>{r.superseded_by_reference}</Text>
                        </Text>
                      )}
                    </Space>
                    {r.source_text && (
                      <Text type="secondary" className="review-removed-source">
                        {r.source_text.slice(0, 220)}
                        {r.source_text.length > 220 ? "…" : ""}
                      </Text>
                    )}
                  </div>
                ))}
              </Space>
            )}
            </div>
          </section>
        )}
      </Space>
    </div>
  );
}
