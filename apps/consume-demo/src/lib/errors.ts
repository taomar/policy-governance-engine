import { INDEX_PROJECTION_UNAVAILABLE, type ApiErrorDetail } from '../contracts/caseDecision'

/**
 * What went wrong, said in a way a reader can act on.
 *
 * THE RULE THIS MODULE EXISTS TO ENFORCE
 *
 * On a policy surface, silence is more dangerous than failure. Every message
 * below names what did *not* happen -- nothing was evaluated, nothing was
 * stored, nothing reached the API -- because a caller who is merely told
 * "something went wrong" will reasonably assume the safest thing, and the
 * safest assumption after a failed policy call is usually the wrong one.
 *
 * No message renders a stack trace, and no message renders the subscription key
 * or any part of it. The key is never passed into this module at all, so there is
 * nothing here to redact.
 */

export type RecoveryKind =
  | 'focus-subscription-key'
  | 'focus-key'
  | 'focus-scenario'
  | 'focus-guidance'
  | 'retry'
  | 'retry-open-base'
  | 'retry-lookup'
  | 'generate-key'
  | 'none'

export interface PlaygroundError {
  /** The HTTP status, or a transport pseudo-status for the two that have none. */
  status: number | 'network' | 'timeout'
  /** The server's own machine-readable code, when it sent one. */
  code?: string
  heading: string
  body: string
  recovery: RecoveryKind
  correlationId?: string
  decisionId?: string
  /** The raw detail, kept for the `Copy error details` control. */
  detail?: unknown
}

export const TIMEOUT_SECONDS = 60

function detailMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') {
    const record = detail as ApiErrorDetail
    if (typeof record.message === 'string') return record.message
    // FastAPI's own validation shape: a list of {loc, msg, type}.
    if (Array.isArray(detail)) {
      return detail
        .map((entry) => {
          if (entry && typeof entry === 'object' && 'msg' in entry) {
            const loc = 'loc' in entry && Array.isArray(entry.loc) ? entry.loc.join('.') : ''
            return loc ? `${loc}: ${String(entry.msg)}` : String(entry.msg)
          }
          return String(entry)
        })
        .join('; ')
    }
  }
  return ''
}

function detailCode(detail: unknown): string | undefined {
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const record = detail as ApiErrorDetail
    if (typeof record.code === 'string') return record.code
  }
  return undefined
}

function detailField(detail: unknown, field: 'correlation_id' | 'decision_id'): string | undefined {
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const value = (detail as ApiErrorDetail)[field]
    if (typeof value === 'string') return value
  }
  return undefined
}

/**
 * Map one failed POST onto the copy for its condition.
 *
 * The `409` family is split by the server's own code rather than by the status,
 * because "you reused a key for a different question", "the first call is still
 * running" and "that key was spent on a failure" require three different
 * actions from the caller and collapsing them into one message would leave two
 * thirds of the readers stuck.
 */
export function mapDecisionError(input: {
  status: number | 'network' | 'timeout'
  detail?: unknown
  projectKey: string
  correlationId?: string
}): PlaygroundError {
  const { status, detail, projectKey } = input
  const code = detailCode(detail)
  const serverMessage = detailMessage(detail)
  const correlationId = detailField(detail, 'correlation_id') ?? input.correlationId
  const decisionId = detailField(detail, 'decision_id')

  const base = { code, correlationId, decisionId, detail }

  if (status === 'network') {
    return {
      ...base,
      status,
      heading: 'The request never reached the API.',
      body: "Check the API base URL, that the server is running, and that this origin is allowed by the server's CORS configuration.",
      recovery: 'retry-open-base',
    }
  }

  if (status === 'timeout') {
    return {
      ...base,
      status,
      heading: `The request timed out after ${TIMEOUT_SECONDS}s.`,
      body: 'The decision may still have been recorded. Verify by decision id before sending again.',
      recovery: 'retry-lookup',
    }
  }

  switch (status) {
    case 401:
      return {
        ...base,
        status,
        heading: 'The subscription key was not accepted.',
        body: 'The API rejected the credential. Paste a current subscription key and send again.',
        recovery: 'focus-subscription-key',
      }
    case 403:
      return {
        ...base,
        status,
        heading: 'This subscription key may not put cases to this project.',
        body: `The credential is valid but is not permitted on project "${projectKey}". Ask the project owner for access.`,
        recovery: 'none',
      }
    case 404:
      return {
        ...base,
        status,
        heading: `No project is published under the key "${projectKey}".`,
        body: "Check the key. Keys are case-sensitive and are not the project's UUID.",
        recovery: 'focus-key',
      }
    case 409:
      if (code === 'idempotency_key_reused') {
        return {
          ...base,
          status,
          heading: 'This Idempotency-Key was already used for a different request.',
          body: 'The guidance or the question changed, so the stored decision does not answer what you just asked. Clear the key, or generate a new one, and send again.',
          recovery: 'generate-key',
        }
      }
      if (code === 'decision_in_progress') {
        return {
          ...base,
          status,
          heading: 'A decision is already in flight for this Idempotency-Key.',
          body: 'Wait for it to finish, then verify it by decision id.',
          recovery: 'retry-lookup',
        }
      }
      if (code === 'decision_previously_failed') {
        return {
          ...base,
          status,
          heading: 'This Idempotency-Key was spent on a decision that failed.',
          body: 'A key is spent once. Generate a new key and send again.',
          recovery: 'generate-key',
        }
      }
      return {
        ...base,
        status,
        heading: 'This project has no active published version.',
        body: 'There is nothing to decide against yet. Publish a version, then send the case again.',
        recovery: 'retry',
      }
    case 422:
      return {
        ...base,
        status,
        heading: 'The request was rejected before evaluation.',
        body: `The API could not read this request. ${serverMessage}`.trim(),
        recovery:
          code === 'additional_instructions_too_long' ? 'focus-guidance' : 'focus-scenario',
      }
    case 503:
      /* NOT A TRANSIENT OUTAGE, AND MUST NOT BE OFFERED AS ONE.
         `index_projection_unavailable` is the single retrieval state the server
         refuses rather than answering with an empty 200, because a question
         reduced to the processing language matched against a corpus never
         rendered into it scores near zero on every policy -- and a near-zero
         ranking reads exactly like a real "nothing bears on this". No amount of
         retrying changes that: the corpus projection has to be rebuilt first.
         Rendering the generic "try again shortly" here would send a caller into
         a retry loop against a condition only an operator can clear. */
      if (code === INDEX_PROJECTION_UNAVAILABLE) {
        return {
          ...base,
          status,
          heading: 'This project’s search index has no usable projection, so nothing could be compared.',
          body: `The index for "${projectKey}" is missing its corpus projection, or the projection was superseded or left incomplete by an unfinished rebuild. Retrying will not clear this: ask the project owner to rebuild the index, then send the case again. Nothing was evaluated, and no answer was produced — this is deliberately not returned as "no policy matched your question", which is what an unrendered corpus would otherwise look like. ${serverMessage}`.trim(),
          recovery: 'none',
        }
      }
      return {
        ...base,
        status,
        heading: 'The policy service is not available right now.',
        body: 'Nothing was evaluated and nothing was stored. Try again shortly.',
        recovery: 'retry',
      }
    case 500:
      // The one 500 this contract names: a decision was made and could not be
      // stored. It is not a success with a caveat -- the result region renders
      // nothing at all, because an unstored decision is not evidence.
      if (code === 'decision_receipt_failed') {
        return {
          ...base,
          status,
          heading: 'The decision was not stored, so it is not usable. Nothing is shown.',
          body: 'A receipt that was not written cannot be verified or cited later, so no verdict, result or hash is rendered for it.',
          recovery: 'retry',
        }
      }
      return {
        ...base,
        status,
        heading: 'The policy service failed while handling this request.',
        body: `Nothing here should be used as evidence. ${serverMessage}`.trim(),
        recovery: 'retry',
      }
    default:
      return {
        ...base,
        status,
        heading: `The API refused this request with status ${status}.`,
        body: `Nothing was evaluated. ${serverMessage}`.trim(),
        recovery: 'retry',
      }
  }
}

/**
 * The GET side of the same job. Verification failures are their own vocabulary
 * because "the receipt could not be read" and "the receipt does not match" are
 * opposite claims and must never be rendered with the same words.
 */
export function mapVerifyError(input: {
  status: number | 'network' | 'timeout'
  detail?: unknown
}): PlaygroundError {
  const { status, detail } = input
  const code = detailCode(detail)
  const base = { code, detail, correlationId: detailField(detail, 'correlation_id') }

  if (status === 403) {
    return {
      ...base,
      status,
      heading:
        'This receipt may be read by the caller who made the decision, or by a policy author or administrator.',
      body: 'Your subscription key made the call but may not read the stored receipt, so this decision is unverified.',
      recovery: 'none',
    }
  }
  if (status === 409) {
    return {
      ...base,
      status,
      heading: 'The decision is still being written. It cannot be verified yet.',
      body: 'A receipt that has not been completed carries no verdict to compare against.',
      recovery: 'retry',
    }
  }
  if (status === 410) {
    return {
      ...base,
      status,
      heading: 'The stored receipt failed and has no verdict to serve.',
      body: 'A failed receipt is not a decision. Nothing here should be used as evidence.',
      recovery: 'none',
    }
  }
  if (status === 401) {
    return {
      ...base,
      status,
      heading: 'The subscription key was not accepted.',
      body: 'The API rejected the credential, so the stored receipt could not be read and this decision is unverified.',
      recovery: 'focus-subscription-key',
    }
  }

  return {
    ...base,
    status,
    heading: 'The stored receipt could not be read, so this decision is unverified.',
    body: 'An unverified decision is not evidence.',
    recovery: 'retry',
  }
}
