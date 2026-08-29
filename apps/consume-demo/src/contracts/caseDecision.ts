/**
 * The wire contract, mirrored.
 *
 * These types are a local, hand-written copy of the server's `case_decision_v1`
 * envelope (`src/policy_platform/contracts/case_decision.py`) and the request
 * body of `POST /api/policy-decisions/{project_key}/case`
 * (`src/policy_platform/api/routers/policy_decisions.py`).
 *
 * They are copied rather than imported, and that is the point of this app: an
 * external consumer has no access to the platform's Python contracts and must
 * be able to work from the published shape alone. Every field name below is
 * spelled exactly as it arrives on the wire, so a mismatch shows up as a type
 * error here rather than as an undefined rendering in the receipt.
 *
 * Everything is optional-tolerant. The server omits fields it cannot report
 * truthfully, and a client that assumes presence turns "not knowable" into
 * "undefined" on screen.
 */

/** The name of the envelope this page is written against. */
export const SCHEMA_VERSION = 'case_decision_v1'

/**
 * The closed set `decision_status` may take -- seven values, not five.
 * `failed` and `not_evaluated` belong to the receipt layer rather than to the
 * decider, and a client that only handles the decider's five will render a
 * blank status for the two that matter most.
 */
export const DECISION_STATUSES = [
  'answered',
  'missing_required_facts',
  'not_settled_by_rules',
  'no_rule_bears',
  'declined',
  'failed',
  'not_evaluated',
] as const

export type DecisionStatus = (typeof DECISION_STATUSES)[number]

/**
 * The single status that carries a verdict. Named here, used as the only
 * guard in the UI, so the client's rule and the server's `STATUS_WITH_VERDICT`
 * cannot drift into disagreeing.
 */
export const STATUS_WITH_VERDICT: DecisionStatus = 'answered'

/** The ceiling the server applies *after* whitespace normalisation. */
export const MAX_ADDITIONAL_INSTRUCTIONS_CHARS = 2000

export interface CallerRef {
  principal_identity: string
  principal_role: string
  authentication_source: string
  calling_system_identity?: string | null
  channel?: string
}

export interface RequestRef {
  scenario: string
  scenario_hash: string
  /**
   * Present on this server. Absent on a server that predates caller guidance --
   * which is why this is optional and why the UI distinguishes "the key was not
   * returned" from "the key was returned holding an empty string".
   */
  additional_instructions?: string
  additional_instructions_hash?: string
  scope: string
  requested_provision_id?: string | null
  reasoning_effort_requested: string
  received_at: string
}

export interface PolicySetRef {
  id: string
  key: string
  name: string
}

export interface VersionRef {
  version_id: string
  version_number?: number | null
  effective_from?: string | null
  effective_to?: string | null
}

export interface PolicyRef {
  provision_id?: string | null
  provision_key?: string | null
  heading_path?: string[]
  rules?: number | null
  retained?: boolean | null
  best_rank?: number | null
  best_score?: number | null
  discard_reason?: string | null
  reason?: string | null
  payload_url?: string | null
}

export interface RetrievalRef {
  status: string
  method?: string | null
  policy_budget?: number | null
  policy_scan?: number | null
  policies_retrieved?: number | null
  policies_considered?: number | null
  policies_retained?: number | null
  policies_discarded?: number | null
  policies_untestable?: number | null
  reason?: string | null
}

export interface CitationSourceRef {
  state: string
  text?: string | null
  page?: number | null
  section?: string | null
}

export interface CitationRef {
  rule_id: string
  policy?: PolicyRef | null
  source: CitationSourceRef
}

export interface DecisionRef {
  intent?: string | null
  classification_reasoning?: string | null
  status: DecisionStatus
  verdict?: string
  explanation?: string
  missing_required_facts?: string[]
  note?: string
  decider_route?: string | null
}

export interface TraceRef {
  prompt_version?: string | null
  instruction_profile?: string | null
  model_deployment?: string | null
  retrieval_method?: string | null
  index_name?: string | null
  index_version_id?: string | null
}

export interface SizeRef {
  combined_chars?: number | null
  budget_chars?: number | null
  oversize?: boolean | null
}

export interface GroundingRef {
  rules_available?: number | null
  rules_cited?: number | null
  policies_grounded?: number | null
  citations_requested?: number | null
  fabricated_citations?: string[]
  oversize?: boolean | null
  prompt_version?: string | null
  [key: string]: unknown
}

/** The full receipt for one audited external project-case decision. */
export interface CaseDecisionEnvelope {
  schema_version: string
  decision_id: string
  correlation_id: string
  idempotency_key?: string | null

  policy_set: PolicySetRef
  active_version?: VersionRef | null

  caller: CallerRef
  request: RequestRef

  decision_status: DecisionStatus

  retrieval: RetrievalRef
  considered?: PolicyRef[]
  excluded?: PolicyRef[]

  decision: DecisionRef
  citations?: CitationRef[]
  grounding?: GroundingRef | null
  size?: SizeRef | null

  trace: TraceRef

  decision_hash: string
  hash_basis?: string
  receipt_url: string
  decided_at: string
  latency_ms: number
}

/**
 * The request body, exactly as it is serialised.
 *
 * `additional_instructions` is optional in the TypeScript sense *and* omitted
 * from the JSON when there is no guidance. The two are not the same thing and
 * the difference is load bearing: an empty string is a value the receipt will
 * echo back, an absent key is an absence the receipt can report as one.
 *
 * `correlation_id` and `idempotency_key` are deliberately not here. They travel
 * as the `X-Correlation-Id` and `Idempotency-Key` headers, because they
 * describe the delivery of the request rather than the question being asked --
 * and putting the idempotency key in the body would make it part of the hash it
 * is compared against.
 */
export interface CaseDecisionRequestBody {
  scenario: string
  reasoning_effort: ReasoningEffort
  calling_system_identity: string
  additional_instructions?: string
}

export type ReasoningEffort = 'low' | 'medium' | 'high'

/** What `GET /api/policy-sets/{key}` returns, narrowed to what this page reads. */
export interface PolicySetSummary {
  id: string
  key: string
  name: string
  active_version_id?: string | null
  active_version_number?: number | null
}

/** What `GET /api/policy-sets/{key}/active-version` returns, narrowed likewise. */
export interface ActiveVersionSummary {
  id: string
  version_number?: number | null
  effective_from?: string | null
  effective_to?: string | null
}

/**
 * The shape of a FastAPI error detail on these routes. The platform returns a
 * structured object with a `code`; it also has paths that return a plain
 * string, so both are accepted.
 */
export interface ApiErrorDetail {
  code?: string
  message?: string
  decision_id?: string
  correlation_id?: string
  [key: string]: unknown
}
