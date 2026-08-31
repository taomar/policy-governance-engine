import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import './playground.css'

import { HEADER, PERSISTENCE_FAILURE, RECEIPT, V2, WAIT } from './copy/strings'
import {
  classifyReceipt,
  type CaseDecisionEnvelope,
  type CaseDecisionEnvelopeV2,
  type CaseDecisionReceipt,
  type MergedCitationRef,
  type ReasoningEffort,
} from './contracts/caseDecision'
import { fetchActiveVersion, fetchPolicySet, getReceipt, postCase } from './lib/apiClient'
import {
  additionalInstructionsHash,
  normaliseAdditionalInstructions,
  requestHash,
  scenarioHash,
} from './lib/canonicalHash'
import type { PlaygroundError } from './lib/errors'
import { formatElapsed } from './lib/format'
import { newUuid } from './lib/identifiers'
import { compareReceipts } from './lib/receiptComparison'
import { buildRequestBody, hostFromBase, isParsableUrl, type DocketValues } from './lib/requestBody'

import { CodeBlock, renderJsonLine } from './components/CodeBlock'
import { CaseOutcomeBand } from './components/CaseOutcomeBand'
import { DecisionReceipt } from './components/DecisionReceipt'
import { DecisionStatusBand } from './components/DecisionStatusBand'
import { ErrorBand, StaleCaption } from './components/ErrorBand'
import { EvidenceTable } from './components/EvidenceTable'
import { GroundingNotices } from './components/GroundingNotices'
import { InformationPanel } from './components/InformationPanel'
import { LanguagePanel } from './components/LanguagePanel'
import { RequestDocket, type ResolutionState } from './components/RequestDocket'
import { RequestInspector } from './components/RequestInspector'
import { ResultGrid } from './components/ResultGrid'
import { RetrievalDisclosure } from './components/RetrievalDisclosure'
import { VerdictPanel } from './components/VerdictPanel'
import type { VerifyState } from './components/VerifyReceipt'

/**
 * One page, one request, one receipt.
 *
 * There is no router, no store and no persistence layer. Every piece of state
 * below lives for the life of this component and dies with the tab, which is
 * the only honest way to hold a credential in a browser page whose entire
 * purpose is to demonstrate that the API needs nothing but a URL and a
 * credential.
 *
 * The two invariants that shape the whole component:
 *
 *   * **Status before verdict.** `envelope` is the only source of the result,
 *     and every result component reads `decision_status` before it renders
 *     anything else. The verdict node is not rendered for the six statuses that
 *     do not carry one.
 *
 *   * **A persistence failure is an error, not a success with a caveat.** The
 *     `500 decision_receipt_failed` path renders the error band and *no*
 *     verdict, result grid, receipt or hash, regardless of any decision payload
 *     the body happens to contain.
 */

/**
 * The committed fallback is the repository-standard local API address, the same
 * one `apps/web/.env.example` and the configuration docs name. A machine running
 * the API somewhere else sets `VITE_POLICY_API_BASE_URL` in its own uncommitted
 * `.env`; baking one developer's port into the source would send every other
 * reader's first request to a closed socket.
 */
const DEFAULT_BASE =
  (import.meta.env.VITE_POLICY_API_BASE_URL as string | undefined) ?? 'http://localhost:8010'

/**
 * The subscription key this demonstration starts with, if the machine running
 * it declared one.
 *
 * `VITE_POLICY_SUBSCRIPTION_KEY` is read from `apps/consume-demo/.env.local`,
 * which is git-ignored. The committed fallback is the empty string and must
 * stay that way: Vite inlines every `VITE_`-prefixed value into the built
 * bundle, so a key committed here would be a key served to every visitor of
 * `dist/`.
 *
 * This exists because the demo is pointed at a local API with a key the
 * operator generated for local use, and retyping a forty-character credential
 * on every reload is how people end up pasting it somewhere that keeps it. It
 * is a local-demonstration convenience and is documented as one — a production
 * browser client must not hold a shared subscription key at all, because the
 * browser is not a place a shared credential can be kept.
 */
const PREFILLED_SUBSCRIPTION_KEY =
  (import.meta.env.VITE_POLICY_SUBSCRIPTION_KEY as string | undefined) ?? ''

function readPrefill(): { base?: string; key?: string } {
  if (typeof window === 'undefined') return {}
  const params = new URLSearchParams(window.location.search)
  // Base and key may be prefilled from the URL. The subscription key and the scenario are
  // deliberately never read from it and never written to it: a URL is logged by
  // every proxy between here and the server, and it survives in history.
  return {
    base: params.get('base') ?? undefined,
    key: params.get('key') ?? undefined,
  }
}

/**
 * What the live region says when a decision lands.
 *
 * A screen-reader user gets one sentence, and for a v2 receipt one sentence has
 * to carry two outcomes — announcing only the verdict would tell someone whose
 * information question was answered that nothing came back. So both tracks are
 * named, and the determination is spoken only when one was reached.
 */
function announceReceipt(receipt: CaseDecisionReceipt): string {
  if (classifyReceipt(receipt) === 'v2') {
    const v2 = receipt as CaseDecisionEnvelopeV2
    const information = `Information ${v2.outcome.information.replace(/_/g, ' ')}`
    const verdict = `verdict ${v2.outcome.verdict.replace(/_/g, ' ')}`
    const reached = v2.verdict?.reached && v2.verdict.decision ? ` ${v2.verdict.decision}` : ''
    const facts = v2.verdict?.missing_information?.length ?? 0
    const blocked =
      v2.outcome.verdict === 'missing_required_facts' && facts > 0
        ? ` ${facts} ${facts === 1 ? 'fact is' : 'facts are'} needed.`
        : ''
    return `${information}, ${verdict}.${reached}${blocked}`
  }

  if (classifyReceipt(receipt) === 'v1') {
    const v1 = receipt as CaseDecisionEnvelope
    return `Decision ${v1.decision_status}. ${
      v1.decision_status === 'answered' && v1.decision.verdict
        ? v1.decision.verdict
        : 'No verdict.'
    }`
  }

  return 'A receipt was returned in an envelope this page does not recognise.'
}

export default function App() {
  const prefill = useMemo(readPrefill, [])

  const [baseUrl, setBaseUrl] = useState(prefill.base ?? DEFAULT_BASE)
  const [projectKey, setProjectKey] = useState(prefill.key ?? '')
  /** The credential. React state and nowhere else, for the life of this tab. */
  const [subscriptionKey, setSubscriptionKey] = useState(PREFILLED_SUBSCRIPTION_KEY)

  const [scenario, setScenario] = useState('')
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>('medium')
  const [callingSystemIdentity, setCallingSystemIdentity] = useState('playground-demo')
  const [idempotencyKey, setIdempotencyKey] = useState('')
  const [additionalInstructions, setAdditionalInstructions] = useState('')
  const [correlationId, setCorrelationId] = useState(() => newUuid())

  const [resolution, setResolution] = useState<ResolutionState>({ kind: 'idle' })
  const [submitting, setSubmitting] = useState(false)
  const [elapsedMs, setElapsedMs] = useState(0)
  const [envelope, setEnvelope] = useState<CaseDecisionReceipt | null>(null)
  const [sentGuidance, setSentGuidance] = useState<string | undefined>(undefined)
  const [submittedHash, setSubmittedHash] = useState<string | null>(null)
  const [error, setError] = useState<PlaygroundError | null>(null)
  const [verifyState, setVerifyState] = useState<VerifyState>({ kind: 'idle' })
  const [announcement, setAnnouncement] = useState('')
  const [docketCollapsed, setDocketCollapsed] = useState(false)

  const guidanceRef = useRef<HTMLTextAreaElement | null>(null)
  const scenarioRef = useRef<HTMLTextAreaElement | null>(null)
  const subscriptionKeyRef = useRef<HTMLInputElement | null>(null)
  const keyRef = useRef<HTMLInputElement | null>(null)
  const resultsRef = useRef<HTMLDivElement | null>(null)

  const onAnnounce = useCallback((message: string) => setAnnouncement(message), [])

  const values: DocketValues = useMemo(
    () => ({ scenario, reasoningEffort, callingSystemIdentity, additionalInstructions }),
    [scenario, reasoningEffort, callingSystemIdentity, additionalInstructions],
  )

  // The preview hash is computed over the same preimage the server binds an
  // idempotency key to, so changing the guidance visibly rotates it and the
  // 409 that follows a reused key is predictable rather than surprising.
  const normalisedGuidance = useMemo(
    () => normaliseAdditionalInstructions(additionalInstructions),
    [additionalInstructions],
  )
  const clientRequestHash = useMemo(
    () =>
      requestHash({
        policySetKey: projectKey.trim(),
        scenario: scenario.trim(),
        provisionId: null,
        reasoningEffort,
        additionalInstructions: normalisedGuidance,
      }),
    [projectKey, scenario, reasoningEffort, normalisedGuidance],
  )
  const clientScenarioHash = useMemo(() => scenarioHash(scenario.trim()), [scenario])
  const clientGuidanceHash = useMemo(
    () => additionalInstructionsHash(normalisedGuidance),
    [normalisedGuidance],
  )

  const idempotencyConflict =
    idempotencyKey.trim().length > 0 &&
    submittedHash !== null &&
    submittedHash !== clientRequestHash

  /* ---------- project resolution (debounced) ---------- */

  useEffect(() => {
    const key = projectKey.trim()
    if (!key || !isParsableUrl(baseUrl) || !subscriptionKey.trim()) {
      setResolution({ kind: 'idle' })
      return
    }

    const controller = new AbortController()
    setResolution({ kind: 'resolving' })

    const timer = setTimeout(async () => {
      const setResult = await fetchPolicySet({ baseUrl, projectKey: key, subscriptionKey, signal: controller.signal })
      if (controller.signal.aborted) return

      if (!setResult.ok) {
        if (setResult.error.status === 404) setResolution({ kind: 'not-found', key })
        else setResolution({ kind: 'unreadable', message: setResult.error.heading })
        return
      }

      const versionResult = await fetchActiveVersion({
        baseUrl,
        projectKey: key,
        subscriptionKey,
        signal: controller.signal,
      })
      if (controller.signal.aborted) return

      const version = versionResult.ok ? versionResult.value : null
      setResolution({
        kind: 'resolved',
        identity: {
          id: setResult.value.id,
          key: setResult.value.key,
          name: setResult.value.name,
          activeVersionNumber:
            version?.version_number ?? setResult.value.active_version_number ?? null,
          activeVersionId: version?.id ?? setResult.value.active_version_id ?? null,
        },
      })
    }, 400)

    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [baseUrl, projectKey, subscriptionKey])

  /* ---------- elapsed timer ---------- */

  useEffect(() => {
    if (!submitting) return
    const started = Date.now()
    setElapsedMs(0)
    const timer = setInterval(() => setElapsedMs(Date.now() - started), 1000)
    return () => clearInterval(timer)
  }, [submitting])

  /* ---------- submit ---------- */

  const submitDisabledReason = useMemo((): string | null => {
    if (!isParsableUrl(baseUrl)) return 'Set a valid API base URL before sending.'
    if (!projectKey.trim()) return 'Enter the project key before sending.'
    if (!subscriptionKey.trim()) return 'Paste your API subscription key before sending.'
    if (scenario.trim().length < 12) return 'Describe the case in at least 12 characters.'
    if (resolution.kind === 'not-found') return 'No project is published under this key.'
    if (resolution.kind === 'resolved' && resolution.identity.activeVersionNumber === null)
      return 'No published version to decide against'
    return null
  }, [baseUrl, projectKey, subscriptionKey, scenario, resolution])

  const submit = useCallback(async () => {
    if (submitDisabledReason !== null || submitting) return

    const guidanceForThisCall = buildRequestBody(values).additional_instructions
    const hashForThisCall = clientRequestHash

    setSubmitting(true)
    setError(null)
    setVerifyState({ kind: 'idle' })

    const result = await postCase({
      baseUrl,
      projectKey,
      subscriptionKey,
      correlationId,
      idempotencyKey,
      values,
    })

    setSubmitting(false)
    setSubmittedHash(hashForThisCall)

    if (!result.ok) {
      // The previous receipt is kept and dimmed rather than dropped; `envelope`
      // is deliberately not cleared here.
      setError(result.error)
      // Focus moves to whatever the caller has to change.
      const focusMap: Record<string, HTMLElement | null> = {
        'focus-subscription-key': subscriptionKeyRef.current,
        'focus-key': keyRef.current,
        'focus-scenario': scenarioRef.current,
        'focus-guidance': guidanceRef.current,
      }
      focusMap[result.error.recovery]?.focus()
      return
    }

    setEnvelope(result.value)
    setSentGuidance(guidanceForThisCall)
    setDocketCollapsed(true)
    // A fresh correlation id for the next call, so the value on screen is
    // always the one the *next* request will carry.
    setCorrelationId(newUuid())

    onAnnounce(announceReceipt(result.value))

    requestAnimationFrame(() => {
      const heading = resultsRef.current?.querySelector<HTMLElement>('#result-heading')
      heading?.focus()
      // Guarded because jsdom has no layout and therefore no scrollIntoView.
      // Scrolling is a courtesy; focus is the accessibility contract, and the
      // courtesy must not be able to break it.
      resultsRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
    })
  }, [
    baseUrl,
    clientRequestHash,
    correlationId,
    idempotencyKey,
    onAnnounce,
    projectKey,
    submitDisabledReason,
    submitting,
    subscriptionKey,
    values,
  ])

  /* ---------- verification ---------- */

  const verify = useCallback(
    async (decisionId?: string) => {
      const id = decisionId ?? envelope?.decision_id
      if (!id) return
      setVerifyState({ kind: 'verifying' })

      const result = await getReceipt({ baseUrl, decisionId: id, subscriptionKey })
      if (!result.ok) {
        setVerifyState({ kind: 'unavailable', error: result.error })
        return
      }
      if (!envelope) {
        // A lookup after a timeout: there is nothing to compare against, so the
        // stored receipt becomes the result rather than a comparison.
        setEnvelope(result.value)
        setVerifyState({ kind: 'idle' })
        return
      }
      setVerifyState({ kind: 'compared', comparison: compareReceipts(envelope, result.value) })
    },
    [baseUrl, envelope, subscriptionKey],
  )

  /* ---------- render ---------- */

  // A persistence failure suppresses the entire result region. This is the
  // strictest reading of "a receipt that was not stored is not a usable
  // success", and it is deliberate.
  const persistenceFailed = error?.code === 'decision_receipt_failed'
  const showResult = envelope !== null && !persistenceFailed
  const stale = showResult && error !== null

  // The tag decides which answer shape is rendered. `unrecognised` is a real
  // third branch rather than a fall-through to v1: reading `.decision` off an
  // envelope that has none is what put a white screen where this receipt should
  // have been, and the honest response to an envelope this build has never seen
  // is to render the identity and the raw body and interpret nothing.
  const kind = envelope ? classifyReceipt(envelope) : null
  const v2 = kind === 'v2' ? (envelope as CaseDecisionEnvelopeV2) : null
  const v1 = kind === 'v1' ? (envelope as CaseDecisionEnvelope) : null

  const v2Citations: MergedCitationRef[] = v2?.citations ?? []
  const v1Citations: MergedCitationRef[] = v1?.citations ?? []

  const requestInspector = (
    <RequestInspector
      values={values}
      baseUrl={baseUrl}
      projectKey={projectKey}
      subscriptionKey={subscriptionKey}
      correlationId={correlationId}
      idempotencyKey={idempotencyKey}
      clientRequestHash={clientRequestHash}
      requestChanged={idempotencyConflict}
      trace={envelope?.trace ?? null}
      response={envelope}
      guidanceRef={guidanceRef}
      onAnnounce={onAnnounce}
    />
  )

  return (
    <>
      <header className="pg-header" role="banner">
        <div className="pg-header__inner">
          <h1 className="pg-header__title">{HEADER.title}</h1>
          <span className="pg-header__eyebrow">{HEADER.eyebrow}</span>
          <span className="pg-header__conn" data-testid="playground-connection">
            {hostFromBase(baseUrl)} · {projectKey.trim() || 'no project'}
          </span>
        </div>
      </header>

      <div className="pg-intro">
        <p className="pg-intro__purpose">{HEADER.purpose}</p>
        {/* Plain secondary text, never a red or amber alert band. A frightening
            banner on every load trains people to ignore banners. */}
        <p className="pg-intro__note" data-testid="playground-demo-note">
          {HEADER.demoNote}
        </p>
      </div>

      <main className="pg-main">
        <RequestDocket
          baseUrl={baseUrl}
          onBaseUrl={setBaseUrl}
          projectKey={projectKey}
          onProjectKey={setProjectKey}
          subscriptionKey={subscriptionKey}
          onSubscriptionKey={setSubscriptionKey}
          subscriptionKeyPrefilled={PREFILLED_SUBSCRIPTION_KEY.length > 0}
          scenario={scenario}
          onScenario={setScenario}
          reasoningEffort={reasoningEffort}
          onReasoningEffort={setReasoningEffort}
          callingSystemIdentity={callingSystemIdentity}
          onCallingSystemIdentity={setCallingSystemIdentity}
          idempotencyKey={idempotencyKey}
          onIdempotencyKey={setIdempotencyKey}
          additionalInstructions={additionalInstructions}
          onAdditionalInstructions={setAdditionalInstructions}
          correlationId={correlationId}
          onRegenerateCorrelation={() => setCorrelationId(newUuid())}
          resolution={resolution}
          submitting={submitting}
          submitDisabledReason={submitDisabledReason}
          onSubmit={submit}
          idempotencyConflict={idempotencyConflict}
          guidanceRef={guidanceRef}
          scenarioRef={scenarioRef}
          subscriptionKeyRef={subscriptionKeyRef}
          keyRef={keyRef}
          onAnnounce={onAnnounce}
          collapsed={docketCollapsed}
          onExpand={() => setDocketCollapsed(false)}
        />

        {/* Before a response exists the inspector remains close to the composer
            so the request can be checked before it is sent. Once Rule evidence
            exists, the same inspector moves directly below that evidence. */}
        {!showResult ? requestInspector : null}

        <div className="pg-results" ref={resultsRef}>
          {submitting ? (
            <div className="wait-strip" role="status" aria-live="polite" data-testid="playground-wait">
              <strong>
                {WAIT.line1} ·{' '}
                <span aria-hidden="true" data-testid="playground-elapsed">
                  {formatElapsed(elapsedMs)} {WAIT.elapsedSuffix}
                </span>
              </strong>
              <span className="small muted">{WAIT.line2}</span>
              {elapsedMs > 20_000 ? <span className="small muted">{WAIT.long}</span> : null}
            </div>
          ) : null}

          {error ? (
            <ErrorBand
              error={error}
              baseUrl={baseUrl}
              onRetry={submit}
              onGenerateKey={() => {
                setIdempotencyKey(newUuid())
                document.querySelector<HTMLElement>('[data-testid="playground-submit"]')?.focus()
              }}
              onLookup={(id) => void verify(id)}
              onAnnounce={onAnnounce}
            />
          ) : null}

          {persistenceFailed ? (
            <div className="banner banner--deny" data-testid="playground-persistence-failure">
              <strong className="banner__heading">{PERSISTENCE_FAILURE}</strong>
            </div>
          ) : null}

          {stale ? <StaleCaption /> : null}

          {showResult && envelope ? (
            <>
              {/* ---------- case_decision_v2: two tracks ---------- */}
              {v2 ? (
                <>
                  {/* Asked, then how each track came out. Everything below is
                      read in the light of this band, which is why it is first
                      and why the reading order below follows it: verdict and
                      the facts it is blocked on, then what the policies state,
                      then the evidence both rest on. */}
                  <CaseOutcomeBand envelope={v2} stale={stale} />

                  <GroundingNotices
                    tracks={[
                      { track: 'verdict', grounding: v2.verdict?.grounding },
                      { track: 'information', grounding: v2.information?.grounding },
                    ]}
                    size={v2.size}
                  />

                  {/* A section is rendered exactly when the server carried one.
                      `not_requested` and `not_evaluated` produce no section, and
                      the band above has already said which of the two it was --
                      printing an empty panel would invite a reader to take the
                      emptiness for a finding. */}
                  {v2.verdict ? (
                    <VerdictPanel section={v2.verdict} onAnnounce={onAnnounce} />
                  ) : null}

                  {v2.information ? <InformationPanel section={v2.information} /> : null}

                  <EvidenceTable citations={v2Citations} baseUrl={baseUrl} />
                </>
              ) : null}

              {/* ---------- case_decision_v1: one status ---------- */}
              {v1 ? (
                <>
                  <DecisionStatusBand envelope={v1} stale={stale} />
                  <ResultGrid envelope={v1} onAnnounce={onAnnounce} />
                  <EvidenceTable
                    citations={v1Citations}
                    baseUrl={baseUrl}
                    fallbackRoute={v1.decision.decider_route}
                  />
                </>
              ) : null}

              {requestInspector}

              {v2 ? (
                <>
                  <RetrievalDisclosure envelope={v2} baseUrl={baseUrl} />
                  {/* Provenance, with the rest of the provenance: which language
                      each stage worked in, what was actually adjudicated, and
                      the standing claim that the quotations above were not
                      rendered into anything. */}
                  <LanguagePanel
                    language={v2.language}
                    requestScenario={v2.request.scenario}
                    onAnnounce={onAnnounce}
                  />
                </>
              ) : null}

              {v1 ? <RetrievalDisclosure envelope={v1} baseUrl={baseUrl} /> : null}

              {/* ---------- an envelope this build has never seen ---------- */}
              {kind === 'unrecognised' ? (
                <div className="banner banner--action" data-testid="playground-unrecognised">
                  <strong className="banner__heading">{V2.unrecognisedHeading}</strong>
                  <span className="banner__body">{V2.unrecognisedBody}</span>
                </div>
              ) : null}

              {/* The receipt reads only fields both envelopes carry, so it is
                  rendered once for every version -- including one this build
                  does not recognise, whose identity and seal are still real. */}
              <DecisionReceipt
                envelope={envelope}
                sentGuidance={sentGuidance}
                clientRequestHash={clientRequestHash}
                clientScenarioHash={clientScenarioHash}
                clientGuidanceHash={clientGuidanceHash}
                stale={stale}
                verifyState={verifyState}
                onVerify={() => void verify()}
                onAnnounce={onAnnounce}
              />

              <details
                className="panel disclosure"
                data-testid="playground-raw-json"
                open={
                  kind === 'unrecognised' ||
                  v1?.decision_status === 'not_evaluated' ||
                  (v2 !== null &&
                    v2.outcome.information === 'not_evaluated' &&
                    v2.outcome.verdict === 'not_evaluated')
                }
              >
                <summary>{RECEIPT.showRaw}</summary>
                <div className="panel__body">
                  <CodeBlock
                    text={JSON.stringify(envelope, null, 2)}
                    language="JSON"
                    what="the full decision envelope"
                    downloadName={`${envelope.decision_id}.json`}
                    maxHeight={420}
                    onAnnounce={onAnnounce}
                    renderLine={renderJsonLine}
                  />
                </div>
              </details>
            </>
          ) : !submitting && !error ? (
            <section className="panel">
              <div className="panel__body">
                <p className="empty-state">
                  No decision has been requested yet. The Request Inspector above shows the exact
                  request this page will send; the receipt, the evidence and the retrieval
                  disclosure appear here once the API answers.
                </p>
              </div>
            </section>
          ) : null}
        </div>
      </main>

      {/* One shared live region. The inspector announces its preview change on
          blur through this node rather than on every keystroke. */}
      <div className="visually-hidden" role="status" aria-live="polite" data-testid="playground-announcer">
        {announcement}
      </div>
    </>
  )
}
