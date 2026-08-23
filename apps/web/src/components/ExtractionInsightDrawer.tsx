import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Drawer, Empty, Space, Spin, Statistic, Table, Tabs, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  extractionApi,
  type CanonicalDocumentElements,
  type CanonicalElement,
  type CoverageDisposition,
  type CoverageResponse,
  type ReadingPlanResponse,
  type StructuralGraphResponse,
} from "../api";

const { Text, Paragraph } = Typography;

/**
 * Everything the extraction pipeline knows about one document version.
 *
 * Consolidates the document's own text with what the pipeline made of it, so a
 * reviewer answers "what does it say" and "what happened to it" in one place
 * rather than by opening two drawers and correlating them by eye.
 *
 * Deliberately read-only. Approving, rejecting and publishing already live in
 * the review queue; duplicating them here would create a second place where
 * policy decisions are made.
 */

interface ExtractionInsightDrawerProps {
  open: boolean;
  onClose: () => void;
  documentVersionId: string | null;
  documentTitle?: string;
}

/**
 * Colours carry meaning, so they are assigned rather than cycled.
 *
 * `unresolved` and anything unaccounted are the two states a reviewer must
 * notice, so they are the only warm colours on the page — everything else is
 * an answer, not a gap.
 */
const DISPOSITION_COLOUR: Record<CoverageDisposition, string> = {
  policy_target: "green",
  supporting_context: "blue",
  dependency: "geekblue",
  non_normative: "default",
  duplicate_structure: "default",
  unresolved: "orange",
};

const DISPOSITION_LABEL: Record<CoverageDisposition, string> = {
  policy_target: "Policy target",
  supporting_context: "Read as target",
  dependency: "Supporting dependency",
  non_normative: "Non-normative",
  duplicate_structure: "Duplicate structure",
  unresolved: "Unresolved",
};

export default function ExtractionInsightDrawer({
  open,
  onClose,
  documentVersionId,
  documentTitle,
}: ExtractionInsightDrawerProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [coverage, setCoverage] = useState<CoverageResponse | null>(null);
  const [plan, setPlan] = useState<ReadingPlanResponse | null>(null);
  const [structure, setStructure] = useState<StructuralGraphResponse | null>(null);
  const [canonical, setCanonical] = useState<CanonicalDocumentElements | null>(null);

  const load = useCallback(async (versionId: string) => {
    setLoading(true);
    setError(null);
    try {
      // Fetched together because the views are read as one answer: a coverage
      // number without the text it describes is not actionable.
      const [coverageResult, planResult, structureResult, canonicalResult] =
        await Promise.all([
          extractionApi.getCoverage(versionId),
          extractionApi.getReadingPlan(versionId),
          extractionApi.getStructure(versionId),
          // Every element, however many windows that takes. Asking for one
          // window and showing it as the document is what hid the last two
          // pages of a 27-page handbook — including its disciplinary schedule
          // — from reviewers checking extraction against the source.
          extractionApi.getAllCanonicalElements(versionId),
        ]);
      setCoverage(coverageResult);
      setPlan(planResult);
      setStructure(structureResult);
      setCanonical(canonicalResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load extraction detail");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open && documentVersionId) {
      void load(documentVersionId);
    }
  }, [open, documentVersionId, load]);

  const unaccounted = useMemo(
    () => new Set(coverage?.unaccounted_element_ids ?? []),
    [coverage]
  );

  /**
   * Every leaf the coverage report accounts for, plus every leaf it could not.
   *
   * The server returns dispositions in `elements` and lists what received none
   * separately, so `elements.length` is the document minus exactly the content
   * nobody looked at — the one part a reviewer most needs to open. Rows for
   * those are added here so the tab's count is the document's leaf count and
   * every element it counts can actually be reached.
   */
  const coverageRows = useMemo<CoverageRow[]>(() => {
    if (!coverage) {
      return [];
    }
    return [
      ...coverage.elements,
      ...coverage.unaccounted_element_ids.map((elementId) => ({
        element_id: elementId,
        disposition: null,
        reason: "No disposition was recorded for this element",
      })),
    ];
  }, [coverage]);

  const coverageColumns: ColumnsType<CoverageRow> = [
    {
      title: "Element",
      dataIndex: "element_id",
      width: 200,
      render: (value: string) => <Text code>{value}</Text>,
    },
    {
      title: "Disposition",
      dataIndex: "disposition",
      width: 190,
      filters: (Object.keys(DISPOSITION_LABEL) as CoverageDisposition[]).map((key) => ({
        text: DISPOSITION_LABEL[key],
        value: key,
      })),
      onFilter: (value, record) => record.disposition === value,
      render: (value: CoverageDisposition | null) =>
        value === null ? (
          <Tag color="red">None recorded</Tag>
        ) : (
          <Tag color={DISPOSITION_COLOUR[value]}>{DISPOSITION_LABEL[value]}</Tag>
        ),
    },
    { title: "Why", dataIndex: "reason" },
  ];

  const planColumns: ColumnsType<ReadingPlanResponse["units"][number]> = [
    { title: "Unit", dataIndex: "unit_id", width: 190, render: (v: string) => <Text code>{v}</Text> },
    {
      title: "Under",
      dataIndex: "heading_path",
      render: (value: string[]) => (value.length ? value.join(" › ") : <Text type="secondary">—</Text>),
    },
    {
      title: "Targets",
      dataIndex: "target_element_ids",
      width: 100,
      render: (value: string[]) => value.length,
    },
    {
      title: "Context (why)",
      dataIndex: "context",
      render: (value: ReadingPlanUnitContext[]) =>
        value.length === 0 ? (
          <Text type="secondary">none</Text>
        ) : (
          <Space size={[4, 4]} wrap>
            {Array.from(new Set(value.map((entry) => entry.reason))).map((reason) => (
              <Tag key={reason}>{reason.replace(/_/g, " ")}</Tag>
            ))}
          </Space>
        ),
    },
  ];

  const documentColumns: ColumnsType<CanonicalElement> = [
    { title: "#", dataIndex: "sequence", width: 60 },
    {
      title: "Type",
      dataIndex: "element_type",
      width: 120,
      render: (value: string | null) => <Tag>{value ?? "—"}</Tag>,
    },
    {
      title: "Section",
      dataIndex: "section",
      width: 190,
      render: (value: string | null) => value ?? <Text type="secondary">—</Text>,
    },
    {
      title: "Text",
      dataIndex: "text",
      render: (value: string, record) => (
        <Space orientation="vertical" size={0}>
          <Text>{value}</Text>
          {/* The offsets are what make a citation checkable rather than
              plausible, so they are shown rather than kept for machines. */}
          {record.source_fragments.length > 0 && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              p{record.source_fragments[0].page} ·{" "}
              {record.source_fragments[0].start_offset}–{record.source_fragments[0].end_offset}
            </Text>
          )}
        </Space>
      ),
    },
  ];

  return (
    <Drawer
      open={open}
      onClose={onClose}
      size={980}
      title={`Extraction detail${documentTitle ? ` — ${documentTitle}` : ""}`}
      destroyOnHidden
    >
      {loading ? (
        <Spin />
      ) : error ? (
        <Alert type="error" title={error} showIcon />
      ) : !coverage ? (
        <Empty description="No extraction detail for this version" />
      ) : (
        <Space orientation="vertical" size="large" style={{ width: "100%" }}>
          <Space size="large" wrap>
            <Statistic title="Canonical leaves" value={coverage.total_leaf_elements} />
            <Statistic
              title="Accounted for"
              value={coverage.accounted}
              suffix={`/ ${coverage.total_leaf_elements}`}
              valueStyle={{
                color: coverage.is_complete ? "var(--success)" : "var(--danger)",
              }}
            />
            <Statistic title="Reading units" value={plan?.unit_count ?? 0} />
            <Statistic title="Structure edges" value={structure?.edge_count ?? 0} />
          </Space>

          {unaccounted.size > 0 && (
            <Alert
              type="error"
              showIcon
              title={`${unaccounted.size} element(s) received no disposition`}
              description={
                <Paragraph style={{ marginBottom: 0 }}>
                  These were never considered by the run. That is different from an element
                  deliberately marked <Text code>unresolved</Text>: content nobody looked at
                  cannot be reviewed, so this blocks handoff until it is explained.
                </Paragraph>
              }
            />
          )}

          {plan && !plan.is_exhaustive && (
            <Alert
              type="warning"
              showIcon
              title={`${plan.uncovered_target_ids.length} element(s) belong to no reading unit`}
              description="Extraction would never have been shown this content."
            />
          )}

          <Tabs
            items={[
              {
                key: "document",
                // The server's total, not the number of rows that happen to be
                // in hand: a count taken from the rows can only ever agree with
                // the rows, so a short list and its count corroborate each
                // other and nothing on screen looks wrong.
                label: `Document (${canonical?.total_elements ?? 0})`,
                children: (
                  <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
                    {canonical && !canonical.is_complete && (
                      <Alert
                        type="warning"
                        showIcon
                        title={`Showing ${canonical.elements.length} of ${canonical.total_elements} elements`}
                        description="The rest could not be retrieved, so this tab is part of the document rather than all of it."
                      />
                    )}
                    <Table
                      size="small"
                      rowKey={(record) => record.element_id ?? String(record.sequence)}
                      columns={documentColumns}
                      dataSource={canonical?.elements ?? []}
                      pagination={{ pageSize: 25, showSizeChanger: true }}
                    />
                  </Space>
                ),
              },
              {
                key: "coverage",
                // Leaf count from the report, so elements that received no
                // disposition are counted rather than quietly dropped.
                label: `Coverage (${coverage.total_leaf_elements})`,
                children: (
                  <Table
                    size="small"
                    rowKey="element_id"
                    columns={coverageColumns}
                    dataSource={coverageRows}
                    pagination={{ pageSize: 25, showSizeChanger: true }}
                  />
                ),
              },
              {
                key: "plan",
                label: `Reading plan (${plan?.unit_count ?? 0})`,
                children: (
                  <Table
                    size="small"
                    rowKey="unit_id"
                    columns={planColumns}
                    dataSource={plan?.units ?? []}
                    pagination={{ pageSize: 25 }}
                  />
                ),
              },
            ]}
          />
        </Space>
      )}
    </Drawer>
  );
}

type ReadingPlanUnitContext = ReadingPlanResponse["units"][number]["context"][number];

/** A coverage row: a disposition the report recorded, or the absence of one.
 *
 * `null` is not a seventh disposition. It is the report saying this element was
 * never considered, which is why it renders differently from every classified
 * outcome.
 */
type CoverageRow = Omit<CoverageResponse["elements"][number], "disposition"> & {
  disposition: CoverageDisposition | null;
};
