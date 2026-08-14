/**
 * What to tell someone while an upload is in flight.
 *
 * The upload endpoint does far more than move bytes. In one request it stores
 * the file, then reads the whole document and splits it into clauses, then
 * indexes those clauses. The reading is the slow part, and on a long document
 * it can run well past a minute. Until it finishes, the request has produced
 * nothing to report on.
 *
 * That last point is why there is no percentage here. `fetch` resolves once,
 * when the server replies; there is no intermediate signal to turn into a bar.
 * Inventing one would mean animating a number the client cannot observe, and a
 * progress bar that is guessing is worse than no progress bar, because it will
 * sit at 90% during the part that actually takes the time.
 *
 * So this reports only things that are true and knowable client-side:
 *   - the name and size of the file, which came from the file itself
 *   - how long the request has been running, which is measured
 *   - what the server is doing, which is fixed by the endpoint
 *   - what happens when it returns, which is fixed by the app
 *
 * Elapsed time is the one that matters most. The complaint this answers is
 * "a reviewer cannot tell a slow parse from a hung one", and a running clock
 * is exactly the discriminator: a number that is still climbing means the
 * request is still open.
 */

/** Binary-prefix units, largest last, so the loop below can walk down. */
const SIZE_UNITS = ["B", "KB", "MB", "GB"] as const;

/**
 * A file size a person can read. Whole bytes below 1 KB (there is no useful
 * fraction of a byte), one decimal above it.
 *
 * Returns null for a size that cannot be stated honestly — a negative or
 * non-finite number. Callers omit the size rather than print nonsense.
 */
export function formatFileSize(bytes: number | null | undefined): string | null {
  if (typeof bytes !== "number" || !Number.isFinite(bytes) || bytes < 0) return null;
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < SIZE_UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const rendered = unit === 0 ? String(Math.round(value)) : value.toFixed(1);
  return `${rendered} ${SIZE_UNITS[unit]}`;
}

/**
 * Elapsed time as m:ss, counting up. Sub-second and negative inputs clamp to
 * zero so a clock skew cannot render "-1:59".
 */
export function formatElapsed(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export interface UploadWaitState {
  /** Headline naming the file being read. */
  headline: string;
  /** The running clock, already formatted. */
  elapsed: string;
  /** What the server is doing right now. */
  activity: string;
  /** What the reviewer gets when it returns. */
  next: string;
}

/**
 * Compose the wait state. `fileSize` is omitted from the headline when the
 * File carries no usable size, rather than printing a placeholder.
 */
export function uploadWaitState(
  fileName: string,
  fileSizeBytes: number | null | undefined,
  elapsedMs: number
): UploadWaitState {
  const size = formatFileSize(fileSizeBytes);
  return {
    headline: size ? `Reading ${fileName} (${size})` : `Reading ${fileName}`,
    elapsed: formatElapsed(elapsedMs),
    activity:
      "The server is reading the whole document and splitting it into clauses before it replies, " +
      "so the time this takes follows the length of the document. There is one reply at the end, " +
      "which is why there is no percentage to show.",
    next: "When it returns, the document is stored as a new version. Extracting rules is a separate step you start afterwards.",
  };
}

/**
 * Fields of the upload response that this app reads back to the reviewer.
 *
 * Named here rather than only at the call site because the client receives the
 * response untyped, so a field renamed on the server would silently render as
 * nothing at all. `tests/unit/test_upload_result_fields_exist.py` reads this
 * list and the endpoint's own return statement, and fails when they disagree.
 */
export const UPLOAD_RESULT_FIELDS_READ = [
  "version_number",
  "clause_count",
  "clauses_indexed",
  "extraction_error",
  "ingestion_diagnostics",
] as const;

export interface UploadOutcome {
  /** Confirmation line, carrying whatever counts the endpoint reported. */
  message: string;
  /** Stated when the document was stored but reading it did not complete. */
  problem: string | null;
  /** Per-page or per-section notes the parser recorded, verbatim. */
  notes: string[];
}

/**
 * Describe a finished upload from what the endpoint actually returned.
 *
 * The endpoint reports a clause count, an indexed count, a parse error and a
 * list of ingestion diagnostics, and the page previously showed none of them:
 * a scanned PDF that yielded no readable text arrived as a plain green
 * "Uploaded" with no hint that nothing had been read out of it. The counts and
 * the diagnostics are the evidence that the document came through intact, so
 * they belong on the same line as the confirmation.
 */
export function uploadOutcome(fileName: string, result: Record<string, unknown>): UploadOutcome {
  const version = result.version_number;
  const clauses = typeof result.clause_count === "number" ? result.clause_count : null;
  const indexed = typeof result.clauses_indexed === "number" ? result.clauses_indexed : null;
  const parseError = typeof result.extraction_error === "string" ? result.extraction_error : null;
  const diagnostics = Array.isArray(result.ingestion_diagnostics) ? result.ingestion_diagnostics : [];

  const notes = diagnostics
    .map((d) => {
      if (typeof d === "string") return d;
      if (d && typeof d === "object") {
        const record = d as Record<string, unknown>;
        const text = record.message ?? record.detail ?? record.code;
        if (typeof text === "string") return text;
      }
      return null;
    })
    .filter((n): n is string => Boolean(n));

  const parts = [`Uploaded ${fileName} as version ${version}.`];
  if (clauses !== null) {
    const detail = [`${clauses} ${clauses === 1 ? "clause" : "clauses"} read from it`];
    if (indexed !== null && indexed !== clauses) {
      detail.push(`${indexed} of them searchable`);
    }
    parts.push(`${detail.join(", ")}.`);
  }

  return {
    message: parts.join(" "),
    problem: parseError ? `The file was stored, but reading it stopped: ${parseError}` : null,
    notes,
  };
}
