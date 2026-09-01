import { useEffect, useRef, useState, type RefObject } from 'react'
import { DOCKET, GUIDANCE_EXAMPLES } from '../copy/strings'
import {
  MAX_ADDITIONAL_INSTRUCTIONS_CHARS,
  type PlaygroundResponseMode,
  type ReasoningEffort,
} from '../contracts/caseDecision'
import { newUuid } from '../lib/identifiers'
import { normaliseAdditionalInstructions } from '../lib/canonicalHash'

/**
 * Everything the caller controls, in three regions of one docket.
 *
 * The grouping is not cosmetic, and neither is the order.
 *
 *   * **Connection** is what you configure once and then stop looking at, so it
 *     is a single ruled register across the top -- four cells divided by
 *     hairlines: where the API is, which project, which key, and what the
 *     server said when we asked it to resolve that project. It is one bordered
 *     container ruled into entries, not four floating fields.
 *   * **The case** is the whole point of the page, so it owns the wide column
 *     and ends in the send band. A caller who lands here should be able to type
 *     a scenario and send it without scrolling: the earlier single-rail docket
 *     put roughly 1,500px of metadata above the button, which meant the primary
 *     action of the page was never in the first viewport.
 *   * **Request metadata** -- calling system, idempotency, correlation and
 *     caller guidance -- is real, is sent, and is not what you are here to do,
 *     so it sits in a narrow rail beside the case rather than above the button.
 *     Every field that will be sent is open at rest; the only thing folded away
 *     is the long-form note about what this demonstration's credential is and
 *     is not, which is prose rather than payload. The Request Inspector
 *     directly below shows the exact bytes either way.
 *
 * Guidance stays a peer of the request rather than a sub-field of it, because
 * on the wire it is a peer -- sealed beside the scenario and bound into the
 * same idempotency hash. Being in the metadata rail says "secondary", not
 * "nested".
 *
 * On a narrow screen the case moves *first* and the connection register follows
 * it. That is a real reorder of the DOM rather than a CSS `order`, so keyboard
 * and screen-reader order still agree with what is on screen. Stacking every
 * connection and metadata field above the button is the mobile version of the
 * same fault the desktop layout had.
 *
 * The subscription key lives in this component's parent as React state and
 * nowhere else. It is not written to `localStorage`, `sessionStorage`, a
 * cookie, the URL, or a log line. It *is* shown in clear, which is a deliberate
 * choice for a local demonstration of an operator-generated key rather than a
 * pattern for a production client. The field says so in one line beside itself
 * -- local demo key, which header carries it, how long this page keeps it --
 * and the full reasoning is a click away under "About the demo key" in the
 * rail, unedited. `lib/subscriptionKey.ts` records the rest.
 */

/**
 * The width below which the two-column docket becomes one column and the case
 * moves above the connection register. It matches the stylesheet's own
 * breakpoint so the DOM order and the grid can never disagree about which
 * layout is on screen.
 */
const NARROW_QUERY = '(max-width: 979px)'

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
  responseMode: PlaygroundResponseMode
  onResponseMode: (value: PlaygroundResponseMode) => void
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
  const [keyNoteOpen, setKeyNoteOpen] = useState(false)
  // Dots until asked for, and not remembered across mounts: revealing a
  // credential is a deliberate act for one moment, not a preference that
  // quietly persists into the next screen share.
  const [revealKey, setRevealKey] = useState(false)
  const announcedThreshold = useRef<number>(0)
  // Read synchronously on the first render rather than in an effect, so the
  // committed DOM order is never briefly the wrong one for the grid on screen.
  const [narrow, setNarrow] = useState(
    () =>
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia(NARROW_QUERY).matches,
  )

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const query = window.matchMedia(NARROW_QUERY)
    const apply = () => setNarrow(query.matches)
    apply()
    query.addEventListener('change', apply)
    return () => query.removeEventListener('change', apply)
  }, [])

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
  const decisionRequest = props.responseMode !== 'policies'
  const noActiveVersion = identity !== null && identity.activeVersionNumber === null
  const keyNotFound = props.resolution.kind === 'not-found'
  const hasConnectionNotes =
    keyNotFound || props.resolution.kind === 'unreadable' || noActiveVersion

  /* ---------- Connection: one ruled register, four entries ---------- */

  const connection = (
    <section
      className="connbar"
      aria-labelledby="connbar-heading"
      data-testid="playground-connection-bar"
    >
      {/* The register is named for assistive technology and read visually from
          its own field labels; a visible "Connection" title would spend a line
          of the first viewport restating what four labelled cells already say. */}
      <h2 className="visually-hidden" id="connbar-heading">
        {DOCKET.connection}
      </h2>

      <div className="connbar__cell">
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

      <div className="connbar__cell">
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
          aria-describedby={keyNotFound ? 'pg-key-helper pg-key-error' : 'pg-key-helper'}
          aria-invalid={keyNotFound}
          onChange={(event) => props.onProjectKey(event.target.value)}
        />
        <p className="connbar__note" id="pg-key-helper" data-testid="playground-key-helper">
          {DOCKET.projectKeyHelper}
        </p>
      </div>

      <div className="connbar__cell">
        <label className="field__label" htmlFor="pg-subscription-key">
          {DOCKET.subscriptionKeyLabel}
        </label>
        <input
          id="pg-subscription-key"
          ref={props.subscriptionKeyRef}
          className="input input--mono"
          data-testid="playground-subscription-key"
          /* Dots by default, with a reveal beside it.
             This field used to be plain text, deliberately: the value has to be
             readable to be checked against a failing call, which is what a
             first integration is usually doing when it gets a 401. That reason
             is still good, and it is served by the reveal.
             What it did not account for is that this page gets screen-shared,
             screenshotted and pasted into tickets, and a credential sitting in
             clear is then in an artefact nobody thinks of as holding one. A
             field that is readable on demand keeps the debugging affordance
             without leaving the value on screen for every other purpose.
             Unchanged: nothing is persisted -- see `lib/subscriptionKey.ts`. */
          type={revealKey ? 'text' : 'password'}
          value={props.subscriptionKey}
          autoComplete="off"
          spellCheck={false}
          name="policy-api-subscription-key"
          aria-describedby="pg-subscription-key-caption"
          onChange={(event) => props.onSubscriptionKey(event.target.value)}
        />
        <button
          type="button"
          className="link-button"
          data-testid="playground-subscription-key-reveal"
          aria-pressed={revealKey}
          aria-controls="pg-subscription-key"
          onClick={() => setRevealKey((shown) => !shown)}
        >
          {revealKey ? DOCKET.hideKey : DOCKET.revealKey}
        </button>
        {/* One line, and it says the three things a reader needs at the moment
            they are typing a credential: what kind of key this is, which header
            carries it, and how long this page keeps it. The rest -- why a
            production browser client must not hold a shared key at all, and
            what `VITE_` does to a committed value -- is a paragraph nobody
            reads in a connection bar, so it lives one click away in the rail
            under "About the demo key" with its wording intact. */}
        <p
          className="connbar__note"
          id="pg-subscription-key-caption"
          data-testid="playground-subscription-key-caption"
        >
          Local demo key · sent as X-Policy-Subscription-Key · held only for this tab.
        </p>
      </div>

      <div className="connbar__cell connbar__cell--state">
        <span className="field__label">Project resolution</span>
        <div className="connbar__state" role="status" aria-live="polite">
          {props.resolution.kind === 'idle' ? (
            <span className="muted small" data-testid="playground-resolution-idle">
              Not resolved yet
            </span>
          ) : null}

          {props.resolution.kind === 'resolving' ? (
            <>
              <span className="small muted">{DOCKET.resolving}</span>
              <span className="skeleton-row skeleton-row--inline" aria-hidden="true" />
            </>
          ) : null}

          {identity ? (
            <span className="connbar__identity" data-testid="playground-identity">
              <span className="connbar__project">{identity.name}</span>
              <span className="connbar__ids">
                <code className="mono">{identity.key}</code>
                {identity.activeVersionNumber != null ? (
                  <span className="pill" data-testid="playground-active-version">
                    v{identity.activeVersionNumber}
                  </span>
                ) : (
                  <span className="muted small">None published</span>
                )}
              </span>
              {identity.activeVersionId ? (
                <code className="mono mono--muted connbar__version-id">
                  {identity.activeVersionId}
                </code>
              ) : null}
              <span className="xsmall muted">{DOCKET.resolvedFrom}</span>
            </span>
          ) : null}

          {keyNotFound ? (
            <span className="connbar__state-bad" data-testid="playground-resolution-bad">
              No project under that key
            </span>
          ) : null}

          {props.resolution.kind === 'unreadable' ? (
            <span className="connbar__state-bad" data-testid="playground-resolution-bad">
              Could not be read
            </span>
          ) : null}
        </div>
      </div>

      {/* At rest this row does not exist. It appears only when the server has
          something to say about the connection: the paper below the register
          is not a place to park standing prose. */}
      {hasConnectionNotes ? (
        <div className="connbar__notes">
          {keyNotFound && props.resolution.kind === 'not-found' ? (
            <p className="field__error" id="pg-key-error" data-testid="playground-key-error">
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
        </div>
      ) : null}
    </section>
  )

  /* ---------- The case: the wide column, ending in the send band ---------- */

  const composer = (
    <div className="compose panel">
      <div className="panel__head">
        <h2 className="panel__title" id="docket-heading">
          {DOCKET.heading}
        </h2>
      </div>

      <div className="compose__body">
        <fieldset className="mode-switch" data-testid="playground-response-mode">
          <legend className="field__label">{DOCKET.responseModeLabel}</legend>
          <div className="mode-switch__options">
            <label
              className={`mode-option${props.responseMode === 'decision' ? ' mode-option--selected' : ''}`}
            >
              <input
                type="radio"
                name="response-mode"
                value="decision"
                checked={props.responseMode === 'decision'}
                onChange={() => props.onResponseMode('decision')}
              />
              <span>
                <strong>{DOCKET.decisionModeLabel}</strong>
                <small>{DOCKET.decisionModeDescription}</small>
              </span>
            </label>
            <label
              className={`mode-option${props.responseMode === 'decision-light' ? ' mode-option--selected' : ''}`}
            >
              <input
                type="radio"
                name="response-mode"
                value="decision-light"
                checked={props.responseMode === 'decision-light'}
                onChange={() => props.onResponseMode('decision-light')}
              />
              <span>
                <strong>{DOCKET.decisionLightModeLabel}</strong>
                <small>{DOCKET.decisionLightModeDescription}</small>
              </span>
            </label>
            <label
              className={`mode-option${props.responseMode === 'policies' ? ' mode-option--selected' : ''}`}
            >
              <input
                type="radio"
                name="response-mode"
                value="policies"
                checked={props.responseMode === 'policies'}
                onChange={() => props.onResponseMode('policies')}
              />
              <span>
                <strong>{DOCKET.policiesModeLabel}</strong>
                <small>{DOCKET.policiesModeDescription}</small>
              </span>
            </label>
          </div>
        </fieldset>

        <div className="field">
          <label className="field__label" htmlFor="pg-scenario">
            {DOCKET.scenarioLabel}
          </label>
          <textarea
            id="pg-scenario"
            ref={props.scenarioRef}
            className="textarea textarea--scenario"
            data-testid="playground-scenario"
            rows={6}
            value={props.scenario}
            placeholder={DOCKET.scenarioPlaceholder}
            onChange={(event) => props.onScenario(event.target.value)}
          />
        </div>
      </div>

      <div className="compose__send">
        <div className="compose__controls">
          {decisionRequest ? (
            <div className="field compose__effort">
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
          ) : (
            <p className="compose__mode-note">{DOCKET.policiesModeNote}</p>
          )}

          <button
            type="submit"
            className="btn btn--primary"
            data-testid="playground-submit"
            aria-disabled={props.submitDisabledReason !== null || props.submitting}
            disabled={props.submitDisabledReason !== null || props.submitting}
            title={props.submitDisabledReason ?? undefined}
          >
            {props.submitting
              ? DOCKET.submitting
              : props.responseMode === 'decision'
                ? DOCKET.submit
                : props.responseMode === 'decision-light'
                  ? DOCKET.submitLight
                  : DOCKET.submitPolicies}
          </button>
        </div>

        <div className="compose__readiness">
          {props.submitDisabledReason ? (
            <p className="compose__blocked" data-testid="playground-submit-reason">
              {props.submitDisabledReason}
            </p>
          ) : null}
          <p className="xsmall muted">{DOCKET.submitCaption}</p>
          <p className="xsmall muted">{DOCKET.memoryOnly}</p>
        </div>
      </div>
    </div>
  )

  /* ---------- Request metadata: real, sent, and not the task ---------- */

  const advanced = (
    <aside className="advanced panel" aria-labelledby="advanced-heading" data-testid="playground-advanced">
      <div className="panel__head">
        <h2 className="panel__title" id="advanced-heading">
          Request metadata
        </h2>
      </div>

      {decisionRequest ? (
        <>
          <fieldset className="advanced__group">
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

          <fieldset className="advanced__group">
            <legend className="eyebrow">{DOCKET.guidance}</legend>

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
          <p
            className="field__caption"
            id="pg-guidance-helper"
            data-testid="playground-guidance-helper"
          >
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
        </>
      ) : (
        <div className="advanced__group" data-testid="playground-light-mode-note">
          <span className="eyebrow">Light request</span>
          <p className="field__caption">{DOCKET.policiesMetadataNote}</p>
        </div>
      )}

      <fieldset className="advanced__group">
        <legend className="eyebrow">{DOCKET.trace}</legend>
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

      {/* The long-form credential note, moved off the connection bar and kept
          word for word. A paragraph about what `VITE_` does to a committed
          value is worth reading once, by someone who has gone looking for it;
          standing above the send button it was only something to scroll past.
          It is a disclosure rather than a deletion because the claim it makes
          -- that this page is a local demonstration and not a pattern for a
          production browser client -- is one the page has to keep making. */}
      <div className="advanced__group">
        <button
          type="button"
          className="disclosure-toggle"
          aria-expanded={keyNoteOpen}
          aria-controls="pg-key-note"
          data-testid="playground-key-note-toggle"
          onClick={() => setKeyNoteOpen((open) => !open)}
        >
          {keyNoteOpen ? '▾ ' : '▸ '}
          About the demo key
        </button>
        <div id="pg-key-note" className="advanced__note" hidden={!keyNoteOpen}>
          <p className="field__caption">{DOCKET.subscriptionKeyCaption}</p>
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
      </div>
    </aside>
  )

  return (
    <form
      className={`docket${props.collapsed ? ' docket--collapsed' : ''}`}
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
      <div className="docket__summary" data-testid="playground-docket-summary">
        <span className="mono">
          {props.projectKey || 'no project'}
          {identity?.activeVersionNumber != null ? ` · v${identity.activeVersionNumber}` : ''}
          {props.responseMode === 'decision'
            ? ` · full decision · effort ${props.reasoningEffort}`
            : props.responseMode === 'decision-light'
              ? ` · decision light · effort ${props.reasoningEffort}`
              : ' · policy JSON'}
        </span>
        <button type="button" className="btn" onClick={props.onExpand}>
          Edit request
        </button>
      </div>

      {/* Narrow puts the case first. This is a real reorder rather than a CSS
          `order`, so tab order and the reading order a screen reader announces
          stay the same as the one on screen. */}
      {narrow ? (
        <>
          {composer}
          {connection}
          {advanced}
        </>
      ) : (
        <>
          {connection}
          {composer}
          {advanced}
        </>
      )}
    </form>
  )
}
