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

/** Batches completed before an ETA is shown.
 *
 * One batch is a terrible sample: the first includes model warm-up and can be
 * twice the steady-state cost, so extrapolating from it produces an estimate
 * that visibly collapses on the next poll. A wrong ETA is worse than none,
 * because it is the number someone uses to decide whether to wait. */
const MIN_BATCHES_FOR_ETA = 2;

function plural(n: number, one: string, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`;
}

/** Compact duration: "2m 05s", or "45s" under a minute. */
function duration(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds));
  if (whole < 60) return `${whole}s`;
  return `${Math.floor(whole / 60)}m ${String(whole % 60).padStart(2, "0")}s`;
}

/**
 * Animate a number towards its target instead of snapping to it.
 *
 * A counter that jumps from 2 to 9 reads as a glitch; the same change rolling
 * up reads as work being done, which is the whole point of a progress display.
 * Deliberately short (400ms) so the figure on screen is never meaningfully
 * behind the truth — this is decoration on a real number, not a substitute
 * for it.
 */
function useCountUp(target: number, ms = 400): number {
  const [value, setValue] = useState(target);
  const fromRef = useRef(target);

  useEffect(() => {
    const from = fromRef.current;
    if (from === target) return;
    // Respect the OS setting: motion is a preference, not a decoration budget.
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      fromRef.current = target;
      setValue(target);
      return;
    }
    const started = performance.now();
    let frame = 0;
    const step = (now: number) => {
      const t = Math.min(1, (now - started) / ms);
      // Ease-out: fast first, settling at the end, so the eye catches the change.
      const eased = 1 - (1 - t) ** 3;
      setValue(Math.round(from + (target - from) * eased));
      if (t < 1) frame = requestAnimationFrame(step);
      else fromRef.current = target;
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, ms]);

  return value;
}

/** One pipeline stage's figure, rolled up rather than snapped. */
function StageValue({ text }: { text: string }) {
  // Only animate a bare number. "37/550" and "—" are composites and would
  // animate into nonsense, so they are rendered as-is.
  const numeric = /^\d+$/.test(text) ? Number(text) : null;
  const shown = useCountUp(numeric ?? 0);
  return <span className="extract-stage-value">{numeric === null ? text : shown}</span>;
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

  // Extrapolated from batches actually finished, not from a fixed per-batch
  // guess: batch cost varies with how much policy a page carries, so the only
  // honest estimate is this run's own observed rate.
  const eta =
    !done && !failed && doneBatches >= MIN_BATCHES_FOR_ETA && totalBatches > doneBatches
      ? (elapsed / doneBatches) * (totalBatches - doneBatches)
      : null;

  const pagesPerMinute =
    elapsed > 20 && donePages > 0 ? (donePages / elapsed) * 60 : null;

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
    elapsed > 0 ? duration(elapsed) + " elapsed" : null,
    // The number someone actually uses to decide whether to wait, so it is
    // stated plainly rather than left to be inferred from batch counts.
    eta !== null ? `about ${duration(eta)} left` : null,
    pagesPerMinute ? `${pagesPerMinute.toFixed(1)} pages/min` : null,
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
                  <StageValue text={stageValue[s.key]} />
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
          <CheckCircleFilled style={{ color: "var(--success)" }} />
        ) : failed ? (
          <CloseCircleFilled style={{ color: "var(--danger)" }} />
        ) : (
          <LoadingOutlined spin />
        )}
        <Text strong>{stage}</Text>
        {runRef && (
          <Tooltip title="Reference for this extraction run. Every rule it produced carries it.">
            <Tag className="extract-run-ref">{runRef}</Tag>
          </Tooltip>
        )}
        {!done && !failed && totalBatches > 0 && (
          <span className="extract-progress-pct">{pct}%</span>
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
        strokeColor={failed ? undefined : "var(--brand-600)"}
      />
      {!done && !failed && (
        // Extraction continues server-side, so the one thing a reviewer needs
        // to know before walking away is that they may. Without it the honest
        // assumption is that closing the tab cancels the run.
        <div className="extract-progress-line extract-progress-hint">
          <Text type="secondary">
            This keeps running if you navigate away — rules appear in the review queue as each
            batch commits.
          </Text>
        </div>
      )}
      {failed && progress.error && (
        <div className="extract-progress-line">
          <Text type="danger">{progress.error}</Text>
        </div>
      )}
    </div>
  );
}
