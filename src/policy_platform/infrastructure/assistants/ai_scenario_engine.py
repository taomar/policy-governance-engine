"""AI-assisted, deterministic-engine-backed "how would this rule be obeyed?"
scenario tester — the real-verdict counterpart to `ai_scenario_eval.py`.

`ai_scenario_eval.py` is deliberately, permanently advisory-only: it never
touches the evaluator, and its own docstring explains why (it exists to
sanity-check wording on an in-progress, possibly-unsaved draft rule that may
not even have a rule_id yet). This module is different and exists for a
different job: letting a reviewer ask, in plain English, how an already
*published* rule would actually be obeyed, and getting back the REAL verdict
from `evaluator.engine.evaluate_policy` — not a guess.

This follows the same "AI drafts, deterministic code decides" split used
throughout this codebase (see `ai_extraction.py`, `ai_test_proposal.py`). AI
is used ONLY for two narrow, clearly-bounded translation steps that never
decide a policy outcome:

1. `infer_scenario_facts` — translate a reviewer's plain-English scenario
   into structured facts, scoped to what the target rule's condition,
   required_facts, and scope actually reference. Conservative by design: a
   fact is only included if the scenario states or clearly implies it. This
   matters architecturally, not just stylistically — inventing a plausible
   -looking value for a fact the scenario never mentioned would silently
   defeat the evaluator's own "missing facts are not false" guarantee
   (Section 5.5/5.7) that the rest of this platform depends on for a
   trustworthy INDETERMINATE result.
2. `explain_rule_outcome` — explain, in plain language, a REAL result
   already produced by `evaluate_policy`. The prompt is explicitly told the
   verdict is already final and must not be contradicted or re-decided.

`run_rule_scenario` orchestrates both steps around a real, unmodified call to
`evaluate_policy` against the policy set's active approved version — full
precedence/scope/aggregate-limit logic runs exactly as it would for any real
caller, mirroring how `evaluator.test_runner.run_policy_test` evaluates for
real and only describes/compares the result afterwards.

Nothing here is persisted as an `Evaluation` audit row. This is a reviewer's
exploratory "what if" check during policy review, not a production system
integration call, so it deliberately does not appear in the append-only
evaluation audit trail alongside real calling-system evaluations. A reviewer
who wants to turn a scenario into a permanent, regression-tested case should
save it as a `PolicyTest` instead (see `ai_test_proposal.py`).
"""
from __future__ import annotations

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.contracts.evaluation import EvaluationRequest, RuleEvaluationResult
from policy_platform.contracts.policy import CanonicalRule
from policy_platform.evaluator.engine import evaluate_policy
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.persistence.mappers import approved_policy_version_to_package
from policy_platform.infrastructure.persistence.repositories import ApprovedPolicyVersionRepository, PolicySetRepository
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

PROMPT_VERSION = "ai-scenario-engine-v1"

VALID_REASONING_EFFORTS = ("low", "medium", "high")

_FACTS_SYSTEM_PROMPT = """You are a precise fact-extraction assistant supporting a deterministic policy \
evaluation engine. You are given one rule as JSON (condition, required_facts, scope) and a plain-English \
scenario. Your ONLY job is to translate the scenario into a flat dict of dotted fact keys -> literal \
values that the engine's condition/scope matching can consume directly.

Rules you must follow exactly:
- Only include a fact if the scenario states it or clearly, unambiguously implies it. If the scenario is \
silent or vague about a fact the condition/required_facts/scope need, LEAVE IT OUT of "facts" entirely — \
do not guess a plausible-sounding value. A missing fact will correctly surface as "cannot determine" to \
the reviewer; a guessed one would silently corrupt the real result.
- Use the exact same dotted key strings that appear in the rule's condition and required_facts (e.g. \
"employee.tenureYears", "amount"). Match each declared required_fact's data_type when choosing the JSON \
type for its value (string/number/boolean/date-as-"YYYY-MM-DD" string).
- Only include the reserved scope keys "subject.persona", "subject.organizationalUnit", \
"subject.jurisdiction", "context.process" if the rule's scope actually restricts that dimension (i.e. it \
is not empty/["*"]) AND the scenario gives you a value for it.
- Never invent a fact name that appears nowhere in the rule's condition, required_facts, or the four \
reserved scope keys above.

Return ONLY a JSON object: {"facts": {fact_name: literal_value, ...}, "assumptions": [str, ...]}. \
"assumptions" lists any interpretive judgment calls you made translating the prose into a literal value \
(e.g. "Interpreted 'contractor' as subject.persona = \\"contractor\\"") so a reviewer can double-check your \
translation step. Empty array if the mapping was unambiguous."""

_EXPLAIN_SYSTEM_PROMPT = """You are explaining a policy decision to a non-technical reviewer. You are given \
a rule, the plain-English scenario a reviewer asked about, the facts that were used, and the REAL, FINAL \
result already produced by a separate deterministic evaluation engine. That result is authoritative and \
already decided — your only job is to explain, in plain English, why the engine reached it, in 2-5 \
sentences. Reference the specific facts and how they compare against the rule's condition/scope. If \
missing_facts is non-empty, explain what additional information would be needed for a confident answer. \
If the rule was not in effect / not applicable at the time of evaluation, say so plainly.

Do not contradict the given result. Do not propose a different status or outcome. Do not hedge with \
"uncertain" language if the real result was a confident SATISFIED/NOT_SATISFIED — only describe genuine \
engine-reported uncertainty (INDETERMINATE / missing facts), never invent your own doubt about a decided \
result.

Return ONLY the explanation text, no JSON, no preamble."""


def _rule_context(rule: CanonicalRule) -> dict:
    mapping_statuses, formulation_requirements = _formulation_status(rule)
    return {
        "rule_id": rule.rule_id,
        "title": rule.title,
        "description": rule.description,
        "rule_type": rule.rule_type.value,
        "condition": rule.condition,
        "required_facts": [f.model_dump(mode="json") for f in rule.required_facts],
        "scope": rule.scope.model_dump(mode="json"),
        "effect": rule.effect.model_dump(mode="json"),
        "exceptions": [e.model_dump(mode="json") for e in rule.exceptions],
        "machine_executable": rule.machine_executable,
        "dmn_mapping_statuses": mapping_statuses,
        "formulation_requirements": formulation_requirements,
    }


def _formulation_status(rule: CanonicalRule) -> tuple[list[str], list[str]]:
    """Return the source-grounded DMN blockers carried on a formulated rule."""

    if rule.formulation is None:
        return [], []
    statuses = sorted({decision.dmn_mapping_status.value for decision in rule.formulation.dmn_decisions})
    requirements = sorted(
        {requirement.value for decision in rule.formulation.dmn_decisions for requirement in decision.requirements}
    )
    return statuses, requirements


async def infer_scenario_facts(rule: CanonicalRule, *, scenario: str, reasoning_effort: str = "medium") -> dict:
    """AI call #1: translate `scenario` into facts scoped to this rule's own
    condition/required_facts/scope. Returns {"facts": dict, "assumptions": list[str]}.
    Never touches the evaluator or persists anything."""

    settings = get_settings()
    if not settings.ai_enabled:
        raise RuntimeError("Azure OpenAI is not configured")

    ai_client = AzureOpenAIClient(settings)
    user_content = json.dumps({"rule": _rule_context(rule), "scenario": scenario}, indent=2, default=str)
    raw = await ai_client.chat(
        [
            {"role": "system", "content": _FACTS_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        deployment=settings.azure_openai_deployment,
        json_mode=True,
        max_tokens=4000,
        timeout=180.0,
        reasoning_effort=reasoning_effort,
    )
    parsed = json.loads(raw)
    facts = parsed.get("facts")
    if not isinstance(facts, dict):
        facts = {}
    assumptions = parsed.get("assumptions")
    if not isinstance(assumptions, list):
        assumptions = []
    return {"facts": facts, "assumptions": [str(a) for a in assumptions]}


def find_rule_result(rule_id: str, rule_results: list[RuleEvaluationResult]) -> RuleEvaluationResult | None:
    """Pure lookup, no AI/DB involved — split out so it's directly unit
    -testable without mocking the AI client."""
    return next((r for r in rule_results if r.rule_id == rule_id), None)


async def explain_rule_outcome(
    rule: CanonicalRule,
    *,
    scenario: str,
    facts: dict,
    result: RuleEvaluationResult | None,
    reasoning_effort: str = "medium",
) -> str:
    """AI call #2: explain a REAL, already-decided result (or the fact that
    the rule wasn't currently in effect/applicable) in plain language. The
    passed-in result is authoritative and must not be second-guessed."""

    settings = get_settings()
    if not settings.ai_enabled:
        raise RuntimeError("Azure OpenAI is not configured")

    ai_client = AzureOpenAIClient(settings)
    user_content = json.dumps(
        {
            "rule_title": rule.title,
            "scenario": scenario,
            "facts_used": facts,
            "real_evaluation_result": result.model_dump(mode="json") if result else None,
            "rule_was_applicable": result is not None,
        },
        indent=2,
        default=str,
    )
    raw = await ai_client.chat(
        [
            {"role": "system", "content": _EXPLAIN_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        deployment=settings.azure_openai_deployment,
        max_tokens=2000,
        timeout=180.0,
        reasoning_effort=reasoning_effort,
    )
    return raw.strip()


def explain_decided_by_reading(
    *,
    rule: CanonicalRule,
    package,
    scenario: str,
    reasoning_effort: str,
    mapping_statuses: list[str],
    formulation_requirements: list[str],
) -> dict:
    """The answer for a policy the deterministic engine will not evaluate.

    Pure, and separate from `run_rule_scenario`, because being buried inside a
    database-coupled function is why it had no test. It covers 53 of the 55
    records in the live corpus — nearly every policy a user would try — and it
    broke silently when `DecisionReadiness.reason` was removed: this branch read
    that field, so scenario-testing any of them raised. Nothing in the suite
    exercised it, so nothing failed.

    No AI call is made. The engine's answer is known before it runs, and
    spending two model calls to arrive at it would be waste on top of a
    foregone conclusion.
    """

    request = EvaluationRequest(
        policy_set_id=package.policy_set_id,
        policy_version_id=package.policy_version_id,
        use_active_version=False,
        facts={},
        correlation_id=None,
        calling_system_identity=f"ai-scenario-test:{rule.rule_id}",
    )
    response = evaluate_policy(package, request)
    rule_result = find_rule_result(rule.rule_id, response.rule_results)

    # Says what is true of the policy, in the vocabulary the record uses.
    #
    # Three earlier wordings were wrong in the same direction. One called the
    # policy "documentation-only", which a reader takes as a verdict on it. One
    # reported the DMN mapping status and the enrichment codes it "requires" —
    # a standing request for configuration, on a policy that states its test in
    # words and will never become a comparison. Both read as a defect where
    # there is a route.
    readiness = rule.decision_readiness
    readiness_note = ""
    if readiness is not None:
        readiness_note = f" Read against its own source, this policy is '{readiness.evaluability}'."

    return {
        "rule_id": rule.rule_id,
        "rule_title": rule.title,
        "scenario": scenario,
        "inferred_facts": {},
        "assumptions": [],
        "rule_result": rule_result.model_dump(mode="json") if rule_result else None,
        "not_in_effect": False,
        "overall_evaluation_status": response.overall_status.value,
        "missing_facts": [],
        "explanation": (
            "The source states this policy's test in words rather than as a comparison "
            "between named quantities, so it is served as ai_ready and decided by a "
            "judge reading the record — the sentence, the facts it names, and the outcome it "
            "states. The deterministic engine returns NOT_APPLICABLE before reading scenario "
            f"facts, which is the correct answer for it to give.{readiness_note}"
        ),
        "reasoning_effort": reasoning_effort,
        "evaluation_timestamp": response.evaluation_timestamp.isoformat(),
        "result_hash": response.result_hash,
        "machine_executable": False,
        "testability_reason": "decided_by_reading",
        "dmn_mapping_statuses": mapping_statuses,
        "formulation_requirements": formulation_requirements,
    }


async def run_rule_scenario(
    session: AsyncSession,
    *,
    policy_set_key: str,
    rule_id: str,
    scenario: str,
    reasoning_effort: str = "medium",
) -> dict:
    """Full "test this rule with a natural-language scenario" flow: AI infers
    facts -> the REAL `evaluate_policy()` decides -> AI explains the real
    result. Raises ValueError for a 404-worthy lookup problem, RuntimeError
    if AI isn't configured."""

    if reasoning_effort not in VALID_REASONING_EFFORTS:
        reasoning_effort = "medium"

    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(policy_set_key)
    if policy_set is None:
        raise ValueError(f"policy set '{policy_set_key}' not found")

    version_repo = ApprovedPolicyVersionRepository(session)
    active = await version_repo.get_active_version(policy_set.id)
    if active is None:
        raise ValueError(f"policy set '{policy_set_key}' has no active approved version to test against")

    package = approved_policy_version_to_package(active)
    rule = next((r for r in package.rules if r.rule_id == rule_id), None)
    if rule is None:
        raise ValueError(f"rule '{rule_id}' not found in the active approved version of '{policy_set_key}'")

    mapping_statuses, formulation_requirements = _formulation_status(rule)

    # A policy decided by reading is deliberately skipped by the evaluator
    # before it reads facts. Do not spend two AI calls translating a scenario
    # the deterministic engine is contractually unable to evaluate, and do not
    # let an explainer guess that the scenario merely omitted facts.
    if not rule.machine_executable:
        return explain_decided_by_reading(
            rule=rule,
            package=package,
            scenario=scenario,
            reasoning_effort=reasoning_effort,
            mapping_statuses=mapping_statuses,
            formulation_requirements=formulation_requirements,
        )

    settings = get_settings()
    if not settings.ai_enabled:
        raise RuntimeError("Azure OpenAI is not configured")

    inferred = await infer_scenario_facts(rule, scenario=scenario, reasoning_effort=reasoning_effort)

    # Mirrors evaluator.test_runner.run_policy_test's own request shape: this
    # calls evaluate_policy() directly, in-process, so policy_set_id only
    # needs to match package.policy_set_id (used solely for the response's
    # own hash/echo fields) — no HTTP round trip through the /api/evaluations
    # router, and nothing about this request is persisted as an audit row.
    request = EvaluationRequest(
        policy_set_id=package.policy_set_id,
        policy_version_id=package.policy_version_id,
        use_active_version=False,
        facts=inferred["facts"],
        correlation_id=None,
        calling_system_identity=f"ai-scenario-test:{rule_id}",
    )
    response = evaluate_policy(package, request)
    rule_result = find_rule_result(rule_id, response.rule_results)
    not_in_effect = rule_result is None and rule_id not in response.applicable_rules

    explanation = await explain_rule_outcome(
        rule,
        scenario=scenario,
        facts=inferred["facts"],
        result=rule_result,
        reasoning_effort=reasoning_effort,
    )

    return {
        "rule_id": rule_id,
        "rule_title": rule.title,
        "scenario": scenario,
        "inferred_facts": inferred["facts"],
        "assumptions": inferred["assumptions"],
        "rule_result": rule_result.model_dump(mode="json") if rule_result else None,
        "not_in_effect": not_in_effect,
        "overall_evaluation_status": response.overall_status.value,
        "missing_facts": rule_result.missing_facts if rule_result else [],
        "explanation": explanation,
        "reasoning_effort": reasoning_effort,
        "evaluation_timestamp": response.evaluation_timestamp.isoformat(),
        "result_hash": response.result_hash,
        "machine_executable": True,
        "testability_reason": None,
        "dmn_mapping_statuses": mapping_statuses,
        "formulation_requirements": formulation_requirements,
    }
