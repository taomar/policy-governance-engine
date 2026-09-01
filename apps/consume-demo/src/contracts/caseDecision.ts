/**
 * The wire contract, mirrored.
 *
 * These types are a local, hand-written copy of the server's receipt envelopes
 * (`src/policy_platform/contracts/case_decision.py`) and the request body of
 * `POST /api/policy-decisions/{project_key}/case`
 * (`src/policy_platform/api/routers/policy_decisions.py`).
 *
 * They are copied rather than imported, and that is the point of this app: an
 * external consumer has no access to the platform's Python contracts and must
 * be able to work from the published shape alone. Every field name below is
 * spelled exactly as it arrives on the wire, so a mismatch shows up as a type
 * error here rather than as an undefined rendering in the receipt.
 *
 * TWO ENVELOPES, ONE TAG
 *
 * The server writes `case_decision_v2` for every new decision and still serves
 * `case_decision_v1` rows that were written before it existed. Both arrive on
 * the same two routes, discriminated by `schema_version`, exactly as the
 * server's own `CaseDecisionReceipt` union is.
 *
 * They are modelled here as a real discriminated union rather than as one
 * permissive interface with everything optional. A permissive shape is how this
 * page white-screened when v2 first arrived: `envelope.decision.verdict` is a
 * property read on `undefined` the moment `decision` stops existing, and no
 * amount of `?.` sprinkled afterwards tells a reader which fields a given
 * receipt actually has. The tag decides, `classifyReceipt` names the branch,
 * and a receipt carrying neither shape is rendered as an unrecognised envelope
 * instead of crashing the page.
 *
 * Everything else is optional-tolerant. The server omits fields it cannot
 * report truthfully, and a client that assumes presence turns "not knowable"
 * into "undefined" on screen.
 */

/** The envelope this page was originally written against. Still served. */
export const SCHEMA_VERSION_V1 = 'case_decision_v1'
/** The envelope every new decision is written as. */
export const SCHEMA_VERSION_V2 = 'case_decision_v2'
/** The retrieval-only response returned when no decision is requested. */
export const POLICY_RETRIEVAL_SCHEMA_VERSION = 'policy_retrieval_v1'
export const DECISION_LIGHT_SCHEMA_VERSION = 'case_decision_light_v1'

/** @deprecated Use {@link SCHEMA_VERSION_V1}. Kept so older imports still read. */
export const SCHEMA_VERSION = SCHEMA_VERSION_V1


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
 * The closed set an *information* track may report. The first four are the
 * informational gather's own states; the last two are the receipt layer's, and
 * they are not interchangeable — `not_requested` says "you did not ask for
 * this", `not_evaluated` says "nothing was evaluated at all". Collapsing them
 * would let a caller read their own silence as the corpus's.
 */
export const INFORMATION_OUTCOMES = [
  'answered',
  'no_rule_bears',
  'declined',
  'failed',
  'not_requested',
  'not_evaluated',
] as const

export type InformationOutcome = (typeof INFORMATION_OUTCOMES)[number]

/** What an information *section* may be in. A section only exists when the track ran. */
export type InformationStatus = 'answered' | 'no_rule_bears' | 'declined' | 'failed'

/** The closed set a *verdict* track may report. */
export const VERDICT_OUTCOMES = [
  'answered',
  'missing_required_facts',
  'not_settled_by_rules',
  'no_rule_bears',
  'declined',
  'failed',
  'not_requested',
  'not_evaluated',
] as const

export type VerdictOutcome = (typeof VERDICT_OUTCOMES)[number]

export type VerdictStatus =
  | 'answered'
  | 'missing_required_facts'
  | 'not_settled_by_rules'
  | 'no_rule_bears'
  | 'declined'
  | 'failed'

/** A track the caller did not ask for. Never the same as nothing being evaluated. */
export const NOT_REQUESTED = 'not_requested'
/** Nothing was evaluated at all. A legitimate 200, and not an answer. */
export const NOT_EVALUATED = 'not_evaluated'

/** Which of the two tracks a merged citation was cited by. */
export const CITATION_SERVES = ['information', 'verdict'] as const
export type CitationServes = (typeof CITATION_SERVES)[number]

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

export interface RequestRef {  scenario: string
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

/**
 * Which language each stage worked in, and what was actually adjudicated.
 *
 * Additive, and present on every decision made under the language boundary.
 * **Null on a receipt written before the boundary existed** — a different fact
 * from a boundary that reported nothing, and the two stay distinguishable here
 * because a client that renders "no language information" for both cannot tell
 * an old receipt from a broken one.
 *
 * WHY THE RENDERED QUESTION IS ON THE RECEIPT AND IS RENDERED BY THIS PAGE
 *
 * Because it is what was read. Retrieval, classification and both gathers ran
 * against `processing_scenario`; showing only the caller's own words would hide
 * the text the decision was actually made from, and a reader comparing the two
 * is the only person who can catch a rendering that changed the question.
 *
 * What it does *not* touch: `request.scenario`, `request.scenario_hash` and the
 * idempotency binding are all still over the caller's own bytes.
 */
export interface LanguageRef {
  /** BCP 47 tag the inbound rendering observed. `und` when it was malformed. */
  source_language: string
  /** The one language every stage worked in. The reason this block exists. */
  processing_language: string
  /** The language the prose in this receipt is written in. */
  response_language: string
  /** `rendered` or `identity`. Never absent: an unmade call and an identity rendering differ. */
  boundary_state: string
  /** `rendered`, `target_unknown`, or `not_required`. */
  output_rendering_state: string
  /** `not_required`, `rendered`, or `unrendered_dropped`. */
  guidance_rendering_state: string
  input_translation_profile: string
  /** Null when nothing was rendered back. */
  output_translation_profile?: string | null
  /** The question as every stage of the decision read it. */
  processing_scenario: string
  /** SHA-256 over `processing_scenario`, sealed by `decision_hash`. */
  processing_scenario_hash: string
  /** The guidance as the gather read it. Empty when it was dropped. */
  processing_additional_instructions?: string
  /** The corpus projection the retrieval index was built under, once one exists. */
  projection_profile?: string | null
}

/** The rendering did not happen because none was needed. */
export const OUTPUT_RENDERING_NOT_REQUIRED = 'not_required'
/** No usable target tag was observed; prose is returned as it was reasoned. */
export const OUTPUT_RENDERING_TARGET_UNKNOWN = 'target_unknown'
/** Guidance could not be carried across and was dropped rather than applied un-rendered. */
export const GUIDANCE_UNRENDERED_DROPPED = 'unrendered_dropped'
/** The question was carried into the processing language. */
export const BOUNDARY_RENDERED = 'rendered'

/** Whether the rule index took part: per retrieval and per policy. */
export const RULE_INDEX_MATCHED = 'matched'
export const RULE_INDEX_DEGRADED = 'degraded'
export const RULE_INDEX_UNAVAILABLE = 'unavailable'

/**
 * The one retrieval state answered `503` rather than with an empty `200`.
 *
 * A question reduced to the processing language and matched against a corpus
 * that was never rendered into it does not score badly — it scores near zero on
 * every policy, and a near-zero ranking is indistinguishable from a real
 * "nothing bears on this". So it is refused, and this page must never render it
 * as a transient outage a retry would fix.
 */
export const INDEX_PROJECTION_UNAVAILABLE = 'index_projection_unavailable'

export interface VersionRef {
  version_id: string
  version_number?: number | null
  effective_from?: string | null
  effective_to?: string | null
}

/**
 * Which of a policy's rules were actually put in front of the model.
 *
 * A policy holding more rules than one case can read is narrowed to a slice.
 * This is what stops that being a hidden narrowing: for a seventy-four-row
 * penalties table, reporting the policy without reporting the slice is the
 * difference between "the schedule was considered" and "eight of its rows
 * were". Absent on a receipt written before rule-level retrieval existed, and
 * on a policy that was never carried into an evaluation.
 */
export interface RuleSelectionRef {
  total_rules: number
  selected_rules: number
  selected_rule_ids?: string[]
  rules_discarded?: number
  /** `whole_policy`, `scenario_relevance_v1`, `scenario_relevance_v2`, or `document_order`. */
  method: string
  sliced?: boolean
  /** Counted inside `selected_rules`: context fills unused slots, never extends the budget. */
  context_rules_added?: number
  context_rules_omitted?: string[]
  /**
   * Rules that were not candidates for selection because an earlier rule of the
   * same policy governs identically. A copy is not a second rule and may not
   * take a second slot.
   */
  duplicate_rules_collapsed?: number
  /**
   * Rules that were not read and did not need to be: each is an exact copy of a
   * rule that was. Part of `rules_discarded`, named so that number is not read
   * as "unknown content". **None of these was put in front of the model.**
   */
  represented_rule_ids?: string[]
  /**
   * Whether the rule index took part in *this policy's* selection: `matched`,
   * `degraded` or `unavailable`. Per policy as well as per retrieval, because a
   * project-wide degradation and a policy with no rule documents are different
   * facts about different policies in one answer.
   */
  rule_index_state?: string | null
  /**
   * How many of this policy's rules the rule index ranked. Zero with `matched`
   * is a real answer — the index was asked and placed none — and is not the
   * same as `unavailable`, where it was not asked.
   */
  rule_index_hits?: number | null
  /** Rules the relevance ranking placed, over whichever corpus it scored. */
  lexical_candidates?: number | null
  /**
   * Rules stating a quantity that admits a quantity the question states. A
   * retrieval rank only: it decides whether a rule is worth reading, never what
   * the rule decides.
   */
  quantity_candidates?: number | null
  /** Rules at least one ranking placed. When zero, the method is `document_order`. */
  fused_candidates?: number | null
  /**
   * Slots reserved so distinct source passages are covered before a passage's
   * second rule competes. Half the budget, rounded up.
   */
  evidence_diversity_quota?: number | null
  /**
   * Rules the relevance ranking could not score because the index returned no
   * English projection for them. They score zero rather than being scored
   * against the document's own language, and can still be placed by the rule
   * index or the quantity rank.
   */
  rules_without_projection?: number | null
  chars?: number | null
  budget_chars?: number | null
  oversize?: boolean
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
  /**
   * Set only on a policy discarded as `duplicate_policy_content`: the provision
   * key of the identically-governing policy retrieved in its place. It names
   * where this policy's terms were in fact read, without claiming this record
   * was read.
   */
  duplicate_of_provision_key?: string | null
  reason?: string | null
  payload_url?: string | null
  rule_selection?: RuleSelectionRef | null
}

export interface RetrievalRef {
  status: string
  method?: string | null
  precision_mode?: string | null
  semantic_candidates?: number | null
  semantic_selected?: number | null
  semantic_largest_gap?: number | null
  semantic_cutoff_score?: number | null
  semantic_elbow_applied?: boolean | null
  direct_policy_order?: string | null
  coverage_expanded_policies?: number | null
  coverage_semantic_floor?: number | null
  rule_rescue_candidates?: number | null
  rule_rescued_policies?: number | null
  rule_rescue_floor?: number | null
  rule_rescue_margin?: number | null
  rule_semantic_window?: number | null
  rule_semantic_candidates?: number | null
  policy_budget?: number | null
  policy_scan?: number | null
  policies_retrieved?: number | null
  policies_considered?: number | null
  policies_retained?: number | null
  policies_discarded?: number | null
  policies_untestable?: number | null
  /** The combined-record ceiling one grounded pass reads, in characters. */
  payload_budget_chars?: number | null
  /** Ranked inside the retention budget and still set aside on size alone. */
  policies_over_payload_budget?: number | null
  /** Above this many rules a policy is read rule by rule rather than whole. */
  large_policy_rule_threshold?: number | null
  selected_rule_budget?: number | null
  /** Retained policies that were read as a slice of their rules. */
  policies_rule_sliced?: number | null
  /**
   * Policies collapsed before the retention budget because they govern
   * identically to a policy already retrieved. A subset of `policies_discarded`
   * and **the only discard whose terms still reached the gather** — each names
   * the representative it was collapsed into.
   */
  policies_duplicate_collapsed?: number | null
  /**
   * How the retained set was chosen from the ranked hits, for example
   * `relevance_then_normative_content_v1`: relevance first, then
   * normative-content diversity.
   */
  policy_selection_order?: string | null
  /**
   * Policies that ranked inside the retention budget and were offered after it
   * because a policy requiring the same thing was offered first. **Not
   * duplicates** — they are not proven identical, they keep their own rank and
   * score, and they carry the ordinary `outside_budget` reason.
   */
  policies_diversity_deferred?: number | null
  /**
   * How many rule-level documents the discovery search examined. A rule
   * document is one authoritative rule of a policy holding more than
   * `large_policy_rule_threshold` of them, indexed on its own so a rule can be
   * found on its own terms rather than only through whatever its policy's
   * combined text had room for.
   */
  rule_scan?: number | null
  /**
   * The versioned corpus projection the index was matched against. A question
   * and the text it is scored against must be rendered under one contract or
   * the two are not comparable, and this names the one that was used. Null when
   * no index was consulted.
   */
  projection_profile?: string | null
  /**
   * Whether the index reported a complete corpus projection under the expected
   * contract. Only ever true on a served answer — an absent, superseded or
   * half-rebuilt projection is refused with `index_projection_unavailable`.
   */
  projection_ready?: boolean | null
  policy_documents_matched?: number | null
  rule_documents_matched?: number | null
  /**
   * Compatibility alias for policies admitted by independently strong
   * rule-only evidence. Rule scores are never added to direct policy scores.
   */
  policies_elevated_by_rule?: number | null
  /** `matched`, `degraded`, or `unavailable`. See `RULE_INDEX_*`. */
  rule_index_state?: string | null
  reason?: string | null
}

/**
 * The discard reason a collapsed exact-duplicate policy carries.
 *
 * Named because it is the one discard that must never be rendered as content
 * the gather did not see: the policy's record was not read, and its terms were,
 * in the representative it names.
 */
export const DISCARD_DUPLICATE_POLICY_CONTENT = 'duplicate_policy_content'

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

export interface TokenUsageRef {
  calls: number
  calls_without_usage: number
  prompt_tokens?: number | null
  completion_tokens?: number | null
  total_tokens?: number | null
  reasoning_tokens?: number | null
}

export interface TraceRef {
  prompt_version?: string | null
  instruction_profile?: string | null
  model_deployment?: string | null
  stage_latency_ms?: Record<string, number> | null
  token_usage?: TokenUsageRef | null
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

/**
 * The fields both envelopes carry, spelled once.
 *
 * Identity, who asked and under what, what retrieval did, and the seal. What
 * differs between v1 and v2 is only *the answer's shape*, so only the answer's
 * shape is modelled twice.
 */
export interface EnvelopeCommon {
  decision_id: string
  correlation_id: string
  idempotency_key?: string | null

  policy_set: PolicySetRef
  active_version?: VersionRef | null

  caller: CallerRef
  request: RequestRef

  retrieval: RetrievalRef
  considered?: PolicyRef[]
  excluded?: PolicyRef[]

  size?: SizeRef | null
  trace: TraceRef

  decision_hash: string
  hash_basis?: string
  receipt_url: string
  decided_at: string
  latency_ms: number
}

/**
 * The full receipt for one audited external project-case decision, `v1`.
 *
 * Historical: nothing writes this shape any more. It is still served for rows
 * written under it, and it still renders here, because a receipt that stopped
 * being readable would defeat the point of having written one.
 */
export interface CaseDecisionEnvelope extends EnvelopeCommon {
  schema_version: typeof SCHEMA_VERSION_V1
  decision_status: DecisionStatus
  decision: DecisionRef
  citations?: CitationRef[]
  grounding?: GroundingRef | null
}

/* ---------- case_decision_v2: two independently answerable tracks -------- */

/**
 * What the classifier read the question as asking for. Nothing derived.
 *
 * Two independent booleans from one classifier call: a question can be
 * information-only, verdict-only, or both. When retrieval produced nothing to
 * evaluate the classifier never ran, both booleans are false and
 * `classifier_version` is null — which is the truth, and is why `outcome` is
 * the field to read first and `asked` is the field that explains it.
 */
export interface AskedRef {
  information_requested: boolean
  verdict_requested: boolean
  /** Prose. Deliberately outside the decision hash: it explains routing. */
  classification_reasoning?: string | null
  classifier_version?: string | null
}

/** One outcome per track. **Read this before either section.** */
export interface OutcomeRef {
  information: InformationOutcome
  verdict: VerdictOutcome
}

/**
 * One rule the receipt rested on, and which track (or tracks) cited it.
 *
 * The top-level list is deduplicated by `rule_id` and the tags accumulate: the
 * rule that *states* a weekly cap is frequently the same rule that *decides*
 * whether a shift was within it, and listing it twice would make a reader count
 * two authorities where the policies hold one.
 */
export interface MergedCitationRef extends CitationRef {
  serves?: CitationServes[]
}

/** What the retained published policies state on the subject asked about. */
export interface InformationSection {
  status: InformationStatus
  /** True exactly when `status` is `answered`. Enforced server-side. */
  answered: boolean
  /** Non-empty exactly when `answered`. */
  answer?: string
  /** Prose composed when the track did *not* answer. Null when it did. */
  explanation?: string | null
  route?: string
  citations?: CitationRef[]
  note?: string
  grounding?: GroundingRef | null
}

/**
 * One fact the case needs before a verdict can be reached.
 *
 * This is the field the v2 redesign exists for. A caller whose case cannot be
 * decided used to receive a status and a list of bare strings; what they need
 * is something a form can be built from — what the fact is, what to call it in
 * front of a user, why it decides anything, and which rules are waiting on it.
 */
export interface MissingInformationItem {
  /** The fact as the policy record names it. */
  fact: string
  /** A short human label, in the language the question was asked in. */
  label: string
  /** One sentence saying which judgement turns on this fact. May be empty. */
  why_needed?: string
  /** Restricted server-side to rules that were actually in front of the gather. */
  required_by_rule_ids?: string[]
}

/**
 * One condition to confirm before acting on a verdict that *was* reached.
 *
 * The counterpart to `MissingInformationItem`, and the difference between them
 * is the whole reason both exist. A missing fact is something the determination
 * hangs on: until it arrives there is no verdict. A verification requirement
 * hangs on nothing — the rules settled the question that was asked — but it must
 * be confirmed before anyone acts on the answer. A balance to check, an approval
 * to seek, a window to observe, a category held on a record elsewhere.
 *
 * So it is additive, and a client must not render it as a blocker: the verdict
 * beside it is a real verdict, and downgrading it would undo the distinction.
 */
export interface VerificationRequirementItem {
  /** The condition's key, as the policy record names the thing to confirm. */
  fact: string
  /** A short human label, in the language the question was asked in. */
  label: string
  /** One sentence saying what to confirm and why, before acting. May be empty. */
  why_needed?: string
  /** Restricted server-side to rules that were actually in front of the gather. */
  required_by_rule_ids?: string[]
}

/**
 * The determination, or the honest account of why there is not one.
 *
 * `decision` is non-empty **iff** `reached` **iff** `status` is `answered`, and
 * the server refuses any other combination. That is what stops the one failure
 * mode that matters: a "no", a "not compliant" or a "denied" is a *reached*
 * verdict and belongs in `decision`; a case that could not be decided leaves it
 * empty, and no client can read the second as the first.
 */
export interface VerdictSection {
  status: VerdictStatus
  reached: boolean
  decision?: string
  explanation?: string
  /** Populated only when `status` is `missing_required_facts`. */
  missing_information?: MissingInformationItem[]
  /** The same facts as bare labels, preserved for older clients. */
  missing_required_facts?: string[]
  /**
   * Conditions to confirm before acting on a reached verdict. Populated only
   * when `status` is `answered`; absent on a receipt written before the field
   * existed, which is why it is optional rather than defaulted.
   */
  verification_requirements?: VerificationRequirementItem[]
  route?: string
  citations?: CitationRef[]
  note?: string
  grounding?: GroundingRef | null
}

/** The full receipt for one audited external project-case decision, `v2`. */
export interface CaseDecisionEnvelopeV2 extends EnvelopeCommon {
  schema_version: typeof SCHEMA_VERSION_V2
  /** The stored row's lifecycle, distinct from either track's outcome. */
  receipt_status?: string

  /**
   * Which language each stage worked in, and the question as it was actually
   * adjudicated. Null only on a receipt written before the language boundary
   * existed — which is why the UI distinguishes "this receipt predates the
   * boundary" from a boundary that reported nothing.
   */
  language?: LanguageRef | null

  asked: AskedRef
  outcome: OutcomeRef

  /** Null when `outcome.information` is `not_requested` or `not_evaluated`. */
  information?: InformationSection | null
  /** Null when `outcome.verdict` is `not_requested` or `not_evaluated`. */
  verdict?: VerdictSection | null

  /** Every rule either track rested on, deduplicated and tagged with `serves`. */
  citations?: MergedCitationRef[]
}

/**
 * The two envelopes as one type, discriminated on `schema_version`.
 *
 * A reader does not branch on the version by hand — `classifyReceipt` does it,
 * and narrows the type while it is at it.
 */
export type CaseDecisionReceipt = CaseDecisionEnvelope | CaseDecisionEnvelopeV2

export type PlaygroundResponseMode = 'decision' | 'decision-light' | 'policies'

export type DecisionLightResponseType = 'informational' | 'decision' | 'mixed' | 'not_evaluated'

export interface DecisionLightInformation {
  status: InformationStatus
  answer: string
  explanation?: string | null
  note: string
}

export interface DecisionLightVerdict {
  status: VerdictStatus
  reached: boolean
  decision: string
  explanation: string
  missing_information: MissingInformationItem[]
  verification_requirements: VerificationRequirementItem[]
  note: string
}

export interface DecisionLightPolicy {
  provision_id?: string | null
  provision_key?: string | null
  heading_path: string[]
}

export interface DecisionLightCitation {
  rule_id: string
  policy?: DecisionLightPolicy | null
  source: CitationSourceRef
  serves: CitationServes[]
}

export interface CaseDecisionLightEnvelope {
  schema_version: typeof DECISION_LIGHT_SCHEMA_VERSION
  response_type: DecisionLightResponseType
  decision_id: string
  correlation_id: string
  idempotency_key?: string | null
  policy_set: PolicySetRef
  active_version?: VersionRef | null
  request: { scenario: string; scenario_hash: string }
  asked: {
    information_requested: boolean
    verdict_requested: boolean
    classifier_version?: string | null
  }
  outcome: OutcomeRef
  information?: DecisionLightInformation | null
  verdict?: DecisionLightVerdict | null
  retrieval: {
    status: string
    method?: string | null
    policies_retained?: number | null
    rule_rescued_policies?: number | null
    reason?: string | null
  }
  policies: DecisionLightPolicy[]
  citations: DecisionLightCitation[]
  trace: {
    classifier_version?: string | null
    prompt_version?: string | null
    plan_profile?: string | null
    selector_catalogue_version?: string | null
    model_deployment?: string | null
    stage_latency_ms?: Record<string, number> | null
    token_usage?: TokenUsageRef | null
  }
  decision_hash: string
  hash_basis: string
  receipt_url: string
  latency_ms: number
}

export interface PolicyRetrievalQueryRef {
  scenario: string
  scenario_hash: string
}

export interface RetrievedPolicyIdentity {
  provision_id?: string | null
  provision_key: string
  heading_path: string[]
}

export interface PolicyMatchRef {
  best_rank?: number | null
  best_score?: number | null
  rule_selection?: RuleSelectionRef | null
}

export interface RetrievedPolicyRecord {
  policy: RetrievedPolicyIdentity
  match: PolicyMatchRef
  payload: Record<string, unknown>
}

/** Filtered published policy records, with no decision-shaped fields. */
export interface PolicyRetrievalEnvelope {
  schema_version: typeof POLICY_RETRIEVAL_SCHEMA_VERSION
  correlation_id: string
  policy_set: PolicySetRef
  active_version?: VersionRef | null
  query: PolicyRetrievalQueryRef
  retrieval: RetrievalRef
  policies: RetrievedPolicyRecord[]
  size: SizeRef
  language: LanguageRef
  token_usage: TokenUsageRef
  latency_ms: number
}

export type ReceiptKind = 'v1' | 'v2' | 'unrecognised'

/**
 * Which envelope this is, by tag first and by shape second.
 *
 * The tag is authoritative and is what the server discriminates on. The
 * structural fallback exists for one honest case and one defensive one: a row
 * written before `schema_version` was ever serialised reads as v1, exactly as
 * the server's own `validate_receipt` treats it; and a future envelope this
 * build has never heard of returns `unrecognised` rather than being coerced
 * into a shape whose fields it does not have. Coercion is what white-screens a
 * page — `envelope.decision.verdict` on a receipt with no `decision`.
 */
export function classifyReceipt(receipt: unknown): ReceiptKind {
  if (receipt === null || typeof receipt !== 'object') return 'unrecognised'
  const candidate = receipt as Record<string, unknown>
  const version = candidate.schema_version

  if (version === SCHEMA_VERSION_V2) return 'v2'
  if (version === SCHEMA_VERSION_V1) return 'v1'

  if (typeof version === 'string' && version.length > 0) {
    // A tag this build does not know. Trust the tag over the shape: a v3 that
    // happens to keep an `outcome` key is not a v2, and guessing would render
    // a partial answer as a whole one.
    return 'unrecognised'
  }

  // No tag at all. Only receipts predating the field can be in this state.
  if ('outcome' in candidate && 'asked' in candidate) return 'v2'
  if ('decision' in candidate && 'decision_status' in candidate) return 'v1'
  return 'unrecognised'
}

export function isV2Receipt(receipt: CaseDecisionReceipt): receipt is CaseDecisionEnvelopeV2 {
  return classifyReceipt(receipt) === 'v2'
}

export function isV1Receipt(receipt: CaseDecisionReceipt): receipt is CaseDecisionEnvelope {
  return classifyReceipt(receipt) === 'v1'
}

/**
 * Whether an outcome means the track produced no section at all.
 *
 * Named because the two values that mean it are not interchangeable and the
 * check is made in several places; spelling `x === 'not_requested' || x ===
 * 'not_evaluated'` by hand is how one of them eventually gets forgotten.
 */
export function trackHasNoSection(outcome: InformationOutcome | VerdictOutcome): boolean {
  return outcome === NOT_REQUESTED || outcome === NOT_EVALUATED
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

export interface PolicyRetrievalRequestBody {
  scenario: string
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
