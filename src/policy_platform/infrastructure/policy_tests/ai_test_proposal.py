"""AI-assisted `PolicyTest` proposal (Section 11.6 "Policy Test Proposal
Agent" / Section 21.6).

This service PROPOSES candidate `PolicyTest` definitions only — it never
executes one. It must never import or call `evaluate_policy` /
`evaluator.test_runner.run_policy_test`; only the deterministic engine ever
decides pass/fail (see `infrastructure/policy_tests/policy_test_execution.py`). This
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
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.contracts.evaluation import EvaluationStatus
from policy_platform.contracts.policy import CanonicalRule
from policy_platform.contracts.policy_test import PolicyTestKind
from policy_platform.domain.models import DocumentVersion
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.persistence.mappers import approved_policy_version_to_package
from policy_platform.infrastructure.persistence.repositories import ApprovedPolicyVersionRepository, PolicySetRepository
from policy_platform.infrastructure.search.search_client import AzureSearchClient
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

CRITICAL — read "evaluation_mode" on every rule before predicting anything about it. A policy is either \
"deterministic", meaning the source states its test as a comparison the engine can compute, or "ai_ready", \
meaning the source states it in words and a judge decides it by reading the record. The engine checks this \
FIRST and, for an ai_ready policy, returns NOT_APPLICABLE immediately without ever looking at its scope, \
its condition or its exceptions. It can NEVER return SATISFIED, NOT_SATISFIED or INDETERMINATE no matter \
how obviously true its condition text looks, and an empty condition like {"all": []} on such a policy is \
NOT a policy that always passes. For those the only correct expected_rule_status is "NOT_APPLICABLE". If \
every policy you were given is ai_ready, then every evaluation of this policy set returns \
overall_status=NOT_APPLICABLE, so do not propose "positive", "boundary" or "exception" tests expecting \
SATISFIED — propose the NOT_APPLICABLE expectations that are actually true.

Be precise about WHY when you describe such a test. ai_ready is a route, not a fault. It does NOT mean the \
policy is vague, incomplete, or unusable: most policy text states its test in words, and the same \
policy may state its subject, its threshold and its approver completely and be decided correctly by a \
judge reading it against a case. Each policy carries a "decision_readiness" object and an "attributes" \
table — read them, and describe the policy accordingly. Writing "this policy cannot be evaluated" as \
though it were a defect is wrong; say it is decided by reading instead.

If the user message contains a "reviewer_guidance" field, treat it as a priority steer from the policy \
reviewer: bias your coverage toward the areas, rules, or risks it names, and propose more tests there. It \
never overrides the rules you were given, the output contract below, or the requirement that expectations \
be correct predictions — if the guidance asks for something the rule set cannot support, cover what it \
can support instead of inventing rules.

Respond with a JSON object: {"tests": [ { "name": str, "scenario_text": str, "description": str, "test_kind": one of \
"positive"|"negative"|"boundary"|"missing_fact"|"scope"|"effective_date"|"exception"|"precedence", \
"input_facts": {fact_name: literal_value_or_null, ...}, "evaluation_timestamp": "YYYY-MM-DD" or null, \
"expected_overall_status": one of "SATISFIED"|"NOT_SATISFIED"|"NOT_APPLICABLE"|"INDETERMINATE"|"ERROR", \
"expected_rule_id": rule_id string or null, "expected_rule_status": same status enum or null (only set \
this if expected_rule_id is set), "expected_missing_facts": array of fact-name strings or null }, ... ]}. \
If nothing meaningful can be proposed, return {"tests": []}."""

_BLIND_BATCH_INSTRUCTIONS = """
This request is for a BLIND validation batch over an explicit reviewer-selected rule set.
- Return EXACTLY tests_per_policy scenarios for EACH selected rule, for exactly scenario_count scenarios in total.
- Every test must include a plain-English "scenario_text" that a reviewer can understand without reading JSON.
- Use neutral scenario names that do not reveal whether the case is positive, negative, boundary, or missing-fact.
- Every test must target one of the selected rule IDs with expected_rule_id and expected_rule_status.
- Vary each policy's combinations across match, non-match, boundary, missing-fact, scope, and exception cases where
  its actual JSON supports them. Do not duplicate the same fact combination under different prose.
- Expectations are committed before execution and hidden from the reviewer until the deterministic engine runs. Do not
  use vague expectations: predict the exact result based only on the supplied JSON and optional Search grounding.
- "json_only" means use only the complete selected rule JSON. "json_search" also includes hybrid Azure AI Search
  passages from the selected source documents. Search passages are supporting source context; rule JSON remains the
  executable contract.
"""

_USER_SCENARIO_INSTRUCTIONS = """
The request contains reviewer_authored_scenario. Preserve that scenario text verbatim. Produce exactly one test for
the single selected policy. Translate only facts explicitly stated or unambiguously implied by the reviewer, and
commit the exact expected outcome based on the supplied policy JSON and optional Search grounding.
"""


def _rule_summary(rule: CanonicalRule) -> dict:
    return {
        "rule_id": rule.rule_id,
        # The routing field, and the single most outcome-determining one in
        # this payload. The evaluator short-circuits an `ai_ready` policy before
        # scope, condition or exceptions are ever consulted, so a model that
        # reasons carefully about all of those and never sees this will
        # confidently predict SATISFIED where the engine can only ever return
        # NOT_APPLICABLE. It must never be omitted again.
        "evaluation_mode": rule.evaluation_mode.value,
        "machine_executable": rule.machine_executable,
        # Answers the question the mode does not: whether the source states
        # enough for the policy to be decided at all, and by whom. Without it a
        # model shown only the mode cannot tell a fully-stated policy from one
        # the document left vague, and writes the same dismissive description
        # for both.
        "decision_readiness": (
            rule.decision_readiness.model_dump(mode="json") if rule.decision_readiness else None
        ),
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
        "evidence": [e.model_dump(mode="json") for e in rule.evidence],
        "formulation": rule.formulation.model_dump(mode="json") if rule.formulation else None,
    }


def _parse_timestamp(value: object | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
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

    evaluation_timestamp = _parse_timestamp(raw.get("evaluation_timestamp"))
    # A timestamp override changes which published rule/version is in effect.
    # It is meaningful only when the test explicitly targets effective dates;
    # letting ordinary boundary/positive tests carry one made local timezone
    # conversion silently move a scenario before the rule's activation date.
    if test_kind != PolicyTestKind.EFFECTIVE_DATE.value:
        evaluation_timestamp = None

    return {
        "name": name,
        "scenario_text": str(raw.get("scenario_text") or raw.get("description") or name).strip(),
        "description": str(raw.get("description") or ""),
        "test_kind": test_kind,
        "input_facts_json": input_facts,
        "evaluation_timestamp_override": evaluation_timestamp,
        "expected_overall_status": expected_overall_status,
        "expected_rule_id": expected_rule_id,
        "expected_rule_status": expected_rule_status,
        "expected_missing_facts_json": expected_missing_facts,
    }, None


async def propose_policy_tests(
    session: AsyncSession,
    *,
    policy_set_key: str,
    reasoning_effort: str = "medium",
    guidance: str = "",
    rule_ids: list[str] | None = None,
    tests_per_policy: int | None = None,
    grounding_mode: str = "json_only",
    policy_version_id: str | None = None,
    user_scenario: str = "",
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
    version = (
        await version_repo.get_by_id(uuid.UUID(policy_version_id))
        if policy_version_id
        else await version_repo.get_active_version(policy_set.id)
    )
    if version is None or version.policy_set_id != policy_set.id:
        raise ValueError(f"policy set '{policy_set_key}' has no active approved version to propose tests against")

    package = approved_policy_version_to_package(version)
    if not package.rules:
        return {
            "policy_set_key": policy_set_key,
            "version_number": version.version_number,
            "reasoning_effort": reasoning_effort,
            "proposed_tests": [],
            "skipped": ["policy set has no rules in its active version; nothing to propose tests for"],
        }

    selected_rules = package.rules
    if rule_ids is not None:
        requested_ids = list(dict.fromkeys(rule_ids))
        rules_by_id = {rule.rule_id: rule for rule in package.rules}
        missing_ids = [rule_id for rule_id in requested_ids if rule_id not in rules_by_id]
        if missing_ids:
            raise ValueError(f"selected rules are not in published version v{version.version_number}: {missing_ids}")
        selected_rules = [rules_by_id[rule_id] for rule_id in requested_ids]
        definitions = [rule.rule_id for rule in selected_rules if rule.rule_type.value == "definition"]
        if definitions:
            raise ValueError("definition and glossary records state meanings rather than tests, so there is nothing to run against them: " + ", ".join(definitions))
        non_executable = [rule.rule_id for rule in selected_rules if not rule.machine_executable]
        if non_executable:
            raise ValueError(
                "blind validation runs against the deterministic engine; these selected rules are decided by reading, so the engine does not run them: "
                + ", ".join(non_executable)
            )

    if tests_per_policy is not None and not 1 <= tests_per_policy <= 10:
        raise ValueError("tests_per_policy must be between 1 and 10")
    if user_scenario.strip() and (len(selected_rules) != 1 or tests_per_policy != 1):
        raise ValueError("a user-authored scenario requires exactly one selected policy and one test")
    if grounding_mode not in ("json_only", "json_search"):
        raise ValueError("grounding_mode must be 'json_only' or 'json_search'")

    ai_client = AzureOpenAIClient(settings)
    grounding_context: dict = {
        "mode": grounding_mode,
        "search_index": None,
        "query": None,
        "hits": [],
    }
    if grounding_mode == "json_search":
        if not settings.search_enabled:
            raise RuntimeError("Azure AI Search is not configured; choose JSON-only grounding")
        evidence_version_ids = {
            uuid.UUID(evidence.document_version_id)
            for rule in selected_rules
            for evidence in rule.evidence
            if evidence.document_version_id
        }
        document_ids: list[str] = []
        if evidence_version_ids:
            result = await session.execute(
                select(DocumentVersion).where(DocumentVersion.id.in_(evidence_version_ids))
            )
            document_ids = sorted({str(version.document_id) for version in result.scalars().all()})
        query_text = guidance.strip() or " ".join(
            f"{rule.title}. {rule.description}" for rule in selected_rules
        )
        [query_vector] = await ai_client.embed([query_text])
        hits = await AzureSearchClient(settings).vector_search(
            settings.azure_search_authoring_index,
            query_text=query_text,
            vector=query_vector,
            policy_ids=document_ids or None,
            top=8,
        )
        grounding_context = {
            "mode": grounding_mode,
            "search_index": settings.azure_search_authoring_index,
            "query": query_text,
            "hits": [
                {
                    "id": hit.get("id"),
                    "document_id": hit.get("document_id"),
                    "clause_id": hit.get("clause_id"),
                    "clause_number": hit.get("clause_number"),
                    "section_heading": hit.get("section_heading"),
                    "heading": hit.get("heading"),
                    "score": hit.get("@search.score"),
                    "body": hit.get("body"),
                }
                for hit in hits
            ],
        }

    request_payload: dict = {
        "approved_rules": [_rule_summary(rule) for rule in selected_rules],
        "grounding_mode": grounding_mode,
    }
    if tests_per_policy is not None:
        request_payload["tests_per_policy"] = tests_per_policy
        request_payload["scenario_count"] = tests_per_policy * len(selected_rules)
    if grounding_context["hits"]:
        request_payload["hybrid_search_grounding"] = grounding_context
    if user_scenario.strip():
        request_payload["reviewer_authored_scenario"] = user_scenario.strip()
    steer = guidance.strip()
    if steer:
        request_payload["reviewer_guidance"] = steer
    user_content = json.dumps(request_payload, indent=2, default=str)

    # See openai_client.chat() docstring: gpt-5.6-sol is a reasoning model
    # and silently returns empty content if max_tokens is too small.
    raw = await ai_client.chat(
        [
            {
                "role": "system",
                "content": (
                    _SYSTEM_PROMPT
                    + (_BLIND_BATCH_INSTRUCTIONS if rule_ids is not None else "")
                    + (_USER_SCENARIO_INSTRUCTIONS if user_scenario.strip() else "")
                ),
            },
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

    valid_rule_ids = {rule.rule_id for rule in selected_rules}
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
            if user_scenario.strip():
                payload["scenario_text"] = user_scenario.strip()
            validated.append(payload)

    return {
        "policy_set_key": policy_set_key,
        "version_number": version.version_number,
        "reasoning_effort": reasoning_effort,
        "proposed_tests": validated,
        "skipped": skipped,
        "policy_version_id": str(version.id),
        "selected_rule_ids": [rule.rule_id for rule in selected_rules],
        "grounding_mode": grounding_mode,
        "grounding_context": grounding_context,
    }
