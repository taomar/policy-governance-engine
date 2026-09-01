import type {
  CaseDecisionLightEnvelope,
  CaseDecisionReceipt,
  PlaygroundResponseMode,
  PolicyRetrievalEnvelope,
  TokenUsageRef,
} from '../contracts/caseDecision'
import { RUN_METER, WAIT } from '../copy/strings'
import { formatElapsed } from '../lib/format'

type MeteredResponse =
  | CaseDecisionReceipt
  | CaseDecisionLightEnvelope
  | PolicyRetrievalEnvelope
  | null

interface RunMetricsProps {
  responseMode: PlaygroundResponseMode
  response: MeteredResponse
  submitting: boolean
  failed: boolean
  elapsedMs: number
  completedMs: number | null
}

const number = new Intl.NumberFormat()

function tokenUsage(response: MeteredResponse): TokenUsageRef | null {
  if (!response) return null
  if ('trace' in response) return response.trace.token_usage ?? null
  return response.token_usage ?? null
}

export function RunMetrics(props: RunMetricsProps) {
  const usage = tokenUsage(props.response)
  const duration = props.submitting ? props.elapsedMs : props.completedMs
  const state = props.submitting
    ? RUN_METER.running
    : props.failed
      ? RUN_METER.failed
      : props.response
        ? RUN_METER.complete
        : RUN_METER.ready
  const mode = RUN_METER.modes[props.responseMode]
  const tokenTotal =
    usage?.total_tokens === null || usage?.total_tokens === undefined
      ? props.submitting
        ? RUN_METER.pending
        : RUN_METER.notReported
      : usage.calls_without_usage > 0
        ? `At least ${number.format(usage.total_tokens)}`
        : number.format(usage.total_tokens)

  return (
    <section
      className={`run-meter${props.submitting ? ' run-meter--running' : ''}${
        props.failed ? ' run-meter--failed' : ''
      }`}
      aria-label={RUN_METER.label}
      data-testid="playground-run-meter"
    >
      <div className="run-meter__identity">
        <span className="eyebrow">{RUN_METER.eyebrow}</span>
        <span className="run-meter__state" role="status" aria-live="polite">
          {state}
        </span>
        <span className="run-meter__mode">{mode}</span>
      </div>

      <dl className="run-meter__values">
        <div className="run-meter__value">
          <dt>{RUN_METER.time}</dt>
          <dd data-testid="playground-run-time" aria-hidden={props.submitting ? 'true' : undefined}>
            <span data-testid="playground-elapsed">
              {duration === null ? '—' : formatElapsed(duration)}
            </span>
          </dd>
          <span>
            {duration === null ? RUN_METER.noCall : `${number.format(duration)} ms round trip`}
          </span>
        </div>

        <div className="run-meter__value">
          <dt>{RUN_METER.tokens}</dt>
          <dd data-testid="playground-token-total">{tokenTotal}</dd>
          <span>
            {usage
              ? `${usage.calls} model ${usage.calls === 1 ? 'call' : 'calls'} · ${
                  usage.prompt_tokens === null || usage.prompt_tokens === undefined
                    ? 'input not reported'
                    : `${number.format(usage.prompt_tokens)} input`
                } · ${
                  usage.completion_tokens === null || usage.completion_tokens === undefined
                    ? 'output not reported'
                    : `${number.format(usage.completion_tokens)} output`
                }${
                  usage.calls_without_usage > 0
                    ? ` · ${usage.calls_without_usage} ${
                        usage.calls_without_usage === 1 ? 'call did' : 'calls did'
                      } not report usage`
                    : ''
                }`
              : RUN_METER.tokenCaption}
          </span>
        </div>
      </dl>

      {props.submitting ? (
        <p className="run-meter__activity" data-testid="playground-wait">
          {props.responseMode === 'policies' ? WAIT.policiesLine1 : WAIT.line1}
          {props.elapsedMs > 20_000 ? ` ${WAIT.long}` : ''}
        </p>
      ) : null}
    </section>
  )
}
