import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Progress, Tag, Tooltip, Typography } from "antd";
import {
  ApartmentOutlined,
  CheckCircleFilled,
  CloseCircleFilled,
  ExperimentOutlined,
  FileTextOutlined,
  LoadingOutlined,
  ScanOutlined,
  SolutionOutlined,
} from "@ant-design/icons";
import { aiApi, type ExtractionProgress } from "../api";
import "./extractionProgressPanel.css";

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
type StageKey = "intake" | "scan" | "formulate" | "link" | "review";

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
    key: "link",
    label: "Linked",
    icon: <ApartmentOutlined />,
    hint: "Rules tied to the others they belong with — rows of one table, a subsection and the rule it qualifies, an explicit cross-reference. Only relationships the document itself establishes are recorded here.",
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
    // Left undefined-if-absent on purpose: a server older than these counters
    // sends neither, and `?? 0` here would turn "the server has no split" into
    // "the split is zero" — two different facts (constraint: absent ≠ empty).
    rules_deterministic: routeDeterministic,
    rules_ai_ready: routeAiReady,
    rules_committed: committed = 0,
    skipped = 0,
    linked = 0,
    superseded = 0,
    delta_new: deltaNew = 0,
    delta_changed: deltaChanged = 0,
    delta_unchanged: deltaUnchanged = 0,
    delta_removed: deltaRemoved = 0,
    elapsed_seconds: elapsed = 0,
  } = progress;

  const pct = totalBatches > 0 ? Math.min(100, Math.round((doneBatches / totalBatches) * 100)) : 0;
  const failed = status === "failed";
  const done = status === "completed";
  // The run's last act is a comparison against the previous extraction. The
  // service emits it ("Comparing against the previous extraction…") while the
  // run's status is still "running", deliberately after every rule has been
  // drafted, linked and committed — classifying earlier would fingerprint a
  // payload the run had not finished writing. So the throughput chain is
  // genuinely settled by this point, but the run is NOT done, and "comparing"
  // is its own state that must read apart from "finished".
  const comparing = !done && !failed && stage.startsWith("Comparing");
  // Nothing more moves through the chain once the run is done or in that
  // trailing comparison pass, so both light every box as complete. `comparing`
  // keeps its own indicator below the chain so it is never mistaken for done.
  const chainSettled = done || comparing;

  // Extrapolated from batches actually finished, not from a fixed per-batch
  // guess: batch cost varies with how much policy a page carries, so the only
  // honest estimate is this run's own observed rate.
  const eta =
    !done && !failed && doneBatches >= MIN_BATCHES_FOR_ETA && totalBatches > doneBatches
      ? (elapsed / doneBatches) * (totalBatches - doneBatches)
      : null;

  // A DOCX reports one page for the whole document, so a page counter reads
  // "1 of 1 page" while batch 6 of 7 is still running — it says finished when
  // it is not, and "0.1 pages/min" is derived from the same degenerate unit.
  // Pages are only shown, and only used for throughput, when the document has
  // enough of them for the number to mean anything.
  const pagesAreMeaningful = totalPages > 1;
  const throughput = pagesAreMeaningful
    ? donePages > 0 && elapsed > 20
      ? { value: (donePages / elapsed) * 60, unit: "pages/min" }
      : null
    : doneClauses > 0 && elapsed > 20
      ? { value: (doneClauses / elapsed) * 60, unit: "clauses/min" }
      : null;

  // Which stage is lit is read from the backend's own stage sentence rather
  // than inferred from counters, which lag a batch behind what is happening.
  // Once the chain is settled nothing in it is active: `done` and `comparing`
  // both light every box as complete. On failure the last-touched box is left
  // lit so the reader sees roughly how far the run got.
  const activeStage: StageKey =
    chainSettled || failed
      ? "review"
      : stage.startsWith("Formulating")
        ? "formulate"
        : stage.startsWith("Reading")
          ? "scan"
          : stage.startsWith("Linking")
            ? "link"
            : "intake";

  const activeIndex = STAGES.findIndex((s) => s.key === activeStage);

  // A stage counter of 0 says two different things and the strip must not let
  // them blur: "the run reached this stage and found nothing" is a result,
  // "the run has not reached this stage" is not. So a stage the run has not yet
  // reached shows an em dash, and only a reached stage shows a number —
  // including a genuine 0. A settled or failed run counts every stage as
  // reached: its figures are the final or partial record, not a dash.
  const reached = (index: number): boolean =>
    chainSettled || failed || index <= activeIndex;

  const stageCount: Record<StageKey, string> = {
    // Intake carries its own em dash for "totals not published yet", so it is
    // never gated on `reached` — it is stage zero and always reached once a run
    // has begun.
    intake: totalClauses > 0 ? `${doneClauses}/${totalClauses}` : "—",
    scan: String(passages),
    formulate: String(drafted),
    link: String(linked),
    review: String(committed),
  };
  const stageValue = (key: StageKey, index: number): string =>
    key === "intake" || reached(index) ? stageCount[key] : "—";

  // Shown only when a previous extraction exists to compare against. On a first
  // run every counter is zero, and a "since the previous extraction" heading
  // over nothing would imply one happened.
  const deltaTotal = deltaNew + deltaChanged + deltaUnchanged + deltaRemoved;

  // The route each drafted rule was assigned as it was drafted — Deterministic
  // where the source states a test the engine computes over named facts, AI
  // Ready where it states its test in words for a judge to read against the
  // case. This is the product's central split, decided per rule during the run,
  // and it is read straight from the server's own tally: `policy.py` keeps the
  // mode derived rather than stored so a second copy cannot disagree with the
  // condition it describes, and recomputing it here would be exactly that second
  // copy. So the panel only ever shows what the run reported.
  //
  // `hasRouteData` gates on the fields being present at all, not on their value:
  // an older server carries neither, and a fabricated 0 would be a claim nobody
  // made. `showRoutes` additionally waits for the first drafted rule — there is
  // nothing to split before that, and "0 · 0" over no rules would read as a
  // found result. Past both gates, a 0 in the readout can only mean "no rule
  // took this route", never "not reached yet".
  const hasRouteData = routeDeterministic !== undefined || routeAiReady !== undefined;
  const routeDet = routeDeterministic ?? 0;
  const routeAi = routeAiReady ?? 0;
  // Not assumed to sum to `drafted`: a rule whose mode is absent, or a route
  // added to the model after this was written, is counted by neither. That
  // remainder is shown, not charged to a side or hidden, so the figures
  // reconcile in view rather than appearing to lose rules.
  const routeUnrouted = Math.max(0, drafted - routeDet - routeAi);
  const showRoutes = hasRouteData && drafted > 0;

  // Counters joined into one line with a separator rather than stacked, so the
  // readout stays a fixed height no matter how many counters exist.
  const counters = [
    pagesAreMeaningful ? `${donePages} of ${plural(totalPages, "page")}` : null,
    totalBatches > 0
      ? `batch ${Math.min(doneBatches + (done ? 0 : 1), totalBatches)} of ${totalBatches}`
      : null,
    elapsed > 0 ? duration(elapsed) + " elapsed" : null,
    // The number someone actually uses to decide whether to wait, so it is
    // stated plainly rather than left to be inferred from batch counts.
    eta !== null ? `about ${duration(eta)} left` : null,
    throughput ? `${throughput.value.toFixed(1)} ${throughput.unit}` : null,
  ].filter(Boolean);

  return (
    <div className={`extract-progress${failed ? " extract-progress--failed" : ""}`}>
      <div className="extract-pipeline" aria-label="Extraction pipeline">
        {STAGES.map((s, i) => {
          // Nothing in the chain is active once it is settled (done, or the
          // trailing comparison pass) or has failed; every box before the lit
          // one, and every box once settled, reads as complete.
          const isActive = !chainSettled && !failed && s.key === activeStage;
          const isPast = chainSettled || i < activeIndex;
          return (
            <div key={s.key} className="extract-pipeline-item">
              <Tooltip title={s.hint}>
                <div
                  className={`extract-stage${isActive ? " extract-stage--active" : ""}${
                    isPast ? " extract-stage--done" : ""
                  }`}
                >
                  <span className="extract-stage-icon">{s.icon}</span>
                  <StageValue text={stageValue(s.key, i)} />
                  <span className="extract-stage-label">{s.label}</span>
                </div>
              </Tooltip>
              {i < STAGES.length - 1 && (
                <div
                  className={`extract-flow${
                    !chainSettled && !failed && i === activeIndex - 1 ? " extract-flow--moving" : ""
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

      {skipped > 0 && (
        // Rendered off the chain, not in it. Skipped statements do not pass
        // through to the next stage — they leave the pipeline, and putting
        // them in the flow would imply they arrive somewhere. It was
        // previously a fragment of the counters line, where the one number
        // saying material was dropped read as an aside.
        <div className="extract-dropout">
          <Tooltip title="Policy statements the formulator could not turn into a rule, or rules it declined to draft. They are recorded on the run with a reason and are not in the review queue.">
            <span className="extract-dropout-box">
              <span className="extract-dropout-arrow" aria-hidden>
                ↳
              </span>
              <StageValue text={String(skipped)} />
              <span className="extract-stage-label">not turned into rules</span>
            </span>
          </Tooltip>
        </div>
      )}

      {showRoutes && (
        // The product's central split, shown as it is decided. Both routes get
        // one weight and one colour and sit as plain counts joined by a middot,
        // the same neutral form the project register uses ("N Deterministic · M
        // AI Ready"). Deliberately NOT a bar or a percentage: on a real corpus
        // the split is heavily one-sided, and a bar would draw the smaller route
        // as a shortfall against the larger. AI Ready is what the source states,
        // not a lesser outcome, so neither route is drawn as filling or lagging.
        <div className="extract-routes" aria-label="How the drafted rules divide by route">
          <span className="extract-routes-label">By route</span>
          <div className="extract-routes-items">
            <Tooltip title="Rules whose test the source states as a comparison the engine computes over named facts.">
              <span className="extract-route">
                <StageValue text={String(routeDet)} />
                <span className="extract-route-name">Deterministic</span>
              </span>
            </Tooltip>
            <span className="extract-route-sep" aria-hidden>
              ·
            </span>
            <Tooltip title="Rules whose test the source states in words, read by a judge against each case — how most policy text is written.">
              <span className="extract-route">
                <StageValue text={String(routeAi)} />
                <span className="extract-route-name">AI Ready</span>
              </span>
            </Tooltip>
            {routeUnrouted > 0 && (
              // Only when the two routes leave a remainder. Kept visible so the
              // counts reconcile against the rules drafted rather than appearing
              // to lose some — the gap is information, not a rounding error.
              <>
                <span className="extract-route-sep" aria-hidden>
                  ·
                </span>
                <Tooltip title="Drafted rules the run placed in neither route — its route is not set, or a route added after this readout was built. Shown so the two counts need not add up to the rules drafted.">
                  <span className="extract-route">
                    <StageValue text={String(routeUnrouted)} />
                    <span className="extract-route-name">unrouted</span>
                  </span>
                </Tooltip>
              </>
            )}
          </div>
        </div>
      )}

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
      {!chainSettled && !failed && (
        // Extraction continues server-side, so the one thing a reviewer needs
        // to know before walking away is that they may. Without it the honest
        // assumption is that closing the tab cancels the run. Gated on
        // `chainSettled`, not just `done`: once the run is comparing, every
        // batch has already committed, so "rules appear as each batch commits"
        // describes work that has stopped — the same "says it is still doing X
        // when it is not" defect the comparison indicator below exists to avoid.
        <div className="extract-progress-line extract-progress-hint">
          <Text type="secondary">
            This keeps running if you navigate away — rules appear in the review queue as each
            batch commits.
          </Text>
        </div>
      )}
      {comparing && (
        // The run's final act: every box in the chain is settled, but the
        // service is still classifying this run against the previous extraction
        // (see ai_extraction.py — emitted while status is still "running").
        // Without this the strip would read as finished mid-work. Placed where
        // the delta lands once the run completes, so "comparing…" resolves in
        // place into "since the previous extraction, N changed" rather than the
        // story jumping elsewhere. role="status" so assistive tech hears that
        // work continues past the settled chain.
        <div className="extract-compare" role="status">
          <LoadingOutlined spin />
          <Text type="secondary">
            Every rule above is drafted, linked and in the review queue. Now checking this run
            against the previous extraction of this document to see what changed.
          </Text>
        </div>
      )}
      {done && deltaTotal > 0 && (
        // What actually needs reviewing. A completed run reported its rule
        // count and nothing else, so a re-extraction of 190 rules where 187
        // are unchanged looked like 190 decisions rather than three.
        <div className="extract-delta">
          <Text type="secondary" className="extract-delta-label">
            Since the previous extraction
          </Text>
          <div className="extract-delta-items">
            {deltaNew > 0 && (
              <Tooltip title="Rules this run found that the previous one did not.">
                <Tag variant="filled" color="green">
                  {deltaNew} new
                </Tag>
              </Tooltip>
            )}
            {deltaChanged > 0 && (
              <Tooltip title="Rules that exist in both runs but whose content differs.">
                <Tag variant="filled" color="gold">
                  {deltaChanged} changed
                </Tag>
              </Tooltip>
            )}
            {deltaRemoved > 0 && (
              <Tooltip title="Rules the previous run produced that this one did not. They generate no row of their own, so this is the only place they appear.">
                <Tag variant="filled" color="red">
                  {deltaRemoved} no longer found
                </Tag>
              </Tooltip>
            )}
            {deltaUnchanged > 0 && (
              <Tooltip title="Rules identical to the previous extraction. Nothing to decide on these.">
                <Tag variant="filled">{deltaUnchanged} unchanged</Tag>
              </Tooltip>
            )}
          </div>
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
