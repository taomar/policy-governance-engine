import { describe, expect, it } from 'vitest'

import {
  buildIntegrationCurl,
  buildIntegrationHttp,
  buildIntegrationPython,
} from './integrationGuide'

const target = {
  baseUrl: 'https://policy.example.com/gateway',
  projectKey: 'employee-policy',
}

describe('integration guide examples', () => {
  it.each([
    ['cURL', buildIntegrationCurl],
    ['Python', buildIntegrationPython],
    ['Raw HTTP', buildIntegrationHttp],
  ])('%s teaches both response modes without carrying a credential', (_name, build) => {
    const text = build(target)

    expect(text).toContain('/api/policy-decisions/')
    expect(text).toContain('/case')
    expect(text).toContain('/case/light')
    expect(text).toContain('/policies')
    expect(text).toContain('employee-policy')
    expect(text).toContain('POLICY_SUBSCRIPTION_KEY')
    expect(text).not.toContain('a-configured-pre-shared-key')
    expect(text).not.toMatch(/X-Policy-Subscription-Key:\s+[A-Za-z0-9_-]{20,}/)
  })

  it('keeps idempotency on decision operations only', () => {
    const text = buildIntegrationHttp(target)
    const [decision, light, policies] = text.split('---')

    expect(decision).toContain('Idempotency-Key')
    expect(light).toContain('Idempotency-Key')
    expect(policies).not.toContain('Idempotency-Key')
  })

  it('preserves a gateway path in raw HTTP request targets', () => {
    const text = buildIntegrationHttp(target)
    const requestLines = text.split('\n').filter((line) => line.startsWith('POST '))

    expect(requestLines).toEqual([
      'POST /gateway/api/policy-decisions/employee-policy/case HTTP/1.1',
      'POST /gateway/api/policy-decisions/employee-policy/case/light HTTP/1.1',
      'POST /gateway/api/policy-decisions/employee-policy/policies HTTP/1.1',
    ])
  })
})
