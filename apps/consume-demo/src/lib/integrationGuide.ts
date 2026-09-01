import { casePath, joinUrl, lightCasePath, policiesPath } from './requestBody'

export interface IntegrationTarget {
  baseUrl: string
  projectKey: string
}

const SCENARIO = 'Describe the situation your system needs governed.'

function targetUrl(target: IntegrationTarget, path: string): string {
  return joinUrl(target.baseUrl || 'https://policy.example.com', path)
}

function rawHttpTarget(target: IntegrationTarget, path: string): string {
  try {
    const url = new URL(targetUrl(target, path))
    return `${url.pathname}${url.search}`
  } catch {
    return path
  }
}

export function buildIntegrationCurl(target: IntegrationTarget): string {
  const key = target.projectKey || '{project_key}'
  return [
    '# Decision JSON: retrieval + reasoning + explanation + stored receipt',
    `curl -sS -X POST "${targetUrl(target, casePath(key))}" \\`,
    '  -H "X-Policy-Subscription-Key: $POLICY_SUBSCRIPTION_KEY" \\',
    '  -H "Content-Type: application/json" \\',
    '  -H "X-Correlation-Id: $(uuidgen)" \\',
    '  -H "Idempotency-Key: $(uuidgen)" \\',
    `  -d '{"scenario":"${SCENARIO}","reasoning_effort":"medium","calling_system_identity":"my-agent"}'`,
    '',
    '# Decision Light: the same stored decision, compact fixed-schema response',
    `curl -sS -X POST "${targetUrl(target, lightCasePath(key))}" \\`,
    '  -H "X-Policy-Subscription-Key: $POLICY_SUBSCRIPTION_KEY" \\',
    '  -H "Content-Type: application/json" \\',
    '  -H "X-Correlation-Id: $(uuidgen)" \\',
    '  -H "Idempotency-Key: $(uuidgen)" \\',
    `  -d '{"scenario":"${SCENARIO}","reasoning_effort":"medium","calling_system_identity":"my-agent"}'`,
    '',
    '# Policy JSON: precision-ranked policy records, without a verdict or receipt',
    `curl -sS -X POST "${targetUrl(target, policiesPath(key))}" \\`,
    '  -H "X-Policy-Subscription-Key: $POLICY_SUBSCRIPTION_KEY" \\',
    '  -H "Content-Type: application/json" \\',
    '  -H "X-Correlation-Id: $(uuidgen)" \\',
    `  -d '{"scenario":"${SCENARIO}"}'`,
  ].join('\n')
}

export function buildIntegrationPython(target: IntegrationTarget): string {
  const base = target.baseUrl.replace(/\/+$/, '') || 'https://policy.example.com'
  const key = target.projectKey || '{project_key}'
  return [
    'import os',
    'import uuid',
    '',
    'import requests',
    '',
    `BASE = "${base}"`,
    `PROJECT_KEY = "${key}"`,
    'HEADERS = {',
    '    "X-Policy-Subscription-Key": os.environ["POLICY_SUBSCRIPTION_KEY"],',
    '    "Content-Type": "application/json",',
    '    "X-Correlation-Id": str(uuid.uuid4()),',
    '}',
    `SCENARIO = "${SCENARIO}"`,
    '',
    '# Option 1: governed decision receipt',
    'decision_headers = {**HEADERS, "Idempotency-Key": str(uuid.uuid4())}',
    'decision = requests.post(',
    '    f"{BASE}/api/policy-decisions/{PROJECT_KEY}/case",',
    '    headers=decision_headers,',
    '    json={',
    '        "scenario": SCENARIO,',
    '        "reasoning_effort": "medium",',
    '        "calling_system_identity": "my-agent",',
    '    },',
    '    timeout=120,',
    ')',
    'decision.raise_for_status()',
    'receipt = decision.json()',
    '',
    '# Option 2: the same stored decision, compact fixed-schema response',
    'light = requests.post(',
    '    f"{BASE}/api/policy-decisions/{PROJECT_KEY}/case/light",',
    '    headers={**HEADERS, "Idempotency-Key": str(uuid.uuid4())},',
    '    json={',
    '        "scenario": SCENARIO,',
    '        "reasoning_effort": "medium",',
    '        "calling_system_identity": "my-agent",',
    '    },',
    '    timeout=120,',
    ')',
    'light.raise_for_status()',
    'compact_decision = light.json()',
    '',
    '# Option 3: filtered policy records only',
    'selection = requests.post(',
    '    f"{BASE}/api/policy-decisions/{PROJECT_KEY}/policies",',
    '    headers=HEADERS,',
    '    json={"scenario": SCENARIO},',
    '    timeout=120,',
    ')',
    'selection.raise_for_status()',
    'policies = selection.json()["policies"]',
  ].join('\n')
}

export function buildIntegrationHttp(target: IntegrationTarget): string {
  const key = target.projectKey || '{project_key}'
  const host = (() => {
    try {
      return new URL(target.baseUrl).host
    } catch {
      return 'policy.example.com'
    }
  })()
  return [
    `POST ${rawHttpTarget(target, casePath(key))} HTTP/1.1`,
    `Host: ${host}`,
    'X-Policy-Subscription-Key: ${POLICY_SUBSCRIPTION_KEY}',
    'Content-Type: application/json',
    'X-Correlation-Id: <uuid>',
    'Idempotency-Key: <uuid>',
    '',
    `{"scenario":"${SCENARIO}","reasoning_effort":"medium","calling_system_identity":"my-agent"}`,
    '',
    '---',
    '',
    `POST ${rawHttpTarget(target, lightCasePath(key))} HTTP/1.1`,
    `Host: ${host}`,
    'X-Policy-Subscription-Key: ${POLICY_SUBSCRIPTION_KEY}',
    'Content-Type: application/json',
    'X-Correlation-Id: <uuid>',
    'Idempotency-Key: <uuid>',
    '',
    `{"scenario":"${SCENARIO}","reasoning_effort":"medium","calling_system_identity":"my-agent"}`,
    '',
    '---',
    '',
    `POST ${rawHttpTarget(target, policiesPath(key))} HTTP/1.1`,
    `Host: ${host}`,
    'X-Policy-Subscription-Key: ${POLICY_SUBSCRIPTION_KEY}',
    'Content-Type: application/json',
    'X-Correlation-Id: <uuid>',
    '',
    `{"scenario":"${SCENARIO}"}`,
  ].join('\n')
}
