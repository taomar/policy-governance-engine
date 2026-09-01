// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import {
  makeEnvelope,
  makeDuplicateCollapsedEnvelope,
  makeFabricatedCitationV2Envelope,
  makeInformationOnlyEnvelope,
  makeLanguageDroppedGuidanceEnvelope,
  makeLanguageIdentityEnvelope,
  makeLanguageRenderedEnvelope,
  makeMixedBlockedEnvelope,
  makeNonAnsweredEnvelope,
  makeNoRuleBearsV2Envelope,
  makeNotEvaluatedV2Envelope,
  makeProjectionNotReadyEnvelope,
  makeQualifiedVerdictEnvelope,
  makeRuleIndexDegradedEnvelope,
  makeRuleIndexMatchedEnvelope,
  makeRuleSlicedEnvelope,
  makeUnnamedDuplicateEnvelope,
  makeV2Envelope,
  makeVerdictOnlyEnvelope,
  V2_MISSING_INFORMATION,
  V2_VERIFICATION_REQUIREMENTS,
} from './lib/testFixtures'
import {
  DECISION_LIGHT_SCHEMA_VERSION,
  DECISION_STATUSES,
  POLICY_RETRIEVAL_SCHEMA_VERSION,
  type CaseDecisionEnvelope,
  type CaseDecisionReceipt,
} from './contracts/caseDecision'

/**
 * The behavioural guarantees, asserted against the rendered page.
 *
 * These are the claims the page makes that a reader cannot check for
 * themselves: that no verdict appears without its status, that the SUBSCRIPTION_KEY never
 * reaches storage or a preview, that the receipt is rendered from the response
 * rather than from what the form remembers. Each is worth a test because each
 * one fails silently -- nothing on screen looks wrong when a verdict is shown
 * for a status that carries none.
 */

const SUBSCRIPTION_KEY = 'demo-subscription-key-0123456789abcdef'

function jsonResponse(body: unknown, init: { status?: number; headers?: Record<string, string> } = {}) {
  return {
    ok: (init.status ?? 200) < 400,
    status: init.status ?? 200,
    headers: { get: (name: string) => init.headers?.[name] ?? null },
    json: async () => body,
  } as unknown as Response
}

interface FetchLog {
  url: string
  init?: RequestInit
}

function installFetch(
  handler: (url: string, init?: RequestInit) => Response | Promise<Response>,
): FetchLog[] {
  const calls: FetchLog[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : String(input)
      calls.push({ url, init })
      return handler(url, init)
    }),
  )
  return calls
}

/** The happy path: project resolves, then the case is answered. */
function standardHandler(envelope: CaseDecisionReceipt = makeEnvelope()) {
  return (url: string) => {
    if (url.includes('/active-version')) {
      return jsonResponse({ id: '5f2c1a4e-3b6d-4c8f-9a2e-7d1b0c3e9b31', version_number: 7 })
    }
    if (url.includes('/api/policy-sets/')) {
      return jsonResponse({
        id: 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
        key: 'demo-project',
        name: 'Supplier Onboarding Policy',
      })
    }
    return jsonResponse(envelope, { headers: { 'X-Correlation-Id': envelope.correlation_id } })
  }
}

async function fillAndSubmit(options: { guidance?: string; SUBSCRIPTION_KEY?: string } = {}) {
  fireEvent.change(screen.getByTestId('playground-project-key'), {
    target: { value: 'demo-project' },
  })
  fireEvent.change(screen.getByTestId('playground-subscription-key'), {
    target: { value: options.SUBSCRIPTION_KEY ?? SUBSCRIPTION_KEY },
  })
  fireEvent.change(screen.getByTestId('playground-scenario'), {
    target: { value: 'A supplier in a sanctioned jurisdiction asks about 90-day payment terms.' },
  })
  if (options.guidance !== undefined) {
    fireEvent.change(screen.getByTestId('playground-additional-instructions'), {
      target: { value: options.guidance },
    })
  }

  await waitFor(() => expect((screen.getByTestId('playground-submit') as HTMLButtonElement).disabled).toBe(false), {
    timeout: 3000,
  })
  fireEvent.click(screen.getByTestId('playground-submit'))
  await screen.findByTestId('playground-receipt', {}, { timeout: 3000 })
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  Object.assign(navigator, { clipboard: { writeText: vi.fn(async () => undefined) } })
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
  localStorage.clear()
  sessionStorage.clear()
})

describe('the request inspector, before anything is submitted', () => {
  it('is present on first load, and the result grid is not', () => {
    installFetch(standardHandler())
    render(<App />)
    expect(screen.getByTestId('playground-request-inspector')).toBeTruthy()
    expect(screen.queryByTestId('playground-result-grid')).toBeNull()
  })

  it('shows request, response, guidance and raw HTTP sections', () => {
    installFetch(standardHandler())
    render(<App />)
    expect(screen.getByTestId('inspector-tab-json')).toBeTruthy()
    expect(screen.getByTestId('inspector-tab-response')).toBeTruthy()
    expect(screen.getByTestId('inspector-response-empty').textContent).toContain('No response yet')
    expect(screen.getByTestId('inspector-tab-guidance')).toBeTruthy()
    expect(screen.getByTestId('inspector-tab-http')).toBeTruthy()
  })

  it('previews the body live, with no submit', () => {
    installFetch(standardHandler())
    render(<App />)
    fireEvent.change(screen.getByTestId('playground-scenario'), {
      target: { value: 'a distinctive scenario string' },
    })
    expect(screen.getByTestId('inspector-tab-json').textContent).toContain(
      'a distinctive scenario string',
    )
  })

  it('switches to a retrieval-only request with no decision-only fields', () => {
    installFetch(standardHandler())
    render(<App />)

    fireEvent.click(screen.getByRole('radio', { name: /Policy JSON/ }))
    fireEvent.change(screen.getByTestId('playground-scenario'), {
      target: { value: '  show the policies governing annual leave  ' },
    })

    const json = screen.getByTestId('inspector-tab-json').textContent ?? ''
    const http = screen.getByTestId('inspector-tab-http').textContent ?? ''
    expect(json).toContain('show the policies governing annual leave')
    expect(json).not.toContain('reasoning_effort')
    expect(json).not.toContain('calling_system_identity')
    expect(json).not.toContain('additional_instructions')
    expect(http).toContain('/api/policy-decisions/{project_key}/policies')
    expect(http).not.toContain('Idempotency-Key')
    expect(screen.queryByTestId('playground-reasoning-effort')).toBeNull()
    expect(screen.queryByTestId('playground-additional-instructions')).toBeNull()
    expect(screen.getByTestId('playground-light-mode-note')).toBeTruthy()
  })

  it('opens an integration guide with agent, curl, Python, and REST examples for both modes', async () => {
    installFetch(standardHandler())
    render(<App />)

    fireEvent.click(screen.getByTestId('playground-integration-guide-button'))
    const guide = screen.getByTestId('playground-integration-guide')
    await waitFor(() =>
      expect(document.activeElement).toBe(
        within(guide).getByRole('button', { name: 'Close integration guide' }),
      ),
    )
    expect(guide.textContent).toContain('/api/policy-decisions/{project_key}/case')
    expect(guide.textContent).toContain('/api/policy-decisions/{project_key}/case/light')
    expect(guide.textContent).toContain('/api/policy-decisions/{project_key}/policies')
    expect(within(guide).getByRole('tab', { name: 'Agents & Copilot' })).toBeTruthy()

    fireEvent.click(within(guide).getByRole('tab', { name: 'cURL' }))
    expect(guide.textContent).toContain('POLICY_SUBSCRIPTION_KEY')
    const copy = within(guide).getByRole('button', {
      name: 'Copy the cURL integration examples',
    })
    copy.focus()
    fireEvent.click(copy)
    await waitFor(() => expect(document.activeElement).toBe(copy))
    fireEvent.click(within(guide).getByRole('tab', { name: 'Python' }))
    expect(guide.textContent).toContain('requests.post')
    fireEvent.click(within(guide).getByRole('tab', { name: 'REST & OpenAPI' }))
    expect(guide.textContent).toContain('POST /api/policy-decisions/')
  })

  describe('policy JSON mode', () => {
    it('returns filtered policy records without rendering a decision receipt', async () => {
      const response = {
        schema_version: POLICY_RETRIEVAL_SCHEMA_VERSION,
        correlation_id: 'policy-correlation',
        policy_set: { id: 'set-1', key: 'demo-project', name: 'Demo project' },
        active_version: { version_id: 'version-1', version_number: 7 },
        query: { scenario: 'show annual leave policies', scenario_hash: 'a'.repeat(64) },
        retrieval: {
          status: 'narrowed',
          method: 'hybrid_policy_rule_rrf_v1',
          policies_considered: 3,
          policies_retained: 1,
          policies_discarded: 2,
        },
        policies: [
          {
            policy: {
              provision_id: 'provision-1',
              provision_key: 'annual-leave',
              heading_path: ['Leave', 'Annual leave'],
            },
            match: { best_rank: 0, best_score: 0.91 },
            payload: {
              projection: 'grounding_projection_v1',
              rules: [{ rule_id: 'rule-annual-leave' }],
            },
          },
        ],
        size: { combined_chars: 1200, budget_chars: 200000, oversize: false },
        language: {
          source_language: 'en',
          processing_language: 'en',
          response_language: 'en',
          boundary_state: 'identity',
          output_rendering_state: 'not_required',
          guidance_rendering_state: 'not_required',
          input_translation_profile: 'case-language-v4',
          processing_scenario: 'show annual leave policies',
          processing_scenario_hash: 'b'.repeat(64),
        },
      }
      const calls = installFetch((url) => {
        if (url.includes('/active-version')) {
          return jsonResponse({ id: 'version-1', version_number: 7 })
        }
        if (url.includes('/api/policy-sets/')) {
          return jsonResponse({ id: 'set-1', key: 'demo-project', name: 'Demo project' })
        }
        return jsonResponse(response, { headers: { 'X-Correlation-Id': 'policy-correlation' } })
      })

      render(<App />)

      fireEvent.click(screen.getByRole('radio', { name: /Policy JSON/ }))
      fireEvent.change(screen.getByTestId('playground-project-key'), {
        target: { value: 'demo-project' },
      })
      fireEvent.change(screen.getByTestId('playground-subscription-key'), {
        target: { value: SUBSCRIPTION_KEY },
      })
      fireEvent.change(screen.getByTestId('playground-scenario'), {
        target: { value: 'show annual leave policies' },
      })
      await waitFor(() =>
        expect((screen.getByTestId('playground-submit') as HTMLButtonElement).disabled).toBe(false),
      )
      fireEvent.click(screen.getByTestId('playground-submit'))

      expect(await screen.findByTestId('playground-policy-result')).toBeTruthy()
      await waitFor(() =>
        expect(document.activeElement).toBe(
          screen.getByRole('heading', { name: 'Filtered policy JSON' }),
        ),
      )
      expect(screen.getByTestId('playground-policy-json').textContent).toContain(
        'rule-annual-leave',
      )
      expect(screen.queryByTestId('playground-receipt')).toBeNull()
      expect(screen.queryByTestId('playground-verdict-panel')).toBeNull()

      const sent = calls.find((call) => call.url.endsWith('/api/policy-decisions/demo-project/policies'))
      expect(sent).toBeTruthy()
      expect(JSON.parse(String(sent?.init?.body))).toEqual({
        scenario: 'show annual leave policies',
      })
      expect((sent?.init?.headers as Record<string, string>)['Idempotency-Key']).toBeUndefined()
    })
  })

  describe('Decision Light mode', () => {
    it('returns compact structured decision JSON and keeps the full receipt behind its URL', async () => {
      const response = {
        schema_version: DECISION_LIGHT_SCHEMA_VERSION,
        response_type: 'decision',
        decision_id: 'decision-light-1',
        correlation_id: 'correlation-light-1',
        idempotency_key: 'one-call-key',
        policy_set: { id: 'set-1', key: 'demo-project', name: 'Demo project' },
        active_version: { version_id: 'version-1', version_number: 7 },
        request: { scenario: 'Is this allowed?', scenario_hash: 'a'.repeat(64) },
        asked: {
          information_requested: false,
          verdict_requested: true,
          classifier_version: 'ai-case-needs-v2',
        },
        outcome: { information: 'not_requested', verdict: 'answered' },
        information: null,
        verdict: {
          status: 'answered',
          reached: true,
          decision: 'allowed',
          explanation: 'The cited policy allows the request.',
          missing_information: [],
          verification_requirements: [
            {
              fact: 'recorded-balance',
              label: 'Recorded balance',
              why_needed: 'Confirm before acting.',
              required_by_rule_ids: ['R-ONE'],
            },
          ],
          note: '',
        },
        retrieval: { status: 'narrowed' },
        policies: [
          {
            provision_id: 'provision-1',
            provision_key: 'annual-leave',
            heading_path: ['Annual leave'],
          },
        ],
        citations: [
          {
            rule_id: 'R-ONE',
            policy: {
              provision_id: 'provision-1',
              provision_key: 'annual-leave',
              heading_path: ['Annual leave'],
            },
            source: {
              state: 'quoted',
              text: 'The policy allows the request.',
              page: 4,
              section: 'Annual leave',
            },
            serves: ['verdict'],
          },
        ],
        trace: {
          classifier_version: 'ai-case-needs-v2',
          prompt_version: 'ai-case-intent-v12',
          plan_profile: 'case-plan-v3',
          selector_catalogue_version: 'case-selectors-v1',
          model_deployment: 'reasoning-model',
          token_usage: {
            calls: 5,
            calls_without_usage: 1,
            prompt_tokens: 100,
            completion_tokens: 23,
            total_tokens: 123,
            reasoning_tokens: 9,
          },
        },
        decision_hash: 'b'.repeat(64),
        hash_basis: 'case_decision_v2_lang_verification',
        receipt_url: '/api/policy-decisions/decision-light-1',
        latency_ms: 1840,
      }
      const calls = installFetch((url) => {
        if (url.includes('/active-version')) {
          return jsonResponse({ id: 'version-1', version_number: 7 })
        }
        if (url.includes('/api/policy-sets/')) {
          return jsonResponse({ id: 'set-1', key: 'demo-project', name: 'Demo project' })
        }
        return jsonResponse(response, { headers: { 'X-Correlation-Id': 'correlation-light-1' } })
      })
      render(<App />)

      fireEvent.click(screen.getByRole('radio', { name: /Decision Light/ }))
      fireEvent.change(screen.getByTestId('playground-project-key'), {
        target: { value: 'demo-project' },
      })
      fireEvent.change(screen.getByTestId('playground-subscription-key'), {
        target: { value: SUBSCRIPTION_KEY },
      })
      fireEvent.change(screen.getByTestId('playground-scenario'), {
        target: { value: 'Is this request allowed under the annual leave policy?' },
      })
      await waitFor(() =>
        expect((screen.getByTestId('playground-submit') as HTMLButtonElement).disabled).toBe(false),
      )
      fireEvent.click(screen.getByTestId('playground-submit'))

      expect(await screen.findByTestId('playground-light-decision-result')).toBeTruthy()
      expect(screen.getByTestId('playground-light-decision-json').textContent).toContain(
        'recorded-balance',
      )
      expect(screen.getByTestId('playground-verdict').textContent).toContain('allowed')
      expect(screen.getByTestId('playground-verification-requirements')).toBeTruthy()
      expect(screen.getByTestId('evidence-count').textContent).toContain('1 rule')
      expect(screen.getByTestId('playground-token-total').textContent).toBe('At least 123')
      expect(screen.getByTestId('playground-run-meter').textContent).toContain(
        '1 call did not report usage',
      )
      expect(screen.getByTestId('playground-light-verdict-outcome').textContent).toContain(
        'Answered',
      )
      expect(screen.queryByTestId('playground-receipt')).toBeNull()
      const sent = calls.find((call) =>
        call.url.endsWith('/api/policy-decisions/demo-project/case/light'),
      )
      expect(sent).toBeTruthy()
      expect(String(sent?.init?.body)).toContain('reasoning_effort')
    })
  })

  it('omits additional_instructions entirely when guidance is empty', () => {
    installFetch(standardHandler())
    render(<App />)
    fireEvent.change(screen.getByTestId('playground-scenario'), { target: { value: 'hello there' } })

    const text = screen.getByTestId('inspector-tab-json').textContent ?? ''
    // Strip the line-number gutter before parsing.
    const body = text.slice(text.indexOf('{'), text.lastIndexOf('}') + 1).replace(/^\s*\d+/gm, '')
    expect(body).not.toContain('additional_instructions')
  })

  it('omits it for whitespace-only guidance too', () => {
    installFetch(standardHandler())
    render(<App />)
    fireEvent.change(screen.getByTestId('playground-scenario'), { target: { value: 'hello there' } })
    fireEvent.change(screen.getByTestId('playground-additional-instructions'), {
      target: { value: '    ' },
    })
    expect(screen.getByTestId('inspector-tab-json').textContent).not.toContain(
      'additional_instructions',
    )
  })

  it('shows the subscription key in the Raw HTTP header, as it will be sent', () => {
    installFetch(standardHandler())
    render(<App />)

    fireEvent.change(screen.getByTestId('playground-subscription-key'), {
      target: { value: SUBSCRIPTION_KEY },
    })
    const http = screen.getByTestId('inspector-tab-http').textContent ?? ''

    expect(http).toContain(`X-Policy-Subscription-Key: ${SUBSCRIPTION_KEY}`)
    // The credential this page no longer sends must not appear at all: a stray
    // `Authorization` line would tell a reader to configure the wrong thing.
    expect(http).not.toContain('Authorization:')
  })

  it('renders a placeholder rather than an empty header before a key is entered', () => {
    installFetch(standardHandler())
    render(<App />)

    const http = screen.getByTestId('inspector-tab-http').textContent ?? ''

    expect(http).toContain('X-Policy-Subscription-Key: <your subscription key>')
    // `X-Policy-Subscription-Key:` with nothing after it is a valid-looking
    // line, and a reader comparing it against a 401 would go looking for a
    // server fault rather than for the field they have not filled in.
    expect(http).not.toMatch(/X-Policy-Subscription-Key:\s*$/m)
  })

  it('never renders the subscription key in the JSON body', () => {
    installFetch(standardHandler())
    render(<App />)
    fireEvent.change(screen.getByTestId('playground-subscription-key'), {
      target: { value: SUBSCRIPTION_KEY },
    })
    fireEvent.change(screen.getByTestId('playground-scenario'), { target: { value: 'hello there' } })

    // The Raw HTTP tab shows it on purpose. The body must not: a credential in
    // a request body would be sealed into the receipt's request hash and
    // stored on the server in clear.
    const json = screen.getByTestId('inspector-tab-json').textContent ?? ''
    for (let i = 0; i + 8 <= SUBSCRIPTION_KEY.length; i += 1) {
      expect(json).not.toContain(SUBSCRIPTION_KEY.slice(i, i + 8))
    }
  })

  it('keeps correlation and idempotency out of the body and in the headers', () => {
    installFetch(standardHandler())
    render(<App />)
    fireEvent.change(screen.getByTestId('playground-scenario'), { target: { value: 'hello there' } })

    expect(screen.getByTestId('inspector-tab-json').textContent).not.toContain('correlation_id')
    expect(screen.getByTestId('inspector-tab-http').textContent).toContain('X-Correlation-Id:')
    // No key set yet, so no header line.
    expect(screen.getByTestId('inspector-tab-http').textContent).not.toContain('Idempotency-Key:')

    fireEvent.change(screen.getByTestId('playground-idempotency-key'), { target: { value: 'k-1' } })
    expect(screen.getByTestId('inspector-tab-http').textContent).toContain('Idempotency-Key: k-1')
  })

  it('rotates the request hash when only the guidance changes, and restores it', () => {
    installFetch(standardHandler())
    render(<App />)
    fireEvent.change(screen.getByTestId('playground-scenario'), { target: { value: 'hello there' } })

    const original = screen.getByTestId('inspector-request-hash').textContent
    fireEvent.change(screen.getByTestId('playground-additional-instructions'), {
      target: { value: 'Explain the approval path first' },
    })
    const changed = screen.getByTestId('inspector-request-hash').textContent
    expect(changed).not.toBe(original)

    fireEvent.change(screen.getByTestId('playground-additional-instructions'), {
      target: { value: '' },
    })
    expect(screen.getByTestId('inspector-request-hash').textContent).toBe(original)
  })

  it('renders the two guidance registers as separate, non-nested sections', () => {
    installFetch(standardHandler())
    render(<App />)
    const editable = screen.getByTestId('inspector-guidance-editable')
    const server = screen.getByTestId('inspector-guidance-server')
    expect(editable.contains(server)).toBe(false)
    expect(server.contains(editable)).toBe(false)
  })

  it('puts no control of any kind in the server instruction register', () => {
    installFetch(standardHandler())
    render(<App />)
    const server = screen.getByTestId('inspector-guidance-server')
    expect(server.querySelectorAll('input, textarea, select, [contenteditable]')).toHaveLength(0)
    // Not even a disabled one: a disabled field implies a lock, and a lock
    // implies a key.
    expect(server.querySelectorAll('[aria-disabled="true"]')).toHaveLength(0)
  })

  it('states that the server prompt is not exposed, without dumping it', () => {
    installFetch(standardHandler())
    render(<App />)
    const server = screen.getByTestId('inspector-guidance-server')
    expect(server.textContent).toContain('They are not exposed here and cannot be sent, replaced, or disabled by a caller.')
    expect((server.textContent ?? '').length).toBeLessThan(1200)
  })

  it('carries the guidance helper sentence verbatim', () => {
    installFetch(standardHandler())
    render(<App />)
    expect(screen.getByTestId('playground-guidance-helper').textContent).toBe(
      'Shapes explanation focus or format. It cannot override published policy, retrieval, decision status, or citation requirements.',
    )
  })

  it('offers exactly the two hardcoded examples and suggests no override', () => {
    installFetch(standardHandler())
    render(<App />)
    const chips = screen.getAllByTestId('playground-guidance-example')
    expect(chips.map((chip) => chip.textContent)).toEqual([
      'Explain the approval path first',
      'Use concise language for a service agent',
    ])

    // The forbidden set is checked against the guidance affordances -- the
    // examples, the field's helper and its placeholder -- because that is where
    // a suggestion to override policy would actually be a suggestion. It is
    // deliberately not checked against the whole page: honest prose such as
    // "the value you are about to send" contains "you are a" and rewriting it
    // to satisfy a substring check would make the page worse, not safer.
    const guidanceSurface = [
      ...chips.map((chip) => chip.textContent ?? ''),
      screen.getByTestId('playground-guidance-helper').textContent ?? '',
      screen.getByTestId('playground-additional-instructions').getAttribute('placeholder') ?? '',
      screen.getByTestId('inspector-tab-guidance').textContent ?? '',
    ]
      .join(' ')
      .toLowerCase()

    for (const forbidden of [
      'ignore policy',
      'ignore the rules',
      'override the',
      'bypass',
      'disregard',
      'pretend',
      'act as',
      'you are a',
    ]) {
      expect(guidanceSurface).not.toContain(forbidden)
    }
  })

  it('inserts an example into the textarea and returns focus to it', () => {
    installFetch(standardHandler())
    render(<App />)
    fireEvent.click(screen.getAllByTestId('playground-guidance-example')[0])
    const field = screen.getByTestId('playground-additional-instructions') as HTMLTextAreaElement
    expect(field.value).toBe('Explain the approval path first')
  })

  it('caps guidance at 2000 characters', () => {
    installFetch(standardHandler())
    render(<App />)
    const field = screen.getByTestId('playground-additional-instructions') as HTMLTextAreaElement
    expect(field.getAttribute('maxLength')).toBe('2000')
    fireEvent.change(field, { target: { value: 'x'.repeat(2100) } })
    expect(field.value).toHaveLength(2000)
    expect(screen.getByTestId('playground-guidance-counter').textContent).toBe('2000 / 2000')
  })

  it('moves the counter through its warning and danger thresholds', () => {
    installFetch(standardHandler())
    render(<App />)
    const field = screen.getByTestId('playground-additional-instructions')
    const counter = () => screen.getByTestId('playground-guidance-counter')

    fireEvent.change(field, { target: { value: 'x'.repeat(1899) } })
    expect(counter().className).toBe('counter')
    fireEvent.change(field, { target: { value: 'x'.repeat(1900) } })
    expect(counter().className).toContain('counter--warning')
    fireEvent.change(field, { target: { value: 'x'.repeat(2000) } })
    expect(counter().className).toContain('counter--danger')
  })

  it('exposes the tab strip as a real tablist', () => {
    installFetch(standardHandler())
    render(<App />)
    expect(document.querySelector('[role="tablist"]')).toBeTruthy()
    expect(document.getElementById('inspector-tab-json')?.getAttribute('role')).toBe('tab')
  })
})

describe('the docket', () => {
  it('holds the subscription key in a visible text field with autocomplete off', () => {
    installFetch(standardHandler())
    render(<App />)
    const field = screen.getByTestId('playground-subscription-key')
    // Visible on purpose. This is a local demonstration of an operator-generated
    // key, and a credential nobody can read is a credential nobody can check
    // against the 401 they just got. Autocomplete stays off: the browser's
    // password manager has no business storing a shared system credential.
    expect(field.getAttribute('type')).toBe('text')
    expect(field.getAttribute('autocomplete')).toBe('off')
  })

  it('says beside the field that this is a local demo key, in one line', () => {
    installFetch(standardHandler())
    render(<App />)

    // One line beside the control, carrying the three facts that matter while
    // someone is typing a credential: what kind of key, which header, how long
    // it is kept. The paragraph about production clients and VITE_ inlining is
    // real and is kept verbatim, but a connection bar is not where it is read.
    expect(screen.getByTestId('playground-subscription-key-caption').textContent).toBe(
      'Local demo key · sent as X-Policy-Subscription-Key · held only for this tab.',
    )
    expect(
      screen.getByTestId('playground-subscription-key').getAttribute('aria-describedby'),
    ).toBe('pg-subscription-key-caption')
  })

  it('keeps the production and VITE_ warning verbatim, one click away', () => {
    installFetch(standardHandler())
    render(<App />)

    const toggle = screen.getByTestId('playground-key-note-toggle')
    expect(toggle.getAttribute('aria-expanded')).toBe('false')

    const note = screen.getByTestId('playground-subscription-key-warning')
    // Present in the document and unedited, so nothing the page claimed about
    // this credential was quietly dropped when it left the first viewport.
    expect(note.textContent).toContain('Local demonstration only')
    expect(note.textContent).toContain(
      'production browser client must never hold a shared subscription key',
    )
    // Not shown until asked for.
    expect(note.closest('[hidden]')).toBeTruthy()

    fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    expect(
      screen.getByTestId('playground-subscription-key-warning').closest('[hidden]'),
    ).toBeNull()
  })

  it('starts with an empty key and no prefill note when no local variable is set', () => {
    installFetch(standardHandler())
    render(<App />)

    // The committed default. `vitest.config.ts` pins the VITE variable empty so
    // this asserts the shipped behaviour rather than whatever the machine
    // running the suite happens to have in `.env.local`.
    expect((screen.getByTestId('playground-subscription-key') as HTMLInputElement).value).toBe('')
    expect(screen.queryByTestId('playground-subscription-key-prefilled')).toBeNull()
  })

  it('shows the exact project-key helper sentence', () => {
    installFetch(standardHandler())
    render(<App />)
    expect(screen.getByTestId('playground-key-helper').textContent).toBe(
      'Stable key used in API paths—not display name or UUID',
    )
  })

  it('shows a correlation id before submit and sends that exact value', async () => {
    const calls = installFetch(standardHandler())
    render(<App />)

    const before = screen.getByTestId('playground-correlation').textContent ?? ''
    expect(before).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    )

    await fillAndSubmit()

    const post = calls.find((call) => call.init?.method === 'POST')
    const headers = post?.init?.headers as Record<string, string>
    expect(headers['X-Correlation-Id']).toBe(before)
    // And it rotates, so the value on screen is always the next request's.
    expect(screen.getByTestId('playground-correlation').textContent).not.toBe(before)
  })

  it('names the single blocking reason when submit is disabled', () => {
    installFetch(standardHandler())
    render(<App />)
    const submit = screen.getByTestId('playground-submit')
    expect(submit.getAttribute('aria-disabled')).toBe('true')
    // The configured base is already valid, so the first unmet condition is the
    // key. One reason is named, never a list -- a disabled control with four
    // reasons is a disabled control with none.
    expect(submit.getAttribute('title')).toBe('Enter the project key before sending.')

    fireEvent.change(screen.getByTestId('playground-base-url'), { target: { value: 'nonsense' } })
    expect(screen.getByTestId('playground-submit').getAttribute('title')).toBe(
      'Set a valid API base URL before sending.',
    )
  })

  it('rotates a successful request key so the next draft is independent', async () => {
    installFetch(standardHandler())
    render(<App />)
    fireEvent.change(screen.getByTestId('playground-idempotency-key'), { target: { value: 'k-1' } })
    await fillAndSubmit()

    expect(screen.queryByTestId('playground-idempotency-conflict')).toBeNull()
    expect((screen.getByTestId('playground-idempotency-key') as HTMLInputElement).value).not.toBe(
      'k-1',
    )

    fireEvent.change(screen.getByTestId('playground-additional-instructions'), {
      target: { value: 'now something different' },
    })

    expect(screen.queryByTestId('playground-idempotency-conflict')).toBeNull()
    expect(screen.queryByTestId('playground-receipt')).toBeNull()
    expect(screen.getByTestId('playground-submit').getAttribute('aria-disabled')).toBe('false')
  })

  it('removes the previous response as soon as the draft scenario changes', async () => {
    installFetch(standardHandler(makeV2Envelope()))
    render(<App />)
    await fillAndSubmit()

    expect(screen.getByTestId('playground-receipt')).toBeTruthy()
    expect(screen.getByTestId('playground-verdict-panel')).toBeTruthy()

    fireEvent.change(screen.getByTestId('playground-scenario'), {
      target: { value: 'A different draft asking about annual vacation entitlement.' },
    })

    expect(screen.queryByTestId('playground-receipt')).toBeNull()
    expect(screen.queryByTestId('playground-verdict-panel')).toBeNull()
    expect(screen.getByText(/No decision has been requested yet/i)).toBeTruthy()
    expect(screen.getByTestId('inspector-tab-json').textContent).toContain(
      'annual vacation entitlement',
    )
  })

  it('does not attach an in-flight response to a draft changed while it was running', async () => {
    let finish: ((response: Response) => void) | undefined
    installFetch((url) => {
      if (url.includes('/active-version')) {
        return jsonResponse({ id: 'version-1', version_number: 7 })
      }
      if (url.includes('/api/policy-sets/')) {
        return jsonResponse({ id: 'set-1', key: 'demo-project', name: 'Demo project' })
      }
      return new Promise<Response>((resolve) => {
        finish = resolve
      })
    })
    render(<App />)
    fireEvent.change(screen.getByTestId('playground-project-key'), {
      target: { value: 'demo-project' },
    })
    fireEvent.change(screen.getByTestId('playground-subscription-key'), {
      target: { value: SUBSCRIPTION_KEY },
    })
    fireEvent.change(screen.getByTestId('playground-scenario'), {
      target: { value: 'A question about sick leave entitlement.' },
    })
    await waitFor(() =>
      expect((screen.getByTestId('playground-submit') as HTMLButtonElement).disabled).toBe(false),
    )
    fireEvent.click(screen.getByTestId('playground-submit'))
    expect(screen.getByTestId('playground-wait')).toBeTruthy()

    fireEvent.change(screen.getByTestId('playground-scenario'), {
      target: { value: 'A new question about annual vacation entitlement.' },
    })
    finish?.(jsonResponse(makeV2Envelope()))

    await waitFor(() => expect(screen.queryByTestId('playground-wait')).toBeNull())
    expect(screen.queryByTestId('playground-receipt')).toBeNull()
    expect(screen.queryByTestId('playground-verdict-panel')).toBeNull()
    expect(screen.getByTestId('inspector-tab-json').textContent).toContain('annual vacation')
  })
})

describe('the request composer layout', () => {
  const follows = (first: HTMLElement, second: HTMLElement) =>
    Boolean(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING)

  it('puts the connection register above the case, and everything secondary after send', () => {
    installFetch(standardHandler())
    render(<App />)

    const connbar = screen.getByTestId('playground-connection-bar')
    const submit = screen.getByTestId('playground-submit')
    const advanced = screen.getByTestId('playground-advanced')
    const inspector = screen.getByTestId('playground-request-inspector')

    // Connection is what you configure once, so it rules the top.
    expect(follows(connbar, submit)).toBe(true)
    // Nothing secondary stands between a reader and the button they came for:
    // the metadata rail and the request preview are both after it in the order
    // a keyboard and a screen reader walk.
    expect(follows(submit, advanced)).toBe(true)
    expect(follows(submit, inspector)).toBe(true)
  })

  it('holds base, project key, subscription key and resolution in one register', () => {
    installFetch(standardHandler())
    render(<App />)
    const connbar = screen.getByTestId('playground-connection-bar')

    expect(within(connbar).getByTestId('playground-base-url')).toBeTruthy()
    expect(within(connbar).getByTestId('playground-project-key')).toBeTruthy()
    expect(within(connbar).getByTestId('playground-subscription-key')).toBeTruthy()
    expect(within(connbar).getByTestId('playground-resolution-idle')).toBeTruthy()
    // The credential is still shown in clear, with one line beside it. The
    // long-form warning is not in this register at all: it is in the rail.
    expect(within(connbar).getByTestId('playground-subscription-key-caption')).toBeTruthy()
    expect(within(connbar).queryByTestId('playground-subscription-key-warning')).toBeNull()
    expect(
      within(screen.getByTestId('playground-advanced')).getByTestId(
        'playground-subscription-key-warning',
      ),
    ).toBeTruthy()
  })

  it('reports the resolved project and its active version in that register', async () => {
    installFetch(standardHandler())
    render(<App />)

    fireEvent.change(screen.getByTestId('playground-project-key'), {
      target: { value: 'demo-project' },
    })
    fireEvent.change(screen.getByTestId('playground-subscription-key'), {
      target: { value: SUBSCRIPTION_KEY },
    })

    const connbar = screen.getByTestId('playground-connection-bar')
    await waitFor(() => expect(within(connbar).getByTestId('playground-identity')).toBeTruthy(), {
      timeout: 3000,
    })
    expect(within(connbar).getByTestId('playground-active-version').textContent).toBe('v7')
  })

  it('keeps the scenario, the reasoning control and send in one composer', () => {
    installFetch(standardHandler())
    render(<App />)

    const composer = screen.getByTestId('playground-submit').closest('.compose') as HTMLElement
    expect(composer).toBeTruthy()
    expect(within(composer).getByTestId('playground-scenario')).toBeTruthy()
    expect(within(composer).getByTestId('playground-reasoning-effort')).toBeTruthy()
    // The one sentence that says why the button is refusing, beside the button.
    expect(within(composer).getByTestId('playground-submit-reason')).toBeTruthy()
  })

  it('keeps every secondary field reachable in the metadata rail, not hidden', () => {
    installFetch(standardHandler())
    render(<App />)
    const advanced = screen.getByTestId('playground-advanced')

    for (const testId of [
      'playground-calling-system',
      'playground-idempotency-key',
      'playground-correlation',
      'playground-additional-instructions',
    ]) {
      const field = within(advanced).getByTestId(testId)
      // Secondary means "beside", not "behind a closed disclosure". Everything
      // that will be sent stays on the page and stays operable.
      expect(field.closest('[hidden]')).toBeNull()
    }
  })

  it('still sends on Ctrl+Enter from the metadata rail, not only from the case', async () => {
    const calls = installFetch(standardHandler())
    render(<App />)

    fireEvent.change(screen.getByTestId('playground-project-key'), {
      target: { value: 'demo-project' },
    })
    fireEvent.change(screen.getByTestId('playground-subscription-key'), {
      target: { value: SUBSCRIPTION_KEY },
    })
    fireEvent.change(screen.getByTestId('playground-scenario'), {
      target: { value: 'A supplier in a sanctioned jurisdiction asks about 90-day payment terms.' },
    })
    await waitFor(
      () =>
        expect((screen.getByTestId('playground-submit') as HTMLButtonElement).disabled).toBe(false),
      { timeout: 3000 },
    )

    // Splitting the docket into three regions must not split the shortcut: the
    // handler is on the form, so the guidance textarea in the rail still sends.
    fireEvent.keyDown(screen.getByTestId('playground-additional-instructions'), {
      key: 'Enter',
      ctrlKey: true,
    })

    await screen.findByTestId('playground-receipt', {}, { timeout: 3000 })
    expect(calls.some((call) => call.init?.method === 'POST')).toBe(true)
  })
})

describe('the result', () => {
  it('renders the full receipt immediately, with no further interaction', async () => {
    installFetch(standardHandler())
    render(<App />)
    await fillAndSubmit({ guidance: 'Explain the approval path first' })

    for (const id of [
      'receipt-decision-id',
      'receipt-project',
      'receipt-version',
      'receipt-correlation',
      'receipt-caller',
      'receipt-timestamp',
      'receipt-envelope',
      'receipt-decision-hash',
      'playground-result-grid',
      'playground-evidence-table',
      'playground-retrieval',
      'playground-raw-json',
    ]) {
      expect(screen.getByTestId(id)).toBeTruthy()
    }
  })

  it('moves the inspector below Rule evidence and exposes the full response JSON', async () => {
    const envelope = makeEnvelope()
    installFetch(standardHandler(envelope))
    render(<App />)
    await fillAndSubmit()

    const evidence = screen.getByTestId('playground-evidence-table')
    const inspector = screen.getByTestId('playground-request-inspector')
    const retrieval = screen.getByTestId('playground-retrieval')
    expect(evidence.compareDocumentPosition(inspector) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0)
    expect(inspector.compareDocumentPosition(retrieval) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(
      0,
    )

    const response = screen.getByTestId('inspector-tab-response').textContent ?? ''
    expect(response).toContain('case_decision_v1')
    expect(response).toContain(envelope.decision_id)
    expect(screen.queryByTestId('inspector-response-empty')).toBeNull()
  })

  it('puts the decision status before the verdict in document order', async () => {
    installFetch(standardHandler())
    render(<App />)
    await fillAndSubmit()

    const status = screen.getByTestId('playground-decision-status')
    const verdict = screen.getByTestId('playground-verdict')
    expect(status.compareDocumentPosition(verdict) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it.each(
    DECISION_STATUSES.filter((status) => status !== 'answered'),
  )('renders no verdict for %s', async (status) => {
    installFetch(standardHandler(makeNonAnsweredEnvelope(status)))
    render(<App />)
    await fillAndSubmit()

    expect(screen.queryByTestId('playground-verdict')).toBeNull()
    expect(screen.queryByTestId('playground-verdict-grid')).toBeNull()

    // The raw-envelope disclosure is excluded from this check on purpose: it
    // renders the response unmodified, and a page that stripped a field out of
    // the raw JSON to look tidier would be forging the evidence. Everywhere the
    // page speaks in its own voice, the verdict is absent.
    const raw = screen.getByTestId('playground-raw-json')
    const responseJson = screen.getByTestId('inspector-tab-response')
    const spoken = Array.from(document.body.querySelectorAll<HTMLElement>('section, .banner'))
      .filter(
        (node) =>
          !raw.contains(node) &&
          !node.contains(raw) &&
          !responseJson.contains(node) &&
          !node.contains(responseJson),
      )
      .map((node) => node.textContent ?? '')
      .join(' ')
    expect(spoken).not.toContain('THIS MUST NEVER BE RENDERED')

    expect(screen.getByTestId('playground-verdict-row').textContent).toContain(
      `Not reached — status is "${status}"`,
    )
  })

  it('lists missing facts as gold tags with an instruction', async () => {
    const envelope = makeNonAnsweredEnvelope('missing_required_facts')
    envelope.decision = { ...envelope.decision, missing_required_facts: ['contract_value'] }
    installFetch(standardHandler(envelope))
    render(<App />)
    await fillAndSubmit()

    const facts = screen.getByTestId('playground-missing-facts')
    expect(facts.textContent).toContain('contract_value')
    expect(screen.getByTestId('playground-result-grid').textContent).toContain(
      'Add these to your scenario and send again.',
    )
  })

  it('puts Decision status first and Decision hash last in the result grid', async () => {
    installFetch(standardHandler())
    render(<App />)
    await fillAndSubmit()

    const rows = Array.from(
      screen.getByTestId('playground-result-grid').querySelectorAll('.ledger__label'),
    ).map((node) => node.textContent)
    expect(rows[0]).toBe('Decision status')
    expect(rows[rows.length - 1]).toBe('Decision hash')
  })

  it('renders the receipt guidance from the response, never from local state', async () => {
    const envelope = makeEnvelope()
    envelope.request = { ...envelope.request, additional_instructions: 'SERVER-VALUE' }
    installFetch(standardHandler(envelope))
    render(<App />)
    await fillAndSubmit({ guidance: 'LOCALLY TYPED TEXT' })

    const block = screen.getByTestId('receipt-guidance')
    expect(block.textContent).toContain('SERVER-VALUE')
    expect(block.textContent).not.toContain('LOCALLY TYPED TEXT')
  })

  it('distinguishes absent guidance from an empty-string guidance', async () => {
    const absent = makeEnvelope()
    absent.request = { ...absent.request, additional_instructions: undefined }
    installFetch(standardHandler(absent))
    const first = render(<App />)
    await fillAndSubmit()
    expect(screen.getByTestId('receipt-guidance-absent').textContent).toBe(
      'No additional instructions were sent with this request.',
    )
    first.unmount()
    cleanup()

    const empty = makeEnvelope()
    empty.request = { ...empty.request, additional_instructions: '' }
    installFetch(standardHandler(empty))
    render(<App />)
    await fillAndSubmit()
    const node = screen.getByTestId('receipt-guidance-empty')
    expect(node.textContent).toContain('An empty instruction value was recorded.')
    expect(node.textContent).toContain('Empty, not absent')
  })

  it('surfaces a failed echo rather than backfilling the field', async () => {
    const envelope = makeEnvelope()
    envelope.request = { ...envelope.request, additional_instructions: undefined }
    installFetch(standardHandler(envelope))
    render(<App />)
    await fillAndSubmit({ guidance: 'Explain the approval path first' })

    const banner = screen.getByTestId('receipt-guidance-not-echoed')
    expect(banner.textContent).toContain('The receipt does not carry the caller guidance that was sent.')
    expect(screen.queryByTestId('receipt-guidance')).toBeNull()
  })

  it('renders evidence rows with the rule id, route, page, quote and payload link', async () => {
    installFetch(standardHandler())
    render(<App />)
    await fillAndSubmit()

    const table = screen.getByTestId('playground-evidence-table')
    expect(table.textContent).toContain('SUP-3.2-R1')
    expect(table.textContent).toContain('Supplier Onboarding › Payment terms')
    expect(table.textContent).toContain('Section 3.2')
    expect(table.textContent).toContain('Page 12')
    expect(within(table).getAllByTestId('evidence-quote')[0].textContent).toContain(
      'Payment terms beyond 60 days require prior sanctions clearance.',
    )
    expect(within(table).getAllByText('View payload →')[0].getAttribute('href')).toBe(
      'https://policy.example.com/api/policy-payload/SUP-3.2',
    )
  })

  it('never paraphrases a missing quotation', async () => {
    const envelope = makeEnvelope()
    envelope.citations = [
      { rule_id: 'R-1', policy: { provision_key: 'P-1' }, source: { state: 'not_stored' } },
    ]
    installFetch(standardHandler(envelope))
    render(<App />)
    await fillAndSubmit()

    expect(screen.getAllByTestId('evidence-quote-missing')[0].textContent).toBe(
      'The citation source is Not Stored; no verbatim quote was returned.',
    )
    expect(screen.queryAllByTestId('evidence-quote')).toHaveLength(0)
  })

  it('reports the retrieval counts as returned', async () => {
    installFetch(standardHandler())
    render(<App />)
    await fillAndSubmit()
    expect(screen.getByTestId('retrieval-counts').textContent).toBe(
      'Considered 12 · Retained 3 · Discarded 9',
    )
  })

  it('never claims all published policies were evaluated when narrowing discarded some', async () => {
    installFetch(standardHandler())
    render(<App />)
    await fillAndSubmit()

    expect(document.body.textContent).not.toContain('All published policies were evaluated')
    expect(screen.getByTestId('retrieval-heading-text').textContent).toBe(
      'Search narrowed the published policies before evaluation',
    )
  })

  it('does say so when retrieval genuinely narrowed nothing', async () => {
    installFetch(
      standardHandler(
        makeEnvelope({
          retrieval: { status: 'narrowed', policies_considered: 3, policies_retained: 3, policies_discarded: 0 },
          considered: [],
          excluded: [],
        }),
      ),
    )
    render(<App />)
    await fillAndSubmit()
    expect(screen.getByTestId('retrieval-heading-text').textContent).toBe(
      'All published policies were evaluated',
    )
  })
})

describe('payload links point at the API, not at this page', () => {
  /** A receipt as the server really returns one: `payload_url` is relative. */
  function relativePayloadEnvelope() {
    const envelope = makeEnvelope()
    return {
      ...envelope,
      citations: (envelope.citations ?? []).map((citation) => ({
        ...citation,
        policy: citation.policy
          ? { ...citation.policy, payload_url: '/api/policy-payload/SUP-3.2' }
          : citation.policy,
      })),
      considered: (envelope.considered ?? []).map((policy) => ({
        ...policy,
        payload_url: '/api/policy-payload/SUP-3.2',
      })),
    } as CaseDecisionEnvelope
  }

  it('resolves a relative citation payload_url against the API base', async () => {
    installFetch(standardHandler(relativePayloadEnvelope()))
    render(<App />)
    await fillAndSubmit()

    const link = screen.getAllByTestId('evidence-payload-link')[0] as HTMLAnchorElement
    // The defect: a relative href resolves against this page's origin, so every
    // link went to the playground (5179) instead of the API.
    expect(link.getAttribute('href')).toBe('http://localhost:8010/api/policy-payload/SUP-3.2')
    expect(link.getAttribute('href')).not.toContain('5179')
  })

  it('resolves a relative retained-policy payload_url against the API base', async () => {
    installFetch(standardHandler(relativePayloadEnvelope()))
    render(<App />)
    await fillAndSubmit()

    const links = screen.getAllByTestId('retrieval-payload-link') as HTMLAnchorElement[]
    expect(links.length).toBeGreaterThan(0)
    for (const link of links) {
      expect(link.getAttribute('href')).toBe('http://localhost:8010/api/policy-payload/SUP-3.2')
    }
  })

  it('leaves an absolute payload_url exactly as the receipt carried it', async () => {
    // The default fixture carries absolute URLs. A receipt read back from
    // storage holds whatever was written when the decision was made, and
    // rewriting it would point a reader at the wrong server.
    installFetch(standardHandler())
    render(<App />)
    await fillAndSubmit()

    const link = screen.getAllByTestId('evidence-payload-link')[0] as HTMLAnchorElement
    expect(link.getAttribute('href')).toBe(
      'https://policy.example.com/api/policy-payload/SUP-3.2',
    )
  })
})

describe('safety', () => {
  it('writes no part of the subscription key to localStorage, sessionStorage or the URL', async () => {
    installFetch(standardHandler())
    render(<App />)
    await fillAndSubmit()

    // The rule that did *not* relax when the field became visible. A value on
    // screen is gone when the tab is; a value in storage is not, and is read
    // by every script the origin ever loads.
    const stores = [JSON.stringify(localStorage), JSON.stringify(sessionStorage), window.location.href]
    for (const store of stores) {
      for (let i = 0; i + 8 <= SUBSCRIPTION_KEY.length; i += 1) {
        expect(store).not.toContain(SUBSCRIPTION_KEY.slice(i, i + 8))
      }
    }
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
    expect(document.cookie).toBe('')
  })

  it('sends the key in X-Policy-Subscription-Key, and no Authorization header', async () => {
    const calls = installFetch(standardHandler())
    render(<App />)
    await fillAndSubmit()

    // Every call this run actually made. The identity and version reads are
    // debounced and do not always land inside a fake-timer run, so the count is
    // not asserted — what is asserted is that no request escapes without the
    // header, which holds for all four calls because `apiClient` builds them
    // from one `apiHeaders` helper.
    expect(calls.length).toBeGreaterThan(0)
    expect(calls.some((call) => call.init?.method === 'POST')).toBe(true)
    for (const call of calls) {
      const headers = (call.init?.headers ?? {}) as Record<string, string>
      expect(headers['X-Policy-Subscription-Key']).toBe(SUBSCRIPTION_KEY)
      // Not both. A server reading one header cannot be handed the other, and
      // sending a bearer header this page has no bearer token for would be a
      // header that is always wrong.
      expect(headers.Authorization).toBeUndefined()
    }
  })

  it('renders the demo note as calm secondary text, not as an alert', () => {
    installFetch(standardHandler())
    render(<App />)
    const note = screen.getByTestId('playground-demo-note')
    expect(note.getAttribute('role')).toBeNull()
    expect(note.className).toContain('pg-intro__note')
  })

  it('carries no admin verb and is not a chat UI', async () => {
    installFetch(standardHandler())
    render(<App />)
    await fillAndSubmit()

    const text = document.body.textContent ?? ''
    for (const verb of ['Approve', 'Publish ', 'Edit policy', 'Review queue', 'Regenerate response', 'Temperature', 'System prompt', 'New chat']) {
      expect(text).not.toContain(verb)
    }
    expect(document.querySelectorAll('[role="log"]')).toHaveLength(0)
  })
})

describe('errors', () => {
  function errorHandler(status: number, detail: unknown) {
    return (url: string) => {
      if (url.includes('/active-version')) return jsonResponse({ id: 'v', version_number: 7 })
      if (url.includes('/api/policy-sets/')) {
        return jsonResponse({ id: 'p', key: 'demo-project', name: 'Supplier Onboarding Policy' })
      }
      return jsonResponse({ detail }, { status })
    }
  }

  async function submitExpectingError(status: number, detail: unknown) {
    installFetch(errorHandler(status, detail))
    render(<App />)
    fireEvent.change(screen.getByTestId('playground-project-key'), { target: { value: 'demo-project' } })
    fireEvent.change(screen.getByTestId('playground-subscription-key'), { target: { value: SUBSCRIPTION_KEY } })
    fireEvent.change(screen.getByTestId('playground-scenario'), {
      target: { value: 'A supplier asks about 90-day payment terms.' },
    })
    await waitFor(() => expect((screen.getByTestId('playground-submit') as HTMLButtonElement).disabled).toBe(false), {
      timeout: 3000,
    })
    fireEvent.click(screen.getByTestId('playground-submit'))
    return screen.findByTestId('playground-error', {}, { timeout: 3000 })
  }

  it('renders errors as an assertive band that stays on the page', async () => {
    const band = await submitExpectingError(401, { code: 'unauthenticated' })
    expect(band.getAttribute('role')).toBe('alert')
    expect(screen.getByTestId('playground-error-heading').textContent).toBe(
      'The subscription key was not accepted.',
    )
  })

  it.each([
    [403, undefined, 'This subscription key may not put cases to this project.'],
    [404, undefined, 'No project is published under the key "demo-project".'],
    [409, { code: 'idempotency_key_reused' }, 'This Idempotency-Key was already used for a different request.'],
    [409, { code: 'decision_in_progress' }, 'A decision is already in flight for this Idempotency-Key.'],
    [409, { code: 'decision_previously_failed' }, 'This Idempotency-Key was spent on a decision that failed.'],
    [422, { message: 'bad' }, 'The request was rejected before evaluation.'],
    [503, undefined, 'The policy service is not available right now.'],
  ])('maps %i to its own heading', async (status, detail, heading) => {
    await submitExpectingError(status as number, detail)
    expect(screen.getByTestId('playground-error-heading').textContent).toBe(heading)
    cleanup()
  })

  it('offers a new key on a reused-key conflict', async () => {
    await submitExpectingError(409, { code: 'idempotency_key_reused' })
    expect(screen.getByTestId('playground-generate-new-key')).toBeTruthy()
  })

  it('renders no verdict, result grid or hash when the receipt was not stored', async () => {
    await submitExpectingError(500, { code: 'decision_receipt_failed', decision_id: 'd-1' })
    expect(screen.queryByTestId('playground-verdict')).toBeNull()
    expect(screen.queryByTestId('playground-result-grid')).toBeNull()
    expect(screen.queryByTestId('receipt-decision-hash')).toBeNull()
    expect(screen.getByTestId('playground-persistence-failure').textContent).toContain(
      'The decision was not stored, so it is not usable. Nothing is shown.',
    )
  })

  it('shows only the new call failure, never the previous receipt', async () => {
    let fail = false
    installFetch((url: string) => {
      if (url.includes('/active-version')) return jsonResponse({ id: 'v', version_number: 7 })
      if (url.includes('/api/policy-sets/')) {
        return jsonResponse({ id: 'p', key: 'demo-project', name: 'Supplier Onboarding Policy' })
      }
      if (fail) return jsonResponse({ detail: { code: 'x' } }, { status: 503 })
      return jsonResponse(makeEnvelope())
    })
    render(<App />)
    await fillAndSubmit()
    expect(screen.getByTestId('receipt-decision-id')).toBeTruthy()

    fail = true
    fireEvent.click(screen.getByTestId('playground-submit'))
    await screen.findByTestId('playground-error', {}, { timeout: 3000 })

    expect(screen.queryByTestId('playground-receipt')).toBeNull()
    expect(screen.queryByTestId('playground-stale-caption')).toBeNull()
    expect(screen.queryByTestId('receipt-decision-id')).toBeNull()
  })

  it('names the base URL and CORS when the request never reached the API', async () => {
    installFetch((url: string) => {
      if (url.includes('/api/policy-sets/')) {
        return jsonResponse({ id: 'p', key: 'demo-project', name: 'Supplier Onboarding Policy' })
      }
      throw new TypeError('Failed to fetch')
    })
    render(<App />)
    fireEvent.change(screen.getByTestId('playground-project-key'), { target: { value: 'demo-project' } })
    fireEvent.change(screen.getByTestId('playground-subscription-key'), { target: { value: SUBSCRIPTION_KEY } })
    fireEvent.change(screen.getByTestId('playground-scenario'), {
      target: { value: 'A supplier asks about 90-day payment terms.' },
    })
    await waitFor(() => expect((screen.getByTestId('playground-submit') as HTMLButtonElement).disabled).toBe(false), {
      timeout: 3000,
    })
    fireEvent.click(screen.getByTestId('playground-submit'))

    const band = await screen.findByTestId('playground-error', {}, { timeout: 3000 })
    expect(band.textContent).toContain('API base URL')
    expect(band.textContent).toContain('CORS')
  })

  it('shows a recovered Decision Light timeout as the stored full receipt', async () => {
    const stored = makeV2Envelope()
    installFetch((url, init) => {
      if (url.includes('/active-version')) {
        return jsonResponse({ id: 'version-1', version_number: 7 })
      }
      if (url.includes('/api/policy-sets/')) {
        return jsonResponse({ id: 'set-1', key: 'demo-project', name: 'Demo project' })
      }
      if (url.endsWith('/case/light')) {
        return new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => {
            reject(new DOMException('Timed out', 'AbortError'))
          })
        })
      }
      if (url.endsWith('/api/policy-decisions/recovered-decision')) {
        return jsonResponse(stored)
      }
      throw new Error(`Unexpected request: ${url}`)
    })
    render(<App />)

    fireEvent.click(screen.getByRole('radio', { name: /Decision Light/ }))
    fireEvent.change(screen.getByTestId('playground-project-key'), {
      target: { value: 'demo-project' },
    })
    fireEvent.change(screen.getByTestId('playground-subscription-key'), {
      target: { value: SUBSCRIPTION_KEY },
    })
    fireEvent.change(screen.getByTestId('playground-scenario'), {
      target: { value: 'Is this request allowed under the policy?' },
    })
    await waitFor(() =>
      expect((screen.getByTestId('playground-submit') as HTMLButtonElement).disabled).toBe(false),
    )
    fireEvent.click(screen.getByTestId('playground-submit'))
    await vi.advanceTimersByTimeAsync(60_100)

    await screen.findByTestId('playground-error')
    fireEvent.change(screen.getByTestId('playground-lookup-id'), {
      target: { value: 'recovered-decision' },
    })
    fireEvent.submit(screen.getByTestId('playground-lookup-id').closest('form')!)

    await screen.findByTestId('playground-receipt')
    expect((screen.getByRole('radio', { name: /Decision JSON/ }) as HTMLInputElement).checked).toBe(
      true,
    )
    expect(screen.queryByTestId('playground-error')).toBeNull()
  })
})

describe('case_decision_v2: the two-track result', () => {
  async function renderV2(envelope: CaseDecisionReceipt) {
    installFetch(standardHandler(envelope))
    render(<App />)
    await fillAndSubmit()
  }

  it('renders a v2 receipt at all, rather than white-screening on the missing v1 keys', async () => {
    await renderV2(makeV2Envelope())

    // The regression this whole contract change exists for: a v2 envelope has
    // no `decision` key, and every v1 component read `envelope.decision.*`.
    expect(screen.getByTestId('playground-outcome-band')).toBeTruthy()
    expect(screen.getByTestId('playground-receipt')).toBeTruthy()
    // ...and the v1 surface is not rendered beside it.
    expect(screen.queryByTestId('playground-verdict-band')).toBeNull()
    expect(screen.queryByTestId('playground-result-grid')).toBeNull()
  })

  it('states what the question asked for before either answer', async () => {
    await renderV2(makeV2Envelope())

    const asked = screen.getByTestId('playground-asked-summary')
    expect(asked.textContent).toBe('Information and a verdict')

    const band = screen.getByTestId('playground-outcome-band')
    const verdictPanel = screen.getByTestId('playground-verdict-panel')
    const informationPanel = screen.getByTestId('playground-information-panel')
    expect(band.compareDocumentPosition(verdictPanel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(
      band.compareDocumentPosition(informationPanel) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
  })

  it('always shows both tracks, so an absent track is never mistaken for a silent failure', async () => {
    await renderV2(makeInformationOnlyEnvelope())

    expect(screen.getByTestId('playground-track-information').getAttribute('data-outcome')).toBe(
      'answered',
    )
    const verdictTrack = screen.getByTestId('playground-track-verdict')
    expect(verdictTrack.getAttribute('data-outcome')).toBe('not_requested')
    expect(verdictTrack.textContent).toContain('Not asked for')
  })

  /* ---------- information only ---------- */

  it('renders an information-only receipt without inventing a verdict panel', async () => {
    await renderV2(makeInformationOnlyEnvelope())

    expect(screen.getByTestId('playground-asked-summary').textContent).toBe('Information only')
    expect(screen.getByTestId('playground-information-answer').textContent).toContain(
      '48 hours in any rolling seven-day period',
    )
    // No section was carried, so no panel is rendered: an empty verdict panel
    // is an emptiness a reader would take for a finding.
    expect(screen.queryByTestId('playground-verdict-panel')).toBeNull()
    expect(screen.queryByTestId('playground-verdict')).toBeNull()
    // And nothing claims the two halves diverged, because only one ran.
    expect(screen.queryByTestId('playground-outcome-split')).toBeNull()
  })

  /* ---------- verdict only ---------- */

  it('renders a verdict-only receipt without inventing an information panel', async () => {
    await renderV2(makeVerdictOnlyEnvelope())

    expect(screen.getByTestId('playground-asked-summary').textContent).toBe('A verdict only')
    expect(screen.getByTestId('playground-verdict').textContent).toBe('Not compliant')
    expect(screen.queryByTestId('playground-information-panel')).toBeNull()
    expect(screen.getByTestId('playground-track-information').getAttribute('data-outcome')).toBe(
      'not_requested',
    )
  })

  it('renders a refusal as a reached verdict, never as an empty one', async () => {
    await renderV2(makeVerdictOnlyEnvelope())

    // "Not compliant" is a verdict the rules reached. It must appear in the
    // verdict node, not in the space reserved for "no verdict was reached".
    expect(screen.getByTestId('playground-verdict').textContent).toBe('Not compliant')
    expect(screen.queryByTestId('playground-verdict-not-reached')).toBeNull()
  })

  /* ---------- mixed, both answered ---------- */

  it('renders both answers when both tracks answered, and claims no divergence', async () => {
    await renderV2(makeV2Envelope())

    expect(screen.getByTestId('playground-verdict').textContent).toBe('Not compliant')
    expect(screen.getByTestId('playground-information-answer').textContent).toContain('48 hours')
    expect(screen.queryByTestId('playground-outcome-split')).toBeNull()
  })

  /* ---------- mixed: information answered, verdict blocked ---------- */

  it('makes the mixed answered/blocked case unmistakable', async () => {
    await renderV2(makeMixedBlockedEnvelope())

    // Two tracks, two different semantic tones, in one band.
    expect(screen.getByTestId('playground-track-information').getAttribute('data-tone')).toBe(
      'allow',
    )
    expect(screen.getByTestId('playground-track-verdict').getAttribute('data-tone')).toBe('action')

    // And it is said in words, not left to be inferred from two colours.
    const split = screen.getByTestId('playground-outcome-split')
    expect(split.textContent).toContain('came out differently')
    expect(split.textContent).toContain('what the policies state is settled')
    expect(screen.getByTestId('playground-split-missing-count').textContent).toBe(
      '2 facts are outstanding.',
    )
  })

  it('renders no verdict node at all when the verdict was not reached', async () => {
    await renderV2(makeMixedBlockedEnvelope())

    // Not hidden, not dimmed, not placed second: absent. There is no traversal
    // of this page on which a determination can be read off a blocked case.
    expect(screen.queryByTestId('playground-verdict')).toBeNull()
    expect(screen.getByTestId('playground-verdict-not-reached').textContent).toContain(
      'No verdict was reached',
    )
    // The information answer is still fully present beside it.
    expect(screen.getByTestId('playground-information-answer').textContent).toContain('48 hours')
  })

  it('renders missing information as an actionable register, not a list of bare strings', async () => {
    await renderV2(makeMixedBlockedEnvelope())

    const block = screen.getByTestId('playground-missing-information')
    expect(within(block).getByTestId('missing-count').textContent).toBe('2 facts')

    const items = within(block).getAllByTestId('missing-item')
    expect(items).toHaveLength(V2_MISSING_INFORMATION.length)

    const labels = within(block).getAllByTestId('missing-item-label').map((n) => n.textContent)
    expect(labels).toEqual(V2_MISSING_INFORMATION.map((item) => item.label))

    // Each fact says which judgement turns on it, and which rules wait for it.
    expect(within(block).getAllByTestId('missing-item-why')[0].textContent).toContain(
      'rolling seven days',
    )
    expect(within(block).getAllByTestId('missing-item-rules')[1].textContent).toContain('HR-4.6-R1')

    // And the whole checklist leaves the page in one press.
    expect(
      within(block).getByRole('button', { name: /Copy the missing-fact checklist/i }),
    ).toBeTruthy()
    expect(block.textContent).toContain('Add these to the scenario above and send the case again.')
  })

  it('names a missing fact honestly when the gather composed no reason for it', async () => {
    const envelope = makeMixedBlockedEnvelope()
    envelope.verdict = {
      ...envelope.verdict!,
      missing_information: [
        { fact: 'shift_end_time', label: 'Shift end time', required_by_rule_ids: [] },
      ],
      missing_required_facts: ['Shift end time'],
    }
    await renderV2(envelope)

    // Nothing is invented to fill the gap; the absence is stated.
    expect(screen.getByTestId('missing-item-no-why').textContent).toContain(
      'No reason was composed',
    )
  })

  it('falls back to the flat label list when no structured facts were carried', async () => {
    const envelope = makeMixedBlockedEnvelope()
    envelope.verdict = {
      ...envelope.verdict!,
      missing_information: [],
      missing_required_facts: ['Hours already worked', 'Approval timestamp'],
    }
    await renderV2(envelope)

    const labels = screen.getAllByTestId('missing-item-label').map((n) => n.textContent)
    expect(labels).toEqual(['Hours already worked', 'Approval timestamp'])
  })

  /* ---------- checks before acting ---------- */

  it('shows the checks before acting beside a verdict that was reached, not instead of it', async () => {
    await renderV2(makeQualifiedVerdictEnvelope())

    // The determination is still a determination. Nothing about the checks
    // downgrades it, hides it or restyles it as a blocked case.
    expect(screen.getByTestId('playground-verdict').textContent).toContain('Entitled')
    expect(screen.getByTestId('playground-track-verdict').getAttribute('data-outcome')).toBe(
      'answered',
    )
    expect(screen.queryByTestId('playground-verdict-not-reached')).toBeNull()

    const block = screen.getByTestId('playground-verification-requirements')
    expect(within(block).getByTestId('verification-count').textContent).toBe('2 checks')

    const labels = within(block)
      .getAllByTestId('verification-item-label')
      .map((n) => n.textContent)
    expect(labels).toEqual(V2_VERIFICATION_REQUIREMENTS.map((item) => item.label))

    // Each check says what to confirm and which rules impose it.
    expect(within(block).getAllByTestId('verification-item-why')[0].textContent).toContain(
      'balance that has actually accrued',
    )
    expect(within(block).getAllByTestId('verification-item-rules')[1].textContent).toContain(
      'HR-4.6-R1',
    )

    // And it says, in words, that the entitlement stands and these are separate.
    expect(block.textContent).toContain('Checks before acting')
  })

  it('never renders a check inside the missing-information register', async () => {
    await renderV2(makeQualifiedVerdictEnvelope())

    // The one confusion the whole field exists to prevent: a condition on
    // acting read as a reason the case could not be decided.
    expect(screen.queryByTestId('playground-missing-information')).toBeNull()
    const block = screen.getByTestId('playground-verification-requirements')
    expect(within(block).queryAllByTestId('missing-item')).toHaveLength(0)
  })

  it('shows no checks at all when the verdict was not reached', async () => {
    const envelope = makeMixedBlockedEnvelope()
    // Even if a section arrived carrying them, a blocked case has nothing to
    // verify before acting on: there is nothing it permits yet.
    envelope.verdict = {
      ...envelope.verdict!,
      verification_requirements: V2_VERIFICATION_REQUIREMENTS,
    }
    await renderV2(envelope)

    expect(screen.queryByTestId('playground-verification-requirements')).toBeNull()
    expect(screen.getByTestId('playground-missing-information')).toBeTruthy()
  })

  it('omits the section entirely when a reached verdict carries no checks', async () => {
    await renderV2(makeVerdictOnlyEnvelope())

    expect(screen.getByTestId('playground-verdict').textContent).toContain('Not compliant')
    expect(screen.queryByTestId('playground-verification-requirements')).toBeNull()
  })

  it('names a check honestly when the gather composed no reason for it', async () => {
    const envelope = makeQualifiedVerdictEnvelope()
    envelope.verdict = {
      ...envelope.verdict!,
      verification_requirements: [
        { fact: 'roster_cover', label: 'Roster cover', required_by_rule_ids: [] },
      ],
    }
    await renderV2(envelope)

    expect(screen.getByTestId('verification-item-no-why').textContent).toContain(
      'No explanation was composed for this check',
    )
  })

  /* ---------- nothing evaluated, and nothing bearing ---------- */

  it('says nothing was evaluated without implying the policies were read and silent', async () => {
    await renderV2(makeNotEvaluatedV2Envelope())

    expect(screen.getByTestId('playground-asked-summary').textContent).toBe(
      'Nothing was classified',
    )
    expect(screen.getByTestId('playground-track-information').getAttribute('data-outcome')).toBe(
      'not_evaluated',
    )
    expect(screen.getByTestId('playground-track-verdict').getAttribute('data-outcome')).toBe(
      'not_evaluated',
    )
    expect(screen.queryByTestId('playground-information-panel')).toBeNull()
    expect(screen.queryByTestId('playground-verdict-panel')).toBeNull()

    // The raw envelope opens by default, because it is the primary evidence
    // when there is no answer to read.
    expect(screen.getByTestId('playground-raw-json').getAttribute('open')).not.toBeNull()
  })

  it('distinguishes "no rule bears" from "not evaluated"', async () => {
    await renderV2(makeNoRuleBearsV2Envelope())

    const info = screen.getByTestId('playground-information-panel')
    expect(info.textContent).toContain('No retained rule states anything on this subject')
    expect(info.textContent).toContain('This is a real answer')
    expect(screen.getByTestId('playground-information-explanation').textContent).toContain(
      'parking allowances',
    )
    expect(screen.queryByTestId('playground-information-answer')).toBeNull()
  })

  /* ---------- evidence ---------- */

  it('tags each citation with the track or tracks that rested on it', async () => {
    await renderV2(makeV2Envelope())

    const rows = screen.getAllByTestId('evidence-cited-by')
    expect(rows.length).toBeGreaterThan(0)

    // The rule both tracks cited appears once and carries both tags, because
    // the policies hold one authority there, not two.
    const table = screen.getByTestId('playground-evidence-table')
    const ruleIds = within(table)
      .getAllByText(/^HR-/)
      .map((node) => node.textContent)
    expect(ruleIds.filter((id) => id === 'HR-4.1-R3')).toHaveLength(1)

    const shared = within(table).getAllByTestId('evidence-cited-by')[1]
    expect(within(shared).getByTestId('evidence-serves-information')).toBeTruthy()
    expect(within(shared).getByTestId('evidence-serves-verdict')).toBeTruthy()
  })

  it('reports a refused citation against the track that tried to make it', async () => {
    await renderV2(makeFabricatedCitationV2Envelope())

    const banner = screen.getByTestId('playground-fabricated')
    expect(banner.getAttribute('data-track')).toBe('verdict')
    expect(banner.textContent).toContain('HR-99.9-R1')
  })

  /* ---------- rule-level retrieval ---------- */

  it('never claims every published policy was evaluated when a policy was rule-sliced', async () => {
    await renderV2(makeRuleSlicedEnvelope())

    // Search discarded nothing, so the policy-count test alone would have
    // printed the over-claiming heading. Sixty-six rules were not read.
    const heading = screen.getByTestId('retrieval-heading-text').textContent ?? ''
    expect(heading).not.toContain('All published policies were evaluated')

    expect(screen.getByTestId('retrieval-sliced-banner').textContent).toContain(
      'One retained policy was read as a slice of its rules',
    )
  })

  it('reports the slice: totals, selection, the rule ids read, and what was not', async () => {
    await renderV2(makeRuleSlicedEnvelope())

    expect(screen.getByTestId('retrieval-counts').textContent).toContain('Rule-sliced 1')

    const claim = screen.getByTestId('rule-slice-claim').textContent ?? ''
    expect(claim).toContain('8 of 74 rules were read')
    expect(claim).toContain('66 rules were not read and not evaluated')

    const ids = screen.getByTestId('rule-slice-ids').textContent ?? ''
    expect(ids).toContain('FIN-12.4-R03')
    expect(ids).toContain('FIN-12.4-R61')

    // Context a selected rule names but that did not fit is named, not dropped.
    expect(screen.getByTestId('rule-slice-omitted').textContent).toContain('FIN-12.4-R62')

    // And the budgets that produced the slice are stated.
    const budgets = screen.getByTestId('retrieval-budgets').textContent ?? ''
    expect(budgets).toContain('above 40 rules')
    expect(budgets).toContain('Up to 8 rules')

    // The policy that was read whole says so, rather than saying nothing and
    // leaving "no slice reported" to be read as "slice not disclosed".
    expect(screen.getByTestId('retrieval-read-whole').textContent).toContain('Read whole')
  })

  /* ---------- de-duplication and diversity deferral ---------- */

  it('keeps a collapsed exact duplicate out of the discarded register', async () => {
    await renderV2(makeDuplicateCollapsedEnvelope())

    // Every other discard names content nothing saw. A collapsed duplicate
    // names content that was read, once, in the policy it points at -- so it
    // must not sit under a heading that says it went unweighed.
    const register = screen.getByTestId('retrieval-collapsed-register')
    expect(register.textContent).toContain('Collapsed as exact duplicates')
    expect(register.textContent).toContain('HW-7.9')
    expect(register.textContent).toContain('HW-8.3')

    const discarded = screen.getByText('Discarded before evaluation').closest('.panel')!
    expect(discarded.textContent).not.toContain('HW-7.9')
    expect(discarded.textContent).not.toContain('HW-8.3')
    // The ordinary misses are still there.
    expect(discarded.textContent).toContain('HW-9.2')
  })

  it('names where a collapsed duplicate’s terms were actually read', async () => {
    await renderV2(makeDuplicateCollapsedEnvelope())

    const representatives = screen
      .getAllByTestId('retrieval-duplicate-of')
      .map((node) => node.textContent)
    expect(representatives[0]).toContain('Terms read in')
    expect(representatives[0]).toContain('HW-2.1')
    expect(representatives[1]).toContain('HW-2.4')

    expect(screen.getByTestId('retrieval-collapsed-note').textContent).toContain(
      '2 policies were collapsed into identical ones',
    )
    expect(screen.getByTestId('retrieval-counts').textContent).toContain('Duplicates collapsed 2')
  })

  it('says so when a receipt collapsed a duplicate without naming the representative', async () => {
    await renderV2(makeUnnamedDuplicateEnvelope())

    // Nothing is guessed. The absence is stated where the representative would
    // have been, because "collapsed into something" with no name is a weaker
    // claim than "collapsed into HW-2.1" and must not be shown as the same one.
    expect(screen.getByTestId('retrieval-duplicate-of-unknown').textContent).toContain(
      'did not name which policy it was collapsed into',
    )
  })

  it('never calls a diversity-deferred policy a duplicate', async () => {
    await renderV2(makeDuplicateCollapsedEnvelope())

    const deferred = screen.getByTestId('retrieval-deferred-note').textContent ?? ''
    expect(deferred).toContain('3 policies were deferred')
    expect(deferred).toContain('not proven identical to anything')
    expect(deferred).toContain('are not duplicates')

    // The deferred policy itself stays an ordinary out-of-budget discard: it
    // carries no duplicate chip and no representative.
    const discarded = screen.getByText('Discarded before evaluation').closest('.panel')!
    expect(discarded.textContent).toContain('HW-5.5')
    expect(discarded.textContent).toContain('Outside Budget')
    expect(within(discarded as HTMLElement).queryByTestId('retrieval-duplicate-of')).toBeNull()
  })

  it('names the selection order that put a highly-ranked policy outside the budget', async () => {
    await renderV2(makeDuplicateCollapsedEnvelope())

    const budgets = screen.getByTestId('retrieval-budgets').textContent ?? ''
    expect(budgets).toContain('Selection order')
    expect(budgets).toContain('relevance_then_normative_content_v1')
    expect(budgets).toContain('Relevance first, then normative-content diversity')
  })

  it('splits a slice’s unread remainder from the copies it represents', async () => {
    await renderV2(makeDuplicateCollapsedEnvelope())

    // 66 were not read. Three of those are exact copies of rules that were, so
    // reporting all 66 as content nobody saw would overstate the loss -- and
    // reporting them as read would overstate the reading.
    const claim = screen.getByTestId('rule-slice-claim').textContent ?? ''
    expect(claim).toContain('8 of 74 rules were read')
    expect(claim).toContain('66 were not')
    expect(claim).toContain('3 of those are exact copies of a rule that was read')
    expect(claim).toContain('63 rules were not read at all')
  })

  it('shows represented rule copies without implying they were read', async () => {
    await renderV2(makeDuplicateCollapsedEnvelope())

    const represented = screen.getByTestId('rule-slice-represented')
    expect(represented.textContent).toContain('HW-2.1-R14')
    expect(represented.textContent).toContain('HW-2.1-R47')

    // They are not in the list of ids that were read.
    expect(screen.getByTestId('rule-slice-ids').textContent).not.toContain('HW-2.1-R14')

    // And the caption refuses the inference outright.
    const disclosure = represented.closest('details')!
    expect(disclosure.textContent).toContain('None of these was put in front of the model')
    expect(disclosure.textContent).toContain('is not a second reading of it')

    expect(screen.getByTestId('rule-slice-collapsed').textContent).toContain(
      '5 further rules were not candidates',
    )
  })

  it('glosses scenario_relevance_v2 as the ranking it is', async () => {
    await renderV2(makeDuplicateCollapsedEnvelope())

    const slice = screen.getByTestId('retrieval-rule-slice').textContent ?? ''
    expect(slice).toContain('scenario_relevance_v2')
    expect(slice).toContain("ranked against the question by the policy's own words")
    // Context is disclosed as spending selected slots, not extending them.
    expect(slice).toContain('2 of those slots went to context')
  })

  it('renders an old v2 receipt unchanged when the new fields are absent', async () => {
    await renderV2(makeRuleSlicedEnvelope())

    // Back-compat: no duplicate or deferral fields on this receipt, so no
    // sentence about either, and the slice claim keeps its simple arithmetic.
    expect(screen.queryByTestId('retrieval-collapsed-register')).toBeNull()
    expect(screen.queryByTestId('retrieval-collapsed-note')).toBeNull()
    expect(screen.queryByTestId('retrieval-deferred-note')).toBeNull()
    expect(screen.queryByTestId('rule-slice-represented')).toBeNull()
    expect(screen.queryByTestId('rule-slice-collapsed')).toBeNull()
    expect(screen.getByTestId('retrieval-counts').textContent).not.toContain('Duplicates collapsed')
    expect(screen.getByTestId('rule-slice-claim').textContent).toContain(
      '66 rules were not read and not evaluated',
    )
  })

  it('renders a v1 receipt unchanged when the new fields are absent', async () => {
    installFetch(standardHandler(makeEnvelope()))
    render(<App />)
    await fillAndSubmit()

    expect(screen.queryByTestId('retrieval-collapsed-register')).toBeNull()
    expect(screen.queryByTestId('retrieval-deferred-note')).toBeNull()
    expect(screen.getByTestId('retrieval-counts').textContent).toBe(
      'Considered 12 · Retained 3 · Discarded 9',
    )
  })

  /* ---------- the language boundary (M2) ---------- */

  it('shows which language each stage worked in', async () => {
    await renderV2(makeLanguageRenderedEnvelope())

    const panel = screen.getByTestId('playground-language')
    expect(within(panel).getByTestId('language-source').textContent).toContain('en-GB')
    expect(within(panel).getByTestId('language-processing').textContent).toContain('en')
    expect(within(panel).getByTestId('language-response').textContent).toContain('en-GB')
    expect(within(panel).getByTestId('language-boundary').textContent).toContain(
      'carried into the processing language before anything read it',
    )
  })

  it('renders the question as it was actually adjudicated when it differs', async () => {
    await renderV2(makeLanguageRenderedEnvelope())

    // The text every stage read, shown because it is not the text that was
    // sent, and comparing the two is the only way to catch a rendering that
    // changed the question.
    expect(screen.getByTestId('language-processing-differs').textContent).toContain(
      'not what you sent',
    )
    expect(screen.getByTestId('language-processing-scenario').textContent).toContain(
      'What do the published policies state about laptop replacement eligibility',
    )
    expect(screen.getByTestId('language-processing-hash').textContent).toBe('e'.repeat(64))

    // And the caller's own bytes are stated to be untouched.
    expect(screen.getByTestId('playground-language').textContent).toContain(
      'the scenario, its hash and the idempotency binding are all still over exactly what you sent',
    )
  })

  it('says an identity rendering left the question byte-for-byte', async () => {
    await renderV2(makeLanguageIdentityEnvelope())

    expect(screen.getByTestId('language-boundary').textContent).toContain(
      'already in the processing language',
    )
    expect(screen.getByTestId('language-processing-same').textContent).toContain(
      'Identical to the question you sent',
    )
    expect(screen.queryByTestId('language-processing-differs')).toBeNull()
    // `not_required` is explained as needing no rendering, not as one failing.
    expect(screen.getByTestId('language-output').textContent).toContain('none was needed')
  })

  it('states plainly when caller guidance was dropped rather than applied un-rendered', async () => {
    await renderV2(makeLanguageDroppedGuidanceEnvelope())

    const guidance = screen.getByTestId('language-guidance')
    expect(guidance.textContent).toContain('unrendered_dropped')
    expect(guidance.textContent).toContain('dropped rather than applied un-rendered')
    expect(guidance.textContent).toContain('The decision itself is unaffected')

    // A malformed inbound tag is named as malformed, not silently shown raw.
    expect(screen.getByTestId('language-source').textContent).toContain('not well-formed')
    expect(screen.getByTestId('language-output').textContent).toContain(
      'returned exactly as it was reasoned',
    )
  })

  it('says the cited source text is never translated, whether or not anything was rendered', async () => {
    await renderV2(makeLanguageRenderedEnvelope())

    // The claim a reader handed rendered prose is most likely to get wrong.
    const citations = screen.getByTestId('language-citations')
    expect(citations.textContent).toContain('Cited source text is never translated')
    expect(citations.textContent).toContain('the published document’s own words')
    expect(citations.textContent).toContain('a paraphrase wearing quotation marks')
  })

  it('names the translation and projection profiles that were used', async () => {
    await renderV2(makeLanguageRenderedEnvelope())

    expect(screen.getByTestId('language-profiles').textContent).toContain('case-language-in-v1')
    expect(screen.getByTestId('language-profiles').textContent).toContain('case-language-out-v1')
    expect(screen.getByTestId('language-projection').textContent).toContain(
      'english_projection_v1',
    )
  })

  it('distinguishes a receipt that predates the boundary from one that reported nothing', async () => {
    // No `language` block at all: the v2 base fixture predates it.
    await renderV2(makeV2Envelope())

    expect(screen.getByTestId('language-absent').textContent).toContain(
      'predates the language boundary',
    )
    expect(screen.getByTestId('playground-language').textContent).toContain(
      'not the same as a boundary that ran and reported nothing',
    )
    // Nothing is fabricated to fill the rows.
    expect(screen.queryByTestId('language-processing')).toBeNull()
    expect(screen.queryByTestId('language-processing-hash')).toBeNull()
  })

  /* ---------- rule-level discovery (M2) ---------- */

  it('reports the rule-level scan, the documents matched, and the index state', async () => {
    await renderV2(makeRuleIndexMatchedEnvelope())

    const discovery = screen.getByTestId('retrieval-rule-discovery').textContent ?? ''
    expect(discovery).toContain('Rule documents examined 412')
    expect(discovery).toContain('Policy documents returned 6')
    expect(discovery).toContain('Rule documents returned 23')
    expect(discovery).toContain('matched')

    expect(screen.getByTestId('retrieval-projection').textContent).toContain(
      'english_projection_v1',
    )
    expect(screen.getByTestId('retrieval-projection').textContent).toContain(
      'complete corpus projection',
    )
  })

  it('says whether rule-level retrieval changed anything, including when it did not', async () => {
    await renderV2(makeRuleIndexMatchedEnvelope())
    expect(screen.getByTestId('retrieval-elevated').textContent).toContain(
      '2 policies were ranked higher because one of their own rules surfaced',
    )

    cleanup()
    await renderV2(makeRuleIndexDegradedEnvelope())
    expect(screen.getByTestId('retrieval-elevated').textContent).toContain(
      'rule-level retrieval altered nothing on this question',
    )
  })

  it('reports the fused candidate pool and the diversity quota that shaped it', async () => {
    await renderV2(makeRuleIndexMatchedEnvelope())

    const candidates = screen.getAllByTestId('rule-ranking-candidates')[0].textContent ?? ''
    expect(candidates).toContain('relevance 19')
    expect(candidates).toContain('quantity 4')
    expect(candidates).toContain('fused 27')
    // A quantity rank decides reading order, never the outcome.
    expect(candidates).toContain('never what the rule decides')

    expect(screen.getByTestId('rule-ranking-quota').textContent).toContain(
      '4 of the budget’s slots were reserved',
    )
  })

  it('never says an unscorable rule was scored in its own language', async () => {
    await renderV2(makeRuleIndexMatchedEnvelope())

    const unprojected = screen.getByTestId('rule-ranking-unprojected').textContent ?? ''
    expect(unprojected).toContain('3 rules could not be scored by relevance')
    expect(unprojected).toContain('no English projection')
    expect(unprojected).toContain('score zero rather than being scored against the document’s own language')
    // They remain reachable by the other ranks, and that is said.
    expect(unprojected).toContain('can still be placed by the rule index or the quantity rank')
  })

  it('tells zero rule-index hits apart from an index that was never asked', async () => {
    await renderV2(makeRuleIndexMatchedEnvelope())

    // HW-2.4 was read whole and the index placed none of its rules.
    expect(screen.getByTestId('rule-ranking-zero-matched').textContent).toContain(
      'asked and placed none',
    )
    expect(screen.getByTestId('rule-ranking-zero-matched').textContent).toContain(
      'an answer, not an outage',
    )
  })

  it('surfaces a degraded rule index as a qualified selection, not a silent one', async () => {
    await renderV2(makeRuleIndexDegradedEnvelope())

    expect(screen.getByTestId('retrieval-rule-index-degraded').textContent).toContain(
      'query against them failed recoverably',
    )
    expect(screen.getByTestId('retrieval-rule-index-degraded').textContent).toContain(
      'rules reachable only through the rule index may not have been placed',
    )
    // And each policy's method says so.
    expect(screen.getByTestId('retrieval-rule-slice').textContent).toContain(
      'scenario_relevance_v3',
    )
    expect(screen.getByTestId('retrieval-rule-slice').textContent).toContain(
      "ran without the rule index's ranking",
    )
  })

  it('glosses hybrid_rule_v1 as the fused ranking it is', async () => {
    await renderV2(makeRuleIndexMatchedEnvelope())

    const slice = screen.getByTestId('retrieval-rule-slice').textContent ?? ''
    expect(slice).toContain('hybrid_rule_v1')
    expect(slice).toContain('fused with the relevance and quantity ranks')
  })

  it('qualifies every ranking when the corpus projection was not ready', async () => {
    await renderV2(makeProjectionNotReadyEnvelope())

    const banner = screen.getByTestId('retrieval-projection-not-ready').textContent ?? ''
    expect(banner).toContain('did not report a complete projection')
    expect(banner).toContain('may not be comparable to the question')
  })

  it('renders none of the M2 retrieval disclosures when the fields are absent', async () => {
    await renderV2(makeRuleSlicedEnvelope())

    expect(screen.queryByTestId('retrieval-rule-discovery')).toBeNull()
    expect(screen.queryByTestId('retrieval-elevated')).toBeNull()
    expect(screen.queryByTestId('retrieval-projection')).toBeNull()
    expect(screen.queryByTestId('retrieval-projection-not-ready')).toBeNull()
    expect(screen.queryByTestId('retrieval-rule-index-degraded')).toBeNull()
    expect(screen.queryByTestId('rule-ranking')).toBeNull()
  })

  /* ---------- v1 is still readable ---------- */
  it('still renders a v1 receipt through the v1 surface', async () => {
    installFetch(standardHandler(makeEnvelope()))
    render(<App />)
    await fillAndSubmit()

    expect(screen.getByTestId('playground-verdict-band')).toBeTruthy()
    expect(screen.getByTestId('playground-result-grid')).toBeTruthy()
    expect(screen.getByTestId('playground-verdict').textContent).toBe(
      'Proceed only with prior sanctions clearance.',
    )
    // And the v2 surface is not rendered beside it.
    expect(screen.queryByTestId('playground-outcome-band')).toBeNull()
  })

  it('shows the v1 decider route in the evidence column that v2 uses for tracks', async () => {
    installFetch(standardHandler(makeEnvelope()))
    render(<App />)
    await fillAndSubmit()

    // v1 rows have no `serves`, so the same column answers the same question
    // with the vocabulary that receipt has.
    expect(screen.getAllByTestId('evidence-cited-by')[0].textContent).toContain('Decision')
    expect(screen.queryByTestId('evidence-serves-verdict')).toBeNull()
  })

  /* ---------- an envelope this build has never seen ---------- */

  it('renders an unrecognised envelope as itself instead of white-screening', async () => {
    const future = {
      ...makeV2Envelope(),
      schema_version: 'case_decision_v9',
    } as unknown as CaseDecisionReceipt
    await renderV2(future)

    expect(screen.getByTestId('playground-unrecognised').textContent).toContain(
      'envelope this page does not recognise',
    )
    // Identity and the seal are still real, so the receipt still renders.
    expect(screen.getByTestId('playground-receipt')).toBeTruthy()
    // Nothing is interpreted: no answer surface of either version appears.
    expect(screen.queryByTestId('playground-outcome-band')).toBeNull()
    expect(screen.queryByTestId('playground-verdict-band')).toBeNull()
    expect(screen.getByTestId('playground-raw-json').getAttribute('open')).not.toBeNull()
  })

  /* ---------- the live region ---------- */

  it('announces both tracks, not just the verdict', async () => {
    await renderV2(makeMixedBlockedEnvelope())

    const announcement = screen.getByTestId('playground-announcer').textContent ?? ''
    expect(announcement).toContain('Information answered')
    expect(announcement).toContain('verdict missing required facts')
    expect(announcement).toContain('2 facts are needed')
  })
})

describe('verification', () => {
  it('issues a GET by decision id and renders five comparison rows', async () => {
    const calls = installFetch((url: string) => {
      if (url.includes('/active-version')) return jsonResponse({ id: 'v', version_number: 7 })
      if (url.includes('/api/policy-sets/')) {
        return jsonResponse({ id: 'p', key: 'demo-project', name: 'Supplier Onboarding Policy' })
      }
      return jsonResponse(makeEnvelope())
    })
    render(<App />)
    await fillAndSubmit()

    fireEvent.click(screen.getByTestId('playground-verify'))
    await screen.findByTestId('verify-match', {}, { timeout: 3000 })

    expect(
      calls.some((call) =>
        call.url.endsWith('/api/policy-decisions/9c0f2d4b-1a7e-4f31-9b02-6d5c8e1a3f77'),
      ),
    ).toBe(true)
    expect(screen.getByTestId('verify-decision-hash-returned').textContent).toBe('c'.repeat(64))
    expect(screen.getByTestId('verify-decision-hash-stored').textContent).toBe('c'.repeat(64))
    expect(screen.getByTestId('verify-comparison').querySelectorAll('.compare__row')).toHaveLength(5)
    expect(screen.getByTestId('verify-match').textContent).toContain('Stored receipt matches.')
  })

  it('renders an undismissible mismatch band when the stored hash differs', async () => {
    let verified = false
    installFetch((url: string) => {
      if (url.includes('/active-version')) return jsonResponse({ id: 'v', version_number: 7 })
      if (url.includes('/api/policy-sets/')) {
        return jsonResponse({ id: 'p', key: 'demo-project', name: 'Supplier Onboarding Policy' })
      }
      if (verified) return jsonResponse(makeEnvelope({ decision_hash: 'd'.repeat(64) }))
      verified = true
      return jsonResponse(makeEnvelope())
    })
    render(<App />)
    await fillAndSubmit()

    fireEvent.click(screen.getByTestId('playground-verify'))
    const band = await screen.findByTestId('verify-mismatch', {}, { timeout: 3000 })

    expect(band.textContent).toContain('does not match')
    expect(band.textContent).toContain('Do not treat this decision as evidence.')
    expect(band.querySelectorAll('button')).toHaveLength(0)
  })

  it('fails verification when the stored guidance is empty and the returned one is absent', async () => {
    const returned = makeEnvelope()
    returned.request = { ...returned.request, additional_instructions: undefined }
    const stored = makeEnvelope()
    stored.request = { ...stored.request, additional_instructions: '' }

    let verified = false
    installFetch((url: string) => {
      if (url.includes('/active-version')) return jsonResponse({ id: 'v', version_number: 7 })
      if (url.includes('/api/policy-sets/')) {
        return jsonResponse({ id: 'p', key: 'demo-project', name: 'Supplier Onboarding Policy' })
      }
      if (verified) return jsonResponse(stored)
      verified = true
      return jsonResponse(returned)
    })
    render(<App />)
    await fillAndSubmit()

    fireEvent.click(screen.getByTestId('playground-verify'))
    await screen.findByTestId('verify-mismatch', {}, { timeout: 3000 })

    expect(screen.getByTestId('verify-guidance-mismatch').textContent).toContain(
      'The stored caller guidance is not the guidance you sent.',
    )
    expect(screen.getByTestId('verify-guidance-returned').textContent).toBe('absent')
    expect(screen.getByTestId('verify-guidance-stored').textContent).toBe('empty string')
  })

  it.each([
    [403, 'This receipt may be read by the caller who made the decision, or by a policy author or administrator.'],
    [409, 'The decision is still being written. It cannot be verified yet.'],
    [410, 'The stored receipt failed and has no verdict to serve.'],
  ])('renders its own copy for a GET %i', async (status, heading) => {
    let verified = false
    installFetch((url: string) => {
      if (url.includes('/active-version')) return jsonResponse({ id: 'v', version_number: 7 })
      if (url.includes('/api/policy-sets/')) {
        return jsonResponse({ id: 'p', key: 'demo-project', name: 'Supplier Onboarding Policy' })
      }
      if (verified) return jsonResponse({ detail: { code: 'x' } }, { status: status as number })
      verified = true
      return jsonResponse(makeEnvelope())
    })
    render(<App />)
    await fillAndSubmit()

    fireEvent.click(screen.getByTestId('playground-verify'))
    const band = await screen.findByTestId('verify-unavailable', {}, { timeout: 3000 })
    expect(band.textContent).toContain(heading)
    cleanup()
  })
})