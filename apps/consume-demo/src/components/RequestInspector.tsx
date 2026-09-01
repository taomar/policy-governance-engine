import { useEffect, useState, type RefObject } from 'react'
import { INSPECTOR } from '../copy/strings'
import {
  MAX_ADDITIONAL_INSTRUCTIONS_CHARS,
  type CaseDecisionLightEnvelope,
  type CaseDecisionReceipt,
  type PlaygroundResponseMode,
  type PolicyRetrievalEnvelope,
  type TraceRef,
} from '../contracts/caseDecision'
import { CodeBlock, renderJsonLine } from './CodeBlock'
import { subscriptionKeyHeaderLine } from '../lib/subscriptionKey'
import {
  casePath,
  hostFromBase,
  lightCasePath,
  policiesPath,
  policyRequestBodyJson,
  policyRequestBodyWire,
  requestBodyJson,
  requestBodyWire,
  type DocketValues,
} from '../lib/requestBody'

/**
 * The hinge of the page.
 *
 * Everything above this component is editable; everything below it is returned
 * fact. It exists so the question "what exactly did you send?" is asked and
 * answered *before* the decision exists, rather than being a claim made after
 * the fact that the audience has to take on trust. It is also why the results
 * column is never an empty void on first load.
 *
 * Four sections, and each one is doing a different job:
 *
 *   * `Request JSON` is the body, byte for byte, with the guidance key absent
 *     when there is no guidance -- because that is what will be on the wire.
 *   * `Response JSON` is the full returned envelope, exactly as the page holds
 *     it. Before the first response it says so rather than showing an empty
 *     code block.
 *   * `Caller guidance` is the page's central safety statement, rendered as two
 *     registers that cannot be mistaken for one control: what the caller may
 *     edit, and what the server owns and will not expose.
 *   * `Raw HTTP` is the whole request including its headers, with the
 *     `X-Policy-Subscription-Key` value shown as it will be sent. That is a
 *     deliberate reversal of the earlier masking, and it applies to this local
 *     demonstration and the operator-generated key it is pointed at: a raw
 *     request with asterisks where the credential goes cannot be pasted,
 *     compared against a failing call, or checked for the typo that causes most
 *     first-integration 401s. What has not changed is that the value is never
 *     persisted anywhere the tab outlives, and that the *exported* snippets
 *     read `$POLICY_SUBSCRIPTION_KEY` instead of carrying a literal.
 *
 * On a narrow screen the tab strip becomes a ruled register of collapsible
 * rows. It renders the same nodes with the same test ids: no content becomes
 * unreachable because a window got smaller.
 */

type SectionId = 'json' | 'response' | 'guidance' | 'http'

const SECTIONS: { id: SectionId; label: string; testId: string }[] = [
  { id: 'json', label: INSPECTOR.tabJson, testId: 'inspector-tab-json' },
  { id: 'response', label: INSPECTOR.tabResponse, testId: 'inspector-tab-response' },
  { id: 'guidance', label: INSPECTOR.tabGuidance, testId: 'inspector-tab-guidance' },
  { id: 'http', label: INSPECTOR.tabHttp, testId: 'inspector-tab-http' },
]

export interface InspectorProps {
  values: DocketValues
  baseUrl: string
  projectKey: string
  /** Rendered into the Raw HTTP header block. See `lib/subscriptionKey.ts`. */
  subscriptionKey: string
  correlationId: string
  idempotencyKey: string
  responseMode: PlaygroundResponseMode
  clientRequestHash: string
  /** True when a key is live and the hash has moved since it was last used. */
  requestChanged: boolean
  /** From the most recent receipt, when there is one. */
  trace: TraceRef | null
  /** The full response envelope, shown byte-for-byte as JSON after a request. */
  response: CaseDecisionReceipt | CaseDecisionLightEnvelope | PolicyRetrievalEnvelope | null
  guidanceRef: RefObject<HTMLTextAreaElement | null>
  onAnnounce: (message: string) => void
}

export function RequestInspector(props: InspectorProps) {
  const [active, setActive] = useState<SectionId>('json')
  const [openRows, setOpenRows] = useState<Record<SectionId, boolean>>({
    json: true,
    response: false,
    guidance: false,
    http: false,
  })
  const [narrow, setNarrow] = useState(false)

  // The register form is not a CSS-only transformation, because each row must
  // be a real `aria-expanded` button controlling a real region. The breakpoint
  // matches the stylesheet's so the two forms never both appear.
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const query = window.matchMedia('(max-width: 899px)')
    const apply = () => setNarrow(query.matches)
    apply()
    query.addEventListener('change', apply)
    return () => query.removeEventListener('change', apply)
  }, [])

  const decisionRequest = props.responseMode !== 'policies'
  const guidance = decisionRequest ? props.values.additionalInstructions.trim() : ''
  const bodyJson = decisionRequest
    ? requestBodyJson(props.values)
    : policyRequestBodyJson(props.values)
  const bodyWire = decisionRequest
    ? requestBodyWire(props.values)
    : policyRequestBodyWire(props.values)
  const path =
    props.responseMode === 'decision'
      ? casePath(props.projectKey)
      : props.responseMode === 'decision-light'
        ? lightCasePath(props.projectKey)
        : policiesPath(props.projectKey)

  const httpLines = [
    `POST ${path} HTTP/1.1`,
    `Host: ${hostFromBase(props.baseUrl)}`,
    subscriptionKeyHeaderLine(props.subscriptionKey),
    'Content-Type: application/json',
    `X-Correlation-Id: ${props.correlationId}`,
    ...(decisionRequest && props.idempotencyKey.trim()
      ? [`Idempotency-Key: ${props.idempotencyKey.trim()}`]
      : []),
    '',
    bodyWire,
  ]
  const httpText = httpLines.join('\n')

  function onTabKeyDown(event: React.KeyboardEvent, index: number) {
    const last = SECTIONS.length - 1
    let next: number | null = null
    if (event.key === 'ArrowRight') next = index === last ? 0 : index + 1
    else if (event.key === 'ArrowLeft') next = index === 0 ? last : index - 1
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = last
    if (next === null) return
    event.preventDefault()
    const section = SECTIONS[next]
    setActive(section.id)
    // Activation follows focus, so the panel a keyboard user is reading is
    // always the one their focus is on.
    document.getElementById(`inspector-tab-${section.id}`)?.focus()
  }

  const jsonPanel = (
    <>
      <CodeBlock
        text={bodyJson}
        language="JSON"
        what="the request JSON"
        downloadName="case-request.json"
        testId="inspector-json-code"
        onAnnounce={props.onAnnounce}
        renderLine={renderJsonLine}
        caption={decisionRequest ? INSPECTOR.jsonCaption : INSPECTOR.policiesJsonCaption}
      />
      {decisionRequest ? (
        <>
          <p className="small" style={{ marginTop: 8 }}>
            <span className="eyebrow">{INSPECTOR.hashLabel}</span>
            <br />
            <code className="mono" data-testid="inspector-request-hash">
              {props.clientRequestHash}
            </code>
          </p>
          <p className="field__caption">{INSPECTOR.hashCaption}</p>
        </>
      ) : null}
    </>
  )

  const guidancePanel = decisionRequest ? (
    <div className="guidance-registers">
      <section
        className="guidance-editable"
        aria-labelledby="inspector-guidance-editable-heading"
        data-testid="inspector-guidance-editable"
      >
        <div className="register-head">
          <span className="register-head__label" id="inspector-guidance-editable-heading">
            {INSPECTOR.editableHeading}
          </span>
          <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span className="pill">{INSPECTOR.editablePill}</span>
            <span className="counter">
              {props.values.additionalInstructions.length} / {MAX_ADDITIONAL_INSTRUCTIONS_CHARS}
            </span>
          </span>
        </div>

        {guidance ? (
          <p className="guidance-quote" data-testid="inspector-guidance-text">
            {guidance}
          </p>
        ) : (
          <p className="muted small" data-testid="inspector-guidance-empty">
            {INSPECTOR.guidanceEmpty}
          </p>
        )}

        <p className="field__caption">{INSPECTOR.guidanceHelperEcho}</p>

        <span>
          <button
            type="button"
            className="btn btn--quiet"
            data-testid="inspector-guidance-edit"
            onClick={() => {
              props.guidanceRef.current?.focus()
              props.onAnnounce('Editing additional instructions.')
            }}
          >
            {INSPECTOR.edit}
          </button>
        </span>
      </section>

      {/* Not a warning band. This is how the system is designed to work, and
          colouring it as a hazard would teach the opposite. */}
      <p className="precedence-line">{INSPECTOR.precedence}</p>

      <section
        className="guidance-server"
        aria-labelledby="inspector-guidance-server-heading"
        data-testid="inspector-guidance-server"
      >
        <div className="register-head">
          <span className="register-head__label" id="inspector-guidance-server-heading">
            {INSPECTOR.serverHeading}
          </span>
          <span className="pill">{INSPECTOR.serverPill}</span>
        </div>

        {/* There is deliberately no control of any kind in this register --
            not even a disabled one. A disabled field implies a lock, and a
            lock implies a key. */}
        <div className="ledger" style={{ borderTop: '1px solid var(--border-subtle)' }}>
          <div className="ledger__row">
            <span className="ledger__label">Profile version</span>
            <span className="ledger__value">
              {props.trace ? (
                <code className="mono" data-testid="inspector-profile-version">
                  {props.trace.prompt_version ?? INSPECTOR.profileUnknown}
                </code>
              ) : (
                <span className="muted small" data-testid="inspector-profile-version">
                  {INSPECTOR.profileUnknownBeforeFirst}
                </span>
              )}            </span>
          </div>
          <div className="ledger__row">
            <span className="ledger__label">Guidance profile</span>
            <span className="ledger__value">
              {props.trace?.instruction_profile ? (
                <code className="mono" data-testid="inspector-instruction-profile">
                  {props.trace.instruction_profile}
                </code>
              ) : (
                <span className="muted small" data-testid="inspector-instruction-profile">
                  {props.trace ? INSPECTOR.profileUnknown : INSPECTOR.profileUnknownBeforeFirst}
                </span>
              )}
            </span>
          </div>
          <div className="ledger__row">
            <span className="ledger__label">Model deployment</span>
            <span className="ledger__value">
              <code className="mono mono--muted">{props.trace?.model_deployment ?? '—'}</code>
            </span>
          </div>
          <div className="ledger__row">
            <span className="ledger__label">Retrieval method</span>
            <span className="ledger__value">
              <code className="mono mono--muted">{props.trace?.retrieval_method ?? '—'}</code>
            </span>
          </div>
        </div>

        <p className="small">{INSPECTOR.serverDisclosure}</p>
        <p className="small muted">{INSPECTOR.serverProfileNote}</p>
      </section>
    </div>
  ) : (
    <p className="empty-state" data-testid="inspector-guidance-not-applicable">
      Policy JSON mode sends no caller guidance and runs no explanation stage.
    </p>
  )

  const responsePanel = props.response ? (
    <CodeBlock
      text={JSON.stringify(props.response, null, 2)}
      language="JSON"
      what="the full response JSON"
      downloadName={
        'decision_id' in props.response
          ? `${props.response.decision_id}.json`
          : 'filtered-policies.json'
      }
      testId="inspector-response-code"
      onAnnounce={props.onAnnounce}
      renderLine={renderJsonLine}
      maxHeight={520}
    />
  ) : (
    <p className="empty-state" data-testid="inspector-response-empty">
      {decisionRequest ? INSPECTOR.responseEmpty : INSPECTOR.policiesResponseEmpty}
    </p>
  )

  const httpPanel = (
    <>
      <CodeBlock
        text={httpText}
        /* Copy and Download emit exactly what is displayed, credential
           included. That is the point of this tab in a local demonstration —
           see the module docstring, and `docs/external-consumption.md` for why
           a production browser client must not hold this credential at all. */
        copyText={httpText}
        language="HTTP"
        what="the raw HTTP request"
        downloadName="case-request.http"
        downloadMime="text/plain"
        testId="inspector-http-code"
        onAnnounce={props.onAnnounce}
      />
      <p className="field__caption" data-testid="inspector-http-auth-caption">
        {INSPECTOR.subscriptionKeyCaption}
      </p>
    </>
  )

  const panels: Record<SectionId, React.ReactNode> = {
    json: jsonPanel,
    response: responsePanel,
    guidance: guidancePanel,
    http: httpPanel,
  }

  return (
    <section
      className="panel"
      data-testid="playground-request-inspector"
      aria-labelledby="inspector-heading"
      /* A live preview that re-announced on every keystroke would be unusable.
         The change is announced once, on blur, by the page's shared region. */
      aria-live="off"
      onBlur={() => props.onAnnounce(INSPECTOR.previewUpdated)}
    >
      <div className="panel__head">
        <h2 className="panel__title" id="inspector-heading">
          {INSPECTOR.title}
        </h2>
        {props.requestChanged ? (
          <span className="chip chip--note" data-testid="inspector-changed-chip">
            {INSPECTOR.changedChip}
          </span>
        ) : null}
        <p className="panel__subtitle">
          {props.responseMode === 'decision'
            ? INSPECTOR.subtitle
            : props.responseMode === 'decision-light'
              ? INSPECTOR.lightSubtitle
              : INSPECTOR.policiesSubtitle}
        </p>
      </div>

      {narrow ? (
        <div className="panel__body panel__body--flush">
          {SECTIONS.map((section) => (
            <div key={section.id}>
              <button
                type="button"
                className="register-toggle"
                style={{ display: 'block' }}
                aria-expanded={openRows[section.id]}
                aria-controls={`inspector-panel-${section.id}`}
                onClick={() =>
                  setOpenRows((rows) => ({ ...rows, [section.id]: !rows[section.id] }))
                }
              >
                {openRows[section.id] ? '▾ ' : '▸ '}
                {section.label}
              </button>
              <div
                id={`inspector-panel-${section.id}`}
                data-testid={section.testId}
                hidden={!openRows[section.id]}
                style={{ padding: 'var(--card-pad)' }}
              >
                {panels[section.id]}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <>
          <div className="tabstrip" role="tablist" aria-label="Request inspector sections">
            {SECTIONS.map((section, index) => (
              <button
                key={section.id}
                type="button"
                role="tab"
                id={`inspector-tab-${section.id}`}
                className="tabstrip__tab"
                aria-selected={active === section.id}
                aria-controls={`inspector-panel-${section.id}`}
                tabIndex={active === section.id ? 0 : -1}
                onKeyDown={(event) => onTabKeyDown(event, index)}
                onClick={() => setActive(section.id)}
              >
                {section.label}
              </button>
            ))}
          </div>
          {SECTIONS.map((section) => (
            <div
              key={section.id}
              role="tabpanel"
              id={`inspector-panel-${section.id}`}
              aria-labelledby={`inspector-tab-${section.id}`}
              data-testid={section.testId}
              tabIndex={0}
              hidden={active !== section.id}
              className="panel__body"
            >
              {panels[section.id]}
            </div>
          ))}
        </>
      )}
    </section>
  )
}
