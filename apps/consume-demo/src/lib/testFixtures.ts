import type { CaseDecisionEnvelope, DecisionStatus } from '../contracts/caseDecision'

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
