import type { CaseDecisionEnvelope, PolicySetSummary, ActiveVersionSummary } from '../contracts/caseDecision'
import type { DocketValues } from './requestBody'
import { buildRequestBody, casePath, joinUrl, receiptPath } from './requestBody'
import { SUBSCRIPTION_KEY_HEADER } from './subscriptionKey'
import { TIMEOUT_SECONDS, mapDecisionError, mapVerifyError, type PlaygroundError } from './errors'

/**
 * The whole of this app's contact with the platform: four `fetch` calls.
 *
 * There is no client library, no generated SDK and no shared module with the
 * product. That is the demonstration -- if this page needed anything from
 * inside the platform to call it, the API would not be the integration surface
 * it claims to be.
 *
 * The subscription key is a parameter on every call and is never stored in this
 * module. It arrives from React state, is handed to `fetch`, and is gone. It
 * is not logged, not cached, not put on a header object that outlives the call,
 * and not written anywhere the browser persists.
 *
 * All four calls carry it in `X-Policy-Subscription-Key` rather than in
 * `Authorization`. The two are different credentials with different
 * lifecycles, and a server reading one header cannot be given the other; see
 * `lib/subscriptionKey.ts`.
 */

export type ApiResult<T> =
  | { ok: true; value: T; correlationId?: string }
  | { ok: false; error: PlaygroundError }

function apiHeaders(subscriptionKey: string): HeadersInit {
  return {
    [SUBSCRIPTION_KEY_HEADER]: subscriptionKey,
    'Content-Type': 'application/json',
  }
}

async function readDetail(response: Response): Promise<unknown> {
  try {
    const parsed = (await response.json()) as { detail?: unknown }
    if (parsed && typeof parsed === 'object' && 'detail' in parsed) return parsed.detail
    return parsed
  } catch {
    return undefined
  }
}

/**
 * A 60-second ceiling.
 *
 * The decider retrieves, narrows and evaluates, so a slow answer is normal and
 * a short timeout would abandon good decisions. But an unbounded wait leaves a
 * user unable to tell a working call from a dead one, and the timeout copy is
 * written for exactly that ambiguity: it says the decision may still have been
 * recorded and offers to look it up by id rather than inviting a second call
 * that would decide the same case twice.
 */
function withTimeout(signalSeconds = TIMEOUT_SECONDS): { signal: AbortSignal; cancel: () => void } {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), signalSeconds * 1000)
  return { signal: controller.signal, cancel: () => clearTimeout(timer) }
}

/** Resolve a project by its stable key. Used for identity, never for routing. */
export async function fetchPolicySet(input: {
  baseUrl: string
  projectKey: string
  subscriptionKey: string
  signal?: AbortSignal
}): Promise<ApiResult<PolicySetSummary>> {
  try {
    const response = await fetch(
      joinUrl(input.baseUrl, `/api/policy-sets/${encodeURIComponent(input.projectKey.trim())}`),
      { headers: apiHeaders(input.subscriptionKey), signal: input.signal },
    )
    if (!response.ok) {
      return {
        ok: false,
        error: mapDecisionError({
          status: response.status,
          detail: await readDetail(response),
          projectKey: input.projectKey,
        }),
      }
    }
    return { ok: true, value: (await response.json()) as PolicySetSummary }
  } catch (cause) {
    if ((cause as Error)?.name === 'AbortError') {
      return {
        ok: false,
        error: mapDecisionError({ status: 'timeout', projectKey: input.projectKey }),
      }
    }
    return { ok: false, error: mapDecisionError({ status: 'network', projectKey: input.projectKey }) }
  }
}

/** The exact published version a case would be decided against today. */
export async function fetchActiveVersion(input: {
  baseUrl: string
  projectKey: string
  subscriptionKey: string
  signal?: AbortSignal
}): Promise<ApiResult<ActiveVersionSummary | null>> {
  try {
    const response = await fetch(
      joinUrl(
        input.baseUrl,
        `/api/policy-sets/${encodeURIComponent(input.projectKey.trim())}/active-version`,
      ),
      { headers: apiHeaders(input.subscriptionKey), signal: input.signal },
    )
    if (response.status === 404 || response.status === 409) {
      // A project with nothing published is a legitimate state, not an error.
      return { ok: true, value: null }
    }
    if (!response.ok) {
      return {
        ok: false,
        error: mapDecisionError({
          status: response.status,
          detail: await readDetail(response),
          projectKey: input.projectKey,
        }),
      }
    }
    return { ok: true, value: (await response.json()) as ActiveVersionSummary }
  } catch (cause) {
    if ((cause as Error)?.name === 'AbortError') {
      return { ok: false, error: mapDecisionError({ status: 'timeout', projectKey: input.projectKey }) }
    }
    return { ok: false, error: mapDecisionError({ status: 'network', projectKey: input.projectKey }) }
  }
}

/**
 * Put one case to a project's published policies.
 *
 * The correlation id and the idempotency key are sent as headers, never in the
 * body: they describe the delivery of the request, not the question. Putting
 * the idempotency key in the body would make it part of the hash it is
 * compared against, which would defeat the whole mechanism.
 */
export async function postCase(input: {
  baseUrl: string
  projectKey: string
  subscriptionKey: string
  correlationId: string
  idempotencyKey?: string
  values: DocketValues
}): Promise<ApiResult<CaseDecisionEnvelope>> {
  const { signal, cancel } = withTimeout()

  const headers: Record<string, string> = {
    ...(apiHeaders(input.subscriptionKey) as Record<string, string>),
    'X-Correlation-Id': input.correlationId,
  }
  const key = (input.idempotencyKey ?? '').trim()
  if (key) headers['Idempotency-Key'] = key

  try {
    const response = await fetch(joinUrl(input.baseUrl, casePath(input.projectKey)), {
      method: 'POST',
      headers,
      body: JSON.stringify(buildRequestBody(input.values)),
      signal,
    })

    const correlationId = response.headers.get('X-Correlation-Id') ?? undefined

    if (!response.ok) {
      return {
        ok: false,
        error: mapDecisionError({
          status: response.status,
          detail: await readDetail(response),
          projectKey: input.projectKey,
          correlationId: correlationId ?? input.correlationId,
        }),
      }
    }

    return { ok: true, value: (await response.json()) as CaseDecisionEnvelope, correlationId }
  } catch (cause) {
    if ((cause as Error)?.name === 'AbortError') {
      return {
        ok: false,
        error: mapDecisionError({
          status: 'timeout',
          projectKey: input.projectKey,
          correlationId: input.correlationId,
        }),
      }
    }
    return {
      ok: false,
      error: mapDecisionError({
        status: 'network',
        projectKey: input.projectKey,
        correlationId: input.correlationId,
      }),
    }
  } finally {
    cancel()
  }
}

/**
 * Read a stored receipt back by id.
 *
 * This is what makes verification a real check rather than a reassurance: the
 * server replays the envelope from storage instead of rebuilding it, so a
 * decision hash that still matches is evidence the stored content has not
 * changed.
 */
export async function getReceipt(input: {
  baseUrl: string
  decisionId: string
  subscriptionKey: string
}): Promise<ApiResult<CaseDecisionEnvelope>> {
  const { signal, cancel } = withTimeout()
  try {
    const response = await fetch(joinUrl(input.baseUrl, receiptPath(input.decisionId)), {
      headers: apiHeaders(input.subscriptionKey),
      signal,
    })
    if (!response.ok) {
      return { ok: false, error: mapVerifyError({ status: response.status, detail: await readDetail(response) }) }
    }
    return { ok: true, value: (await response.json()) as CaseDecisionEnvelope }
  } catch (cause) {
    if ((cause as Error)?.name === 'AbortError') {
      return { ok: false, error: mapVerifyError({ status: 'timeout' }) }
    }
    return { ok: false, error: mapVerifyError({ status: 'network' }) }
  } finally {
    cancel()
  }
}
