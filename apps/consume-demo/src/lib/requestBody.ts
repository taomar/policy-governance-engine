import type { CaseDecisionRequestBody, ReasoningEffort } from '../contracts/caseDecision'

/**
 * Turning what is on screen into what goes on the wire.
 *
 * This module is deliberately the only place a request body is constructed, so
 * the Request Inspector's preview and the request the page actually sends are
 * the same function called twice rather than two functions that agree today.
 * A preview that is assembled separately from the send is a preview of nothing.
 */

export interface DocketValues {
  scenario: string
  reasoningEffort: ReasoningEffort
  callingSystemIdentity: string
  additionalInstructions: string
}

/**
 * The body, exactly as it will be serialised.
 *
 * Two rules, and both are about honesty rather than tidiness:
 *
 *   * The scenario and the guidance are **trimmed**, and the inspector shows
 *     the trimmed value, so what is displayed is what is sent.
 *
 *   * When the guidance field is empty or whitespace-only the key is **omitted
 *     entirely**. Not `""`, not `null`. An empty string is a value that the
 *     receipt will echo back and that verification will compare; an absent key
 *     is an absence the receipt can report as one. Collapsing the two would
 *     make the receipt unable to say which of them happened.
 */
export function buildRequestBody(values: DocketValues): CaseDecisionRequestBody {
  const guidance = values.additionalInstructions.trim()

  const body: CaseDecisionRequestBody = {
    scenario: values.scenario.trim(),
    reasoning_effort: values.reasoningEffort,
    calling_system_identity: values.callingSystemIdentity.trim(),
  }

  if (guidance.length > 0) {
    body.additional_instructions = guidance
  }

  return body
}

/**
 * The body as JSON, in the key order the client sends them.
 *
 * `JSON.stringify` preserves insertion order for string keys, and
 * `buildRequestBody` inserts them in wire order, so the pretty-printed preview
 * and the compact wire form list the same keys in the same sequence.
 */
export function requestBodyJson(values: DocketValues, indent = 2): string {
  return JSON.stringify(buildRequestBody(values), null, indent)
}

/** The compact single-line form, as it appears on the Raw HTTP tab. */
export function requestBodyWire(values: DocketValues): string {
  return JSON.stringify(buildRequestBody(values))
}

/**
 * `{base}` and a path, joined without producing a double slash or losing a
 * path prefix. A base of `https://host/api-gateway` is a real deployment shape,
 * so the base's own path is kept.
 */
export function joinUrl(base: string, path: string): string {
  const trimmedBase = base.trim().replace(/\/+$/, '')
  const trimmedPath = path.startsWith('/') ? path : `/${path}`
  return `${trimmedBase}${trimmedPath}`
}

/** The POST path for one project, as it appears in the request line. */
export function casePath(projectKey: string): string {
  const key = projectKey.trim()
  // The placeholder is rendered as itself. Percent-encoding `{project_key}`
  // into `%7Bproject_key%7D` in the pre-submit preview makes the one line an
  // integrator is most likely to copy look like a bug in the API.
  if (!key) return '/api/policy-decisions/{project_key}/case'
  return `/api/policy-decisions/${encodeURIComponent(key)}/case`
}

/** The GET path for one stored receipt. */
export function receiptPath(decisionId: string): string {
  return `/api/policy-decisions/${encodeURIComponent(decisionId.trim())}`
}

/**
 * The `Host:` header line for the Raw HTTP tab. A base URL the user is still
 * typing is not an error worth withholding the preview over -- the raw value is
 * shown as written instead, which is also what a real client would send it as.
 */
export function hostFromBase(base: string): string {
  try {
    return new URL(base.trim()).host
  } catch {
    return base.trim() || 'policy.example.com'
  }
}

export function isParsableUrl(value: string): boolean {
  const trimmed = value.trim()
  if (!trimmed) return false
  try {
    const url = new URL(trimmed)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}
