/**
 * How a document version's ingestion outcome is worded for a reader.
 *
 * WHY THIS IS A SEPARATE MODULE
 *
 * The backend ships codes, not prose: `ingestion_status` is one of a small set
 * of stable identifiers and the diagnostics carry `code` values, not sentences.
 * Turning those into something a reviewer reads is a UI decision, and keeping it
 * in one exported map means the register, the upload confirmation and anything
 * added later cannot describe the same ingestion in two different ways.
 *
 * It also gives the guard something to check. `tests/unit/
 * test_ingestion_problems_outlive_the_upload.py` compares the statuses the API
 * can emit against the keys below, so a status added on the server that nobody
 * taught the UI to render fails a test instead of rendering as blank space.
 */

/** Mirrors `INGESTION_STATUS_*` in `src/policy_platform/api/schemas.py`. */
export type IngestionStatus = "ok" | "warning" | "error" | "unrecorded";

export interface IngestionOutcome {
  /** Short enough for a table cell. */
  label: string;
  /** Ant Design Tag colour. `undefined` renders the neutral default. */
  color?: string;
  /** The longer sentence, shown on hover. */
  hint: string;
}

export const INGESTION_OUTCOMES: Record<IngestionStatus, IngestionOutcome> = {
  ok: {
    label: "Read cleanly",
    hint: "Every part of the source resolved to the text recorded against it.",
  },
  warning: {
    label: "Read with warnings",
    color: "orange",
    hint:
      "The source was read, but parts of it came through in a way worth checking. " +
      "Clause coverage may be lower than the document itself.",
  },
  error: {
    label: "Did not read cleanly",
    color: "red",
    hint:
      "Reading this document ran into an error. What was stored may be incomplete, " +
      "so treat a low clause count as unexplained rather than as a short document.",
  },
  unrecorded: {
    label: "Not recorded",
    hint:
      "This version was uploaded before ingestion problems were kept, so nothing is " +
      "known either way. Absence of a warning here is not evidence it read cleanly.",
  },
};

/** Falls back to `unrecorded` rather than inventing reassurance for a status we do not know. */
export function ingestionOutcome(status: string | null | undefined): IngestionOutcome {
  if (status && status in INGESTION_OUTCOMES) {
    return INGESTION_OUTCOMES[status as IngestionStatus];
  }
  return INGESTION_OUTCOMES.unrecorded;
}
