import { API_UNREACHABLE_STATUS, PolicyPlatformApiError } from "./api";

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

/**
 * Whether a failure means the server was never reached, as opposed to the
 * server answering with a refusal. Only the first justifies "we do not know" —
 * a 403 is a real answer and should not be dressed up as an outage.
 */
export function isUnreachable(error: unknown): boolean {
  return error instanceof PolicyPlatformApiError && error.status === API_UNREACHABLE_STATUS;
}
