import { useEffect, useRef, useState, type RefObject } from 'react'
import { DOCKET, GUIDANCE_EXAMPLES } from '../copy/strings'
import { MAX_ADDITIONAL_INSTRUCTIONS_CHARS, type ReasoningEffort } from '../contracts/caseDecision'
import { newUuid } from '../lib/identifiers'
import { normaliseAdditionalInstructions } from '../lib/canonicalHash'

/**
 * Everything the caller controls, in one sticky rail.
 *
 * The grouping is not cosmetic. `Connection` is what you configure once,
 * `Request` is the question, `Caller guidance` is the one thing a caller may
 * shape about the *presentation* of the answer, and `Trace` is what will
 * identify this call afterwards. Guidance is a peer of the request rather than
 * a sub-field of it, because on the wire it is a peer -- sealed beside the
 * scenario and bound into the same idempotency hash.
 *
 * The subscription key lives in this component's parent as React state and
 * nowhere else. It is not written to `localStorage`, `sessionStorage`, a
 * cookie, the URL, or a log line. It *is* shown in clear, which is a deliberate
 * choice for a local demonstration of an operator-generated key rather than a
 * pattern for a production client -- the field carries that warning beside it,
 * and `lib/subscriptionKey.ts` records the reasoning.
 */

export interface ProjectIdentity {
  id: string
  key: string
  name: string
  activeVersionNumber: number | null
  activeVersionId: string | null
}

export type ResolutionState =
  | { kind: 'idle' }
  | { kind: 'resolving' }
  | { kind: 'resolved'; identity: ProjectIdentity }
  | { kind: 'not-found'; key: string }
  | { kind: 'unreadable'; message: string }

export interface DocketProps {
  baseUrl: string
  onBaseUrl: (value: string) => void
  projectKey: string
  onProjectKey: (value: string) => void
  subscriptionKey: string
  onSubscriptionKey: (value: string) => void
  /** True when the field was filled from the local VITE variable at load. */
  subscriptionKeyPrefilled: boolean
  scenario: string
  onScenario: (value: string) => void
  reasoningEffort: ReasoningEffort
  onReasoningEffort: (value: ReasoningEffort) => void
  callingSystemIdentity: string
  onCallingSystemIdentity: (value: string) => void
  idempotencyKey: string
  onIdempotencyKey: (value: string) => void
  additionalInstructions: string
  onAdditionalInstructions: (value: string) => void
  correlationId: string
  onRegenerateCorrelation: () => void
  resolution: ResolutionState
  submitting: boolean
  submitDisabledReason: string | null
  onSubmit: () => void
  /** True when a key is present and the request changed since it was last used. */
  idempotencyConflict: boolean
  guidanceRef: RefObject<HTMLTextAreaElement | null>
  scenarioRef: RefObject<HTMLTextAreaElement | null>
  subscriptionKeyRef: RefObject<HTMLInputElement | null>
  keyRef: RefObject<HTMLInputElement | null>
  onAnnounce: (message: string) => void
  collapsed: boolean
  onExpand: () => void
}

function counterClass(length: number): string {
  if (length >= MAX_ADDITIONAL_INSTRUCTIONS_CHARS) return 'counter counter--danger'
  if (length >= 1900) return 'counter counter--warning'
  return 'counter'
}

export function RequestDocket(props: DocketProps) {
  const [truncatedNotice, setTruncatedNotice] = useState('')
  const announcedThreshold = useRef<number>(0)

  // The counter is announced when it crosses a threshold, never per character:
  // a live region that speaks on every keystroke is a field nobody can use.
  const { additionalInstructions, onAnnounce } = props
  useEffect(() => {
    const length = additionalInstructions.length
    const threshold =
      length >= MAX_ADDITIONAL_INSTRUCTIONS_CHARS ? 2000 : length >= 1900 ? 1900 : 0
    if (threshold !== announcedThreshold.current) {
      announcedThreshold.current = threshold
      if (threshold === 2000) onAnnounce('Character limit reached.')
      else if (threshold === 1900) onAnnounce(`${length} of 2000 characters used.`)
    }
  }, [additionalInstructions, onAnnounce])

  function insertExample(text: string) {
    const field = props.guidanceRef.current
    const current = props.additionalInstructions
    const separator = current.length > 0 && !current.endsWith('\n') ? '\n' : ''
    const next = `${current}${separator}${text}`.slice(0, MAX_ADDITIONAL_INSTRUCTIONS_CHARS)
    props.onAdditionalInstructions(next)
    props.onAnnounce('Example inserted.')
    // Focus returns to the textarea with the caret after the insertion: an
    // example chip is an aid to writing, not a place to be left standing.
    requestAnimationFrame(() => {
      if (!field) return
      field.focus()
      field.setSelectionRange(next.length, next.length)
    })
  }

  const guidanceLength = props.additionalInstructions.length
  const normalisedLength = normaliseAdditionalInstructions(props.additionalInstructions).length
  const identity = props.resolution.kind === 'resolved' ? props.resolution.identity : null
  const noActiveVersion = identity !== null && identity.activeVersionNumber === null

  return (
    <form
      className={`panel docket${props.collapsed ? ' docket--collapsed' : ''}`}
      aria-labelledby="docket-heading"
      data-testid="playground-docket"
      onSubmit={(event) => {
        event.preventDefault()
        props.onSubmit()
      }}
      onKeyDown={(event) => {
        // Ctrl/Cmd+Enter sends from anywhere in the docket, including from
        // inside the guidance textarea. Plain Enter never sends: a policy
        // decision is always an explicit act.
        if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
          event.preventDefault()
          props.onSubmit()
        }
      }}
    >
      <div className="panel__head">
        <h2 className="panel__title" id="docket-heading">
          {DOCKET.heading}
        </h2>
      </div>

      <div className="docket__summary" data-testid="playground-docket-summary">
        <span className="mono">
          {props.projectKey || 'no project'}
          {identity?.activeVersionNumber != null ? ` · v${identity.activeVersionNumber}` : ''}
          {` · effort ${props.reasoningEffort}`}
        </span>
        <button type="button" className="btn" onClick={props.onExpand}>
          Edit request
        </button>
      </div>

      {/* ---------- Connection ---------- */}
      <fieldset className="docket__group" style={{ border: 'none', margin: 0 }}>
        <legend className="eyebrow" style={{ padding: 0 }}>
          {DOCKET.connection}
        </legend>

        <div className="field">
          <label className="field__label" htmlFor="pg-base">
            {DOCKET.apiBaseLabel}
          </label>
          <input
            id="pg-base"
            className="input input--mono"
            data-testid="playground-base-url"
            value={props.baseUrl}
            spellCheck={false}
            autoComplete="off"
            placeholder="https://policy.example.com"
            onChange={(event) => props.onBaseUrl(event.target.value)}
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="pg-key">
            {DOCKET.projectKeyLabel}
          </label>
          <input
            id="pg-key"
            ref={props.keyRef}
            className="input input--mono"
            data-testid="playground-project-key"
            value={props.projectKey}
            spellCheck={false}
            autoComplete="off"
            aria-describedby="pg-key-helper"
            aria-invalid={props.resolution.kind === 'not-found'}
            onChange={(event) => props.onProjectKey(event.target.value)}
          />
          <p className="field__caption" id="pg-key-helper" data-testid="playground-key-helper">
            {DOCKET.projectKeyHelper}
          </p>
          {props.resolution.kind === 'not-found' ? (
            <p className="field__error" data-testid="playground-key-error">
              No project is published under the key &quot;{props.resolution.key}&quot; on this server.
              <br />
              <span className="muted small">
                Check the key with the project owner. Keys are case-sensitive and are not the
                project&apos;s UUID.
              </span>
            </p>
          ) : null}
          {props.resolution.kind === 'unreadable' ? (
            <p className="field__error" data-testid="playground-key-unreadable">
              {props.resolution.message}
            </p>
          ) : null}
        </div>

        <div className="field">
          <label className="field__label" htmlFor="pg-subscription-key">
            {DOCKET.subscriptionKeyLabel}
          </label>
          <input
            id="pg-subscription-key"
            ref={props.subscriptionKeyRef}
            className="input input--mono"
            data-testid="playground-subscription-key"
            /* A plain text field, deliberately. This is a local demonstration
               of an operator-generated key, and the value has to be readable to
               be checked against a failing call — which is what a first
               integration is usually doing when it gets a 401. The credential
               that must never be visible is a personal bearer token, and this
               page no longer sends one. What still holds is that nothing is
               persisted: see `lib/subscriptionKey.ts`. */
            type="text"
            value={props.subscriptionKey}
            autoComplete="off"
            spellCheck={false}
            name="policy-api-subscription-key"
            aria-describedby="pg-subscription-key-caption pg-subscription-key-warning"
            onChange={(event) => props.onSubscriptionKey(event.target.value)}
          />
          <p className="field__caption" id="pg-subscription-key-caption">
            {DOCKET.subscriptionKeyCaption}
          </p>
          <p
            className="field__caption field__caption--warning"
            id="pg-subscription-key-warning"
            data-testid="playground-subscription-key-warning"
          >
            {DOCKET.subscriptionKeyLocalWarning}
          </p>
          {props.subscriptionKeyPrefilled ? (
            <p
              className="field__caption muted"
              data-testid="playground-subscription-key-prefilled"
            >
              {DOCKET.subscriptionKeyPrefilled}
            </p>
          ) : null}
        </div>

        {props.resolution.kind === 'resolving' ? (
          <div className="identity-register" role="status" aria-live="polite">
            <p className="small muted" style={{ padding: '6px 10px 0' }}>
              {DOCKET.resolving}
            </p>
            <div className="skeleton-row" />
            <div className="skeleton-row" style={{ width: '60%' }} />
            <div className="skeleton-row" style={{ width: '75%', marginBottom: 8 }} />
          </div>
        ) : null}

        {identity ? (
          <div className="identity-register" data-testid="playground-identity">
            <div className="ledger">
              <div className="ledger__row">
                <span className="ledger__label">Project</span>
                <span className="ledger__value">{identity.name}</span>
              </div>
              <div className="ledger__row">
                <span className="ledger__label">Key</span>
                <span className="ledger__value">
                  <code className="mono">{identity.key}</code>
                  <span className="pill">Use this in API paths</span>
                </span>
              </div>
              <div className="ledger__row">
                <span className="ledger__label">Active version</span>
                <span className="ledger__value">
                  {identity.activeVersionNumber != null ? (
                    <>
                      <span className="mono">v{identity.activeVersionNumber}</span>
                      {identity.activeVersionId ? (
                        <code className="mono mono--muted">{identity.activeVersionId}</code>
                      ) : null}
                    </>
                  ) : (
                    <span className="muted small">None published</span>
                  )}
                </span>
              </div>
            </div>
            <p className="xsmall muted" style={{ padding: '4px 10px 8px' }}>
              {DOCKET.resolvedFrom}
            </p>
          </div>
        ) : null}

        {noActiveVersion ? (
          <div className="banner banner--action" data-testid="playground-no-version">
            <strong className="banner__heading">
              This project has no published version, so there is nothing to decide against yet.
            </strong>
            <span className="banner__body">
              A case sent now would be refused by the API. Publish a version first.
            </span>
          </div>
        ) : null}
      </fieldset>

      {/* ---------- Request ---------- */}
      <fieldset className="docket__group" style={{ border: 'none', margin: 0 }}>
        <legend className="eyebrow" style={{ padding: 0 }}>
          {DOCKET.request}
        </legend>

        <div className="field">
          <label className="field__label" htmlFor="pg-scenario">
            {DOCKET.scenarioLabel}
          </label>
          <textarea
            id="pg-scenario"
            ref={props.scenarioRef}
            className="textarea"
            data-testid="playground-scenario"
            rows={5}
            value={props.scenario}
            placeholder={DOCKET.scenarioPlaceholder}
            onChange={(event) => props.onScenario(event.target.value)}
          />
        </div>

        <div className="field">
          <label className="field__label" htmlFor="pg-effort">
            {DOCKET.reasoningLabel}
          </label>
          <select
            id="pg-effort"
            className="select"
            data-testid="playground-reasoning-effort"
            value={props.reasoningEffort}
            onChange={(event) => props.onReasoningEffort(event.target.value as ReasoningEffort)}
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </div>

        <div className="field">
          <label className="field__label" htmlFor="pg-calling-system">
            {DOCKET.callingSystemLabel}
          </label>
          <input
            id="pg-calling-system"
            className="input"
            data-testid="playground-calling-system"
            value={props.callingSystemIdentity}
            autoComplete="off"
            onChange={(event) => props.onCallingSystemIdentity(event.target.value)}
          />
          <p className="field__caption">{DOCKET.callingSystemCaption}</p>
        </div>

        <div className="field">
          <label className="field__label" htmlFor="pg-idempotency">
            {DOCKET.idempotencyLabel}
          </label>
          <div className="input-with-action">
            <input
              id="pg-idempotency"
              className="input input--mono"
              data-testid="playground-idempotency-key"
              value={props.idempotencyKey}
              autoComplete="off"
              spellCheck={false}
              onChange={(event) => props.onIdempotencyKey(event.target.value)}
            />
            <button
              type="button"
              className="btn"
              data-testid="playground-generate-key"
              onClick={() => props.onIdempotencyKey(newUuid())}
            >
              {DOCKET.generate}
            </button>
          </div>
          <p className="field__caption">{DOCKET.idempotencyCaption}</p>
          {props.idempotencyConflict ? (
            <p
              className="field__caption"
              style={{ color: 'var(--info)' }}
              data-testid="playground-idempotency-conflict"
            >
              {DOCKET.idempotencyConflict}
            </p>
          ) : null}
        </div>
      </fieldset>

      {/* ---------- Caller guidance ---------- */}
      <fieldset className="docket__group" style={{ border: 'none', margin: 0 }}>
        <legend className="eyebrow" style={{ padding: 0 }}>
          {DOCKET.guidance}
        </legend>

        <div className="field">
          <div className="field__labelrow">
            <label className="field__label" htmlFor="pg-guidance">
              {DOCKET.guidanceLabel}
            </label>
            <span
              className={counterClass(guidanceLength)}
              id="pg-guidance-counter"
              aria-live="polite"
              data-testid="playground-guidance-counter"
            >
              {guidanceLength} / {MAX_ADDITIONAL_INSTRUCTIONS_CHARS}
            </span>
          </div>
          <textarea
            id="pg-guidance"
            ref={props.guidanceRef}
            className="textarea"
            data-testid="playground-additional-instructions"
            rows={3}
            value={props.additionalInstructions}
            maxLength={MAX_ADDITIONAL_INSTRUCTIONS_CHARS}
            aria-describedby="pg-guidance-helper pg-guidance-counter"
            onPaste={(event) => {
              const pasted = event.clipboardData.getData('text')
              const target = event.currentTarget
              const projected =
                props.additionalInstructions.length -
                (target.selectionEnd - target.selectionStart) +
                pasted.length
              if (projected > MAX_ADDITIONAL_INSTRUCTIONS_CHARS) {
                setTruncatedNotice('Pasted text was truncated to the 2,000 character limit.')
                props.onAnnounce('Pasted text was truncated to the 2,000 character limit.')
              }
            }}
            onChange={(event) =>
              props.onAdditionalInstructions(
                event.target.value.slice(0, MAX_ADDITIONAL_INSTRUCTIONS_CHARS),
              )
            }
          />
          <p className="field__caption" id="pg-guidance-helper" data-testid="playground-guidance-helper">
            {DOCKET.guidanceHelper}
          </p>
          {guidanceLength >= MAX_ADDITIONAL_INSTRUCTIONS_CHARS ? (
            <p className="field__caption" style={{ color: 'var(--danger)' }}>
              Character limit reached. Additional instructions are capped at 2,000 characters.
            </p>
          ) : guidanceLength >= 1900 ? (
            <p className="field__caption" style={{ color: 'var(--warning)' }}>
              {guidanceLength} of 2000 characters used.
            </p>
          ) : null}
          {truncatedNotice ? (
            <p className="field__caption" data-testid="playground-guidance-truncated">
              {truncatedNotice}
            </p>
          ) : null}
          {normalisedLength !== guidanceLength ? (
            <p className="field__caption">
              The server normalises whitespace before measuring. This counts as {normalisedLength}{' '}
              characters there.
            </p>
          ) : null}

          <div className="btn-row" style={{ marginTop: 4 }}>
            {GUIDANCE_EXAMPLES.map((example) => (
              <button
                key={example}
                type="button"
                className="example-chip"
                data-testid="playground-guidance-example"
                onClick={() => insertExample(example)}
              >
                {example}
              </button>
            ))}
          </div>
          <p className="field__caption">{DOCKET.guidanceExamplesCaption}</p>
        </div>
      </fieldset>

      {/* ---------- Trace ---------- */}
      <fieldset className="docket__group" style={{ border: 'none', margin: 0 }}>
        <legend className="eyebrow" style={{ padding: 0 }}>
          {DOCKET.trace}
        </legend>
        <div className="field">
          <div className="field__labelrow">
            <span className="field__label">{DOCKET.correlationLabel}</span>
            <button
              type="button"
              className="btn btn--quiet"
              onClick={props.onRegenerateCorrelation}
              aria-label="Regenerate the correlation id"
            >
              {DOCKET.regenerate}
            </button>
          </div>
          <code className="mono" data-testid="playground-correlation">
            {props.correlationId}
          </code>
          <p className="field__caption">{DOCKET.correlationCaption}</p>
        </div>
      </fieldset>

      <div className="docket__submit">
        <button
          type="submit"
          className="btn btn--primary"
          data-testid="playground-submit"
          aria-disabled={props.submitDisabledReason !== null || props.submitting}
          disabled={props.submitDisabledReason !== null || props.submitting}
          title={props.submitDisabledReason ?? undefined}
        >
          {props.submitting ? DOCKET.submitting : DOCKET.submit}
        </button>
        {props.submitDisabledReason ? (
          <p className="xsmall muted" data-testid="playground-submit-reason">
            {props.submitDisabledReason}
          </p>
        ) : null}
        <p className="xsmall muted">{DOCKET.submitCaption}</p>
        <p className="xsmall muted">{DOCKET.memoryOnly}</p>
      </div>
    </form>
  )
}
