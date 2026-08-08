import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Progress, Tag, Tooltip, Typography } from "antd";
import {
  CheckCircleFilled,
  CloseCircleFilled,
  ExperimentOutlined,
  FileTextOutlined,
  LoadingOutlined,
  ScanOutlined,
  SolutionOutlined,
} from "@ant-design/icons";
import { aiApi, type ExtractionProgress } from "../api";

const { Text } = Typography;

interface Props {
  /** The document version being extracted. Progress is keyed on this because
   * the client cannot know the run id until the extract call returns. */
  documentVersionId: string;
  /** True while the extract request is in flight. */
  running: boolean;
}

/** Poll interval. Batches take tens of seconds, so a faster poll would only add
 * request noise without the readout changing. */
const POLL_MS = 2000;

function plural(n: number, one: string, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`;
}

/** The pipeline a document actually travels, in order. Each stage shows the
 * count of what has passed through it, so the reviewer sees work moving rather
 * than one opaque percentage. */
type StageKey = "intake" | "scan" | "formulate" | "review";

const STAGES: { key: StageKey; label: string; icon: ReactNode; hint: string }[] = [
  {
    key: "intake",
    label: "Document",
    icon: <FileTextOutlined />,
    hint: "Clauses read from the source document, in document order.",
  },
  {
    key: "scan",
    label: "Policy statements",
    icon: <ScanOutlined />,
    hint: "Stage 1 — spans of the document that actually carry policy, copied verbatim. Contents pages, boilerplate and amendment instructions are dropped here.",
  },
  {
    key: "formulate",
    label: "Rules drafted",
    icon: <ExperimentOutlined />,
    hint: "Stage 2 — the formulator agent turns each policy statement into a structured, testable rule.",
  },
  {
    key: "review",
    label: "In review queue",
    icon: <SolutionOutlined />,
    hint: "Committed as candidate rules, waiting for a human decision. Nothing here is live policy yet.",
  },
];

/** Live status for a running extraction: a compact pipeline showing what is
 * moving where, plus a two-line status readout underneath.
 *
 * The status lines are *replaced* on every poll rather than appended — the
 * reviewer's question is "what is it doing now and how far in is it", not "what
 * did it do thirty batches ago". The batch history is already recoverable from
 * the created/skipped summary once the run finishes.
 *
 * Owns its own polling so the parent page carries no timer lifecycle, and so
 * the readout can be dropped next to any extraction trigger.
 */
export default function ExtractionProgressPanel({ documentVersionId, running }: Props) {
  const [progress, setProgress] = useState<ExtractionProgress | null>(null);
  // Ref, not state: the poll loop reads this to decide whether to reschedule,
  // and a stale closure over `running` would leave a timer running forever.
  const runningRef = useRef(running);
  runningRef.current = running;

  useEffect(() => {
    if (!running) return;
    let cancelled = false;
    let timer: number | undefined;

    const poll = async () => {
      try {
        const next = await aiApi.extractionProgress(documentVersionId);
        if (!cancelled) setProgress(next);
      } catch {
        // A failed poll is not a failed extraction — the run continues
        // server-side regardless. Keep the last good readout and retry.
      }
      if (!cancelled && runningRef.current) {
        timer = window.setTimeout(poll, POLL_MS);
      }
    };

    void poll();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [documentVersionId, running]);

  // One last read after the request resolves, so the panel settles on the
  // terminal "Done — N rules" line instead of freezing on the final batch.
  useEffect(() => {
    if (running) return;
    if (!progress) return;
    let cancelled = false;
    void aiApi
      .extractionProgress(documentVersionId)
      .then((next) => {
        if (!cancelled) setProgress(next);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
    // Intentionally not depending on `progress` — this fires on the
    // running→idle edge only, and re-running on its own result would loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running, documentVersionId]);

  if (!running && !progress?.active) return null;

  if (!progress?.active) {
    // Request is in flight but the server has not published totals yet (it is
    // still loading clauses). Say so rather than showing a bare 0-of-0.
    return (
      <div className="extract-progress">
        <div className="extract-progress-line">
          <LoadingOutlined spin />
          <Text strong>Starting extraction…</Text>
        </div>
        <div className="extract-progress-line extract-progress-counters">
          <Text type="secondary">Loading the document&rsquo;s clauses</Text>
        </div>
      </div>
    );
  }

  const {
    status = "running",
    stage = "",
    run_reference: runRef = "",
    total_batches: totalBatches = 0,
    processed_batches: doneBatches = 0,
    total_clauses: totalClauses = 0,
    processed_clauses: doneClauses = 0,
    total_pages: totalPages = 0,
    processed_pages: donePages = 0,
    passages_found: passages = 0,
    rules_drafted: drafted = 0,
    rules_committed: committed = 0,
    skipped = 0,
    superseded = 0,
    elapsed_seconds: elapsed = 0,
  } = progress;

  const pct = totalBatches > 0 ? Math.min(100, Math.round((doneBatches / totalBatches) * 100)) : 0;
  const failed = status === "failed";
  const done = status === "completed";

  // Which stage is lit is read from the backend's own stage sentence rather
  // than inferred from counters, which lag a batch behind what is happening.
  const activeStage: StageKey =
    done || failed
      ? "review"
      : stage.startsWith("Formulating")
        ? "formulate"
        : stage.startsWith("Reading")
          ? "scan"
          : stage.startsWith("Linking")
            ? "review"
            : "intake";

  const stageValue: Record<StageKey, string> = {
    intake: totalClauses > 0 ? `${doneClauses}/${totalClauses}` : "—",
    scan: String(passages),
    formulate: String(drafted),
    review: String(committed),
  };

  const activeIndex = STAGES.findIndex((s) => s.key === activeStage);

  // Counters joined into one line with a separator rather than stacked, so the
  // readout stays a fixed height no matter how many counters exist.
  const counters = [
    totalPages > 0 ? `${donePages} of ${plural(totalPages, "page")}` : null,
    totalBatches > 0
      ? `batch ${Math.min(doneBatches + (done ? 0 : 1), totalBatches)} of ${totalBatches}`
      : null,
    skipped > 0 ? `${skipped} skipped` : null,
    elapsed > 0
      ? `${Math.floor(elapsed / 60)}m ${String(Math.round(elapsed % 60)).padStart(2, "0")}s`
      : null,
  ].filter(Boolean);

  return (
    <div className={`extract-progress${failed ? " extract-progress--failed" : ""}`}>
      <div className="extract-pipeline" aria-label="Extraction pipeline">
        {STAGES.map((s, i) => {
          const isActive = !done && !failed && s.key === activeStage;
          const isPast = done || i < activeIndex;
          return (
            <div key={s.key} className="extract-pipeline-item">
              <Tooltip title={s.hint}>
                <div
                  className={`extract-stage${isActive ? " extract-stage--active" : ""}${
                    isPast ? " extract-stage--done" : ""
                  }`}
                >
                  <span className="extract-stage-icon">{s.icon}</span>
                  <span className="extract-stage-value">{stageValue[s.key]}</span>
                  <span className="extract-stage-label">{s.label}</span>
                </div>
              </Tooltip>
              {i < STAGES.length - 1 && (
                <div
                  className={`extract-flow${
                    !done && !failed && i === activeIndex - 1 ? " extract-flow--moving" : ""
                  }${isPast ? " extract-flow--done" : ""}`}
                  aria-hidden
                >
                  <span className="extract-flow-dot" />
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="extract-progress-line">
        {done ? (
          <CheckCircleFilled style={{ color: "#16a34a" }} />
        ) : failed ? (
          <CloseCircleFilled style={{ color: "#dc2626" }} />
        ) : (
          <LoadingOutlined spin />
        )}
        <Text strong>{stage}</Text>
        {runRef && (
          <Tooltip title="Reference for this extraction run. Every rule it produced carries it.">
            <Tag className="extract-run-ref">{runRef}</Tag>
          </Tooltip>
        )}
      </div>
      <div className="extract-progress-line extract-progress-counters">
        <Text type="secondary">{counters.join(" · ")}</Text>
        {superseded > 0 && (
          <Tooltip title="Unreviewed rules from the previous run of this document, replaced by this run. Rules you had already approved or rejected were kept.">
            <Tag color="gold">replaced {superseded} from previous run</Tag>
          </Tooltip>
        )}
      </div>
      <Progress
        percent={done ? 100 : pct}
        size="small"
        showInfo={false}
        status={failed ? "exception" : done ? "success" : "active"}
        strokeColor={failed ? undefined : "#2563eb"}
      />
      {failed && progress.error && (
        <div className="extract-progress-line">
          <Text type="danger">{progress.error}</Text>
        </div>
      )}
    </div>
  );
}
