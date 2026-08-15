/**
 * Typed HTTP client for the PolicyVerbAItim API.
 *
 * Mirrors src/policy_platform/api/schemas.py and contracts/evaluation.py.
 * Kept dependency-free (native fetch) since this is a thin admin/demo UI,
 * not a large SPA.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8010";

import { actorRoleRefusalText, isActorRoleRefusal } from "./actorRole";
// A sighting is declared where it is rendered, and read from there here, so the
// wire shape has one description rather than two that agree until they do not.
// A previous copy of this interface was written from the design instead of from
// a response and named three fields the server never sends; it cost a crash no
// test caught, because each side was checking itself against its own idea of
// the shape. `tests/unit/test_provision_history.py` now compares the pane's
// declaration against the endpoint's keys in both directions, so retyping it
// here would fail that guard, and would be right to.
import type { PolicySightingView } from "./components/policyTabPanes";

export interface ApiError {
  status: number;
  detail: string;
}

export class PolicyPlatformApiError extends Error implements ApiError {
  status: number;
  detail: string;
  /**
   * The server's own name for this refusal, when it sent one.
   *
   * Present when `detail` was an object rather than a sentence. A caller that
   * needs to act on a particular refusal matches this and never the words,
   * so rewording cannot change behaviour.
   */
  code?: string;
  /** The rest of a structured refusal, for a caller that needs its fields. */
  data?: Record<string, unknown>;
  constructor(
    status: number,
    detail: string,
    options?: { cause?: unknown; code?: string; data?: Record<string, unknown> },
  ) {
    super(detail, options);
    this.status = status;
    this.detail = detail;
    this.code = options?.code;
    this.data = options?.data;
  }
}

/**
 * Status used when no HTTP response happened at all — the request never reached
 * a server. It is deliberately not a real status code: a caller needs to tell
 * "the server answered, and the answer was no" from "we could not ask", and
 * those two lead to different things being shown to a reader.
 */
export const API_UNREACHABLE_STATUS = 0;

/**
 * `fetch` rejects with a bare `TypeError: Failed to fetch` when the server is
 * down, the connection drops, or CORS refuses the request. That is an internal
 * exception name and it was reaching policy reviewers verbatim. Converting it
 * here, at the one seam every request passes through, means no calling page has
 * to know what a TypeError is.
 */
function unreachable(cause: unknown): PolicyPlatformApiError {
  return new PolicyPlatformApiError(
    API_UNREACHABLE_STATUS,
    "Cannot reach the policy platform server. It may be restarting, or the connection was interrupted.",
    { cause },
  );
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
  } catch (cause) {
    throw unreachable(cause);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      // A structured refusal: the server sent a code and the fields a reader's
      // sentence needs, and the words for it live in this app. Before this,
      // `body.detail ?? JSON.stringify(body)` would have put the raw object in
      // front of a reviewer as `[object Object]`.
      if (isActorRoleRefusal(body.detail)) {
        throw new PolicyPlatformApiError(res.status, actorRoleRefusalText(body.detail), {
          code: body.detail.code,
          data: body.detail,
        });
      }
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body);
    } catch (cause) {
      if (cause instanceof PolicyPlatformApiError) throw cause;
      // ignore parse failure, fall back to statusText
    }
    throw new PolicyPlatformApiError(res.status, detail);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

/** Badge counts for the project workspace tab strip — one request for all tabs. */
export interface WorkspaceCounts {
  documents: number;
  review_pending: number;
  policies: number;
  versions: number;
  limits: number;
  tests: number;
  regression_tests: number;
  exceptions_open: number;
  correlation_findings: number;
  decisions: number;
}

export interface ProjectPortfolioInsight {  key: string;
  document_count: number;
  review_pending: number;
  /** Live (non-superseded) candidate records held by this project, whether or not
   *  any have been published. `active_rule_count` below counts PUBLISHED rules and
   *  is 0 until a version is approved, so the two disagree by design: they measure
   *  different stages of the same record's life, not the same thing twice. */
  live_candidate_count: number;
  /** Live records whose test the source states as a comparison, so it can be
   *  evaluated directly. */
  candidate_direct_count: number;
  /** Live records the source states in words, so they are decided by reading.
   *  Counted independently of `candidate_direct_count`: a record carrying neither
   *  mode is in no route count, so the two need not sum to `live_candidate_count`
   *  and a caller must not derive one by subtracting the other. */
  candidate_reading_count: number;
  version_count: number;
  active_version_number: number | null;
  last_published_at: string | null;
  active_rule_count: number;
  machine_executable_count: number;
  test_count: number;
  regression_test_count: number;
  /** The bytes of the document this set governs. Two projects sharing it are
   *  two extractions of one document, which is what the register groups on --
   *  titles carry each run's annotation and cannot serve. */
  document_content_hash: string | null;
  /** The title this document was first given, before any re-run renamed it. */
  document_title: string | null;
  /** Extraction runs reaching this set through its document versions. */
  run_count: number | null;
  latest_quality_high: number | null;
  latest_quality_medium: number | null;
  latest_quality_low: number | null;
  latest_quality_at: string | null;
  /** Which population the latest quality evaluation covered — `candidates` or
   *  `published`. Carried because the register now surfaces whichever ran most
   *  recently, and a finding count that silently switched population would be
   *  reporting two different things under one label. */
  latest_quality_scope: string | null;
  /** How many rules that evaluation covered, so a finding count can be read
   *  against the size of what was checked. */
  latest_quality_rule_count: number | null;
}

export interface TrustedConfigResponse {
  policy_set_key: string;
  trusted_config: Record<string, unknown>;
  /** Shape problems that would make part of the config silently unreachable by the agent. */
  warnings: string[];
  fact_count: number;
  output_count: number;
}

export interface PolicySet {
  id: string;
  key: string;
  name: string;
  owner: string;
  description: string;
  category: string;
  tags: string[];
  review_due_date: string | null;
  last_reviewed_at: string | null;
  is_review_overdue: boolean;
  accountable_owner: string;
  delegate_approver: string;
  escalation_contact: string;
  consulted_parties: string[];
  informed_parties: string[];
}

export interface CreatePolicySetRequest {
  key: string;
  name: string;
  owner: string;
  description?: string;
  category?: string;
  tags?: string[];
  accountable_owner?: string;
  delegate_approver?: string;
  escalation_contact?: string;
  consulted_parties?: string[];
  informed_parties?: string[];
}

export interface UpdatePolicySetRequest {
  name?: string;
  description?: string;
  category?: string;
  tags?: string[];
  review_due_date?: string | null;
  clear_review_due_date?: boolean;
  accountable_owner?: string;
  delegate_approver?: string;
  escalation_contact?: string;
  consulted_parties?: string[];
  informed_parties?: string[];
}

export interface MarkPolicySetReviewedRequest {
  next_due_date?: string | null;
}

export interface ApprovedPolicyVersion {
  id: string;
  policy_set_id: string;
  version_number: number;
  effective_from: string;
  effective_to: string | null;
  is_active: boolean;
  approved_by: string;
  approved_at: string;
  rule_count: number;
}

export interface ImportPolicyVersionRequest {
  version_number: number;
  effective_from: string;
  effective_to?: string | null;
  approved_by: string;
  is_active?: boolean;
  rules: unknown[];
}

export interface PolicyAuthority {
  level: string;
  owner: string;
  rank: number;
}

export interface PolicyScope {
  jurisdictions: string[];
  organizational_units: string[];
  personas: string[];
  processes: string[];
}

export type ConditionOperator =
  | "equals"
  | "notEquals"
  | "greaterThan"
  | "greaterThanOrEqual"
  | "lessThan"
  | "lessThanOrEqual"
  | "in"
  | "notIn"
  | "contains"
  | "startsWith"
  | "endsWith"
  | "exists"
  | "isNull"
  | "before"
  | "after"
  | "onOrBefore"
  | "onOrAfter"
  | "withinDuration"
  | "countEquals"
  | "countGreaterThan";

/**
 * One attribute the formulator assigned, with the words it assigned.
 *
 * Three parts and nothing else: the attribute's own name, the document's text,
 * and the identifier a case supplies a value for. Derived once on the server
 * and served in the JSON, so a view of a record and the record itself are the
 * same table.
 */
export interface PolicyAttribute {
  /** The canonical field name, exactly as the record declares it. */
  attribute: string;
  /** The document's words for that attribute, verbatim. */
  text: string;
  /** The fact a case supplies a value for, or null when the document states it. */
  fact: string | null;
  /** `money` | `duration` | `number` | `boolean`, when the fact states one. */
  data_type: string | null;
}

/** A rule's attributes, split into what scopes it and what follows. */
export interface PolicyAttributes {
  applies: PolicyAttribute[];
  outcome: PolicyAttribute[];
}

/**
 * One thing the policy names that a case must supply a value for.
 *
 * Names and phrases are the document's own words. The policy's own numbers are
 * deliberately absent: a stated amount is what the document tells you, not
 * something a case establishes.
 */
export interface PolicyFact {
  /** Stable identifier derived from the phrase's own words. */
  name: string;
  /** The document's wording, verbatim. */
  source_phrase: string;
  /** Every part the phrase plays: `subject`, `threshold`, `authority`, … */
  roles: string[];
  /** `money` | `duration` | `number` | `boolean`, or null when unstated. */
  data_type: string | null;
}

/**
 * Why a rule's condition tree is what it is, as the server derived it.
 * Mirrors `contracts/policy.ConditionProvenance`.
 *
 * A code, not a sentence. The server used to send a paragraph per rule saying
 * what a reviewer should do about it; wording for a human belongs here, in the
 * interface that shows it to them.
 */
export interface ConditionProvenance {
  /** `derived` | `derived_from_stated_bound` | `conditions_not_projected`
   *  | `conditions_not_representable` | `no_scope_derived` */
  code: string;
  unsupported_expression: string;
  /**
   * The document's own wording for a quantity that reached the record and did
   * not compile into a comparison.
   *
   * Two of the route wordings tell the reviewer this figure is shown beside
   * the reason. The server sent it and this interface did not declare it, so
   * the sentence promised evidence that nothing drew — and a reviewer shown no
   * figure concludes the document stated none, which is the opposite of what
   * the refusal recorded.
   */
  unprojected_quantity: string;
}

/** One phrase the projection classified, with the evidence for its role. */
export interface ClassifiedEntity {
  phrase: string;
  role: string;
  basis: string;
  normalized_id?: string | null;
}

/**
 * A condition the source states, decomposed.
 *
 * `concept` is a stable identifier for what the condition is *about*, derived
 * from the source's own wording. `operator` and `value` are present only when
 * the sentence actually states a comparison — `predicate_status` says which
 * case it is, so an unstated comparison reads as unstated rather than as a
 * missing value someone forgot to supply.
 */
export interface SourceCondition {
  source_text: string;
  concept: string;
  predicate_status: string;
  operator?: string | null;
  value?: string | null;
  unspecified_note?: string | null;
  fact_model_status?: string | null;
  mapped_to?: string | null;
}

/**
 * How a rule reads as an access-control decision, derived on the server from
 * the canonical record. Kept separate from the rule's own fields: this is a
 * projection, and the canonical record stays the source of truth.
 */
export interface PolicyXacmlView {
  source_semantics: {
    subjects: ClassifiedEntity[];
    resources: ClassifiedEntity[];
    action?: ClassifiedEntity | null;
    conditions: SourceCondition[];
    normative_modality?: string | null;
    outcome?: string | null;
    unclassified: ClassifiedEntity[];
  };
  xacml_projection: {
    target: { subject_ids: string[]; resource_ids: string[]; action_ids: string[] };
    condition: unknown[];
    effect?: string | null;
    effect_basis: string;
    obligation_expressions: unknown[];
    advice_expressions: unknown[];
    compilation_status: string;
  };
  fact_model_readiness: { required_attributes: unknown[]; fact_model_configured: boolean };
  runtime_evaluation?: unknown;
}

export interface FactComparisonCondition {
  type: "factComparison";
  fact: string;
  operator: ConditionOperator;
  value: unknown;
}

/**
 * A right-hand side that names another fact instead of a literal value.
 * `factor` scales it before comparison, so 0.10 encodes "10% of".
 */
export interface FactOperand {
  fact: string;
  factor: number;
}

/**
 * Compares a fact against a multiple of *another* fact — "an annual increase
 * not exceeding 10% of the employee's current basic salary". Distinct from
 * `factComparison` because both sides are fact paths, so both must be shown
 * and both are required at evaluation time.
 */
export interface FactRelativeComparisonCondition {
  type: "factRelativeComparison";
  fact: string;
  operator: ConditionOperator;
  reference: FactOperand;
}

export interface AllCondition {
  type: "all";
  all: ConditionNode[];
}

export interface AnyCondition {
  type: "any";
  any: ConditionNode[];
}

export interface NotCondition {
  type: "not";
  not: ConditionNode;
}

export type ConditionNode =
  | FactComparisonCondition
  | FactRelativeComparisonCondition
  | AllCondition
  | AnyCondition
  | NotCondition;

export interface Effect {
  // "informational": the rule states vocabulary/classification (definition,
  // classification rule_type) rather than authorizing or forbidding
  // anything — never rendered as allow/deny, never contributes to
  // required_actions/denied_actions.
  type: "allow" | "deny" | "require_action" | "informational";
  action: string;
}

export interface RequiredFact {
  name: string;
  data_type: string;
  required: boolean;
}

export interface RuleException {
  exception_id: string;
  description: string;
  condition?: ConditionNode | null;
  effect_override?: Effect | null;
  // Structured magnitude for exceptions that carry a limit rather than only
  // prose (e.g. "up to 15 days/year for a sick family member").
  limit_value?: number | null;
  limit_unit?: string | null;
}

/** Non-blocking supplementary guidance attached to a rule's decision (XACML
 * Advice), distinct from the mandatory `effect`/`require_action` Obligation.
 * See ADR-0011. */
export interface Advice {
  advice_id: string;
  text: string;
}

/** Request-side mirror of a rule's `PolicyScope` (XACML Subject/Environment
 * attributes matched against a rule's Target). Not part of the
 * EvaluationRequest wire contract — use `principalToFacts()` to flatten this
 * into reserved fact keys before submitting an evaluation. */
export interface PrincipalContext {
  persona?: string | null;
  organizational_unit?: string | null;
  jurisdiction?: string | null;
  process?: string | null;
}

/** Mirrors `PrincipalContext.to_facts()` on the backend: flattens populated
 * dimensions into the reserved fact keys the evaluator's Target-matching
 * step reads out of `EvaluationRequest.facts`. Only populated dimensions are
 * included — an absent key is treated identically to an absent fact. */
export function principalToFacts(principal: PrincipalContext): Record<string, string> {
  const facts: Record<string, string> = {};
  if (principal.persona) facts["subject.persona"] = principal.persona;
  if (principal.organizational_unit) facts["subject.organizationalUnit"] = principal.organizational_unit;
  if (principal.jurisdiction) facts["subject.jurisdiction"] = principal.jurisdiction;
  if (principal.process) facts["context.process"] = principal.process;
  return facts;
}

export interface AggregateLimitContribution {
  rule_id: string;
  amount_fact: string;
}

/** Cross-rule cap on combined numeric outcome of several rules (DMN
 * Collect+SUM). See ADR-0008. */
export interface AggregateLimit {
  aggregate_id: string;
  description: string;
  contributing_rules: AggregateLimitContribution[];
  aggregator: "SUM";
  max_value: number;
  period?: string | null;
}

/** Mutable draft aggregate-limit CRUD row (policy-set scoped, edited directly
 * by a Policy Manager — no per-candidate review workflow). Snapshotted
 * verbatim into an immutable `AggregateLimit` at publish time. */
export interface AggregateLimitResponse {
  id: string;
  policy_set_id: string;
  aggregate_key: string;
  description: string;
  contributing_rules: AggregateLimitContribution[];
  aggregator: "SUM";
  max_value: number;
  period?: string | null;
}

export interface CreateAggregateLimitRequest {
  aggregate_key: string;
  description?: string;
  contributing_rules: AggregateLimitContribution[];
  aggregator?: "SUM";
  max_value: number;
  period?: string | null;
}

export interface UpdateAggregateLimitRequest {
  description?: string;
  contributing_rules: AggregateLimitContribution[];
  aggregator?: "SUM";
  max_value: number;
  period?: string | null;
}

/** Stable blocker codes from infrastructure/aggregate_eligibility.py. The
 * evaluator drops a contribution silently in both cases, so these are the two
 * reasons a saved cap can look configured and do nothing. */
export type AggregateBlocker = "not_machine_executable" | "no_numeric_fact";

export interface NumericFact {
  name: string;
  data_type: string;
}

export interface RuleEligibility {
  rule_id: string;
  title: string;
  eligible: boolean;
  machine_executable: boolean;
  numeric_facts: NumericFact[];
  blockers: AggregateBlocker[];
}

export interface AggregateEligibilityResponse {
  total_rules: number;
  eligible_count: number;
  blocked_count: number;
  can_build_limit: boolean;
  blocker_totals: Record<string, number>;
  rules: RuleEligibility[];
}

export interface ProposedContribution {
  rule_id: string;
  amount_fact: string;
  why: string;
}

export interface ProposedAggregateLimit {
  aggregate_key: string;
  description: string;
  rationale: string;
  max_value: number;
  /** "stated" when the ceiling is in the source text, "unstated" when the model
   * inferred a shared cap exists but supplied the number itself. */
  max_value_confidence: "stated" | "unstated";
  period: string | null;
  aggregator: string;
  contributing_rules: ProposedContribution[];
}

export interface ProposeAggregateLimitsResponse {
  policy_set_key: string;
  version_number: number;
  reasoning_effort: string;
  prompt_version: string;
  eligibility: AggregateEligibilityResponse;
  proposals: ProposedAggregateLimit[];
  skipped: string[];
}

export interface PreviewContribution {
  rule_id: string;
  amount_fact: string;
  rule_status: string;
  contributed: boolean;
  amount: number | null;
  reason: string;
}

export interface PreviewAggregateLimitResponse {
  max_value: number;
  total: number;
  breached: boolean;
  contributing_count: number;
  contributions: PreviewContribution[];
  overall_status: string;
  /** "inert" is reported separately from "within_limit": a cap nothing
   * contributed to is not a pass. */
  verdict: "breached" | "within_limit" | "inert";
}

export interface EvidenceReference {
  document_version_id: string;
  source_hash: string;
  page: number | null;
  section: string | null;
  clause_id: string | null;
  start_offset: number | null;
  end_offset: number | null;
}

export interface RuleLineage {
  extraction_run_id: string | null;
  deployment_name: string | null;
  prompt_version: string | null;
  parser_version: string | null;
  schema_version: string;
}

// The policy-formulator agent's two paired outputs, preserved verbatim on
// every AI-extracted rule (see contracts.formulation.RuleFormulation on the
// backend). `canonical` is CANONICAL_JSON — the subject/predicate/object
// decomposition of the source text, before any lossy mapping into this
// platform's executable rule_type/effect vocabulary. `dmn_decisions` is
// DMN_JSON — the OMG DMN 1.5 / FEEL decision projection. Both are shown to
// reviewers so they can check the mapped rule (above) against what the AI
// actually said, rather than only ever seeing the derived form. Nested
// fields the spec leaves open-ended are typed permissively rather than
// exhaustively, matching how the backend itself treats them.
export interface CanonicalEvidence {
  subject?: string;
  predicate?: string;
  object?: string;
  condition?: string;
}

export interface CanonicalPolicyRule {
  rule_type: string;
  subject?: string;
  modality?: string;
  predicate?: string;
  object?: string;
  actor?: string;
  beneficiary?: string;
  candidate?: string;
  recipient?: string;
  assigner?: string;
  trigger?: string;
  condition?: string;
  constraint?: string;
  threshold?: string;
  temporal_constraint?: string;
  frequency?: string;
  deadline?: string;
  location?: string;
  exception?: string;
  prerequisite?: string;
  sequence?: string;
  consequence?: string;
  remedy?: string;
  calculation?: string;
  unit?: string;
  currency?: string;
  source_origin?: string;
}

export interface CanonicalPolicy {
  source_text: string;
  extraction_status: string;
  rule?: CanonicalPolicyRule;
  relationships: unknown[];
  ambiguity: string[];
  missing_components: unknown[];
}

/**
 * The source-grounded meaning the formulator recorded when it could not
 * generate executable FEEL (spec Sections 88-90).
 *
 * Deliberately NOT expressed as a `ConditionNode`. Those types are the
 * evaluator's language: a `factComparison` names a fact path the fact model is
 * expected to supply. Projecting "The ED/CEO" into `subject.role = "ED/CEO"`
 * would put a path no fact model defines into the executable contract — the
 * same invention the pointer-only design exists to prevent, just relocated.
 *
 * Shapes differ by status, so every field is optional: `subject`/`predicate`/
 * `object` for `not_directly_mappable`, `conditions`/`outcome` for
 * `enrichment_required`, `condition_source`/`outcome_source` for `ambiguous`.
 */
export interface DmnSemanticProjection {
  rule_type?: string | null;
  subject?: string | null;
  predicate?: string | null;
  object?: string | null;
  conditions?: string[];
  outcome?: string | null;
  condition_source?: string | null;
  outcome_source?: string | null;
}

export interface DmnDecision {
  source_rule_indexes: number[];
  dmn_mapping_status: string;
  semantic_projection?: DmnSemanticProjection | null;
  decision_table?: Record<string, unknown> | null;
  literal_expression?: Record<string, unknown>;
  dependencies: string[];
}

export interface RuleFormulation {
  source_index: number;
  canonical?: CanonicalPolicy;
  dmn_decisions: DmnDecision[];
}

export interface CanonicalRule {
  schema_version: string;
  policy_set_id: string;
  policy_version_id: string;
  rule_id: string;
  rule_revision: number;
  title: string;
  description: string;
  rule_type: string;
  authority: PolicyAuthority;
  scope: PolicyScope;
  condition: ConditionNode;
  /**
   * How this policy should be decided: `deterministic` when the record carries
   * a condition and the facts it needs, `ai_ready` otherwise. The field a
   * consumer routes on before reading anything else.
   */
  evaluation_mode?: "deterministic" | "ai_ready";
  /** The facts the policy's own sentence names. Derived on read. */
  fact_model?: PolicyFact[];
  /** Every attribute, with the document's words and the fact for it. Derived on read. */
  attributes?: PolicyAttributes;
  /** Why `condition` is what it is. Absent on hand-authored rules. */
  condition_provenance?: ConditionProvenance | null;
  effect: Effect;
  required_facts: RequiredFact[];
  exceptions: RuleException[];
  priority: number;
  effective_from: string;
  effective_to: string | null;
  machine_executable: boolean;
  ambiguity_status: string;
  review_status: string;
  evidence: EvidenceReference[];
  lineage: RuleLineage;
  category: string;
  tags: string[];
  group_label: string;
  related_rule_ids: string[];
  // Section 15.4 precedence dimensions: a deliberate, named override of
  // otherwise-applicable rules, and explicit same-version rule supersession.
  is_explicit_override: boolean;
  supersedes_rule_ids: string[];
  // Non-blocking guidance attached to this rule's decision (XACML Advice).
  // See ADR-0011. Empty on the vast majority of existing rules.
  advice: Advice[];
  // The formulator agent's canonical + DMN extraction record. Absent for
  // hand-authored rules or rules drafted before this agent existed.
  formulation?: RuleFormulation;
  decision_readiness?: DecisionReadiness;
  /** Derived on read from the canonical record; never stored. */
  xacml_view?: PolicyXacmlView | null;
}

/**
 * A party the rule names, quoted from the source.
 *
 * Roles follow XACML 3.0 §B.2 subject categories where the standard has them.
 * `authority` has none — XACML models a required approval as an Obligation on
 * a Permit, not as a subject of the request — so it is named for what it is
 * rather than forced into a category that means something else.
 */
export interface RuleParty {
  name: string;
  role: "access_subject" | "recipient_subject" | "authority";
  /** Canonical field or delegation phrase it was read from, for verification. */
  source: string;
}

/** One thing an evaluator must find in the customer's case, quoted. */
export interface RequiredAttribute {
  phrase: string;
  role: string;
}

/**
 * Whether an LLM can decide this rule, and what it needs to do so.
 *
 * Distinct from `machine_executable`, which asks whether the *FEEL* evaluator
 * can decide it and is false for every AI-extracted rule because no fact model
 * exists. The shipped JSON is evaluated by an LLM that binds terms from the
 * customer's case at evaluation time, so that flag measures a capability the
 * deployment does not use.
 */
export interface DecisionReadiness {
  evaluability:
    | "decidable"
    | "discretionary"
    | "underspecified"
    | "not_a_decision"
    | "malformed";
  required_attributes: RequiredAttribute[];
  parties: RuleParty[];
}

export interface DocumentVersion {
  id: string;
  version_number: number;
  content_hash: string;
  storage_path: string;
  mime_type: string;
  created_at: string;
}

export interface Clause {
  id: string;
  document_version_id: string;
  clause_ref: string;
  section: string | null;
  page: number | null;
  text: string;
  sequence: number;
  element_id?: string | null;
  element_type?: string | null;
  /** Exact key used for this clause in the configured Azure AI Search index. */
  search_document_id: string;
  search_index: string;
}

export interface SourceDocument {
  id: string;
  title: string;
  owner: string;
  source_system: string;
  created_at: string;
  versions: DocumentVersion[];
  policy_set_id?: string | null;
  policy_set_key?: string | null;
  policy_set_name?: string | null;
}

export interface CandidateRuleDraftRequest {
  rule: Record<string, unknown>;
}

export interface CandidateRule {
  id: string;
  policy_set_id: string;
  extraction_run_id: string;
  rule_type: string;
  revision: number;
  review_status: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_notes: string | null;
  published_version_id: string | null;
  created_at: string;
  /** How this rule compares to the previous extraction of the same document.
   *  Null for rules drafted before delta tracking, and for hand-authored rules
   *  that have no run to compare against. */
  delta_status: "baseline" | "new" | "changed" | "unchanged" | null;
  /** Same meaning as the previous run's rule, but the model rewrote the prose. */
  reworded: boolean;
  baseline_candidate_id: string | null;
  /** The record that replaced this one, when a later run re-read the same
   *  sentence. Absent means this is the latest reading. Derived by the server
   *  over the set returned, because being latest depends on what was asked
   *  for: opening one run's output must not make its rules look superseded by
   *  a run nobody requested. */
  superseded_by_candidate_id: string | null;
  superseded_at: string | null;
  /** Which persisted provision states this rule — a reference, nothing more.
   *
   *  Resolves against `AssembledPolicy.provision_id` from
   *  `GET /policy-sets/{key}/policies`. Deliberately not accompanied by the
   *  heading chain or the sibling rules: that composition is served once, there,
   *  and a second copy travelling on the flat list would be free to disagree
   *  with it the moment a filter separated them.
   *
   *  Null for a rule extracted before provisions existed, or one whose document
   *  defeated grouping. Null means "not linked", never "no provisions here". */
  provision_id?: string | null;
  rule: CanonicalRule;
}

export interface ReviewFacetDocument {
  id: string;
  title: string;
  rule_count: number;
}

export interface ReviewFacetRun {
  id: string;
  reference: string | null;
  status: string;
  started_at: string | null;
  document_id: string;
  document_title: string;
  document_version_id: string;
  version_label: string;
  content_hash: string | null;
  total: number;
  pending: number;
  delta: { new: number; changed: number; unchanged: number; baseline: number };
}

export interface RemovedRule {
  id: string;
  title: string;
  rule_type: string;
  review_status: string;
  superseded_at: string | null;
  superseded_by_run_id: string | null;
  superseded_by_reference: string | null;
  source_text: string;
}

export interface ReviewFacets {
  documents: ReviewFacetDocument[];
  runs: ReviewFacetRun[];
  delta_totals: {
    new: number;
    changed: number;
    unchanged: number;
    baseline: number;
    unclassified: number;
  };
  removed: RemovedRule[];
  /** Non-superseded rule counts keyed by review_status (candidate, approved, …). */
  status_totals: Record<string, number>;
}

export interface RuleFieldChange {
  field: string;
  before: unknown;
  after: unknown;
}

export interface RuleChangeExplanation {
  candidate_id: string;
  /** False when the rule has no predecessor — a normal state, not an error. */
  comparable: boolean;
  delta_status: string | null;
  /** Populated only when `comparable` is false, explaining why. */
  reason: string | null;
  baseline_candidate_id?: string;
  baseline_run_reference?: string | null;
  baseline_review_status?: string;
  /** Fields that change what the rule does when evaluated. */
  semantic_changes: RuleFieldChange[];
  /** Title/description rewording — reported, but does not affect behaviour. */
  wording_changes: RuleFieldChange[];
  /** Optional plain-English reading of the diff. Null if the model was unavailable. */
  narrative: string | null;
}

/**
 * A plain-language reading of one policy's extracted record.
 *
 * `rules` is the deterministic half and is always populated: it is what the
 * reviewer checks. `stated_text` on each is the document's own sentence and was
 * never sent to the model — see the server module for why that omission is the
 * design rather than an economy.
 *
 * Three outcomes are distinguishable and must stay so:
 *
 * - `explanation` set — this is the reading;
 * - `unavailable_code` set — it was asked for and none came back;
 * - both null — nobody asked, because the model is not configured here.
 */
export interface PolicyExplanation {
  provision_id: string;
  heading_path: string[];
  rule_count: number;
  rules: {
    rule_id: string;
    title: string;
    /** The parts the extraction identified. What the model was shown. */
    states: Record<string, string>;
    effect: string;
    /** The document's own words. Never sent to the model. */
    stated_text: string;
  }[];
  /** False when a budget stopped some rules reaching the model. */
  covers_every_rule: boolean;
  explanation: string | null;
  unavailable_code: string | null;
  generated_at: string | null;
  model_deployment: string | null;
  prompt_version: string;
  source_digest: string;
  /** True when this came from an earlier generation of the same record. */
  generated_earlier?: boolean;
}

export interface CandidateRuleFilters {
  status?: string;
  document_id?: string;
  document_version_id?: string;
  extraction_run_id?: string;
  delta_status?: string;
  include_superseded?: boolean;
}

/** Scoping accepted by `GET /policy-sets/{key}/policies`. Deliberately a subset
 *  of CandidateRuleFilters: the assembling view is a rearrangement of one
 *  population, so it takes the filters that choose a population and not those
 *  that choose rows within it. */
export interface PolicyAssemblyFilters {
  document_id?: string;
  document_version_id?: string;
  extraction_run_id?: string;
}

/** One rule as it appears inside its policy.
 *
 *  Carries only what the assembling view needs to arrange and label; the rest
 *  of the rule comes from `listCandidateRules`, which is the same population
 *  under a different arrangement. `rule_id` is the join. */
export interface AssembledPolicyRule {
  rule_id: string;
  title: string;
  /** This rule's own route. A policy can hold rules taking different routes,
   *  so this is per rule and never summarised away. */
  evaluation_mode: string;
}

/** One passage of the source, carrying every rule stated in it.
 *
 *  The inner boundary of a policy: it is what tells a reviewer which sentence
 *  each rule came from, which a fourteen-rule card needs and a flat list of
 *  fourteen would have thrown away. */
export interface AssembledPassage {
  /** The anchoring element, e.g. `p9-E000074`. */
  key: string;
  /** Full attribution, verbatim. Differs from `key` when rules cite several
   *  elements, in which case the passage is anchored to the first. */
  source_elements: string;
  page: number | null;
  rule_count: number;
  rules: AssembledPolicyRule[];
}

/** A short name for the subject a policy is about, generated by this system.
 *
 *  Not the document's. Every other string on a policy is characters the source
 *  wrote; this one is ours, and it is carried in its own object under its own
 *  key so that no consumer can pick it up while reading the document's words.
 *
 *  `generated` is stated by the server rather than inferred here, because the
 *  one property this must never lose is that these words are not evidence, and
 *  a property each caller derives is a property some caller derives wrongly.
 *
 *  Exactly one of `text` and `unavailable_code` is set. A missing object is a
 *  third thing again — nobody has asked for a label — and the card says so
 *  differently, because "not asked for" and "asked for, nothing usable came
 *  back" send a reviewer to different actions. */
export interface PolicyTopicLabel {
  generated: true;
  /** The generated words, in the language of the passage. Null when the attempt
   *  produced nothing usable. Never empty: an empty reply is a failure and is
   *  recorded as one, so a card never has to render a blank as a name. */
  text: string | null;
  /** Why there is no label. A code, not a sentence — the reader-facing wording
   *  lives beside the reader, where it can be worded for them. */
  unavailable_code: string | null;
  model_deployment: string | null;
  prompt_version: string;
  generated_at: string | null;
}

/** What one naming run did.
 *
 *  Counts rather than a success flag. A run that names sixty policies and
 *  cannot name the other ten has done sixty policies' worth of good, and a
 *  caller told only "failed" would have thrown that away. `unavailable` is a
 *  count of policies that were asked about and yielded nothing usable — those
 *  carry a recorded outcome and will say so on their card, which is different
 *  from the ones nobody has asked about yet. */
export interface TopicLabelGenerationResult {
  provisions: number;
  attempted: number;
  named: number;
  unavailable: number;
  skipped_with_no_rules: number;
  prompt_version: string;
}

/** A short generated handle for what one rule is for.
 *
 *  IT IS NOT PART OF THE RULE, AND THIS SHAPE IS HOW THAT IS KEPT TRUE
 *
 *  A rule's record is evidence about a document. This is our commentary on that
 *  record, and if it ever rode along inside the record an export or a published
 *  version would carry words the document never stated. So it is fetched on its
 *  own, keyed by the rule it describes, and it is never a field of a rule. The
 *  separation is structural: there is no shape here that a consumer could spread
 *  into a rule without noticing.
 *
 *  Exactly one of `text` and `unavailable_code` is set. No entry at all is a
 *  third thing — nobody has asked yet — and the caller keeps all three apart. */
export interface RuleName {
  generated: true;
  /** The generated words, in the language the heading is written in. Null when
   *  the attempt produced nothing usable. Never empty. */
  text: string | null;
  /** Why there is no name. A code, not a sentence. */
  unavailable_code: string | null;
  model_deployment: string | null;
  prompt_version: string;
  generated_at: string | null;
}

/** Names for the rules that were asked about, keyed by candidate rule id.
 *
 *  A rule with no stored name is simply absent from the map, which is how "not
 *  asked yet" stays distinguishable from "asked, and nothing usable came back". */
export interface RuleNameLookupResult {
  names: Record<string, RuleName>;
}

/** What one rule-naming run did.
 *
 *  Counts and not a success flag, for the reason the label run gives: partial
 *  work is still work. `duplicates_within_a_policy` is reported because names
 *  that repeat across sibling rules would defeat the only thing this is for —
 *  telling one rule from another at a glance. */
export interface RuleNameGenerationResult {
  policies: number;
  attempted: number;
  named: number;
  unavailable: number;
  duplicates_within_a_policy: number;
  skipped_with_no_rules: number;
  prompt_version: string;
}

/** One section of the source, carrying every passage stated under it.
 *
 *  A policy holding one rule is the ordinary case and is built exactly like a
 *  policy holding seventy-two — there is no separate shape for it. */
export interface AssembledPolicy {
  /** Grouping key. The provision the pipeline recorded when the document was
   *  read, or — for a rule extracted before provisions existed — the heading
   *  its evidence records. Opaque either way; `heading` is what to show. */
  key: string;
  /** What to call this policy: its own innermost heading, verbatim. The card
   *  *is* the section, so it is named by the section rather than by a sentence
   *  lifted out of one of the passages beneath it. */
  heading: string;
  /** The governing headings, outermost first, verbatim. For a policy grouped by
   *  the read-time fallback it holds the one heading that grouping used, so it
   *  is empty only when the document recorded no heading at all — which is how
   *  the client tells "unnamed" from "named by its innermost heading" without
   *  comparing strings. Sent as a list so the client can render a trail without
   *  the server having had to join it into a string the document never wrote. */
  heading_path: string[];
  /** A generated name for the subject, or null when none has been generated.
   *
   *  Deliberately not merged into `heading` or `heading_path`: those are the
   *  document's characters and this one is not, and keeping it in its own
   *  object is what lets the card render them so a reader is never in doubt
   *  which words the document wrote. */
  topic_label?: PolicyTopicLabel | null;
  /** Whether this policy's boundary is the one the pipeline recorded, or one
   *  inferred at read time from the headings its rules cite. Shown rather than
   *  hidden: a reviewer approving a policy is entitled to know which. */
  persisted: boolean;
  /** Which persisted provision this policy is. Present exactly when `persisted`
   *  is true, and the target of `CandidateRule.provision_id` — so a client
   *  holding both lists joins rule to policy by identity, never by matching
   *  headings. Matching headings is the derivation persisting the grouping
   *  exists to make unnecessary. */
  provision_id?: string | null;
  /** Scopes the grouping: two documents may share a heading without thereby
   *  stating one policy. */
  document_version_id: string | null;
  /** The passages under this heading, in document order. */
  source_elements: string;
  page: number | null;
  rule_count: number;
  passage_count: number;
  /** Summary of the routes its rules take: every rule computable, every rule
   *  read, or both present. A summary for the header only — it never replaces
   *  the per-rule mode above. */
  route: string;
  passages: AssembledPassage[];
  /** Every rule under this heading, flat, in document order — the same rules
   *  the passages hold, once each. */
  rules: AssembledPolicyRule[];
}

export interface CandidateRuleReviewRequest {
  decision: "approve" | "reject";
  reviewer: string;
  notes?: string | null;
}

export interface CandidateRuleEditRequest {
  rule: Record<string, unknown>;
  editor: string;
}

export interface RequestChangesRequest {
  manager: string;
  actor_role: string;
  reason: string;
  notes?: string | null;
}

export interface OverrideReviewRequest {
  manager: string;
  actor_role: string;
  decision: "approve" | "reject";
  reason: string;
  notes?: string | null;
}

export interface PublishCandidatesRequest {
  approved_by: string;
  effective_from: string;
  effective_to?: string | null;
  version_number?: number | null;
  is_active?: boolean;
}

export type EvaluationStatus =
  | "SATISFIED"
  | "NOT_SATISFIED"
  | "NOT_APPLICABLE"
  | "INDETERMINATE"
  | "ERROR";

export interface RuleEvaluationResult {
  rule_id: string;
  rule_revision: number;
  status: EvaluationStatus;
  effect_action: string | null;
  // The rule's effect type ("allow"/"deny"/"require_action"/"informational"),
  // so a satisfied DENY can be told apart from a satisfied ALLOW without
  // re-fetching the rule.
  effect_type?: "allow" | "deny" | "require_action" | "informational" | null;
  missing_facts: string[];
  triggered_exceptions: string[];
  // Populated when status is NOT_APPLICABLE specifically because a
  // non-wildcard scope dimension didn't match the principal's facts (XACML
  // Target mismatch) — e.g. "scope_mismatch:persona".
  not_applicable_reason?: string | null;
  // rule_id of the higher-precedence rule that won when this SATISFIED
  // rule's action conflicted with another SATISFIED rule on the opposite
  // allow/deny axis. null means this rule's outcome (if satisfied) stands.
  overridden_by?: string | null;
  // This rule's own advice text(s), populated only when SATISFIED. See
  // ADR-0011 / EvaluationResponse.advice_notes for the aggregated version.
  advice?: string[];
}

/** One aggregate limit whose contributing rules' summed amount exceeded
 * max_value for this evaluation. See AggregateLimit / ADR-0008. */
export interface AggregateBreach {
  aggregate_id: string;
  description: string;
  total: number;
  max_value: number;
  contributing_rule_ids: string[];
}

export interface EvaluationResponse {
  evaluation_id: string;
  policy_set_id: string;
  policy_version_id: string;
  overall_status: EvaluationStatus;
  outcome: string | null;
  applicable_rules: string[];
  satisfied_rules: string[];
  failed_rules: string[];
  missing_facts: string[];
  // SATISFIED rules whose effect is allow/require_action only.
  required_actions: string[];
  // SATISFIED rules whose effect is deny, kept on its own axis rather than
  // mixed into required_actions.
  denied_actions?: string[];
  triggered_exceptions: string[];
  evidence_references: string[];
  rule_results: RuleEvaluationResult[];
  aggregate_breaches?: AggregateBreach[];
  // Aggregated non-blocking guidance (XACML Advice) from the winning side's
  // SATISFIED rules, deduped and sorted. See ADR-0011.
  advice_notes?: string[];
  result_hash: string;
  evaluation_timestamp: string;
}

export interface EvaluationRequest {
  policy_set_id: string;
  policy_version_id?: string | null;
  use_active_version?: boolean;
  evaluation_timestamp?: string | null;
  facts: Record<string, unknown>;
  correlation_id?: string | null;
  calling_system_identity?: string | null;
}

// ---------- Decision Log (ADR-0009: OPA Decision-Log parity) ----------
//
// Every POST /api/evaluations call is persisted append-only as an `Evaluation`
// row. This is the read-only browse path over that history — same posture as
// `auditApi` above (governance actions) but for runtime evaluation calls
// (the deterministic engine's actual decisions for calling systems).

/** One row of the decision log. Omits the full facts/response — see
 * `EvaluationLogDetail` for the single-record view that includes them. */
export interface EvaluationLogSummary {
  id: string;
  policy_set_id: string;
  policy_version_id: string;
  correlation_id: string | null;
  calling_system_identity: string | null;
  overall_status: EvaluationStatus;
  result_hash: string;
  evaluation_timestamp: string;
}

export interface EvaluationLogDetail extends EvaluationLogSummary {
  request_facts: Record<string, unknown>;
  response: EvaluationResponse;
}

export interface EvaluationLogPage {
  evaluations: EvaluationLogSummary[];
  count: number;
  truncated: boolean;
}

export const evaluationLogApi = {
  list: (
    policySetKey: string,
    params: {
      overallStatus?: string;
      correlationId?: string;
      callingSystemIdentity?: string;
      limit?: number;
    } = {}
  ) => {
    const qs = new URLSearchParams();
    if (params.overallStatus) qs.set("overall_status", params.overallStatus);
    if (params.correlationId) qs.set("correlation_id", params.correlationId);
    if (params.callingSystemIdentity) qs.set("calling_system_identity", params.callingSystemIdentity);
    if (params.limit) qs.set("limit", String(params.limit));
    const suffix = qs.toString();
    return request<EvaluationLogPage>(
      `/api/evaluations/policy-sets/${encodeURIComponent(policySetKey)}${suffix ? `?${suffix}` : ""}`
    );
  },

  getDetail: (evaluationId: string) =>
    request<EvaluationLogDetail>(`/api/evaluations/${encodeURIComponent(evaluationId)}`),
};

// ---------- AI features ----------

export interface AiStatus {
  ai_enabled: boolean;
  search_enabled: boolean;
  chat_deployment: string | null;
  fast_deployment: string | null;
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface AskSource {
  heading: string | null;
  section: string | null;
  clause_id: string;
  document_id: string;
}

export interface AskFact {
  text: string;
  source_label: string | null;
}

export interface AskGroup {
  heading: string;
  facts: AskFact[];
}

export interface AskResponse {
  groups: AskGroup[];
  reflection: string;
  sources: AskSource[];
}

export interface ExtractResult {
  extraction_run_id: string;
  created: string[];
  skipped: { item: unknown; reason: string }[];
}

/** Live counters for an in-flight extraction, polled while a run is going.
 *
 * `active: false` means nothing is being tracked for this document version —
 * either it was never extracted or the record has been pruned. That is a normal
 * state, not an error, so the UI falls back to a plain spinner. */
export interface ExtractionProgress {
  active: boolean;
  status?: "running" | "completed" | "failed";
  /** One short sentence describing what is happening right now. Replaced on
   * every poll — a status line, not an append-only log. */
  stage?: string;
  total_clauses?: number;
  processed_clauses?: number;
  total_batches?: number;
  processed_batches?: number;
  total_pages?: number;
  processed_pages?: number;
  passages_found?: number;
  rules_drafted?: number;
  rules_committed?: number;
  skipped?: number;
  /** Rules that gained at least one confirmed relationship. */
  linked?: number;
  superseded?: number;
  /**
   * How this run's rules differ from the previous extraction of the same
   * document. Populated once, at the end.
   *
   * These are the numbers a reviewer acts on: a run of 190 rules where 187 are
   * unchanged needs three decisions, not 190, and reporting only the total
   * hides that. `delta_removed` has no row of its own anywhere, so without it
   * a rule the previous run found and this one did not is invisible.
   */
  delta_new?: number;
  delta_changed?: number;
  delta_unchanged?: number;
  delta_removed?: number;
  run_reference?: string;
  error?: string | null;
  elapsed_seconds?: number;
}

/** What one extraction run passed over, and whether the document was covered.
 *
 * Two unrelated events land in the same skip list and only `kind` tells them
 * apart. `batches_unread` is material the run never read — the document is not
 * covered and the run should be repeated. `read_not_extracted` is sentences it
 * read and judged to carry no rule; coverage is whole and a judgement was made
 * that may be worth checking. Reported separately because a single count told a
 * clean run it had a hole in it, which is the fastest way to teach someone to
 * ignore the warning.
 */
export interface RunCoverage {
  complete: boolean;
  batches_unread: number;
  passages_discarded: number;
  read_not_extracted: number;
  /** The entries themselves, so a reviewer can read what was dropped. */
  skipped: { item: string; reason: string; kind: string }[];
}

/** One recorded extraction attempt against a document version. */
export interface ExtractionRunSummary {
  id: string;
  /** Short human-quotable form, e.g. `RUN-3F9A2B1C`. */
  reference: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  prompt_version: string | null;
  deployment_name: string | null;
  rules_total: number;
  rules_reviewed: number;
  /** True for the run whose rules are the ones currently in the review queue.
   */
  is_current: boolean;
  /** Null for runs recorded before skips were kept — which is weaker than a
   * run that skipped nothing, so it is shown as unknown rather than as zero. */
  coverage: RunCoverage | null;
}

export interface RewriteSuggestion {
  current: CanonicalRule;
  suggested: CanonicalRule;
  explanation: string;
}

export interface ScenarioEvaluation {
  applies: "yes" | "no" | "uncertain";
  reasoning: string;
  predicted_outcome: string;
  missing_facts: string[];
  reasoning_effort: string;
}

/** Result of the REAL, deterministic-engine-backed scenario tester (distinct
 * from ScenarioEvaluation above, which is advisory-only). AI only produced
 * `inferred_facts`/`assumptions` and `explanation`; `rule_result` and
 * `overall_evaluation_status` come straight from evaluator.engine.evaluate_policy —
 * see ai_scenario_engine.py's module docstring. */
export interface RuleScenarioTestResult {
  rule_id: string;
  rule_title: string;
  scenario: string;
  inferred_facts: Record<string, unknown>;
  assumptions: string[];
  rule_result: RuleEvaluationResult | null;
  not_in_effect: boolean;
  overall_evaluation_status: EvaluationStatus;
  missing_facts: string[];
  explanation: string;
  reasoning_effort: string;
  evaluation_timestamp: string;
  result_hash: string;
  machine_executable: boolean;
  testability_reason: "rule_not_machine_executable" | null;
  dmn_mapping_statuses: string[];
  formulation_requirements: string[];
}

export interface QualityFinding {
  severity: "high" | "medium" | "low";
  category: string;
  summary?: string;
  finding: string;
  why_it_matters?: string;
  acceptable_when?: string;
  unacceptable_when?: string;
  review_questions?: string[];
  affected_rule_ids: string[];
  recommendation: string;
  analysis_status?: "confirmed" | "requires_human_confirmation";
  source: "deterministic" | "ai_review";
}

/** A completed evaluation: something looked at the rules and reached a verdict. */
export interface QualityReport {
  policy_set_key: string;
  scope?: "published" | "candidates";
  /** Always true here. The discriminant against {@link QualityNotEvaluated}. */
  evaluated?: true;
  version_number: number | null;
  rule_count: number;
  candidate_statuses_included?: string[];
  findings: QualityFinding[];
  finding_count?: number;
  quality_run_id?: string | null;
  run_at?: string | null;
  ai_review_used?: boolean;
  triggered_by?: string | null;
  methodology_version?: string;
}

/** Nobody has evaluated this scope yet.
 *
 * `findings` is null, not `[]`. An empty list would render identically to a
 * completed evaluation that found nothing, and those are opposite facts: one
 * says the rules were examined and are clean, the other says nobody has looked.
 * Callers must branch on `evaluated` before reading a count.
 */
export interface QualityNotEvaluated {
  policy_set_key: string;
  scope: "published" | "candidates";
  evaluated: false;
  version_number: null;
  rule_count: null;
  findings: null;
  finding_count: null;
  quality_run_id: null;
  run_at: null;
  ai_review_used: null;
  triggered_by: null;
  methodology_version: null;
  /** Plain-language explanation, safe to show a reader as-is. */
  detail: string;
}

/** What a read of the quality endpoints returns: a past evaluation, or the
 *  recorded absence of one. */
export type QualityReadout = QualityReport | QualityNotEvaluated;

/** Narrow a readout to a real evaluation. */
export const hasBeenEvaluated = (readout: QualityReadout): readout is QualityReport =>
  readout.evaluated !== false;

/** One past evaluation, summarised. Findings are omitted so the history list
 *  stays cheap to render; fetch them per-run with `getQualityRun`. */
export interface QualityRunSummary {
  id: string;
  scope: "published" | "candidates";
  version_number: number | null;
  rule_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  finding_count: number;
  ai_review_used: boolean;
  methodology_version: string;
  triggered_by: string | null;
  run_at: string;
}

/**
 * A list the server may have cut short, saying so.
 *
 * Endpoints that apply a `limit` return this rather than a bare array, because
 * an array gives the caller nothing to distinguish "this is all of them" from
 * "this is the newest handful of them" — and a UI that cannot tell those apart
 * will always render the second as if it were the first.
 *
 * `count` is how many rows arrived. When `truncated` is true, `count` is also
 * the cap the server applied, so "the most recent {count}" is accurate without
 * the client needing to know the limit it asked for.
 */
export interface CappedRunList<T> {
  runs: T[];
  count: number;
  truncated: boolean;
}

export interface QualityRunDetail extends QualityReport {
  id: string;
  ai_review_used: boolean;
  triggered_by: string | null;
  run_at: string;
}

export interface CompareResult {
  policy_set_key: string;
  version_a: number;
  version_b: number;
  added: CanonicalRule[];
  removed: CanonicalRule[];
  changed: { rule_id: string; title: string; changed_fields: Record<string, { before: unknown; after: unknown }> }[];
  unchanged_count: number;
  narrative: string | null;
}

export interface PolicySetSummaryStats {
  total_rules: number;
  by_rule_type: Record<string, number>;
  by_effect: Record<string, number>;
  by_ambiguity_status: Record<string, number>;
  by_category: Record<string, number>;
  scope_coverage: {
    jurisdictions: string[];
    organizational_units: string[];
    personas: string[];
    processes: string[];
  };
  explicit_overrides_count: number;
  explicit_overrides: { rule_id: string; title: string }[];
  advice_rules_count: number;
  aggregate_limits_count: number;
  rules_with_sunset_date: number;
}

export interface PolicySetSummary {
  policy_set_key: string;
  policy_set_name: string;
  version_number: number;
  is_active: boolean;
  effective_from: string | null;
  effective_to: string | null;
  stats: PolicySetSummaryStats;
  narrative: string | null;
}

// ---------- Notes ----------

export type NoteEntityType = "policy_set" | "policy_version" | "candidate_rule" | "rule";

export interface Note {
  id: string;
  entity_type: NoteEntityType;
  entity_id: string;
  author: string;
  author_role: string;
  body: string;
  created_at: string;
}

export interface CreateNoteRequest {
  entity_type: NoteEntityType;
  entity_id: string;
  author: string;
  author_role: string;
  body: string;
}

// ---------- Policy Tests (Section 21.6 / 11.6 / 9.11 step 6) ----------
//
// Named, saved test cases for a policy set — distinct from the ad hoc
// `/api/evaluations` simulation (see `EvaluationRequest`/`evaluate` above).
// AI may propose a PolicyTest via `propose`, but every test is actually
// executed by the real deterministic evaluator server-side; the frontend
// never computes pass/fail itself.

export type PolicyTestKind =
  | "positive"
  | "negative"
  | "boundary"
  | "missing_fact"
  | "scope"
  | "effective_date"
  | "exception"
  | "precedence";

export type PolicyTestRunStatus = "pass" | "fail" | "error";

export interface PolicyTest {
  id: string;
  policy_set_id: string;
  name: string;
  description: string;
  test_kind: PolicyTestKind;
  input_facts: Record<string, unknown>;
  evaluation_timestamp: string | null;
  scenario_text: string;
  generation_batch_id: string | null;
  expectation_hash: string | null;
  expectation_revealed: boolean;
  expected_overall_status: EvaluationStatus | null;
  expected_rule_id: string | null;
  expected_rule_status: EvaluationStatus | null;
  expected_missing_facts: string[] | null;
  proposed_by: "ai" | "human";
  review_status: "active" | "pending_review" | "rejected";
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_notes: string | null;
  is_active: boolean;
  created_at: string;
}

export interface PolicyTestRun {
  id: string;
  policy_test_id: string;
  policy_version_id: string;
  status: PolicyTestRunStatus;
  explanation: string;
  actual_response_json: EvaluationResponse | null;
  expected_assertions_json: {
    scenario_text: string;
    input_facts: Record<string, unknown>;
    evaluation_timestamp: string | null;
    expected_overall_status: EvaluationStatus;
    expected_rule_id: string | null;
    expected_rule_status: EvaluationStatus | null;
    expected_missing_facts: string[] | null;
  } | null;
  expectation_hash: string | null;
  run_trigger: "manual" | "on_publish";
  triggered_by: string;
  run_at: string;
}

export interface PolicyTestListItem {
  test: PolicyTest;
  latest_run: PolicyTestRun | null;
  runs: PolicyTestRun[];
}

export interface CreatePolicyTestRequest {
  name: string;
  description?: string;
  test_kind: PolicyTestKind;
  input_facts: Record<string, unknown>;
  evaluation_timestamp?: string | null;
  expected_overall_status: EvaluationStatus;
  expected_rule_id?: string | null;
  expected_rule_status?: EvaluationStatus | null;
  expected_missing_facts?: string[] | null;
}

export interface ProposePolicyTestsResponse {
  policy_set_key: string;
  version_number: number;
  reasoning_effort: string;
  proposed_tests: PolicyTest[];
  skipped: string[];
}

export type PolicyTestGroundingMode = "json_only" | "json_search";

export interface PolicyTestBatch {
  id: string;
  policy_set_id: string;
  policy_version_id: string;
  version_number: number;
  grounding_mode: PolicyTestGroundingMode;
  selected_rule_ids: string[];
  grounding_context: {
    mode: PolicyTestGroundingMode;
    search_index: string | null;
    query: string | null;
    hits: Array<{
      id: string | null;
      document_id: string | null;
      clause_id: string | null;
      clause_number: string | null;
      section_heading: string | null;
      heading: string | null;
      score: number | null;
      body: string | null;
    }>;
  };
  scenario_count: number;
  tests_per_policy: number;
  reasoning_effort: string;
  guidance: string;
  created_by: string;
  status: "generated" | "executed";
  executed_at: string | null;
  created_at: string;
  tests: PolicyTestListItem[];
}

export const policyTestApi = {
  list: (policySetKey: string, opts?: { isActive?: boolean; testKind?: string }) => {
    const params = new URLSearchParams();
    if (opts?.isActive !== undefined) params.set("is_active", String(opts.isActive));
    if (opts?.testKind) params.set("test_kind", opts.testKind);
    const qs = params.toString();
    return request<PolicyTestListItem[]>(
      `/api/policy-tests/policy-sets/${encodeURIComponent(policySetKey)}${qs ? `?${qs}` : ""}`
    );
  },

  listFailing: (policySetKey: string) =>
    request<PolicyTestListItem[]>(`/api/policy-tests/policy-sets/${encodeURIComponent(policySetKey)}/failing`),

  create: (policySetKey: string, body: CreatePolicyTestRequest) =>
    request<PolicyTest>(`/api/policy-tests/policy-sets/${encodeURIComponent(policySetKey)}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  propose: (
    policySetKey: string,
    reasoningEffort: "low" | "medium" | "high" = "medium",
    guidance = ""
  ) =>
    request<ProposePolicyTestsResponse>(`/api/policy-tests/policy-sets/${encodeURIComponent(policySetKey)}/propose`, {
      method: "POST",
      body: JSON.stringify({ reasoning_effort: reasoningEffort, guidance }),
    }),

  review: (testId: string, decision: "accept" | "reject", reviewer: string, notes?: string) =>
    request<PolicyTest>(`/api/policy-tests/${encodeURIComponent(testId)}/review`, {
      method: "POST",
      body: JSON.stringify({ decision, reviewer, notes: notes ?? null }),
    }),

  run: (testId: string, triggeredBy: string, policyVersionId?: string) =>
    request<PolicyTestRun>(`/api/policy-tests/${encodeURIComponent(testId)}/run`, {
      method: "POST",
      body: JSON.stringify({ triggered_by: triggeredBy, policy_version_id: policyVersionId ?? null }),
    }),

  listRuns: (testId: string) => request<PolicyTestRun[]>(`/api/policy-tests/${encodeURIComponent(testId)}/runs`),

  generateBatch: (
    policySetKey: string,
    body: {
      rule_ids: string[];
      tests_per_policy: number;
      policy_version_id?: string;
      scenario_text?: string;
      grounding_mode: PolicyTestGroundingMode;
      reasoning_effort: "low" | "medium" | "high";
      guidance: string;
      created_by: string;
    }
  ) =>
    request<PolicyTestBatch>(
      `/api/policy-tests/policy-sets/${encodeURIComponent(policySetKey)}/validation-batches`,
      { method: "POST", body: JSON.stringify(body) }
    ),

  listBatches: (policySetKey: string) =>
    request<PolicyTestBatch[]>(
      `/api/policy-tests/policy-sets/${encodeURIComponent(policySetKey)}/validation-batches`
    ),

  runBatch: (batchId: string, triggeredBy: string, policyVersionId?: string) =>
    request<PolicyTestBatch>(`/api/policy-tests/validation-batches/${encodeURIComponent(batchId)}/run`, {
      method: "POST",
      body: JSON.stringify({ triggered_by: triggeredBy, policy_version_id: policyVersionId ?? null }),
    }),
};

// ---------- Policy Exceptions (ADR-0009) ----------
//
// Ad hoc, human-requested, time-bounded waivers of a rule (or an entire
// policy set) for one particular case — decided by a human reviewer, never
// auto-evaluated. Distinct from the `exceptions` embedded in `CanonicalRule`
// (a standing, automatically-evaluated carve-out baked into a rule's own
// definition, e.g. "employees under 2 years get a reduced limit").

export type PolicyExceptionDecision = "pending" | "granted" | "denied";

export interface PolicyException {
  id: string;
  policy_set_id: string;
  rule_id: string | null;
  requester: string;
  justification: string;
  decision: PolicyExceptionDecision;
  expiry_date: string | null;
  decided_by: string | null;
  decided_at: string | null;
  decision_notes: string | null;
  is_expired: boolean;
  created_at: string;
}

export interface CreatePolicyExceptionRequest {
  rule_id?: string | null;
  requester: string;
  justification: string;
  expiry_date?: string | null;
}

export interface DecidePolicyExceptionRequest {
  decision: "granted" | "denied";
  decided_by: string;
  decision_notes?: string | null;
}

export const policyExceptionApi = {
  list: (policySetKey: string, opts?: { decision?: string; ruleId?: string }) => {
    const params = new URLSearchParams();
    if (opts?.decision) params.set("decision", opts.decision);
    if (opts?.ruleId) params.set("rule_id", opts.ruleId);
    const qs = params.toString();
    return request<PolicyException[]>(
      `/api/policy-exceptions/policy-sets/${encodeURIComponent(policySetKey)}${qs ? `?${qs}` : ""}`
    );
  },

  create: (policySetKey: string, body: CreatePolicyExceptionRequest) =>
    request<PolicyException>(`/api/policy-exceptions/policy-sets/${encodeURIComponent(policySetKey)}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  decide: (exceptionId: string, body: DecidePolicyExceptionRequest) =>
    request<PolicyException>(`/api/policy-exceptions/${encodeURIComponent(exceptionId)}/decide`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

// ---------- Policy Attestations (ADR-0012) ----------
//
// Employee attestation/acknowledgment tracking (ISO 37301 §7.3): a Policy
// Manager launches a campaign assigning one published policy version's
// acknowledgment obligation to a batch of employees sharing one due date.
// Employees are explicitly not one of this app's 3 governance actors (see
// ActorContext) — there's no login for them, so they find their own pending
// items via a name/identifier search instead.

export type PolicyAttestationStatus = "pending" | "acknowledged" | "overdue";

export interface AttestationAssignee {
  name: string;
  identifier?: string | null;
}

export interface PolicyAttestation {
  id: string;
  policy_set_id: string;
  policy_version_id: string;
  version_number: number;
  employee_name: string;
  employee_identifier: string | null;
  due_date: string;
  assigned_by: string;
  acknowledged_at: string | null;
  acknowledgment_notes: string | null;
  status: PolicyAttestationStatus;
  created_at: string;
}

export interface CreatePolicyAttestationCampaignRequest {
  policy_version_id: string;
  employees: AttestationAssignee[];
  due_date: string;
  assigned_by: string;
  actor_role: string;
}

export interface AcknowledgePolicyAttestationRequest {
  acknowledgment_notes?: string | null;
}

export const policyAttestationApi = {
  list: (policySetKey: string, status?: PolicyAttestationStatus) => {
    const qs = status ? `?status=${status}` : "";
    return request<PolicyAttestation[]>(
      `/api/policy-attestations/policy-sets/${encodeURIComponent(policySetKey)}${qs}`
    );
  },

  createCampaign: (policySetKey: string, body: CreatePolicyAttestationCampaignRequest) =>
    request<PolicyAttestation[]>(
      `/api/policy-attestations/policy-sets/${encodeURIComponent(policySetKey)}/campaigns`,
      {
        method: "POST",
        body: JSON.stringify(body),
      }
    ),

  /** No-login, self-service lookup: matches `q` against name or identifier across every policy set. */
  search: (q: string) => request<PolicyAttestation[]>(`/api/policy-attestations/search?q=${encodeURIComponent(q)}`),

  acknowledge: (attestationId: string, body: AcknowledgePolicyAttestationRequest) =>
    request<PolicyAttestation>(`/api/policy-attestations/${encodeURIComponent(attestationId)}/acknowledge`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

// ---------- Export ----------

export type ExportFormat = "json" | "jsonl" | "csv";

/** Triggers a browser download for an already-fetched blob.
 *
 * The anchor must be connected to the document before click, and the object URL
 * must survive beyond the current task. Chromium-based embedded webviews can
 * otherwise cancel the navigation before the blob stream is opened.
 */
export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Parses `attachment; filename="..."` out of a Content-Disposition header. */
function filenameFromContentDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const match = /filename="?([^";]+)"?/i.exec(header);
  return match ? match[1] : fallback;
}

async function downloadFile(path: string, fallbackFilename: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`);
  } catch (cause) {
    throw unreachable(cause);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      // ignore
    }
    throw new PolicyPlatformApiError(res.status, detail);
  }
  const blob = await res.blob();
  const filename = filenameFromContentDisposition(res.headers.get("Content-Disposition"), fallbackFilename);
  downloadBlob(blob, filename);
}

/**
 * Correlation: relationships *between* rules.
 *
 * The classification vocabulary is closed (Section 51 of the contradiction
 * detector specification) so findings can be grouped and triaged; an open
 * vocabulary would let each finding coin its own label.
 *
 * Note the deliberate absence of a confidence score. `analysisStatus` says
 * whether the finding is real; `severity` says how bad it is if it is. A single
 * number would collapse "certainly a minor overlap" and "possibly a critical
 * contradiction" into the same value, and those need opposite handling.
 */
export type CorrelationSeverity = "critical" | "high" | "medium" | "low" | "informational";
export type CorrelationAnalysisStatus = "confirmed" | "potential" | "ambiguous" | "resolved";
export type CorrelationDisposition = "open" | "accepted" | "dismissed" | "resolved";

export interface CorrelationEvidence {
  policy_index: number;
  rule_id: string;
  source_text: string;
  relevant_semantics?: Record<string, unknown>;
}

export interface CorrelationFinding {
  id: string;
  run_id: string;
  classification: string;
  analysis_status: CorrelationAnalysisStatus;
  severity: CorrelationSeverity;
  rule_ids: string[];
  reason: string;
  evidence: CorrelationEvidence[];
  overlap?: { type?: string | null; fact?: string | null; scope?: string | null } | null;
  requirements: string[];
  disposition: CorrelationDisposition;
  disposition_by: string | null;
  disposition_at: string | null;
  disposition_notes: string | null;
  created_at: string | null;
}

export interface CorrelationFindingsResponse {
  run_id: string | null;
  findings: CorrelationFinding[];
  by_classification: Record<string, number>;
  by_severity: Record<string, number>;
}

export interface CorrelationRunSummary {
  id: string;
  status: string;
  rules_analyzed: number;
  groups_analyzed: number;
  /** Total groups the corpus yields, of which `groups_analyzed` is the portion
   * the budget allowed. Lets a truncated run say how much it left behind rather
   * than only that it left something. Null for runs recorded before this was
   * tracked. */
  groups_available: number | null;
  /** Rules this run never examined, for any reason. Surfaced because a coverage
   * gap the reviewer cannot see is one they will assume does not exist. See
   * `rules_budget_skipped` for the part of it that means the run was truncated
   * rather than the rules genuinely standing alone. */
  rules_uncompared: number;
  /** The subset of `rules_uncompared` that could have been compared but fell
   * outside the group budget. Non-zero means re-running with a larger budget
   * would examine more. Null for runs recorded before this was tracked — the
   * honest answer there is "unknown", not "none". */
  rules_budget_skipped: number | null;
  prompt_version: string | null;
  error_message: string | null;
  created_at: string | null;
  completed_at: string | null;
}

export interface CorrelationRunResult {
  correlation_run_id: string;
  policy_set_key: string;
  rules_analyzed: number;
  groups_analyzed: number;
  groups_available: number;
  rules_uncompared: number;
  rules_budget_skipped: number;
  findings_stored: number;
  duplicates_suppressed: number;
  findings_examined: number;
  non_actionable_suppressed: number;
  examined_by_classification: Record<string, number>;
  by_classification: Record<string, number>;
  by_severity: Record<string, number>;
}

/** One step of the AI drafting pipeline, as actually executed. Rendered as a
 * live derivation trail so a reviewer can see how their words became a rule,
 * rather than watching an opaque spinner. */
export interface DraftTraceStep {
  key: string;
  label: string;
  status: "done" | "skipped" | "failed";
  detail: string;
  items: Record<string, unknown>[];
}

export interface DraftFromTextResult {
  policy_set_key: string;
  source_text: string;
  rules: CanonicalRule[];
  skipped: { item?: string; reason?: string }[];
  trace: DraftTraceStep[];
  extraction_statuses: string[];
  /** Always false: authored text has no source clause to cite. Stated by the
   * server so the UI can explain the empty evidence panel instead of leaving
   * a reviewer to guess. */
  has_evidence: boolean;
}

export const aiApi = {
  status: () => request<AiStatus>("/api/ai/status"),

  explainChange: (candidateId: string, narrative = true) =>
    request<RuleChangeExplanation>(
      `/api/ai/candidate-rules/${encodeURIComponent(candidateId)}/explain-change?narrative=${narrative}`,
    ),

  /**
   * Ask for a plain-language reading of one policy's extracted record.
   *
   * POST because it may spend a model call. It writes nothing, and asking twice
   * for an unchanged record costs one call — the server keeps the answer
   * against a digest of the record it explains.
   */
  explainPolicy: (provisionId: string, regenerate = false) =>
    request<PolicyExplanation>(
      `/api/ai/provisions/${encodeURIComponent(provisionId)}/explain?regenerate=${regenerate}`,
      { method: "POST" },
    ),

  /**
   * Read stored names for a set of rules. Reads only — it never generates.
   *
   * A POST because the ids go in a body: a queue draws dozens of rules at once
   * and a query string of that many identifiers is a URL length limit waiting
   * to be found. Nothing is written, and a rule nobody has named yet is simply
   * missing from the reply rather than being invented on the spot.
   */
  ruleNames: (candidateIds: string[]) =>
    request<RuleNameLookupResult>("/api/ai/rule-names/lookup", {
      method: "POST",
      body: JSON.stringify({ candidate_ids: candidateIds }),
    }),

  /**
   * Ask for a name for each rule in this set, one request per policy.
   *
   * Per policy and not per rule, for two reasons that are really one. Sibling
   * rules are drawn from the same sentence, so what tells them apart is only
   * visible when they are seen together; and asking once for a whole policy
   * costs a fraction of asking once per rule.
   */
  generateRuleNames: (key: string, body?: { limit?: number; regenerate?: boolean }) =>
    request<RuleNameGenerationResult>(
      `/api/ai/policy-sets/${encodeURIComponent(key)}/rule-names`,
      { method: "POST", body: JSON.stringify(body ?? {}) },
    ),

  ask: (question: string, policySetKey?: string, history: ChatTurn[] = [], focusCandidateRuleId?: string) =>
    request<AskResponse>("/api/ai/ask", {
      method: "POST",
      body: JSON.stringify({
        question,
        policy_set_key: policySetKey ?? null,
        history,
        focus_candidate_rule_id: focusCandidateRuleId ?? null,
      }),
    }),

  extractWithAi: (policySetKey: string, documentVersionId: string) =>
    request<ExtractResult>(
      `/api/ai/policy-sets/${encodeURIComponent(policySetKey)}/documents/${encodeURIComponent(documentVersionId)}/extract`,
      { method: "POST" }
    ),

  extractionProgress: (documentVersionId: string) =>
    request<ExtractionProgress>(
      `/api/ai/documents/${encodeURIComponent(documentVersionId)}/extraction-progress`
    ),

  listExtractionRuns: (documentVersionId: string) =>
    request<ExtractionRunSummary[]>(
      `/api/ai/documents/${encodeURIComponent(documentVersionId)}/extraction-runs`
    ),

  suggestRewrite: (candidateId: string, instruction: string) =>
    request<RewriteSuggestion>(`/api/ai/candidate-rules/${encodeURIComponent(candidateId)}/rewrite`, {
      method: "POST",
      body: JSON.stringify({ instruction }),
    }),

  applyRewrite: (candidateId: string, suggestedPayload: Record<string, unknown>) =>
    request<{ id: string; revision: number }>(
      `/api/ai/candidate-rules/${encodeURIComponent(candidateId)}/rewrite/apply`,
      { method: "POST", body: JSON.stringify({ suggested_payload: suggestedPayload }) }
    ),

  // Same AI rewrite as `suggestRewrite`, but for a rule that has no saved
  // CandidateRule yet (the "Revise this rule" form, pre-filled from a
  // published rule). Returns a suggestion the caller applies to its own
  // in-progress form state — nothing is persisted server-side.
  rewritePreview: (rule: CanonicalRule, instruction: string) =>
    request<RewriteSuggestion>("/api/ai/rules/rewrite-preview", {
      method: "POST",
      body: JSON.stringify({ rule, instruction }),
    }),

  // Formulate policy text the user typed into draft rules. Same formulator
  // agent and same deterministic mapper as document extraction, minus the
  // verbatim passage stage (the author's text *is* the passage). Returns
  // unsaved drafts plus a trace of the derivation; the caller loads one into
  // its form and submits it through the ordinary draft endpoint, so nothing
  // reaches the review queue without a human action.
  draftFromText: (policySetKey: string, text: string) =>
    request<DraftFromTextResult>(
      `/api/ai/policy-sets/${encodeURIComponent(policySetKey)}/rules/draft-from-text`,
      { method: "POST", body: JSON.stringify({ text }) }
    ),

  // Advisory-only AI reasoning about how a rule (possibly still being
  // edited) would apply to a plain-English scenario. Never touches the
  // deterministic evaluation engine — see ai_scenario_eval.py.
  evaluateScenario: (rule: CanonicalRule, scenario: string, reasoningEffort: string) =>
    request<ScenarioEvaluation>("/api/ai/rules/evaluate-scenario", {
      method: "POST",
      body: JSON.stringify({ rule, scenario, reasoning_effort: reasoningEffort }),
    }),

  // The REAL, deterministic-engine-backed scenario tester for an already
  // -published rule: AI only translates the scenario into facts and explains
  // the result; evaluator.engine.evaluate_policy always decides the verdict.
  // See ai_scenario_engine.py's module docstring for how this differs from
  // evaluateScenario above.
  testRuleScenario: (policySetKey: string, ruleId: string, scenario: string, reasoningEffort: string) =>
    request<RuleScenarioTestResult>(
      `/api/ai/policy-sets/${encodeURIComponent(policySetKey)}/rules/${encodeURIComponent(ruleId)}/test-scenario`,
      {
        method: "POST",
        body: JSON.stringify({ scenario, reasoning_effort: reasoningEffort }),
      }
    ),

  compareVersions: (policySetKey: string, versionA: number, versionB: number, narrative = true) =>
    request<CompareResult>(
      `/api/ai/policy-sets/${encodeURIComponent(policySetKey)}/compare?version_a=${versionA}&version_b=${versionB}&narrative=${narrative}`
    ),

  // Reading and running are separate calls, because they cost different things.
  //
  // A read returns the last evaluation that was recorded and touches neither
  // the model nor the database. A run costs a full AI review -- around two
  // minutes on 273 rules -- and appends a row to the history below. While these
  // were one GET, opening the page was enough to append a row, so the sequence
  // a reviewer reads as a trend was partly made of page loads.
  readQuality: (policySetKey: string) =>
    request<QualityReadout>(`/api/ai/policy-sets/${encodeURIComponent(policySetKey)}/quality`),

  readCandidateQuality: (policySetKey: string) =>
    request<QualityReadout>(`/api/ai/policy-sets/${encodeURIComponent(policySetKey)}/candidates/quality`),

  runQuality: (policySetKey: string) =>
    request<QualityReport>(
      `/api/ai/policy-sets/${encodeURIComponent(policySetKey)}/quality/runs`,
      { method: "POST" }
    ),

  runCandidateQuality: (policySetKey: string) =>
    request<QualityReport>(
      `/api/ai/policy-sets/${encodeURIComponent(policySetKey)}/candidates/quality/runs`,
      { method: "POST" }
    ),

  /** @deprecated Use `readQuality` (a read) or `runQuality` (an evaluation).
   *
   * These two hit the same URLs as `readQuality`/`readCandidateQuality`, but
   * their declared type is deliberately optimistic: it still promises
   * `findings: QualityFinding[]` when the endpoint can now answer
   * `{ evaluated: false, findings: null }`. ReviewQueue.tsx iterates
   * `report.findings` directly and is owned by another workstream, so widening
   * the type here would break a file this change is not allowed to touch.
   *
   * The consequence is real and belongs to that owner: a scope nobody has
   * evaluated yet now returns null findings, and iterating it throws. Switching
   * that call to `readCandidateQuality` and branching on `evaluated` fixes it.
   */
  getQuality: (policySetKey: string) =>
    request<QualityReport>(`/api/ai/policy-sets/${encodeURIComponent(policySetKey)}/quality`),

  getCandidateQuality: (policySetKey: string) =>
    request<QualityReport>(`/api/ai/policy-sets/${encodeURIComponent(policySetKey)}/candidates/quality`),

  // History exists so a reviewer can tell whether the policy set is getting
  // better or worse. A single evaluation says "12 findings", which is only
  // meaningful next to last week's number.
  //
  // `limit` is omitted unless a caller asks for one, so the server's own
  // default applies rather than a copy of it kept here. Whatever it settles
  // on, the response says whether it had to cut the list short.
  getQualityHistory: (policySetKey: string, scope?: "published" | "candidates", limit?: number) => {
    const query = new URLSearchParams();
    if (scope) query.set("scope", scope);
    if (limit !== undefined) query.set("limit", String(limit));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return request<CappedRunList<QualityRunSummary>>(
      `/api/ai/policy-sets/${encodeURIComponent(policySetKey)}/quality/history${suffix}`
    );
  },

  getQualityRun: (policySetKey: string, runId: string) =>
    request<QualityRunDetail>(
      `/api/ai/policy-sets/${encodeURIComponent(policySetKey)}/quality/history/${encodeURIComponent(runId)}`
    ),

  // Whole-policy-set rollup: deterministic rule-count/scope/override/obligation
  // breakdown, plus (when narrative=true and AI is enabled) a plain-English AI
  // narrative of what the policy set as a whole governs. Defaults to the
  // active published version. See ai_summary.py.
  getPolicySetSummary: (policySetKey: string, narrative = true) =>
    request<PolicySetSummary>(
      `/api/ai/policy-sets/${encodeURIComponent(policySetKey)}/summary?narrative=${narrative}`
    ),

  // Correlation: relationships *between* rules. Quality review examines one
  // rule at a time and so cannot see a contradiction — both rules in a
  // contradictory pair are usually well-formed on their own.
  runCorrelation: (policySetKey: string, body: { actionable_only?: boolean; max_groups?: number } = {}) =>
    request<CorrelationRunResult>(`/api/ai/policy-sets/${encodeURIComponent(policySetKey)}/correlate`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listCorrelationRuns: (policySetKey: string) =>
    request<CappedRunList<CorrelationRunSummary>>(
      `/api/ai/policy-sets/${encodeURIComponent(policySetKey)}/correlate/runs`
    ),

  getCorrelationFindings: (policySetKey: string, runId?: string) =>
    request<CorrelationFindingsResponse>(
      `/api/ai/policy-sets/${encodeURIComponent(policySetKey)}/correlate/findings` +
        (runId ? `?run_id=${encodeURIComponent(runId)}` : "")
    ),

  setFindingDisposition: (findingId: string, disposition: string, dispositionBy: string, notes = "") =>
    request<CorrelationFinding>(
      `/api/ai/correlate/findings/${encodeURIComponent(findingId)}/disposition`,
      {
        method: "POST",
        body: JSON.stringify({ disposition, disposition_by: dispositionBy, notes }),
      }
    ),
};

export interface AuditEvent {
  id: string;
  event_type: string;
  entity_type: string;
  entity_id: string | null;
  actor: string;
  details: Record<string, unknown>;
  created_at: string | null;
}

export interface AuditEventPage {
  events: AuditEvent[];
  count: number;
  truncated: boolean;
}

export const auditApi = {
  list: (params: {
    entityType?: string;
    entityId?: string;
    eventType?: string;
    actor?: string;
    limit?: number;
  } = {}) => {
    const qs = new URLSearchParams();
    if (params.entityType) qs.set("entity_type", params.entityType);
    if (params.entityId) qs.set("entity_id", params.entityId);
    if (params.eventType) qs.set("event_type", params.eventType);
    if (params.actor) qs.set("actor", params.actor);
    if (params.limit) qs.set("limit", String(params.limit));
    const suffix = qs.toString();
    return request<AuditEventPage>(`/api/audit-events${suffix ? `?${suffix}` : ""}`);
  },
};

// ---------------------------------------------------------------------------
// Extraction surfaces (Docling integration)
//
// Read-only, and deliberately so: everything a reviewer *does* already has an
// endpoint on `api` below. These answer the questions the existing surfaces
// cannot — what the converter produced, how the document is structured, how the
// run progressed, and what happened to every element.
// ---------------------------------------------------------------------------

export interface CanonicalSourceFragment {
  page: number;
  start_offset: number;
  end_offset: number;
  text: string;
}

export interface CanonicalElement {
  element_id: string | null;
  element_type: string | null;
  sequence: number;
  section: string | null;
  page: number | null;
  clause_ref: string;
  text: string;
  source_fragments: CanonicalSourceFragment[];
}

export interface CanonicalDocumentPage {
  document_version_id: string;
  total_elements: number;
  offset: number;
  elements: CanonicalElement[];
}

export interface StructuralNode {
  element_id: string;
  element_type: string;
  reading_order: number;
  section: string | null;
  page: number | null;
}

export interface StructuralEdge {
  source: string;
  target: string;
  kind: string;
}

export interface StructuralGraphResponse {
  document_version_id: string;
  node_count: number;
  edge_count: number;
  leaf_element_ids: string[];
  nodes: StructuralNode[];
  edges: StructuralEdge[];
}

export interface ReadingPlanContext {
  element_id: string;
  /** Why this element was shown alongside the target — the first question a
   * reviewer asks about a wrong extraction. */
  reason: string;
  /** True when a candidate graph proposed it rather than deterministic
   * structure, so an unverified suggestion never looks like a structural fact. */
  is_candidate: boolean;
}

export interface ReadingPlanUnit {
  unit_id: string;
  heading_path: string[];
  target_element_ids: string[];
  context: ReadingPlanContext[];
}

export interface ReadingPlanResponse {
  document_version_id: string;
  unit_count: number;
  is_exhaustive: boolean;
  uncovered_target_ids: string[];
  units: ReadingPlanUnit[];
}

/** Mirrors CoverageDisposition in contracts/graph_run.py. */
export type CoverageDisposition =
  | "policy_target"
  | "supporting_context"
  | "dependency"
  | "non_normative"
  | "duplicate_structure"
  | "unresolved";

export interface ElementCoverage {
  element_id: string;
  disposition: CoverageDisposition;
  reason: string;
}

export interface CoverageResponse {
  document_version_id: string;
  total_leaf_elements: number;
  accounted: number;
  unresolved: number;
  /** Elements that received no disposition at all. Distinct from `unresolved`,
   * which is a deliberate "could not classify": these were never considered,
   * which is the silent loss the coverage gate exists to catch. */
  unaccounted_element_ids: string[];
  is_complete: boolean;
  elements: ElementCoverage[];
}

/** Every canonical element of one version, assembled from as many windows as it took.
 *
 * Distinct from {@link CanonicalDocumentPage}, which is one window. The
 * distinction is the point: a caller holding a page has no idea whether it is
 * holding the collection, so a page and a whole are not interchangeable and
 * are not the same type. (Found the hard way — a viewer that treated one for
 * the other showed a document's first window and counted that as the document.)
 */
export interface CanonicalDocumentElements {
  document_version_id: string;
  /** The server's count of every element in the version, not of what arrived. */
  total_elements: number;
  elements: CanonicalElement[];
  /** True when `elements` holds all `total_elements` of them. False means the
   * walk stopped short of the server's own declared total, and a caller
   * displaying this list owes the reader a visible note that it is partial. */
  is_complete: boolean;
}

/** One window of canonical elements, starting at `offset`.
 *
 * `limit` is left out unless a caller has its own reason to name one, so the
 * server's window governs and this module holds no opinion about how big a
 * window is. A client that names a page size is asserting something about the
 * server that it cannot check, and the assertion rots silently the day the
 * server's default moves.
 */
const fetchCanonicalPage = (documentVersionId: string, offset: number, limit?: number) => {
  const query = new URLSearchParams({ offset: String(offset) });
  if (limit !== undefined) {
    query.set("limit", String(limit));
  }
  return request<CanonicalDocumentPage>(
    `/api/extraction/${encodeURIComponent(documentVersionId)}/canonical?${query.toString()}`
  );
};

export const extractionApi = {
  getCanonicalDocument: (documentVersionId: string, offset = 0, limit?: number) =>
    fetchCanonicalPage(documentVersionId, offset, limit),

  /** Walk the windows until the version's elements are all in hand.
   *
   * The endpoint answers with a window and the true total beside it. Reading
   * the window and ignoring the total is how the document viewer came to hide
   * the end of a handbook, so this asks again until what it holds matches what
   * the server says exists.
   */
  getAllCanonicalElements: async (
    documentVersionId: string
  ): Promise<CanonicalDocumentElements> => {
    const elements: CanonicalElement[] = [];
    let totalElements = 0;
    let resolvedVersionId = documentVersionId;
    let requests = 0;
    let stalled = false;

    // Two ways to stop short, both faults in the exchange rather than limits on
    // how large a document is allowed to be:
    //
    //   - a window comes back empty while the total says there is more, so
    //     asking again would only ask the same question;
    //   - the walk has made more requests than the server said there are
    //     elements. Every honest window carries at least one element, so an
    //     honest server is satisfied inside `total_elements` requests; past
    //     that it is not honouring the total it declared.
    //
    // Neither is a capacity ceiling. The bound is the server's own number, so
    // it grows with the document and cannot truncate a large one — only a
    // broken exchange. Either way the shortfall leaves through `is_complete`,
    // never as a short list wearing a full count.
    do {
      // Ask from where this walk has reached, not from a page number: the next
      // element wanted is the one after those in hand, whatever size the server
      // chose to answer in.
      const page = await fetchCanonicalPage(documentVersionId, elements.length);
      requests += 1;
      totalElements = page.total_elements;
      resolvedVersionId = page.document_version_id;
      elements.push(...page.elements);
      stalled = page.elements.length === 0;
    } while (!stalled && elements.length < totalElements && requests <= totalElements);

    return {
      document_version_id: resolvedVersionId,
      total_elements: totalElements,
      elements,
      is_complete: elements.length >= totalElements,
    };
  },

  getStructure: (documentVersionId: string) =>
    request<StructuralGraphResponse>(
      `/api/extraction/${encodeURIComponent(documentVersionId)}/structure`
    ),

  getReadingPlan: (documentVersionId: string) =>
    request<ReadingPlanResponse>(
      `/api/extraction/${encodeURIComponent(documentVersionId)}/reading-plan`
    ),

  getCoverage: (documentVersionId: string) =>
    request<CoverageResponse>(
      `/api/extraction/${encodeURIComponent(documentVersionId)}/coverage`
    ),
};

export const api = {
  health: () => request<{ status: string }>("/health"),

  listPolicySets: () => request<PolicySet[]>("/api/policy-sets"),

  getProjectPortfolioSummary: () =>
    request<ProjectPortfolioInsight[]>("/api/policy-sets/portfolio/summary"),

  getPolicySet: (key: string) => request<PolicySet>(`/api/policy-sets/${encodeURIComponent(key)}`),

  createPolicySet: (body: CreatePolicySetRequest) =>
    request<PolicySet>("/api/policy-sets", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updatePolicySet: (key: string, body: UpdatePolicySetRequest) =>
    request<PolicySet>(`/api/policy-sets/${encodeURIComponent(key)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  markPolicySetReviewed: (key: string, body: MarkPolicySetReviewedRequest = {}) =>
    request<PolicySet>(`/api/policy-sets/${encodeURIComponent(key)}/review`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getWorkspaceCounts: (key: string) =>
    request<WorkspaceCounts>(`/api/policy-sets/${encodeURIComponent(key)}/workspace-counts`),

  getTrustedConfig: (key: string) =>
    request<TrustedConfigResponse>(`/api/policy-sets/${encodeURIComponent(key)}/trusted-config`),

  putTrustedConfig: (key: string, trusted_config: Record<string, unknown>) =>
    request<TrustedConfigResponse>(`/api/policy-sets/${encodeURIComponent(key)}/trusted-config`, {
      method: "PUT",
      body: JSON.stringify({ trusted_config }),
    }),

  importPolicyVersion: (key: string, body: ImportPolicyVersionRequest) =>
    request<ApprovedPolicyVersion>(`/api/policy-sets/${encodeURIComponent(key)}/versions`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getActiveVersion: (key: string) =>
    request<ApprovedPolicyVersion>(`/api/policy-sets/${encodeURIComponent(key)}/active-version`),

  listPolicyVersions: (key: string) =>
    request<ApprovedPolicyVersion[]>(`/api/policy-sets/${encodeURIComponent(key)}/versions`),

  getVersionRules: (key: string, versionId: string) =>
    request<CanonicalRule[]>(
      `/api/policy-sets/${encodeURIComponent(key)}/versions/${encodeURIComponent(versionId)}/rules`
    ),

  getVersionAggregateLimits: (key: string, versionId: string) =>
    request<AggregateLimit[]>(
      `/api/policy-sets/${encodeURIComponent(key)}/versions/${encodeURIComponent(versionId)}/aggregate-limits`
    ),

  listAggregateLimits: (key: string) =>
    request<AggregateLimitResponse[]>(`/api/policy-sets/${encodeURIComponent(key)}/aggregate-limits`),

  /** Which published rules could actually contribute to a combined cap.
   * Deterministic and AI-free — see infrastructure/aggregate_eligibility.py. */
  getAggregateEligibility: (key: string) =>
    request<AggregateEligibilityResponse>(
      `/api/policy-sets/${encodeURIComponent(key)}/aggregate-limits/eligibility`
    ),

  /** Ask the model to find rule groups sharing one finite pool. Returns
   * proposals only; nothing is saved until the reviewer says so. */
  proposeAggregateLimits: (key: string, body: { reasoning_effort?: string; guidance?: string }) =>
    request<ProposeAggregateLimitsResponse>(
      `/api/policy-sets/${encodeURIComponent(key)}/aggregate-limits/propose`,
      { method: "POST", body: JSON.stringify(body) }
    ),

  /** Run a draft cap through the real evaluator without saving it. */
  previewAggregateLimit: (
    key: string,
    body: {
      contributing_rules: AggregateLimitContribution[];
      max_value: number;
      description?: string;
      facts: Record<string, unknown>;
    }
  ) =>
    request<PreviewAggregateLimitResponse>(
      `/api/policy-sets/${encodeURIComponent(key)}/aggregate-limits/preview`,
      { method: "POST", body: JSON.stringify(body) }
    ),

  createAggregateLimit: (key: string, body: CreateAggregateLimitRequest) =>
    request<AggregateLimitResponse>(`/api/policy-sets/${encodeURIComponent(key)}/aggregate-limits`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateAggregateLimit: (key: string, aggregateKey: string, body: UpdateAggregateLimitRequest) =>
    request<AggregateLimitResponse>(
      `/api/policy-sets/${encodeURIComponent(key)}/aggregate-limits/${encodeURIComponent(aggregateKey)}`,
      { method: "PUT", body: JSON.stringify(body) }
    ),

  deleteAggregateLimit: (key: string, aggregateKey: string) =>
    request<void>(
      `/api/policy-sets/${encodeURIComponent(key)}/aggregate-limits/${encodeURIComponent(aggregateKey)}`,
      { method: "DELETE" }
    ),

  listDocuments: (policySetKey?: string) =>
    request<SourceDocument[]>(
      `/api/documents${policySetKey ? `?policy_set_key=${encodeURIComponent(policySetKey)}` : ""}`
    ),

  getDocumentClauses: (documentVersionId: string) =>
    request<Clause[]>(`/api/documents/${encodeURIComponent(documentVersionId)}/clauses`),

  uploadDocument: async (title: string, owner: string, file: File, policySetKey?: string) => {
    const form = new FormData();
    form.append("file", file);
    const params = new URLSearchParams({ title, owner });
    if (policySetKey) params.set("policy_set_key", policySetKey);
    const res = await (async () => {
      try {
        return await fetch(`${API_BASE_URL}/api/documents/upload?${params.toString()}`, {
          method: "POST",
          body: form,
        });
      } catch (cause) {
        throw unreachable(cause);
      }
    })();
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body.detail ?? JSON.stringify(body);
      } catch {
        // ignore
      }
      throw new PolicyPlatformApiError(res.status, detail);
    }
    return res.json();
  },

  assignDocumentToProject: (documentId: string, policySetKey: string | null) =>
    request<SourceDocument>(`/api/documents/${encodeURIComponent(documentId)}/assign`, {
      method: "PATCH",
      body: JSON.stringify({ policy_set_key: policySetKey }),
    }),

  draftCandidateRule: (key: string, body: CandidateRuleDraftRequest) =>
    request<CandidateRule>(`/api/policy-sets/${encodeURIComponent(key)}/candidate-rules`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listCandidateRules: (key: string, status?: string, filters?: CandidateRuleFilters) => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (filters?.document_id) params.set("document_id", filters.document_id);
    if (filters?.document_version_id) params.set("document_version_id", filters.document_version_id);
    if (filters?.extraction_run_id) params.set("extraction_run_id", filters.extraction_run_id);
    if (filters?.delta_status) params.set("delta_status", filters.delta_status);
    if (filters?.include_superseded) params.set("include_superseded", "true");
    const qs = params.toString();
    return request<CandidateRule[]>(
      `/api/policy-sets/${encodeURIComponent(key)}/candidate-rules${qs ? `?${qs}` : ""}`
    );
  },

  reviewFacets: (key: string) =>
    request<ReviewFacets>(`/api/policy-sets/${encodeURIComponent(key)}/review-facets`),

  /**
   * The same rules as `listCandidateRules`, arranged under the passage that
   * stated them.
   *
   * A paragraph is one policy stating one or more rules. The flat list is what
   * a reviewer edits; this is what a reviewer reads, and without it a single
   * sentence imposing three obligations appears as three unrelated cards.
   *
   * Grouping is the server's, not this client's. Deriving it here as well would
   * be a second definition of the same relationship, and the two would drift.
   * The rule ids returned index into the ids from `listCandidateRules`, so a
   * caller holding both needs no further fetch.
   */
  listPolicies: (key: string, filters?: PolicyAssemblyFilters) => {
    const params = new URLSearchParams();
    if (filters?.document_id) params.set("document_id", filters.document_id);
    if (filters?.document_version_id) params.set("document_version_id", filters.document_version_id);
    if (filters?.extraction_run_id) params.set("extraction_run_id", filters.extraction_run_id);
    const qs = params.toString();
    return request<AssembledPolicy[]>(
      `/api/policy-sets/${encodeURIComponent(key)}/policies${qs ? `?${qs}` : ""}`
    );
  },

  /**
   * The policies of one published version.
   *
   * The same payload shape `listPolicies` returns, from the published side of
   * the boundary, and assembled by the same `assemble()` on the server rather
   * than by a parallel implementation — so a policy is the same policy whether
   * a reviewer is deciding it or reading what was published.
   */
  listVersionPolicies: (key: string, versionId: string) =>
    request<AssembledPolicy[]>(
      `/api/policy-sets/${encodeURIComponent(key)}/versions/${encodeURIComponent(
        versionId,
      )}/policies`,
    ),

  /**
   * Every version this policy has been seen in, oldest first.
   *
   * Keyed by the provision key rather than by a row id, because a policy is not
   * a row: `document_provisions.id` belongs to one document version and cannot
   * follow a policy through a re-extraction, while the key does. That is what
   * makes a history derivable at all.
   *
   * A failure is raised, never flattened into an empty list. The pane draws a
   * different sentence for "not asked" than for "no other version was found",
   * and turning the first into the second would have it claim a fact about the
   * record that this call never established.
   */
  listProvisionHistory: (key: string, provisionKey: string) =>
    request<PolicySightingView[]>(
      `/api/policy-sets/${encodeURIComponent(key)}/provisions/${encodeURIComponent(
        provisionKey,
      )}/history`,
    ),

  /**
   * Ask for a short generated name for the subject of each policy in this set.
   *
   * A batch and not a per-card call, deliberately. Naming is a model call, and
   * a card that generated its own name on render would spend one every time a
   * queue was drawn — the reviewer would pay for the same seventy names each
   * time they came back to the page. Asked for once, stored, and read
   * thereafter by `listPolicies`.
   *
   * Policies already named are skipped unless `regenerate`, so asking twice
   * costs nothing the second time.
   */
  generateTopicLabels: (
    key: string,
    body?: { limit?: number; regenerate?: boolean }
  ) =>
    request<TopicLabelGenerationResult>(
      `/api/ai/policy-sets/${encodeURIComponent(key)}/topic-labels`,
      { method: "POST", body: JSON.stringify(body ?? {}) }
    ),

  reviewCandidateRule: (key: string, candidateId: string, body: CandidateRuleReviewRequest) =>
    request<CandidateRule>(
      `/api/policy-sets/${encodeURIComponent(key)}/candidate-rules/${encodeURIComponent(candidateId)}/review`,
      { method: "POST", body: JSON.stringify(body) }
    ),

  editCandidateRule: (key: string, candidateId: string, body: CandidateRuleEditRequest) =>
    request<CandidateRule>(
      `/api/policy-sets/${encodeURIComponent(key)}/candidate-rules/${encodeURIComponent(candidateId)}`,
      { method: "PUT", body: JSON.stringify(body) }
    ),

  requestChanges: (key: string, candidateId: string, body: RequestChangesRequest) =>
    request<CandidateRule>(
      `/api/policy-sets/${encodeURIComponent(key)}/candidate-rules/${encodeURIComponent(candidateId)}/request-changes`,
      { method: "POST", body: JSON.stringify(body) }
    ),

  overrideReview: (key: string, candidateId: string, body: OverrideReviewRequest) =>
    request<CandidateRule>(
      `/api/policy-sets/${encodeURIComponent(key)}/candidate-rules/${encodeURIComponent(candidateId)}/override`,
      { method: "POST", body: JSON.stringify(body) }
    ),

  bulkReviewCandidateRules: (
    key: string,
    body: { candidate_ids: string[]; decision: "approve" | "reject"; reviewer: string; notes?: string }
  ) =>
    request<{ reviewed: number; skipped: string[] }>(
      `/api/policy-sets/${encodeURIComponent(key)}/candidate-rules/bulk-review`,
      { method: "POST", body: JSON.stringify(body) }
    ),

  publishCandidates: (key: string, body: PublishCandidatesRequest) =>
    request<ApprovedPolicyVersion>(`/api/policy-sets/${encodeURIComponent(key)}/publish`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  evaluate: (body: EvaluationRequest) =>
    request<EvaluationResponse>("/api/evaluations", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // ---------- Notes ----------

  listNotes: (entityType: NoteEntityType, entityId: string) =>
    request<Note[]>(
      `/api/notes?entity_type=${encodeURIComponent(entityType)}&entity_id=${encodeURIComponent(entityId)}`
    ),

  createNote: (body: CreateNoteRequest) =>
    request<Note>("/api/notes", { method: "POST", body: JSON.stringify(body) }),

  deleteNote: (noteId: string) => request<void>(`/api/notes/${encodeURIComponent(noteId)}`, { method: "DELETE" }),

  // ---------- Export (triggers a browser download; no return value) ----------

  exportVersionRules: (key: string, versionId: string, format: ExportFormat) =>
    downloadFile(
      `/api/policy-sets/${encodeURIComponent(key)}/versions/${encodeURIComponent(versionId)}/export?format=${format}`,
      `${key}-rules.${format}`
    ),

  exportCandidateRules: (key: string, format: ExportFormat, status?: string) =>
    downloadFile(
      `/api/policy-sets/${encodeURIComponent(key)}/candidate-rules/export?format=${format}${
        status ? `&status=${encodeURIComponent(status)}` : ""
      }`,
      `${key}-candidate-rules.${format}`
    ),
};
