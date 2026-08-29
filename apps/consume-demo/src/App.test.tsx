// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { makeEnvelope, makeNonAnsweredEnvelope } from './lib/testFixtures'
import { DECISION_STATUSES, type CaseDecisionEnvelope } from './contracts/caseDecision'

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
function standardHandler(envelope: CaseDecisionEnvelope = makeEnvelope()) {
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

  it('shows all three sections', () => {
    installFetch(standardHandler())
    render(<App />)
    expect(screen.getByTestId('inspector-tab-json')).toBeTruthy()
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

  it('says beside the field that showing a credential is a local-demo choice', () => {
    installFetch(standardHandler())
    render(<App />)
    const warning = screen.getByTestId('playground-subscription-key-warning')
    const text = warning.textContent ?? ''

    expect(text).toContain('Local demonstration only')
    expect(text).toContain('production browser client must never hold a shared subscription key')
    // The field points at the warning, so a screen reader reaches it rather
    // than only a sighted reader who happens to look below the input.
    expect(
      screen.getByTestId('playground-subscription-key').getAttribute('aria-describedby'),
    ).toContain('pg-subscription-key-warning')
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

  it('warns about a reused key when the request changed, without disabling submit', async () => {
    installFetch(standardHandler())
    render(<App />)
    fireEvent.change(screen.getByTestId('playground-idempotency-key'), { target: { value: 'k-1' } })
    await fillAndSubmit()

    expect(screen.queryByTestId('playground-idempotency-conflict')).toBeNull()

    fireEvent.change(screen.getByTestId('playground-additional-instructions'), {
      target: { value: 'now something different' },
    })

    expect(screen.getByTestId('playground-idempotency-conflict').textContent).toBe(
      'Request changed; sending with this key may return 409',
    )
    expect(screen.getByTestId('inspector-changed-chip')).toBeTruthy()
    // The 409 is the demonstration. Blocking the send would hide it.
    expect(screen.getByTestId('playground-submit').getAttribute('aria-disabled')).toBe('false')
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
    const spoken = Array.from(document.body.querySelectorAll<HTMLElement>('section, .banner'))
      .filter((node) => !raw.contains(node) && !node.contains(raw))
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

  it('keeps the previous receipt, dimmed and marked, after a failed refresh', async () => {
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

    expect(screen.getByTestId('playground-receipt').getAttribute('data-stale')).toBe('true')
    expect(screen.getByTestId('playground-stale-caption').textContent).toBe(
      'Previous decision, not refreshed',
    )
    expect(screen.getByTestId('receipt-decision-id')).toBeTruthy()
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