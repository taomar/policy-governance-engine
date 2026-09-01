import type {
  CaseDecisionEnvelope,
  CaseDecisionEnvelopeV2,
  DecisionStatus,
  InformationSection,
  LanguageRef,
  MergedCitationRef,
  MissingInformationItem,
  PolicyRef,
  VerdictSection,
  VerificationRequirementItem,
} from '../contracts/caseDecision'

/**
 * A realistic `case_decision_v1` envelope for tests.
 *
 * Written by hand from the server contract rather than captured from a live
 * call, so a test that depends on a field name fails when the contract changes
 * rather than when a fixture goes stale.
 */
export function makeEnvelope(overrides: Partial<CaseDecisionEnvelope> = {}): CaseDecisionEnvelope {
  return {
    schema_version: 'case_decision_v1',
    decision_id: '9c0f2d4b-1a7e-4f31-9b02-6d5c8e1a3f77',
    correlation_id: '6f1c9d2e-1b7a-4a55-9a4c-2d3f5b8e1c04',
    idempotency_key: null,
    policy_set: {
      id: 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
      key: 'demo-project',
      name: 'Supplier Onboarding Policy',
    },
    active_version: {
      version_id: '5f2c1a4e-3b6d-4c8f-9a2e-7d1b0c3e9b31',
      version_number: 7,
      effective_from: '2026-01-01',
      effective_to: null,
    },
    caller: {
      principal_identity: 'policy.admin@example.com',
      principal_role: 'admin',
      authentication_source: 'local-token',
      calling_system_identity: 'playground-demo',
      channel: 'api',
    },
    request: {
      scenario: 'A supplier in a sanctioned jurisdiction asks about 90-day payment terms.',
      scenario_hash: 'a'.repeat(64),
      additional_instructions: 'Explain the approval path first',
      additional_instructions_hash: 'b'.repeat(64),
      scope: 'project',
      requested_provision_id: null,
      reasoning_effort_requested: 'medium',
      received_at: '2026-08-29T10:15:00.000Z',
    },
    decision_status: 'answered',
    retrieval: {
      status: 'narrowed',
      method: 'hybrid',
      policies_considered: 12,
      policies_retained: 3,
      policies_discarded: 9,
      reason: null,
    },
    considered: [
      {
        provision_key: 'SUP-3.2',
        heading_path: ['Supplier Onboarding', 'Payment terms'],
        retained: true,
        rules: 4,
        payload_url: 'https://policy.example.com/api/policy-payload/SUP-3.2',
      },
      {
        provision_key: 'SUP-9.1',
        heading_path: ['Supplier Onboarding', 'Travel'],
        retained: false,
        discard_reason: 'no_match',
      },
    ],
    excluded: [],
    decision: {
      intent: 'decision',
      status: 'answered',
      verdict: 'Proceed only with prior sanctions clearance.',
      explanation: 'The approval path requires sanctions clearance before terms are agreed.',
      missing_required_facts: [],
      note: '',
      decider_route: 'decision',
    },
    citations: [
      {
        rule_id: 'SUP-3.2-R1',
        policy: {
          provision_key: 'SUP-3.2',
          heading_path: ['Supplier Onboarding', 'Payment terms'],
          payload_url: 'https://policy.example.com/api/policy-payload/SUP-3.2',
        },
        source: {
          state: 'quoted',
          text: 'Payment terms beyond 60 days require prior sanctions clearance.',
          page: 12,
          section: '3.2',
        },
      },
    ],
    grounding: { rules_available: 14, rules_cited: 1, fabricated_citations: [] },
    size: { combined_chars: 4200, budget_chars: 42000, oversize: false },
    trace: {
      prompt_version: 'ai-case-intent-v4',
      instruction_profile: 'case-guidance-v1',
      model_deployment: 'gpt-5.6-sol',
      retrieval_method: 'hybrid',
      index_name: 'policy-authoring',
      index_version_id: '5f2c1a4e-3b6d-4c8f-9a2e-7d1b0c3e9b31',
    },
    decision_hash: 'c'.repeat(64),
    hash_basis: 'case_decision_v1',
    receipt_url: 'https://policy.example.com/api/policy-decisions/9c0f2d4b-1a7e-4f31-9b02-6d5c8e1a3f77',
    decided_at: '2026-08-29T10:15:09.500Z',
    latency_ms: 9500,
    ...overrides,
  }
}

/** The same envelope moved to a status that carries no verdict. */
export function makeNonAnsweredEnvelope(status: DecisionStatus): CaseDecisionEnvelope {
  const base = makeEnvelope()
  return {
    ...base,
    decision_status: status,
    decision: {
      ...base.decision,
      status,
      // The server empties the verdict for every status but `answered`. The
      // fixture deliberately leaves a stale value in place so a test proves the
      // *client* guard, not the server's own emptying.
      verdict: 'THIS MUST NEVER BE RENDERED',
    },
  }
}

/* ==========================================================================
   case_decision_v2

   Written by hand from `src/policy_platform/contracts/case_decision.py` rather
   than captured from a live call, so a test that depends on a field name fails
   when the contract changes rather than when a fixture goes stale.

   Every builder below produces an envelope the server's own model validators
   would accept -- in particular the two that matter most:

     * `information.answered` is true exactly when `information.status` is
       `answered`, and only an answered section carries an `answer`.
     * `verdict.reached` is true exactly when `verdict.status` is `answered`,
       only a reached verdict carries a `decision`, and missing information
       belongs only to a verdict blocked on `missing_required_facts`.

   A fixture that violated either would be testing a shape the server cannot
   emit, and the client guard it appeared to prove would be untested.
   ========================================================================== */

const V2_INFORMATION_CITATION: MergedCitationRef = {
  rule_id: 'HR-4.1-R2',
  policy: {
    provision_key: 'HR-4.1',
    heading_path: ['Working time', 'Weekly limits'],
    payload_url: '/api/policy-payload/HR-4.1',
  },
  source: {
    state: 'quoted',
    text: 'Staff may not be scheduled for more than 48 hours in any rolling seven-day period.',
    page: 22,
    section: '4.1',
  },
  serves: ['information'],
}

/** Cited by both tracks: the rule that states the cap also decides the case. */
const V2_SHARED_CITATION: MergedCitationRef = {
  rule_id: 'HR-4.1-R3',
  policy: {
    provision_key: 'HR-4.1',
    heading_path: ['Working time', 'Weekly limits'],
    payload_url: '/api/policy-payload/HR-4.1',
  },
  source: {
    state: 'quoted',
    text: 'A shift that takes an employee past the weekly limit requires written approval before it is worked.',
    page: 23,
    section: '4.1',
  },
  serves: ['information', 'verdict'],
}

const V2_VERDICT_CITATION: MergedCitationRef = {
  rule_id: 'HR-4.6-R1',
  policy: {
    provision_key: 'HR-4.6',
    heading_path: ['Working time', 'Approvals'],
    payload_url: '/api/policy-payload/HR-4.6',
  },
  source: {
    state: 'quoted',
    text: 'Written approval is valid only when it is recorded before the shift begins.',
    page: 26,
    section: '4.6',
  },
  serves: ['verdict'],
}

export const V2_MISSING_INFORMATION: MissingInformationItem[] = [
  {
    fact: 'hours_worked_in_rolling_week',
    label: 'Hours already worked in the rolling seven-day period',
    why_needed:
      'The weekly limit is measured across a rolling seven days, so the shift cannot be tested without the hours that precede it.',
    required_by_rule_ids: ['HR-4.1-R3'],
  },
  {
    fact: 'written_approval_recorded_at',
    label: 'When the written approval was recorded',
    why_needed:
      'Approval counts only if it was recorded before the shift began, so the timestamp decides whether it applies.',
    required_by_rule_ids: ['HR-4.6-R1', 'HR-4.1-R3'],
  },
]

/**
 * Conditions on acting that ride alongside a verdict that *was* reached.
 *
 * Deliberately not the same values as the missing facts above: the two lists
 * mean different things, and a fixture that reused one for the other would let
 * a test pass while the page conflated them.
 */
export const V2_VERIFICATION_REQUIREMENTS: VerificationRequirementItem[] = [
  {
    fact: 'accrued_balance_on_the_day',
    label: 'The balance standing on the day the leave starts',
    why_needed:
      'The entitlement is established, but the days can only be taken out of a balance that has actually accrued by then.',
    required_by_rule_ids: ['HR-4.1-R3'],
  },
  {
    fact: 'roster_cover_for_the_period',
    label: 'That the roster is covered for the period',
    why_needed:
      'The rules make cover a condition of taking the days, not a condition of being owed them.',
    required_by_rule_ids: ['HR-4.6-R1'],
  },
]

function answeredInformation(overrides: Partial<InformationSection> = {}): InformationSection {
  return {
    status: 'answered',
    answered: true,
    answer:
      'The published policies cap scheduled working time at 48 hours in any rolling seven-day period, and require written approval, recorded before the shift starts, for any shift that would take an employee past it.',
    explanation: null,
    route: 'informational',
    citations: [V2_INFORMATION_CITATION, V2_SHARED_CITATION],
    note: '',
    grounding: { rules_available: 11, rules_cited: 2, fabricated_citations: [] },
    ...overrides,
  }
}

function blockedVerdict(overrides: Partial<VerdictSection> = {}): VerdictSection {
  return {
    status: 'missing_required_facts',
    reached: false,
    decision: '',
    explanation:
      'Whether this shift was within the weekly limit turns on hours already worked and on when the approval was recorded. Neither was supplied, so the case was not decided.',
    missing_information: V2_MISSING_INFORMATION,
    missing_required_facts: V2_MISSING_INFORMATION.map((item) => item.label),
    route: 'decision',
    citations: [V2_SHARED_CITATION, V2_VERDICT_CITATION],
    note: '',
    grounding: { rules_available: 11, rules_cited: 2, fabricated_citations: [] },
    ...overrides,
  }
}

function reachedVerdict(overrides: Partial<VerdictSection> = {}): VerdictSection {
  return {
    status: 'answered',
    reached: true,
    decision: 'Not compliant',
    explanation:
      'The shift took the employee to 52 hours in the rolling week and the written approval was recorded after it began, so it fails both conditions the rules impose.',
    missing_information: [],
    missing_required_facts: [],
    route: 'decision',
    citations: [V2_SHARED_CITATION, V2_VERDICT_CITATION],
    note: '',
    grounding: { rules_available: 11, rules_cited: 2, fabricated_citations: [] },
    ...overrides,
  }
}

/**
 * The base v2 envelope: both tracks asked for, both answered.
 *
 * Every other builder below is this one with the two sections and the two
 * outcomes replaced, so a field added to the envelope is added in one place.
 */
export function makeV2Envelope(
  overrides: Partial<CaseDecisionEnvelopeV2> = {},
): CaseDecisionEnvelopeV2 {
  return {
    schema_version: 'case_decision_v2',
    receipt_status: 'completed',
    decision_id: '2f7a1c93-58bd-4d0e-9c31-7ae4f0b62d18',
    correlation_id: '6f1c9d2e-1b7a-4a55-9a4c-2d3f5b8e1c04',
    idempotency_key: null,
    policy_set: {
      id: 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
      key: 'demo-project',
      name: 'Staff Handbook',
    },
    active_version: {
      version_id: '5f2c1a4e-3b6d-4c8f-9a2e-7d1b0c3e9b31',
      version_number: 7,
      effective_from: '2026-01-01',
      effective_to: null,
    },
    caller: {
      principal_identity: 'policy.admin@example.com',
      principal_role: 'admin',
      authentication_source: 'local-token',
      calling_system_identity: 'playground-demo',
      channel: 'api',
    },
    request: {
      scenario:
        'What do the policies say about weekly working limits, and was Tuesday’s 11-hour shift within them?',
      scenario_hash: 'a'.repeat(64),
      additional_instructions: 'Explain the approval path first',
      additional_instructions_hash: 'b'.repeat(64),
      scope: 'project',
      requested_provision_id: null,
      reasoning_effort_requested: 'medium',
      received_at: '2026-08-30T09:15:00.000Z',
    },
    asked: {
      information_requested: true,
      verdict_requested: true,
      classification_reasoning:
        'The question asks what the policies state about weekly limits and also asks whether one specific shift complied, so both tracks were run.',
      classifier_version: 'case-intent-classifier-v2',
    },
    outcome: { information: 'answered', verdict: 'answered' },
    information: answeredInformation(),
    verdict: reachedVerdict(),
    retrieval: {
      status: 'narrowed',
      method: 'hybrid',
      policies_considered: 12,
      policies_retained: 2,
      policies_discarded: 10,
      reason: null,
    },
    considered: [
      {
        provision_key: 'HR-4.1',
        heading_path: ['Working time', 'Weekly limits'],
        retained: true,
        rules: 9,
        payload_url: '/api/policy-payload/HR-4.1',
      },
      {
        provision_key: 'HR-4.6',
        heading_path: ['Working time', 'Approvals'],
        retained: true,
        rules: 5,
        payload_url: '/api/policy-payload/HR-4.6',
      },
      {
        provision_key: 'HR-9.2',
        heading_path: ['Working time', 'Travel time'],
        retained: false,
        discard_reason: 'no_match',
      },
    ],
    excluded: [],
    citations: [V2_INFORMATION_CITATION, V2_SHARED_CITATION, V2_VERDICT_CITATION],
    size: { combined_chars: 6100, budget_chars: 42000, oversize: false },
    trace: {
      prompt_version: 'ai-case-intent-v5',
      instruction_profile: 'case-guidance-v2',
      model_deployment: 'gpt-5.6-sol',
      retrieval_method: 'hybrid',
      index_name: 'policy-authoring',
      index_version_id: '5f2c1a4e-3b6d-4c8f-9a2e-7d1b0c3e9b31',
    },
    decision_hash: 'd'.repeat(64),
    hash_basis: 'case_decision_v2',
    receipt_url:
      'https://policy.example.com/api/policy-decisions/2f7a1c93-58bd-4d0e-9c31-7ae4f0b62d18',
    decided_at: '2026-08-30T09:15:11.200Z',
    latency_ms: 11200,
    ...overrides,
  }
}

/** The classifier read the question as asking only what the policies state. */
export function makeInformationOnlyEnvelope(): CaseDecisionEnvelopeV2 {
  return makeV2Envelope({
    request: {
      ...makeV2Envelope().request,
      scenario: 'What do the published policies say about weekly working limits?',
    },
    asked: {
      information_requested: true,
      verdict_requested: false,
      classification_reasoning:
        'The question asks what the policies state and describes no case to evaluate, so only the information track was run.',
      classifier_version: 'case-intent-classifier-v2',
    },
    outcome: { information: 'answered', verdict: 'not_requested' },
    information: answeredInformation(),
    verdict: null,
    citations: [V2_INFORMATION_CITATION, V2_SHARED_CITATION],
  })
}

/** The classifier read the question as asking only for a determination. */
export function makeVerdictOnlyEnvelope(): CaseDecisionEnvelopeV2 {
  return makeV2Envelope({
    request: {
      ...makeV2Envelope().request,
      scenario: 'Was Tuesday’s 11-hour shift within the weekly limit?',
    },
    asked: {
      information_requested: false,
      verdict_requested: true,
      classification_reasoning:
        'The question puts one concrete case and asks whether it complied, so only the verdict track was run.',
      classifier_version: 'case-intent-classifier-v2',
    },
    outcome: { information: 'not_requested', verdict: 'answered' },
    information: null,
    verdict: reachedVerdict(),
    citations: [V2_SHARED_CITATION, V2_VERDICT_CITATION],
  })
}

/**
 * A verdict that was reached and still carries conditions on acting.
 *
 * The case the whole "checks before acting" section exists for: the records
 * settle the entitlement, so a determination is owed, and separately impose
 * things a caller must confirm before exercising it. Both are true at once, and
 * the page has to say so without dressing either up as the other.
 */
export function makeQualifiedVerdictEnvelope(): CaseDecisionEnvelopeV2 {
  return makeV2Envelope({
    outcome: { information: 'answered', verdict: 'answered' },
    information: answeredInformation(),
    verdict: reachedVerdict({
      decision: 'Entitled',
      verification_requirements: V2_VERIFICATION_REQUIREMENTS,
    }),
  })
}

/**
 * The case this redesign is shaped around: information answered, verdict
 * blocked on facts the case did not supply.
 */
export function makeMixedBlockedEnvelope(): CaseDecisionEnvelopeV2 {
  return makeV2Envelope({
    outcome: { information: 'answered', verdict: 'missing_required_facts' },
    information: answeredInformation(),
    verdict: blockedVerdict(),
  })
}

/** Retrieval produced nothing to evaluate, so the classifier never ran. */
export function makeNotEvaluatedV2Envelope(): CaseDecisionEnvelopeV2 {
  return makeV2Envelope({
    asked: {
      information_requested: false,
      verdict_requested: false,
      classification_reasoning: null,
      classifier_version: null,
    },
    outcome: { information: 'not_evaluated', verdict: 'not_evaluated' },
    information: null,
    verdict: null,
    retrieval: {
      status: 'no_match',
      method: 'hybrid',
      policies_considered: 12,
      policies_retained: 0,
      policies_discarded: 12,
      reason: 'no_match',
    },
    considered: [
      {
        provision_key: 'HR-9.2',
        heading_path: ['Working time', 'Travel time'],
        retained: false,
        discard_reason: 'no_match',
      },
    ],
    citations: [],
  })
}

/** Both tracks ran; neither found a rule that bears. A real answer, not a gap. */
export function makeNoRuleBearsV2Envelope(): CaseDecisionEnvelopeV2 {
  return makeV2Envelope({
    outcome: { information: 'no_rule_bears', verdict: 'no_rule_bears' },
    information: {
      status: 'no_rule_bears',
      answered: false,
      answer: '',
      explanation:
        'The retained policies cover working time and approvals; none of them states anything about parking allowances.',
      route: 'informational',
      citations: [],
      note: '',
      grounding: { rules_available: 11, rules_cited: 0, fabricated_citations: [] },
    },
    verdict: {
      status: 'no_rule_bears',
      reached: false,
      decision: '',
      explanation: 'No retained rule determines this case.',
      missing_information: [],
      missing_required_facts: [],
      route: 'decision',
      citations: [],
      note: '',
      grounding: { rules_available: 11, rules_cited: 0, fabricated_citations: [] },
    },
    citations: [],
  })
}

/**
 * A retained policy read as a slice of its rules.
 *
 * The seventy-four-row penalties table the contract's own docstring names: it
 * survives retrieval, it contributes citations, and by any policy count nothing
 * was discarded — which is exactly why a receipt that reports the policy
 * without reporting the slice implies all seventy-four rows were weighed.
 */
export function makeRuleSlicedEnvelope(): CaseDecisionEnvelopeV2 {
  const slicedPolicy: PolicyRef = {
    provision_key: 'FIN-12.4',
    heading_path: ['Finance', 'Penalties schedule'],
    retained: true,
    rules: 74,
    payload_url: '/api/policy-payload/FIN-12.4',
    rule_selection: {
      total_rules: 74,
      selected_rules: 8,
      selected_rule_ids: [
        'FIN-12.4-R03',
        'FIN-12.4-R07',
        'FIN-12.4-R11',
        'FIN-12.4-R12',
        'FIN-12.4-R28',
        'FIN-12.4-R31',
        'FIN-12.4-R55',
        'FIN-12.4-R61',
      ],
      rules_discarded: 66,
      method: 'scenario_relevance_v1',
      sliced: true,
      context_rules_added: 2,
      context_rules_omitted: ['FIN-12.4-R62'],
      chars: 8100,
      budget_chars: 9000,
      oversize: false,
    },
  }

  return makeV2Envelope({
    outcome: { information: 'answered', verdict: 'answered' },
    retrieval: {
      // Not narrowed at the policy level: every published policy survived
      // search. The slicing is the only narrowing, which is the case a
      // policy-count-only guard would have called "all policies evaluated".
      status: 'not_narrowed',
      method: 'hybrid',
      policies_considered: 2,
      policies_retained: 2,
      policies_discarded: 0,
      policies_rule_sliced: 1,
      large_policy_rule_threshold: 40,
      selected_rule_budget: 8,
      payload_budget_chars: 42000,
      policies_over_payload_budget: 0,
      reason: null,
    },
    considered: [
      slicedPolicy,
      {
        provision_key: 'FIN-3.1',
        heading_path: ['Finance', 'Late payment'],
        retained: true,
        rules: 6,
        payload_url: '/api/policy-payload/FIN-3.1',
        rule_selection: {
          total_rules: 6,
          selected_rules: 6,
          selected_rule_ids: [],
          rules_discarded: 0,
          method: 'whole_policy',
          sliced: false,
        },
      },
    ],
    excluded: [],
  })
}

/** A v2 envelope whose fabrication guard refused a citation on one track. */
export function makeFabricatedCitationV2Envelope(): CaseDecisionEnvelopeV2 {
  return makeV2Envelope({
    verdict: reachedVerdict({
      grounding: {
        rules_available: 11,
        rules_cited: 2,
        fabricated_citations: ['HR-99.9-R1'],
      },
    }),
  })
}

/**
 * The de-duplication disclosures, all at once.
 *
 * Three different things a count could flatten into "we did not read it", kept
 * apart here because they are three different claims:
 *
 *   * **Collapsed exact duplicates** (`HW-7.9`, `HW-8.3`) — proven identical to
 *     a retrieved policy, named as `duplicate_policy_content`, each carrying
 *     the representative its terms were read in. Discarded records, undiscarded
 *     content.
 *   * **Diversity-deferred** (`HW-5.5`) — nothing was proven about it. It
 *     ranked inside the budget and was offered after it because a policy
 *     requiring the same thing came first, so it carries the ordinary
 *     `outside_budget` reason and must never be called a duplicate.
 *   * **An ordinary miss** (`HW-9.2`) — it did not surface in the scan at all.
 *
 * And one level down, `HW-2.1` is read as a slice whose discarded remainder is
 * itself split: three of the sixty-six are exact copies of rules that were
 * read, and sixty-three are rules nothing saw.
 */
export function makeDuplicateCollapsedEnvelope(): CaseDecisionEnvelopeV2 {
  return makeV2Envelope({
    outcome: { information: 'answered', verdict: 'answered' },
    retrieval: {
      status: 'narrowed',
      method: 'hybrid',
      policies_considered: 14,
      policies_retained: 2,
      policies_discarded: 12,
      policies_duplicate_collapsed: 2,
      policies_diversity_deferred: 3,
      policy_selection_order: 'relevance_then_normative_content_v1',
      policies_rule_sliced: 1,
      large_policy_rule_threshold: 40,
      selected_rule_budget: 8,
      payload_budget_chars: 42000,
      policies_over_payload_budget: 1,
      reason: null,
    },
    considered: [
      {
        provision_key: 'HW-2.1',
        heading_path: ['Hardware', 'Replacement cycle'],
        retained: true,
        rules: 74,
        payload_url: '/api/policy-payload/HW-2.1',
        rule_selection: {
          total_rules: 74,
          selected_rules: 8,
          selected_rule_ids: [
            'HW-2.1-R03',
            'HW-2.1-R07',
            'HW-2.1-R11',
            'HW-2.1-R12',
            'HW-2.1-R28',
            'HW-2.1-R31',
            'HW-2.1-R55',
            'HW-2.1-R61',
          ],
          rules_discarded: 66,
          method: 'scenario_relevance_v2',
          sliced: true,
          context_rules_added: 2,
          context_rules_omitted: ['HW-2.1-R62'],
          duplicate_rules_collapsed: 5,
          // Part of the 66, and not read: an identical rule was.
          represented_rule_ids: ['HW-2.1-R14', 'HW-2.1-R33', 'HW-2.1-R47'],
          chars: 8100,
          budget_chars: 9000,
          oversize: false,
        },
      },
      {
        provision_key: 'HW-2.4',
        heading_path: ['Hardware', 'Early replacement'],
        retained: true,
        rules: 6,
        payload_url: '/api/policy-payload/HW-2.4',
        rule_selection: {
          total_rules: 6,
          selected_rules: 6,
          selected_rule_ids: [],
          rules_discarded: 0,
          method: 'whole_policy',
          sliced: false,
        },
      },
      {
        provision_key: 'HW-7.9',
        heading_path: ['Hardware', 'Replacement cycle (regional annex)'],
        retained: false,
        discard_reason: 'duplicate_policy_content',
        duplicate_of_provision_key: 'HW-2.1',
      },
      {
        provision_key: 'HW-8.3',
        heading_path: ['Hardware', 'Early replacement (contractor annex)'],
        retained: false,
        discard_reason: 'duplicate_policy_content',
        duplicate_of_provision_key: 'HW-2.4',
      },
      {
        // Deferred for coverage. Nothing was proven identical about it, so it
        // carries the ordinary reason and no representative.
        provision_key: 'HW-5.5',
        heading_path: ['Hardware', 'Peripheral replacement'],
        retained: false,
        best_rank: 3,
        best_score: 0.71,
        discard_reason: 'outside_budget',
      },
      {
        provision_key: 'HW-9.2',
        heading_path: ['Hardware', 'Disposal'],
        retained: false,
        discard_reason: 'no_retrieval_match',
      },
    ],
    excluded: [],
  })
}

/** A collapsed duplicate whose receipt did not name the representative. */
export function makeUnnamedDuplicateEnvelope(): CaseDecisionEnvelopeV2 {
  const base = makeDuplicateCollapsedEnvelope()
  return {
    ...base,
    considered: (base.considered ?? []).map((policy) =>
      policy.provision_key === 'HW-7.9'
        ? { ...policy, duplicate_of_provision_key: null }
        : policy,
    ),
  }
}

/* ==========================================================================
   M2: the language boundary and rule-level discovery

   Every question in every fixture below is English, deliberately. A regional
   tag carried into the processing tag (`en-GB` → `en`) exercises the whole
   rendered path -- a `processing_scenario` that differs from `request.scenario`,
   an outbound rendering, a dropped guidance -- without putting a single string
   of text nobody on this project can proof-read into the suite.
   ========================================================================== */

const ENGLISH_RENDERED_LANGUAGE: LanguageRef = {
  source_language: 'en-GB',
  processing_language: 'en',
  response_language: 'en-GB',
  boundary_state: 'rendered',
  output_rendering_state: 'rendered',
  guidance_rendering_state: 'rendered',
  input_translation_profile: 'case-language-in-v1',
  output_translation_profile: 'case-language-out-v1',
  // Deliberately not byte-identical to `request.scenario`: this is the text the
  // pipeline read, and a reader comparing the two is the only person who can
  // catch a rendering that changed the question.
  processing_scenario:
    'What do the published policies state about laptop replacement eligibility, and is a 26-month-old laptop eligible for replacement now?',
  processing_scenario_hash: 'e'.repeat(64),
  processing_additional_instructions: 'Explain the approval path first',
  projection_profile: 'english_projection_v1',
}

/** The question was rendered, the answer was rendered back, guidance survived. */
export function makeLanguageRenderedEnvelope(): CaseDecisionEnvelopeV2 {
  return makeV2Envelope({
    request: {
      ...makeV2Envelope().request,
      scenario:
        'What do the policies say about laptop replacement eligibility, and is my 26-month-old laptop eligible now?',
    },
    language: ENGLISH_RENDERED_LANGUAGE,
  })
}

/** The rendering call reported the question was already in the processing language. */
export function makeLanguageIdentityEnvelope(): CaseDecisionEnvelopeV2 {
  const base = makeV2Envelope()
  return makeV2Envelope({
    language: {
      ...ENGLISH_RENDERED_LANGUAGE,
      source_language: 'en',
      response_language: 'en',
      boundary_state: 'identity',
      output_rendering_state: 'not_required',
      guidance_rendering_state: 'not_required',
      output_translation_profile: null,
      // Identity: what was adjudicated is byte-for-byte what was sent.
      processing_scenario: base.request.scenario,
    },
  })
}

/** No usable target tag, and the caller's guidance could not be carried across. */
export function makeLanguageDroppedGuidanceEnvelope(): CaseDecisionEnvelopeV2 {
  return makeV2Envelope({
    language: {
      ...ENGLISH_RENDERED_LANGUAGE,
      source_language: 'und',
      response_language: 'en',
      output_rendering_state: 'target_unknown',
      guidance_rendering_state: 'unrendered_dropped',
      output_translation_profile: null,
      processing_additional_instructions: '',
    },
  })
}

/**
 * Rule-level discovery did something: the rule index was queried, its ranking
 * was fused, and two policies were ranked higher because their own rules
 * surfaced — one of which the policy-level search never returned.
 */
export function makeRuleIndexMatchedEnvelope(): CaseDecisionEnvelopeV2 {
  return makeV2Envelope({
    language: ENGLISH_RENDERED_LANGUAGE,
    retrieval: {
      status: 'narrowed',
      method: 'hybrid',
      policies_considered: 9,
      policies_retained: 2,
      policies_discarded: 7,
      policies_rule_sliced: 1,
      large_policy_rule_threshold: 40,
      selected_rule_budget: 8,
      payload_budget_chars: 42000,
      policy_selection_order: 'relevance_then_normative_content_v1',
      rule_scan: 412,
      projection_profile: 'english_projection_v1',
      projection_ready: true,
      policy_documents_matched: 6,
      rule_documents_matched: 23,
      policies_elevated_by_rule: 2,
      rule_index_state: 'matched',
      reason: null,
    },
    considered: [
      {
        provision_key: 'HW-2.1',
        heading_path: ['Hardware', 'Replacement cycle'],
        retained: true,
        rules: 74,
        payload_url: '/api/policy-payload/HW-2.1',
        rule_selection: {
          total_rules: 74,
          selected_rules: 8,
          selected_rule_ids: [
            'HW-2.1-R03',
            'HW-2.1-R07',
            'HW-2.1-R11',
            'HW-2.1-R12',
            'HW-2.1-R28',
            'HW-2.1-R31',
            'HW-2.1-R55',
            'HW-2.1-R61',
          ],
          rules_discarded: 66,
          method: 'hybrid_rule_v1',
          sliced: true,
          context_rules_added: 1,
          rule_index_state: 'matched',
          rule_index_hits: 12,
          lexical_candidates: 19,
          quantity_candidates: 4,
          fused_candidates: 27,
          evidence_diversity_quota: 4,
          rules_without_projection: 3,
        },
      },
      {
        // Retained, read whole, and the rule index was asked and placed none of
        // its rules. Zero hits under `matched` is an answer, not an outage.
        provision_key: 'HW-2.4',
        heading_path: ['Hardware', 'Early replacement'],
        retained: true,
        rules: 6,
        payload_url: '/api/policy-payload/HW-2.4',
        rule_selection: {
          total_rules: 6,
          selected_rules: 6,
          selected_rule_ids: [],
          rules_discarded: 0,
          method: 'whole_policy',
          sliced: false,
          rule_index_state: 'matched',
          rule_index_hits: 0,
        },
      },
      {
        provision_key: 'HW-9.2',
        heading_path: ['Hardware', 'Disposal'],
        retained: false,
        discard_reason: 'no_retrieval_match',
      },
    ],
    excluded: [],
  })
}

/** The rule index existed and its query failed recoverably. */
export function makeRuleIndexDegradedEnvelope(): CaseDecisionEnvelopeV2 {
  const base = makeRuleIndexMatchedEnvelope()
  return {
    ...base,
    retrieval: {
      ...base.retrieval,
      rule_index_state: 'degraded',
      rule_documents_matched: 0,
      policies_elevated_by_rule: 0,
    },
    considered: (base.considered ?? []).map((policy) =>
      policy.rule_selection
        ? {
            ...policy,
            rule_selection: {
              ...policy.rule_selection,
              method:
                policy.rule_selection.method === 'hybrid_rule_v1'
                  ? 'scenario_relevance_v3'
                  : policy.rule_selection.method,
              rule_index_state: 'degraded',
              rule_index_hits: null,
            },
          }
        : policy,
    ),
  }
}

/** The index reported no complete projection under the expected contract. */
export function makeProjectionNotReadyEnvelope(): CaseDecisionEnvelopeV2 {
  const base = makeRuleIndexMatchedEnvelope()
  return {
    ...base,
    retrieval: { ...base.retrieval, projection_ready: false },
  }
}
