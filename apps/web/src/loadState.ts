import { PolicyPlatformApiError } from "./api";

/**
 * The vocabulary the interface was missing.
 *
 * Panels here were written with two states: "we have the answer" and
 * everything else. Everything else was then rendered as a zero, an empty
 * collection, or a spinner that never stops — all three of which are claims
 * about the data rather than admissions about the request.
 *
 * An absent answer is not an empty answer:
 *
 *   loading      we have asked and have not heard back yet
 *   ready        we asked and this is the answer, including a true zero
 *   unavailable  we could not ask, so we do not know
 *
 * `unavailable` is a true statement. A fabricated zero is not.
 *
 * There is deliberately no `isUnreachable` helper here. One was written and
 * removed: every caller maps *any* failure to `unavailable`, because a 500 and
 * a refused connection both leave us without the answer. What differs between
 * them is the sentence shown to the reader, and that is already decided at the
 * api.ts seam — a real HTTP failure keeps its own `detail`, a transport failure
 * gets the "cannot reach" wording. The status distinction therefore never needs
 * to be re-derived here, and an exported helper whose only callers were its own
 * tests is the same dead-capability shape the reachability guard exists to find.
 */
export type LoadState = "loading" | "ready" | "unavailable";

/**
 * Rendered where a count would go when we do not have one. A reader seeing
 * this knows the number is unknown; a reader seeing "0" believes it is zero.
 */
export const UNKNOWN_COUNT = "—";

/**
 * Turn any thrown value into something a policy reviewer can read.
 *
 * Callers used to write `e instanceof PolicyPlatformApiError ? e.detail : String(e)`,
 * and `String(e)` on a failed `fetch` produces "TypeError: Failed to fetch" —
 * an internal exception name shown to someone reviewing employment policy.
 * Transport failures are now converted in `api.ts`, but this stays defensive:
 * an exception name must never be the message of last resort.
 */
export function describeApiFailure(error: unknown): string {
  if (error instanceof PolicyPlatformApiError) return error.detail;
  if (error instanceof Error && error.message && !looksLikeExceptionName(error.message)) {
    return error.message;
  }
  return "Something went wrong and the request could not be completed.";
}

/** True when a message is really a developer-facing exception name. */
function looksLikeExceptionName(message: string): boolean {
  return /^[A-Z]\w*Error\b/.test(message) || /^Failed to fetch$/i.test(message);
}
