import { describe, expect, it } from 'vitest'
import { mapDecisionError, mapVerifyError } from './errors'

const projectKey = 'demo-project'

describe('mapDecisionError', () => {
  it('names the credential for 401 and sends focus to the subscription key field', () => {
    const error = mapDecisionError({ status: 401, projectKey })
    expect(error.heading).toBe('The subscription key was not accepted.')
    expect(error.recovery).toBe('focus-subscription-key')
  })

  it('does not offer a retry for 403, because retrying cannot help', () => {
    const error = mapDecisionError({ status: 403, projectKey })
    expect(error.heading).toBe('This subscription key may not put cases to this project.')
    expect(error.body).toContain('demo-project')
    expect(error.recovery).toBe('none')
  })

  it('says a key is not a UUID for 404', () => {
    const error = mapDecisionError({ status: 404, projectKey })
    expect(error.heading).toBe('No project is published under the key "demo-project".')
    expect(error.body).toContain("not the project's UUID")
    expect(error.recovery).toBe('focus-key')
  })

  describe('the 409 family is split by the server code, not by the status', () => {
    it('idempotency_key_reused offers a new key', () => {
      const error = mapDecisionError({
        status: 409,
        detail: { code: 'idempotency_key_reused' },
        projectKey,
      })
      expect(error.heading).toBe('This Idempotency-Key was already used for a different request.')
      expect(error.recovery).toBe('generate-key')
    })

    it('decision_in_progress tells the caller to wait and verify, not to resend', () => {
      const error = mapDecisionError({
        status: 409,
        detail: { code: 'decision_in_progress' },
        projectKey,
      })
      expect(error.heading).toBe('A decision is already in flight for this Idempotency-Key.')
      expect(error.body).toContain('verify it by decision id')
    })

    it('decision_previously_failed says a key is spent once', () => {
      const error = mapDecisionError({
        status: 409,
        detail: { code: 'decision_previously_failed' },
        projectKey,
      })
      expect(error.heading).toBe('This Idempotency-Key was spent on a decision that failed.')
      expect(error.recovery).toBe('generate-key')
    })

    it('falls back to the no-published-version reading when no code is sent', () => {
      const error = mapDecisionError({ status: 409, projectKey })
      expect(error.heading).toBe('This project has no active published version.')
    })
  })

  it('carries the server detail into the 422 body', () => {
    const error = mapDecisionError({
      status: 422,
      detail: { code: 'additional_instructions_too_long', message: 'too long' },
      projectKey,
    })
    expect(error.heading).toBe('The request was rejected before evaluation.')
    expect(error.body).toContain('too long')
    expect(error.recovery).toBe('focus-guidance')
  })

  it('flattens FastAPI validation lists rather than printing [object Object]', () => {
    const error = mapDecisionError({
      status: 422,
      detail: [{ loc: ['body', 'scenario'], msg: 'field required', type: 'missing' }],
      projectKey,
    })
    expect(error.body).toContain('body.scenario: field required')
  })

  it('says nothing was evaluated and nothing stored for 503', () => {
    const error = mapDecisionError({ status: 503, projectKey })
    expect(error.body).toContain('Nothing was evaluated and nothing was stored.')
  })

  it('names both the base URL and CORS on a transport failure', () => {
    const error = mapDecisionError({ status: 'network', projectKey })
    expect(error.body).toContain('API base URL')
    expect(error.body).toContain('CORS')
    expect(error.recovery).toBe('retry-open-base')
  })

  it('offers lookup by id on a timeout, rather than inviting a second decision', () => {
    const error = mapDecisionError({ status: 'timeout', projectKey })
    expect(error.heading).toBe('The request timed out after 60s.')
    expect(error.body).toContain('may still have been recorded')
    expect(error.recovery).toBe('retry-lookup')
  })

  it('treats a persistence failure as an unusable result, not a caveated success', () => {
    const error = mapDecisionError({
      status: 500,
      detail: { code: 'decision_receipt_failed', decision_id: 'd-1', correlation_id: 'c-1' },
      projectKey,
    })
    expect(error.heading).toBe('The decision was not stored, so it is not usable. Nothing is shown.')
    expect(error.code).toBe('decision_receipt_failed')
    expect(error.decisionId).toBe('d-1')
    expect(error.correlationId).toBe('c-1')
  })

  it('never renders the word Error alone as a heading', () => {
    for (const status of [401, 403, 404, 409, 422, 500, 503, 599] as const) {
      expect(mapDecisionError({ status, projectKey }).heading.trim()).not.toBe('Error')
    }
  })
})

describe('mapVerifyError', () => {
  it('distinguishes 403, 409 and 410, which mean three different things', () => {
    expect(mapVerifyError({ status: 403 }).heading).toContain(
      'may be read by the caller who made the decision',
    )
    expect(mapVerifyError({ status: 409 }).heading).toBe(
      'The decision is still being written. It cannot be verified yet.',
    )
    expect(mapVerifyError({ status: 410 }).heading).toBe(
      'The stored receipt failed and has no verdict to serve.',
    )
    expect(mapVerifyError({ status: 410 }).body).toContain('not a decision')
  })

  it('says an unverified decision is not evidence for everything else', () => {
    expect(mapVerifyError({ status: 404 }).body).toBe('An unverified decision is not evidence.')
    expect(mapVerifyError({ status: 503 }).heading).toBe(
      'The stored receipt could not be read, so this decision is unverified.',
    )
  })
})
