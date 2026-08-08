"""AI-assisted `PolicyTest` proposal (Section 11.6 "Policy Test Proposal
Agent" / Section 21.6).

This service PROPOSES candidate `PolicyTest` definitions only — it never
executes one. It must never import or call `evaluate_policy` /
`evaluator.test_runner.run_policy_test`; only the deterministic engine ever
decides pass/fail (see `infrastructure/policy_test_execution.py`). This
mirrors `ai_extraction.py`'s "AI drafts, deterministic code / human review
decides" philosophy and `ai_scenario_eval.py`'s "advisory only" framing.

Proposed tests come back from this module as plain validated dicts shaped
for `PolicyTestRepository.create(...)`; the router persists them with
`proposed_by="ai"`, `review_status="pending_review"`, `is_active=False` so
they cannot affect the on-publish auto-rerun or the Findings/Quality view
until a human explicitly accepts them (an AI can mis-predict an expected
status, and a wrong-but-active test would generate misleading "failing
test" noise).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.contracts.evaluation import EvaluationStatus
from policy_platform.contracts.policy import CanonicalRule
from policy_platform.contracts.policy_test import PolicyTestKind
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.mappers import approved_policy_version_to_package
from policy_platform.infrastructure.repositories import ApprovedPolicyVersionRepository, PolicySetRepository
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

PROMPT_VERSION = "ai-test-proposal-v2"

VALID_REASONING_EFFORTS = ("low", "medium", "high")
_VALID_TEST_KINDS = {k.value for k in PolicyTestKind}
_VALID_STATUSES = {s.value for s in EvaluationStatus}

_SYSTEM_PROMPT = """You are a QA analyst for a deterministic policy evaluation engine. You are given \
the full list of currently-approved rules for one policy set (rule_id, title, description, condition, \
required_facts, scope, effect, exceptions, effective dates, priority). Propose a set of NAMED, SAVED \
test cases that exercise this rule set thoroughly. These tests will be executed later by a real \
deterministic evaluator (never by you) and their results compared against the expectations you specify \
here — so your expectations must be genuinely correct predictions of how the rules would evaluate, not \
guesses.

Propose tests covering these kinds (include several of each where the rule set gives you enough to work \
with; it is fine to omit a kind if nothing in the rules justifies it):
- "positive": input facts that clearly satisfy a rule's condition and scope -> expect SATISFIED.
- "negative": input facts that clearly do NOT satisfy a rule's condition -> expect NOT_SATISFIED.
- "boundary": input facts sitting exactly at a numeric/date threshold used in a condition (e.g. exactly \
at a limit value) -> reason carefully about which side of the boundary the operator (e.g. \
greaterThanOrEqual vs greaterThan) puts the boundary value on.
- "missing_fact": deliberately OMIT a fact the condition needs -> expect INDETERMINATE, with \
expected_missing_facts naming the omitted fact(s).
- "scope": input facts whose principal/context attributes (jurisdiction, organizationalUnit, persona, \
process — supplied as facts like "subject.persona") fall OUTSIDE a rule's non-wildcard scope dimension \
-> expect NOT_APPLICABLE for that rule.
- "effective_date": set evaluation_timestamp before a rule's effective_from (or after its effective_to \
if set) -> expect NOT_APPLICABLE for that rule; or on/after effective_from -> expect it to apply.
- "exception": input facts that trigger one of a rule's exceptions -> reason about what that does to \
the rule's outcome given the exception's own condition.
- "precedence": only if two or more rules can genuinely conflict (same action, opposite effect, or an \
explicit override/supersession) — facts that trigger the conflict, expecting the higher-precedence \
rule's outcome to win.

Facts you invent for input_facts must use the same dotted key convention shown in the rules' conditions \
and required_facts (e.g. "employee.tenureYears", "subject.persona"). Only ever reference rule_id values \
that were given to you.

CRITICAL — read "machine_executable" on every rule before predicting anything about it. The engine checks \
that flag FIRST and, when it is false, returns NOT_APPLICABLE for that rule immediately without ever \
looking at its scope, its condition or its exceptions. A rule with machine_executable=false is documented \
prose that has not been reduced to executable logic; it can NEVER return SATISFIED, NOT_SATISFIED or \
INDETERMINATE no matter how obviously true its condition text looks, and an empty condition like \
{"all": []} on such a rule is NOT a rule that always passes. For those rules the only correct \
expected_rule_status is "NOT_APPLICABLE". If every rule you were given has machine_executable=false, then \
every evaluation of this policy set returns overall_status=NOT_APPLICABLE, so do not propose "positive", \
"boundary" or "exception" tests expecting SATISFIED — propose the NOT_APPLICABLE expectations that are \
actually true, and say plainly in each description that the rule is not machine-executable yet.

If the user message contains a "reviewer_guidance" field, treat it as a priority steer from the policy \
reviewer: bias your coverage toward the areas, rules, or risks it names, and propose more tests there. It \
never overrides the rules you were given, the output contract below, or the requirement that expectations \
be correct predictions — if the guidance asks for something the rule set cannot support, cover what it \
can support instead of inventing rules.

Respond with a JSON object: {"tests": [ { "name": str, "description": str, "test_kind": one of \
"positive"|"negative"|"boundary"|"missing_fact"|"scope"|"effective_date"|"exception"|"precedence", \
"input_facts": {fact_name: literal_value_or_null, ...}, "evaluation_timestamp": "YYYY-MM-DD" or null, \
"expected_overall_status": one of "SATISFIED"|"NOT_SATISFIED"|"NOT_APPLICABLE"|"INDETERMINATE"|"ERROR", \
"expected_rule_id": rule_id string or null, "expected_rule_status": same status enum or null (only set \
this if expected_rule_id is set), "expected_missing_facts": array of fact-name strings or null }, ... ]}. \
If nothing meaningful can be proposed, return {"tests": []}."""


def _rule_summary(rule: CanonicalRule) -> dict:
    return {
        "rule_id": rule.rule_id,
        # `machine_executable` short-circuits `_evaluate_rule` before scope,
        # condition or exceptions are ever consulted, so a model that reasons
        # carefully about all of those and never sees this flag will confidently
        # predict SATISFIED for a rule the engine can only ever return
        # NOT_APPLICABLE for. It is the single most outcome-determining field in
        # this payload and must never be omitted from it again.
        "machine_executable": rule.machine_executable,
        "title": rule.title,
        "description": rule.description,
        "rule_type": rule.rule_type.value,
        "condition": rule.condition,
        "required_facts": [f.model_dump(mode="json") for f in rule.required_facts],
        "scope": rule.scope.model_dump(mode="json"),
        "effect": rule.effect.model_dump(mode="json"),
        "exceptions": [e.model_dump(mode="json") for e in rule.exceptions],
        "priority": rule.priority,
        "is_explicit_override": rule.is_explicit_override,
        "supersedes_rule_ids": rule.supersedes_rule_ids,
        "effective_from": str(rule.effective_from),
        "effective_to": str(rule.effective_to) if rule.effective_to else None,
    }


def _parse_timestamp(value: object | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None


def _validate_proposed_test(raw: dict, valid_rule_ids: set[str]) -> tuple[dict | None, str | None]:
    """Return (validated_payload, None) or (None, skip_reason). Never raises —
    a malformed proposal is skipped, not fatal to the rest of the batch."""

    name = str(raw.get("name") or "").strip()
    if not name:
        return None, "missing 'name'"

    test_kind = str(raw.get("test_kind") or "").strip()
    if test_kind not in _VALID_TEST_KINDS:
        return None, f"test '{name}': invalid test_kind '{test_kind}'"

    expected_overall_status = str(raw.get("expected_overall_status") or "").strip()
    if expected_overall_status not in _VALID_STATUSES:
        return None, f"test '{name}': invalid expected_overall_status '{expected_overall_status}'"

    input_facts = raw.get("input_facts")
    if not isinstance(input_facts, dict):
        input_facts = {}

    expected_rule_id = raw.get("expected_rule_id") or None
    if expected_rule_id is not None and expected_rule_id not in valid_rule_ids:
        # Soft validation: keep the test but drop the dangling reference —
        # `run_policy_test` already handles an unknown expected_rule_id as a
        # clean FAIL, but not silently ignoring the mismatch here would let a
        # hallucinated rule_id block every future run of an otherwise-useful
        # test.
        logger.warning("AI test proposal: test '%s' referenced unknown rule_id '%s'; clearing it", name, expected_rule_id)
        expected_rule_id = None

    expected_rule_status = raw.get("expected_rule_status") or None
    if expected_rule_status is not None and expected_rule_status not in _VALID_STATUSES:
        expected_rule_status = None
    if expected_rule_id is None:
        expected_rule_status = None

    expected_missing_facts = raw.get("expected_missing_facts")
    if not isinstance(expected_missing_facts, list):
        expected_missing_facts = None
    else:
        expected_missing_facts = [str(f) for f in expected_missing_facts]

    return {
        "name": name,
        "description": str(raw.get("description") or ""),
        "test_kind": test_kind,
        "input_facts_json": input_facts,
        "evaluation_timestamp_override": _parse_timestamp(raw.get("evaluation_timestamp")),
        "expected_overall_status": expected_overall_status,
        "expected_rule_id": expected_rule_id,
        "expected_rule_status": expected_rule_status,
        "expected_missing_facts_json": expected_missing_facts,
    }, None


async def propose_policy_tests(
    session: AsyncSession, *, policy_set_key: str, reasoning_effort: str = "medium", guidance: str = ""
) -> dict:
    """Ask Azure OpenAI to propose `PolicyTest` candidates for the policy
    set's currently active approved version. Returns validated payloads
    ready for `PolicyTestRepository.create(...)` (still to be persisted by
    the caller with proposed_by="ai" and pending-review status), plus a
    list of any proposals that were skipped and why.

    `guidance` is an optional plain-English steer from the reviewer ("focus on
    overtime thresholds", "we care most about termination cases"). It is passed
    as *user* content rather than folded into the system prompt, so it can bias
    which scenarios are chosen but cannot silently redefine the output contract
    or the validation rules applied to each proposal below. Every proposal is
    still validated against the real rule ids and enum values regardless of what
    the guidance asked for.
    """

    settings = get_settings()
    if not settings.ai_enabled:
        raise RuntimeError("Azure OpenAI is not configured")
    if reasoning_effort not in VALID_REASONING_EFFORTS:
        reasoning_effort = "medium"

    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(policy_set_key)
    if policy_set is None:
        raise ValueError(f"policy set '{policy_set_key}' not found")

    version_repo = ApprovedPolicyVersionRepository(session)
    active = await version_repo.get_active_version(policy_set.id)
    if active is None:
        raise ValueError(f"policy set '{policy_set_key}' has no active approved version to propose tests against")

    package = approved_policy_version_to_package(active)
    if not package.rules:
        return {
            "policy_set_key": policy_set_key,
            "version_number": active.version_number,
            "reasoning_effort": reasoning_effort,
            "proposed_tests": [],
            "skipped": ["policy set has no rules in its active version; nothing to propose tests for"],
        }

    ai_client = AzureOpenAIClient(settings)
    request_payload: dict = {"approved_rules": [_rule_summary(r) for r in package.rules]}
    steer = guidance.strip()
    if steer:
        request_payload["reviewer_guidance"] = steer
    user_content = json.dumps(request_payload, indent=2, default=str)

    # See openai_client.chat() docstring: gpt-5.6-sol is a reasoning model
    # and silently returns empty content if max_tokens is too small.
    raw = await ai_client.chat(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        deployment=settings.azure_openai_deployment,
        json_mode=True,
        max_tokens=12000,
        timeout=180.0,
        reasoning_effort=reasoning_effort,
    )
    parsed = json.loads(raw)
    proposals = parsed.get("tests") or []
    if not isinstance(proposals, list):
        raise RuntimeError("AI test proposal response did not contain a 'tests' array")

    valid_rule_ids = {r.rule_id for r in package.rules}
    validated: list[dict] = []
    skipped: list[str] = []
    for raw_test in proposals:
        if not isinstance(raw_test, dict):
            skipped.append("proposal was not a JSON object")
            continue
        payload, skip_reason = _validate_proposed_test(raw_test, valid_rule_ids)
        if payload is None:
            skipped.append(skip_reason or "invalid proposal")
        else:
            validated.append(payload)

    return {
        "policy_set_key": policy_set_key,
        "version_number": active.version_number,
        "reasoning_effort": reasoning_effort,
        "proposed_tests": validated,
        "skipped": skipped,
    }
