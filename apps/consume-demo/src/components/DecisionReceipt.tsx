import type { EnvelopeCommon } from '../contracts/caseDecision'
import { RECEIPT } from '../copy/strings'
import { additionalInstructionsHash, scenarioHash } from '../lib/canonicalHash'
import { formatTimestamp } from '../lib/format'
import { guidanceEchoState } from '../lib/receiptComparison'
import { CodeBlock, CopyButton, renderJsonLine } from './CodeBlock'
import { VerifyReceipt, type VerifyState } from './VerifyReceipt'

/**
 * The screenshot anatomy, extended.
 *
 * Decision id → project → policy version → correlation → caller → timestamp →
 * envelope → receipt state, then the request as sent, then its hashes. Every
 * identifier is copyable because every identifier is something a reader will
 * eventually have to quote to somebody else.
 *
 * THE RULE THIS COMPONENT IS BUILT AROUND
 *
 * The `Request as sent` panel renders `request.scenario` and
 * `request.additional_instructions` **from the response**, never from local
 * React state. If the page rendered what it believed it sent, the receipt would
 * prove nothing -- it would be a screenshot of the form, not evidence of the
 * request. That is also why absent and empty guidance render as two different
 * things: they are two different things on the wire, and a receipt that cannot
 * tell them apart cannot be honest about what was asked.
 */

interface ReceiptProps {
  /**
   * Typed on the fields both envelopes share, because everything this panel
   * renders — identity, the request as sent, the seal — is common to v1 and v2.
   * The answer's shape is the only thing that differs between them, and the
   * answer is not rendered here.
   */
  envelope: EnvelopeCommon & { schema_version: string }
  /** What the docket held at submit time. Used only to detect a failed echo. */
  sentGuidance: string | undefined
  /** The inspector's pre-submit preview, for the authoritative comparison. */
  clientRequestHash: string
  clientScenarioHash: string
  clientGuidanceHash: string
  stale: boolean
  verifyState: VerifyState
  onVerify: () => void
  onAnnounce: (message: string) => void
}

function Row({
  label,
  testId,
  children,
}: {
  label: string
  testId?: string
  children: React.ReactNode
}) {
  return (
    <div className="ledger__row" data-testid={testId}>
      <span className="ledger__label">{label}</span>
      <span className="ledger__value">{children}</span>
    </div>
  )
}

export function DecisionReceipt(props: ReceiptProps) {
  const { envelope } = props
  const times = formatTimestamp(envelope.decided_at)
  const echo = guidanceEchoState(envelope, props.sentGuidance)
  const serverGuidance = envelope.request.additional_instructions

  const scenarioBlock = JSON.stringify({ scenario: envelope.request.scenario }, null, 2)
  const combined = JSON.stringify(
    {
      scenario: envelope.request.scenario,
      additional_instructions: serverGuidance ?? null,
    },
    null,
    2,
  )

  // Both hashes the receipt actually carries can be recomputed here from the
  // values the receipt itself returns, so "matches preview" is a real check
  // rather than a reassurance.
  const scenarioHashMatches = scenarioHash(envelope.request.scenario) === envelope.request.scenario_hash
  const guidanceHashMatches =
    envelope.request.additional_instructions_hash === undefined ||
    additionalInstructionsHash(serverGuidance ?? '') === envelope.request.additional_instructions_hash
  const previewMatches =
    props.clientScenarioHash === envelope.request.scenario_hash &&
    (envelope.request.additional_instructions_hash === undefined ||
      props.clientGuidanceHash === envelope.request.additional_instructions_hash)

  return (
    <section
      className={`panel${props.stale ? ' stale' : ''}`}
      data-testid="playground-receipt"
      data-stale={props.stale ? 'true' : undefined}
      aria-labelledby="receipt-heading"
    >
      <div className="panel__head">
        <h3 className="panel__title" id="receipt-heading">
          {RECEIPT.heading}
        </h3>
        {props.stale ? <span className="chip chip--neutral">{RECEIPT.staleChip}</span> : null}
      </div>

      <div className="ledger">
        <Row label="Decision id" testId="receipt-decision-id">
          <code className="mono">{envelope.decision_id}</code>
          <CopyButton
            className="btn btn--quiet"
            text={envelope.decision_id}
            label="Copy"
            what="the decision id"
            onAnnounce={props.onAnnounce}
          />
        </Row>

        <Row label="Project" testId="receipt-project">
          <span>{envelope.policy_set.name}</span>
          <code className="mono">{envelope.policy_set.key}</code>
          <span className="pill">{RECEIPT.usedInPaths}</span>
          <code className="mono mono--muted">{envelope.policy_set.id}</code>
          <span className="pill">{RECEIPT.traceIdentity}</span>
        </Row>

        <Row label="Policy version" testId="receipt-version">
          {envelope.active_version ? (
            <>
              <span className="mono">
                v{envelope.active_version.version_number ?? '—'}
              </span>
              <code className="mono mono--muted">{envelope.active_version.version_id}</code>
              <CopyButton
                className="btn btn--quiet"
                text={envelope.active_version.version_id}
                label="Copy"
                what="the policy version id"
                onAnnounce={props.onAnnounce}
              />
            </>
          ) : (
            <span className="muted">
              No published version was loaded, so nothing was decided against one.
            </span>
          )}
        </Row>

        <Row label="Correlation id" testId="receipt-correlation">
          <code className="mono">{envelope.correlation_id}</code>
          <CopyButton
            className="btn btn--quiet"
            text={envelope.correlation_id}
            label="Copy"
            what="the correlation id"
            onAnnounce={props.onAnnounce}
          />
        </Row>

        {envelope.idempotency_key ? (
          <Row label="Idempotency key" testId="receipt-idempotency">
            <code className="mono">{envelope.idempotency_key}</code>
          </Row>
        ) : null}

        <Row label="Calling system" testId="receipt-caller">
          <span>{envelope.caller.principal_identity}</span>
          <span className="pill">{envelope.caller.principal_role}</span>
          <span className="muted">
            declared: {envelope.caller.calling_system_identity ?? '—'}
          </span>
          <span className="ledger__caption">{RECEIPT.callerCaption}</span>
        </Row>

        <Row label="Timestamp" testId="receipt-timestamp">
          <span>{times.local}</span>
          <code className="mono mono--muted">{times.utc}</code>
          <span className="muted small">· {envelope.latency_ms} ms</span>
        </Row>

        <Row label="Envelope" testId="receipt-envelope">
          <code className="mono">{envelope.schema_version}</code>
          <span className="pill">{RECEIPT.contractVersion}</span>
          {envelope.hash_basis ? (
            <>
              <code className="mono mono--muted">hash basis: {envelope.hash_basis}</code>
            </>
          ) : null}
        </Row>

        <Row label="Receipt" testId="receipt-state">
          <VerifyReceipt
            state={props.verifyState}
            onVerify={props.onVerify}
            onAnnounce={props.onAnnounce}
            decisionId={envelope.decision_id}
          />
        </Row>

        {envelope.receipt_url ? (
          <Row label="Receipt URL" testId="receipt-url">
            <code className="mono mono--muted">{envelope.receipt_url}</code>
            <CopyButton
              className="btn btn--quiet"
              text={envelope.receipt_url}
              label="Copy"
              what="the receipt URL"
              onAnnounce={props.onAnnounce}
            />
          </Row>
        ) : null}
      </div>

      {/* ---------- Request as sent ---------- */}
      <div className="panel__body">
        <h4 className="panel__title" style={{ fontSize: 'var(--fs-base)' }}>
          {RECEIPT.requestAsSent}
        </h4>
        <p className="field__caption">
          Rendered from the server&apos;s response, not from what this page had on screen.
        </p>

        <div>
          <span className="eyebrow">{RECEIPT.scenario}</span>
          <CodeBlock
            text={scenarioBlock}
            language="JSON"
            what="the scenario as recorded on the receipt"
            downloadName={`${envelope.decision_id}-scenario.json`}
            testId="receipt-scenario"
            onAnnounce={props.onAnnounce}
            renderLine={renderJsonLine}
          />
        </div>

        <div>
          <span className="eyebrow">{RECEIPT.guidance}</span>
          {echo === 'not-echoed' ? (
            <div className="banner banner--note" data-testid="receipt-guidance-not-echoed">
              <strong className="banner__heading">{RECEIPT.guidanceNotEchoed}</strong>
              <span className="banner__body">{RECEIPT.guidanceNotEchoedBody}</span>
            </div>
          ) : echo === 'absent' ? (
            <p className="muted small" data-testid="receipt-guidance-absent">
              {RECEIPT.guidanceAbsent}
            </p>
          ) : echo === 'empty' ? (
            <p className="muted small" data-testid="receipt-guidance-empty">
              {RECEIPT.guidanceEmpty} <span className="chip chip--note">{RECEIPT.guidanceEmptyChip}</span>
            </p>
          ) : (
            <CodeBlock
              text={serverGuidance ?? ''}
              language="Text"
              what="the caller guidance as recorded on the receipt"
              downloadName={`${envelope.decision_id}-guidance.txt`}
              downloadMime="text/plain"
              testId="receipt-guidance"
              onAnnounce={props.onAnnounce}
            />
          )}
        </div>

        <div className="btn-row">
          <CopyButton
            text={combined}
            label={RECEIPT.copyBoth}
            what="the scenario and caller guidance"
            onAnnounce={props.onAnnounce}
            className="btn"
          />
          <button
            type="button"
            className="btn"
            data-testid="receipt-download-request"
            data-download-name={`${envelope.decision_id}-request.json`}
            onClick={() => {
              const blob = new Blob([combined], { type: 'application/json;charset=utf-8' })
              const url = URL.createObjectURL(blob)
              const anchor = document.createElement('a')
              anchor.href = url
              anchor.download = `${envelope.decision_id}-request.json`
              document.body.appendChild(anchor)
              anchor.click()
              document.body.removeChild(anchor)
              URL.revokeObjectURL(url)
            }}
          >
            {RECEIPT.downloadRequest}
          </button>
        </div>

        <div className="ledger" style={{ border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)' }}>
          <Row label="Request hash" testId="receipt-request-hash">
            <code className="mono">{props.clientRequestHash}</code>
            <span className={`chip chip--${previewMatches ? 'neutral' : 'note'}`} data-testid="receipt-hash-preview-chip">
              {previewMatches ? RECEIPT.matchesPreview : RECEIPT.differsFromPreview}
            </span>
            <span className="ledger__caption">
              {RECEIPT.requestHashCaption} This server&apos;s receipt does not carry the combined
              request hash, so the value shown is this page&apos;s own preview; the two component
              hashes below are the server&apos;s and are authoritative.
            </span>
          </Row>

          <Row label="Scenario hash" testId="receipt-scenario-hash">
            <code className="mono mono--muted">{envelope.request.scenario_hash}</code>
            <span className={`chip chip--${scenarioHashMatches ? 'neutral' : 'note'}`}>
              {scenarioHashMatches ? 'Recomputes from the receipt' : 'Does not recompute'}
            </span>
            <CopyButton
              className="btn btn--quiet"
              text={envelope.request.scenario_hash}
              label="Copy"
              what="the scenario hash"
              onAnnounce={props.onAnnounce}
            />
          </Row>

          {envelope.request.additional_instructions_hash !== undefined ? (
            <Row label="Guidance hash" testId="receipt-guidance-hash">
              <code className="mono mono--muted">
                {envelope.request.additional_instructions_hash}
              </code>
              <span className={`chip chip--${guidanceHashMatches ? 'neutral' : 'note'}`}>
                {guidanceHashMatches ? 'Recomputes from the receipt' : 'Does not recompute'}
              </span>
            </Row>
          ) : null}

          <Row label="Instruction profile" testId="receipt-profile-version">
            <code className="mono">{envelope.trace.prompt_version ?? 'Not reported on this receipt.'}</code>
            <span className="pill">Read only</span>
            {envelope.trace.instruction_profile ? (
              <code className="mono mono--muted">{envelope.trace.instruction_profile}</code>
            ) : null}
            <CopyButton
              className="btn btn--quiet"
              text={envelope.trace.prompt_version ?? ''}
              label="Copy"
              what="the server instruction profile version"
              onAnnounce={props.onAnnounce}
            />
            <span className="ledger__caption">{RECEIPT.profileCaption}</span>
          </Row>
        </div>
      </div>
    </section>
  )
}
