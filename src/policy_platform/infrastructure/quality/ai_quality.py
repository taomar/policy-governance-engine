"""Policy quality evaluation: deterministic structural checks + an AI
qualitative review layered on top, clearly labeled by provenance.

This is the "are these policies actually any good?" feature. Findings are
tagged `source: "deterministic"` (always exact — computed by inspecting the
persisted rule set with plain code, no LLM involved) or `source: "ai_review"`
(the model's judgment about gaps/redundancy/ambiguous wording — genuinely
useful, but not infallible, and never silently presented as fact).
"""
from __future__ import annotations

import collections
import json
import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.contracts.policy import (
    CanonicalRule,
    EvaluationMode,
    unanswered_for_judge,
    unrunnable_reasons,
)
from policy_platform.domain.models import QualityRun
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.extraction.decision_families import (
    FamilyMember,
    decision_families,
    promoted_qualifiers,
)
from policy_platform.infrastructure.extraction.evaluability import dangling_referents
from policy_platform.infrastructure.extraction.formulation_mapping import _is_separator_predicate
from policy_platform.infrastructure.quality.logic_faithfulness import (
    LogicFinding,
    LogicFindingSeverity,
    MismatchShape,
    judge_logic,
)
from policy_platform.infrastructure.persistence.mappers import approved_policy_version_to_package
from policy_platform.infrastructure.persistence.repositories import (
    ApprovedPolicyVersionRepository,
    CandidateRuleRepository,
    PolicySetRepository,
    QualityRunRepository,
)
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

QUALITY_METHODOLOGY_VERSION = "2"

#: Fixed so repeated reviews of an unchanged rule set ask the service for the
#: same sampling every time. Measured, and it does not work: six live reviews of
#: one unchanged 3-rule set returned 5, 3, 3, 5, 4 and 5 findings, and the two
#: unseeded runs agreed with each other more closely than either seeded pair
#: did. The seed is kept because it is the only control this deployment accepts
#: and costs nothing, not because it makes a run reproducible. Nothing in this
#: module may assume two runs are comparable -- see `_run_ai_review`.
_AI_REVIEW_SEED = 20250101

_AI_REVIEW_SYSTEM_PROMPT = """You are a senior policy analyst reviewing a versioned package of formalized \
governance rules. Deterministic structural findings are supplied separately. Identify only ADDITIONAL \
qualitative issues that require human judgment: reachable decision gaps, overlapping rules with competing \
outcomes and no precedence, material ambiguity, missing exception handling, unsafe governance boundaries, \
or consequential redundancy.

Accuracy rules:
1. Treat every issue as a POTENTIAL quality finding requiring human confirmation, not as a proven defect.
2. For a conflict, name the concrete input/state in which the affected rules can both apply, the outcome \
each rule directs, and why scope, effective dates, priority, explicit overrides, or supersession do not \
already resolve it.
3. For a gap, name the exact reachable boundary or workflow state left without an outcome and the adjacent \
rules that create the boundary.
4. Do not report a conflict when scopes or effective windows do not overlap, or when explicit precedence \
already identifies the controlling rule.
5. Do not infer laws, controls, or business requirements that are absent from the supplied policy package. \
You may report them as risks to confirm, never as violated requirements.
6. Do not repeat deterministic findings. Do not fabricate or alter rule IDs.
7. Explain the evaluator or operational failure mode, what would make the current state acceptable, what \
would make it unacceptable, and the specific questions a reviewer must answer.

Respond with one JSON object:
{"findings": [{
  "severity": "high"|"medium"|"low",
  "category": "snake_case",
  "summary": "one plain-language sentence",
  "finding": "specific evidence-based explanation naming the interaction and concrete boundary/state",
  "why_it_matters": "the evaluator, control, audit, or user consequence if confirmed",
  "acceptable_when": "the factual condition under which no policy change is required",
  "unacceptable_when": "the factual condition under which remediation is required",
  "review_questions": ["specific decision question", "..."],
  "affected_rule_ids": ["only IDs supplied in the input"],
  "recommendation": "smallest policy correction that closes the issue"
}]}

If there is no additional evidence-based issue, return {"findings": []}."""


def _quality_rule_context(rule: CanonicalRule) -> dict:
    """Decision-grade, bounded context for the qualitative review.

    Sending only title/description/condition made the model blind to the exact
    precedence and lifecycle fields it was expected to reason about. This keeps
    the payload bounded while including every field that can prove or disprove an
    overlap, gap, or exception claim.
    """
    formulation = getattr(rule, "formulation", None)
    canonical = getattr(formulation, "canonical", None)
    return {
        "rule_id": rule.rule_id,
        "title": rule.title,
        "description": rule.description,
        "source_text": getattr(canonical, "source_text", "") if canonical else "",
        "rule_type": rule.rule_type.value,
        "effect": rule.effect.model_dump(mode="json"),
        "condition": rule.condition.model_dump(mode="json"),
        "scope": rule.scope.model_dump(mode="json"),
        "exceptions": [item.model_dump(mode="json") for item in rule.exceptions],
        "required_facts": [item.model_dump(mode="json") for item in rule.required_facts],
        "priority": rule.priority,
        "effective_from": rule.effective_from.isoformat(),
        "effective_to": rule.effective_to.isoformat() if rule.effective_to else None,
        "machine_executable": rule.machine_executable,
        "ambiguity_status": rule.ambiguity_status.value,
        "is_explicit_override": rule.is_explicit_override,
        "supersedes_rule_ids": list(rule.supersedes_rule_ids),
        "related_rule_ids": list(rule.related_rule_ids),
    }


def _normalize_ai_finding(raw: object, valid_rule_ids: set[str]) -> dict | None:
    """Validate one model finding before it becomes immutable quality evidence."""
    if not isinstance(raw, dict):
        return None

    severity = raw.get("severity")
    if severity not in {"high", "medium", "low"}:
        return None

    finding = str(raw.get("finding") or "").strip()
    if not finding:
        return None

    raw_references = raw.get("affected_rule_ids")
    if raw_references is not None and not isinstance(raw_references, list):
        logger.warning("Discarding AI quality finding with malformed rule references: %r", raw_references)
        return None
    references = raw_references if isinstance(raw_references, list) else []
    requested_ids = [str(value).strip() for value in references if str(value).strip()]
    unsupported_ids = [rule_id for rule_id in requested_ids if rule_id not in valid_rule_ids]
    if unsupported_ids:
        logger.warning("Discarding AI quality finding with unsupported rule references: %s", requested_ids)
        return None
    affected_rule_ids = list(dict.fromkeys(requested_ids))

    summary = str(raw.get("summary") or "").strip()
    if not summary:
        summary = finding.split(".", 1)[0].strip()

    review_questions = raw.get("review_questions")
    questions = (
        [str(value).strip() for value in review_questions if str(value).strip()][:6]
        if isinstance(review_questions, list)
        else []
    )

    return {
        "severity": severity,
        "category": str(raw.get("category") or "qualitative_risk").strip() or "qualitative_risk",
        "summary": summary[:500],
        "finding": finding[:4000],
        "why_it_matters": str(raw.get("why_it_matters") or "").strip()[:2000],
        "acceptable_when": str(raw.get("acceptable_when") or "").strip()[:2000],
        "unacceptable_when": str(raw.get("unacceptable_when") or "").strip()[:2000],
        "review_questions": questions,
        "affected_rule_ids": affected_rule_ids,
        "recommendation": str(raw.get("recommendation") or "").strip()[:3000],
        "analysis_status": "requires_human_confirmation",
        "source": "ai_review",
    }


def _mark_deterministic_findings(findings: list[dict]) -> None:
    for finding in findings:
        if finding.get("source") == "deterministic":
            finding.setdefault("analysis_status", "confirmed")


def _deterministic_findings(rules: list[CanonicalRule]) -> list[dict]:
    findings: list[dict] = []

    seen_ids: dict[str, int] = {}
    for r in rules:
        seen_ids[r.rule_id] = seen_ids.get(r.rule_id, 0) + 1
    for rid, count in seen_ids.items():
        if count > 1:
            findings.append(
                {
                    "severity": "high",
                    "category": "duplicate_rule_id",
                    "finding": f"rule_id '{rid}' appears {count} times in the same approved version",
                    "affected_rule_ids": [rid],
                    "recommendation": "Ensure every rule_id is unique within a policy version.",
                    "source": "deterministic",
                }
            )

    for r in rules:
        if r.ambiguity_status.value == "blocking":
            findings.append(
                {
                    "severity": "high",
                    "category": "ambiguity",
                    "finding": f"Rule '{r.title}' ({r.rule_id}) has ambiguity_status=blocking",
                    "affected_rule_ids": [r.rule_id],
                    "recommendation": "Have a human reviewer formalize this rule's condition/wording before relying on it in automated evaluation.",
                    "source": "deterministic",
                }
            )
        if r.effective_to is not None and r.effective_to < date.today():
            findings.append(
                {
                    "severity": "medium",
                    "category": "expired_rule",
                    "finding": f"Rule '{r.title}' ({r.rule_id}) has effective_to={r.effective_to} in the past but is still in the active version",
                    "affected_rule_ids": [r.rule_id],
                    "recommendation": "Remove or update this rule's effective_to, or supersede it in a new version.",
                    "source": "deterministic",
                }
            )
        fact_names = {f.name for f in r.required_facts}
        for exc in r.exceptions:
            if exc.condition is not None and hasattr(exc.condition, "fact"):
                if exc.condition.fact not in fact_names:
                    findings.append(
                        {
                            "severity": "low",
                            "category": "orphan_exception_fact",
                            "finding": (
                                f"Exception '{exc.exception_id}' on rule '{r.rule_id}' references fact "
                                f"'{exc.condition.fact}' which is not declared in required_facts"
                            ),
                            "affected_rule_ids": [r.rule_id],
                            "recommendation": "Add the fact to required_facts so callers know to supply it.",
                            "source": "deterministic",
                        }
                    )

    # Conflicting-effect heuristic: same rule_type + same effect.action but opposite allow/deny.
    by_type_action: dict[tuple[str, str], list[CanonicalRule]] = {}
    for r in rules:
        by_type_action.setdefault((r.rule_type.value, r.effect.action), []).append(r)
    for (rtype, action), group in by_type_action.items():
        effects = {r.effect.type.value for r in group}
        if {"allow", "deny"} <= effects:
            findings.append(
                {
                    "severity": "high",
                    "category": "conflicting_effect",
                    "finding": (
                        f"Multiple rules of type '{rtype}' target the same action '{action}' but disagree "
                        f"(some allow, some deny): {[r.rule_id for r in group]}"
                    ),
                    "affected_rule_ids": [r.rule_id for r in group],
                    "recommendation": "Review scope/condition/priority to confirm these are meant to coexist, or consolidate them.",
                    "source": "deterministic",
                }
            )

    findings.extend(_non_blocking_ambiguity_findings(rules))
    findings.extend(_definition_effect_findings(rules))
    findings.extend(_degenerate_predicate_findings(rules))
    findings.extend(_eligibility_polarity_findings(rules))
    # Checks on the extraction itself: one sentence read twice, read two ways,
    # or read differently by two runs. A finding here points upstream — nothing
    # downstream can repair a policy that was extracted wrong.
    findings.extend(_duplicate_extraction_findings(rules))
    findings.extend(_contradictory_reading_findings(rules))
    findings.extend(_unstable_extraction_findings(rules))
    # And whether each record can be decided the way it says it can.
    findings.extend(_runner_fitness_findings(rules))
    # Whether the slice the extractor took can be read on its own, and whether
    # it is a whole decision. Both are defects in the cut, not in the document.
    findings.extend(_self_containment_findings(rules))
    findings.extend(_split_decision_findings(rules))
    findings.extend(_promoted_qualifier_findings(rules))
    # And whether the logic formed from each sentence still quotes it.
    findings.extend(_logic_faithfulness_findings(rules))

    return findings


#: How a logic-faithfulness verdict ranks among the findings a reviewer sees.
#: `reextraction` sits below a fabricated claim and above a note, because it is
#: serious but nobody reading the record can act on it — the document has to be
#: read again.
_LOGIC_SEVERITY: dict[LogicFindingSeverity, str] = {
    LogicFindingSeverity.BLOCKING: "high",
    LogicFindingSeverity.REEXTRACTION: "medium",
    LogicFindingSeverity.REVIEW: "low",
}

#: What to do about each, keyed to what actually went wrong rather than to how
#: it ranks. Severity says who can act; this says what the action is, and the
#: two are not the same axis — a damaged decomposition and a fabricated phrase
#: are both serious, but only one of them can be answered by editing wording.
#: Every one of these is a defect in how the document was *read* — never in the
#: policy, and never in a record being decided by reading, which is a route and
#: not a shortfall.
_LOGIC_RECOMMENDATION_BY_SHAPE: dict[MismatchShape, str] = {
    MismatchShape.UNSUPPORTED: (
        "Compare this phrase against the quoted sentence. If the document does not "
        "say it, correct the record's wording or reject it."
    ),
    MismatchShape.CONCATENATED: (
        "Re-extract this record's source. Its structure was flattened when the "
        "document was read, and editing the wording cannot separate values the "
        "record no longer holds apart."
    ),
    MismatchShape.INVERTED: (
        "Check this phrase against the sentence's negation. The record may state "
        "the opposite of what the document says."
    ),
    MismatchShape.SUPPLIED: (
        "Confirm the document supports this phrase somewhere, such as a governing "
        "clause or heading it was formulated under."
    ),
}

#: For findings that are not a quotation mismatch and so carry no shape.
_LOGIC_RECOMMENDATION_BY_CODE: dict[str, str] = {
    "decomposition_malformed": (
        "Re-extract this sentence. The decomposition is missing a part the rest of "
        "the record is derived from, so its wording cannot be corrected in place."
    ),
    "discretion_without_authority": (
        "Record who exercises the discretion, or note that the source leaves it "
        "unnamed."
    ),
}

_LOGIC_RECOMMENDATION_FALLBACK = (
    "Compare this record against the sentence quoted beside it."
)


def _logic_recommendation(finding: LogicFinding) -> str:
    """What to do about a faithfulness finding, by what it found."""

    if finding.shape is not None:
        return _LOGIC_RECOMMENDATION_BY_SHAPE[finding.shape]
    return _LOGIC_RECOMMENDATION_BY_CODE.get(
        finding.code, _LOGIC_RECOMMENDATION_FALLBACK
    )


def _logic_faithfulness_findings(rules: list[CanonicalRule]) -> list[dict]:
    """Whether each record's formed logic still quotes the sentence it came from.

    Advisory. It reports and does not gate, deliberately: the largest population
    it finds is flattened table structure, which the extractor produced and no
    reviewer can repair by editing, and holding a record for a defect its reader
    cannot fix is not a decision to put in front of them.
    """

    findings: list[dict] = []
    for rule in rules:
        canonical = rule.formulation.canonical if rule.formulation else None
        if canonical is None:
            continue
        for finding in judge_logic(canonical).findings:
            findings.append(
                {
                    "severity": _LOGIC_SEVERITY[finding.severity],
                    "category": finding.code,
                    "finding": (
                        f"Rule '{rule.title}' ({rule.rule_id}): {finding.claim!r} — "
                        f"{finding.detail}. Source: {finding.source_excerpt[:200]!r}"
                    ),
                    "affected_rule_ids": [rule.rule_id],
                    "recommendation": _logic_recommendation(finding),
                    "source": "deterministic",
                }
            )
    return findings


def _source_sentence(rule: CanonicalRule) -> str:
    """The document sentence a rule was extracted from, verbatim."""

    canonical = rule.formulation.canonical if rule.formulation else None
    return (canonical.source_text or "").strip() if canonical else ""


def _decomposition(rule: CanonicalRule) -> tuple:
    """What the extractor made of a sentence's *words*, as a comparable value.

    The linguistic fields only. `rule_type` and the effect are the extractor's
    classification *of* that reading, and holding them here would mean two
    records that split one sentence into identical parts, then labelled it
    `definition` on one run and `routing` on the next, never compared as the
    same reading — which is exactly the disagreement worth reporting. The first
    version did that, and the contradiction check could not fire at all.

    Volatile fields are absent for the opposite reason: `rule_id`, dates and
    lineage differ on every record, and including them means nothing ever
    matches.
    """

    canonical = rule.formulation.canonical if rule.formulation else None
    core = canonical.rule if canonical else None
    if core is None:
        return ()
    fields = (
        "subject",
        "modality",
        "predicate",
        "object",
        "threshold",
        "condition",
        "prerequisite",
        "trigger",
        "beneficiary",
        "assigner",
    )
    values = []
    for name in fields:
        value = getattr(core, name, None)
        values.append(value.strip().lower() if isinstance(value, str) else "")
    return tuple(values)


def _extraction_run(rule: CanonicalRule) -> str:
    return (rule.lineage.extraction_run_id or "") if rule.lineage else ""


def _by_sentence(rules: list[CanonicalRule]) -> dict[str, list[CanonicalRule]]:
    grouped: dict[str, list[CanonicalRule]] = {}
    for rule in rules:
        sentence = _source_sentence(rule)
        if sentence:
            grouped.setdefault(sentence, []).append(rule)
    return grouped


def _duplicate_extraction_findings(rules: list[CanonicalRule]) -> list[dict]:
    """One sentence read the same way twice.

    A sentence can legitimately carry two policies — "shall not exceed 10% …,
    and the increase is associated with the appraisal" is two — and those
    decompose differently. Two records with the *identical* decomposition are
    not that: the same reading was stored twice, and a consumer asking what the
    sentence requires gets the same answer under two identities.

    Reported as an extraction defect, because that is what it is. Nothing
    downstream can repair it, and a search API indexing both will return both.
    """

    findings: list[dict] = []
    for sentence, group in _by_sentence(rules).items():
        if len(group) < 2:
            continue
        by_shape: dict[tuple, list[CanonicalRule]] = {}
        for rule in group:
            by_shape.setdefault(_decomposition(rule), []).append(rule)
        for shape, same in by_shape.items():
            if len(same) < 2 or not shape:
                continue
            # Differing effects are the stronger, separate finding below.
            if len({r.effect.type.value for r in same}) > 1:
                continue
            findings.append(
                {
                    "severity": "high",
                    "category": "duplicate_extraction",
                    "finding": (
                        f"{len(same)} records carry the same reading of one sentence: "
                        f"{sentence[:110]!r}"
                    ),
                    "affected_rule_ids": [r.rule_id for r in same],
                    "recommendation": (
                        "Keep one and supersede the rest. Two identities for one policy means a "
                        "search returns it twice and a change has to be made twice."
                    ),
                    "source": "deterministic",
                }
            )
    return findings


def _contradictory_reading_findings(rules: list[CanonicalRule]) -> list[dict]:
    """One sentence, one reading, opposing outcomes.

    Stronger than a duplicate and stronger than the effect conflict beside it,
    which only fires when `allow` and `deny` both appear. The damaging case is
    subtler: the same sentence, decomposed identically, stored once as
    informational and once as an obligation. A consumer cannot choose between
    them, and neither can a judge.
    """

    findings: list[dict] = []
    for sentence, group in _by_sentence(rules).items():
        if len(group) < 2:
            continue
        by_shape: dict[tuple, list[CanonicalRule]] = {}
        for rule in group:
            by_shape.setdefault(_decomposition(rule), []).append(rule)
        for shape, same in by_shape.items():
            effects = {r.effect.type.value for r in same}
            if len(same) < 2 or not shape or len(effects) < 2:
                continue
            findings.append(
                {
                    "severity": "high",
                    "category": "contradictory_reading",
                    "finding": (
                        f"{len(same)} records read one sentence the same way but disagree about "
                        f"what follows ({', '.join(sorted(effects))}): {sentence[:100]!r}"
                    ),
                    "affected_rule_ids": [r.rule_id for r in same],
                    "recommendation": (
                        "Decide which reading the sentence supports and supersede the others. "
                        "Nothing downstream can choose between them."
                    ),
                    "source": "deterministic",
                }
            )
    return findings


def _unstable_extraction_findings(rules: list[CanonicalRule]) -> list[dict]:
    """The same sentence classified differently by two extraction runs.

    Re-running extraction over an unchanged document should produce the same
    reading of each sentence. Where it does not, the difference is in the
    extractor rather than in the policy — and it is invisible from any single
    record, because each looks complete on its own.

    Measured across a real pair of runs, one sentence was typed `routing` on
    one run and `obligation` on the next, and one action was stored once as
    "be considered as promotion" and once as "cannot be considered as
    promotion" — an inverted reading of the same words.
    """

    findings: list[dict] = []
    for sentence, group in _by_sentence(rules).items():
        runs = {_extraction_run(r) for r in group if _extraction_run(r)}
        if len(group) < 2 or len(runs) < 2:
            continue
        types = {r.rule_type.value for r in group}
        actions = {(r.effect.action or "").strip().lower() for r in group}
        differing: list[str] = []
        if len(types) > 1:
            differing.append(f"rule type ({', '.join(sorted(types))})")
        if len(actions) > 1:
            differing.append("the action it records")
        if not differing:
            continue
        findings.append(
            {
                "severity": "medium",
                "category": "unstable_extraction",
                "finding": (
                    f"Two extraction runs read one sentence differently — {' and '.join(differing)} "
                    f"— for: {sentence[:100]!r}"
                ),
                "affected_rule_ids": [r.rule_id for r in group],
                "recommendation": (
                    "Compare the readings against the sentence and keep the one it supports. A "
                    "difference here is in the extraction, not in the document."
                ),
                "source": "deterministic",
            }
        )
    return findings


def _runner_fitness_findings(rules: list[CanonicalRule]) -> list[dict]:
    """Whether each record can actually be decided the way it says it can.

    Two populations, two questions, and each has to be asked its own. A
    `deterministic` record claims the engine can evaluate it, so a condition
    naming a fact the record never declares is a defect that only appears at
    run time. An `ai_ready` record claims a judge can decide it by reading, so
    it has to answer — from itself — what the document said, what the rule
    requires, what a case must establish, what follows, and where it came from.

    Asking one question of both populations is what produced the finding this
    replaced: it reported 53 of 55 records as defective for failing a check
    that could not apply to them.
    """

    findings: list[dict] = []
    for rule in rules:
        if rule.evaluation_mode is EvaluationMode.DETERMINISTIC:
            reasons = unrunnable_reasons(rule)
            if reasons:
                findings.append(
                    {
                        "severity": "high",
                        "category": "not_runnable_as_stored",
                        "finding": (
                            f"'{rule.title}' ({rule.rule_id}) is routed to the engine but "
                            f"{'; '.join(reasons)}."
                        ),
                        "affected_rule_ids": [rule.rule_id],
                        "recommendation": (
                            "Every fact a condition names must be declared, or evaluation reports "
                            "a missing input for a policy that looks complete."
                        ),
                        "source": "deterministic",
                    }
                )
            continue
        missing = unanswered_for_judge(rule)
        if missing:
            findings.append(
                {
                    "severity": "high",
                    "category": "not_decidable_as_written",
                    "finding": (
                        f"'{rule.title}' ({rule.rule_id}) is decided by reading, but the record "
                        f"does not say {', or '.join(missing)}."
                    ),
                    "affected_rule_ids": [rule.rule_id],
                    "recommendation": (
                        "A judge sees this record and nothing else. What it omits cannot be "
                        "recovered downstream."
                    ),
                    "source": "deterministic",
                }
            )
    return findings


def _canonical_core(rule: CanonicalRule):
    """The subject/predicate/object decomposition, or None if there is none."""

    canonical = rule.formulation.canonical if rule.formulation else None
    return canonical.rule if canonical else None


def _self_containment_findings(rules: list[CanonicalRule]) -> list[dict]:
    """Records whose operative wording points outside themselves.

    A record decided by reading is read on its own, so wording like "in the
    case of absences on that day" is only usable where the record also says
    which day. Where it does not, the reader is sent to a neighbour the record
    does not name, and the record still looks complete: it carries a condition,
    so nothing that counts fields notices.

    The document is not at fault and neither is the route. The passage this was
    cut from says which day; the cut is what lost it. So the finding is against
    the extraction, and the remedy is to re-cut the record or link it to the
    neighbour that supplies the referent — never to paste the neighbour's words
    into it, which would put text in the record that the source does not carry.
    """

    findings: list[dict] = []
    for rule in rules:
        core = _canonical_core(rule)
        if core is None:
            continue
        dangling = dangling_referents(core, _source_sentence(rule))
        if not dangling:
            continue
        findings.append(
            {
                "severity": "high",
                "category": "record_does_not_stand_alone",
                "finding": (
                    f"'{rule.title}' ({rule.rule_id}) was cut away from wording it depends "
                    f"on: {'; '.join(item.as_reason() for item in dangling)}."
                ),
                "affected_rule_ids": [rule.rule_id],
                "recommendation": (
                    "Re-cut this record to include the wording it points at, or link it to "
                    "the record that carries it. Do not copy the neighbour's words in: the "
                    "record has to quote one passage of the source, not assemble one."
                ),
                "source": "deterministic",
            }
        )
    return findings


def _split_decision_findings(rules: list[CanonicalRule]) -> list[dict]:
    """One decision cut into several records, each holding a piece.

    The mirror of the check above. There a record carries too little of its
    sentence to be read alone; here several records carry one obligation
    between them, agreeing on who must do what and differing only in which
    thing, which occasion, or which limit.

    Splitting is often right — two subjects or two actions are two decisions,
    and this never groups those. What it reports is one obligation appearing
    more than once with a different piece attached each time, which leaves a
    reader unable to answer what the obligation actually requires without
    finding every fragment first.

    Nothing is merged. Combining fragments would state something no single
    sentence of the document states, and a record that cannot be traced to one
    passage is worth less than several that can.
    """

    members = [
        FamilyMember(rule_id=rule.rule_id, sentence=_source_sentence(rule), core=core)
        for rule in rules
        if (core := _canonical_core(rule)) is not None
    ]
    titles = {rule.rule_id: rule.title for rule in rules}

    findings: list[dict] = []
    for family in decision_families(members):
        first = titles.get(family.rule_ids[0], family.rule_ids[0])
        findings.append(
            {
                "severity": "medium",
                "category": "decision_split_across_records",
                "finding": (
                    f"'{first}' and {len(family.rule_ids) - 1} other record(s) were cut from "
                    f"one statement and {family.as_reason()}: {family.sentence[:110]!r}. As "
                    f"stored, nothing tells a reader which of them applies to a given case."
                ),
                "affected_rule_ids": list(family.rule_ids),
                "recommendation": (
                    "Check the sentence. If it states one obligation, the pieces belong in "
                    "one record whose fields carry them all. If it states several, each "
                    "record needs whatever distinguishes it — that is what is missing here, "
                    "and it was lost in extraction rather than absent from the document."
                ),
                "source": "deterministic",
            }
        )
    return findings


def _promoted_qualifier_findings(rules: list[CanonicalRule]) -> list[dict]:
    """A qualifier cut out of its sentence and made a rule of its own.

    A relative clause, an apposition or a trailing predicate says something
    *about* the thing an obligation lands on. Split out, it becomes a record
    whose subject is that thing rather than a party, and a record about a thing
    gives a reader no case to apply it to.

    The signature is string identity between one record's subject and another's
    object, both cut from one sentence. It reports a shape rather than asserting
    a defect: a genuine hand-off, where a party acted upon then carries an
    obligation of its own, has the same shape and is correct. Telling those
    apart needs to know which nouns name parties, which is vocabulary rather
    than structure, so the judgement is left to the reviewer.

    Nothing is merged. The remedy is to fold the qualifier back into the record
    that names what it qualifies, which is a re-cut of the source, not an
    assembly of two records.
    """

    members = [
        FamilyMember(rule_id=rule.rule_id, sentence=_source_sentence(rule), core=core)
        for rule in rules
        if (core := _canonical_core(rule)) is not None
    ]
    titles = {rule.rule_id: rule.title for rule in rules}

    findings: list[dict] = []
    for promotion in promoted_qualifiers(members):
        qualifier = titles.get(promotion.qualifier_rule_id, promotion.qualifier_rule_id)
        findings.append(
            {
                "severity": "medium",
                "category": "qualifier_promoted_to_record",
                "finding": (
                    f"'{qualifier}' was cut from the same statement as "
                    f"{', '.join(promotion.antecedent_rule_ids)} and "
                    f"{promotion.as_reason()}: {promotion.sentence[:110]!r}. As stored, "
                    f"it states something about a thing rather than about anyone, so a "
                    f"reader has no case to apply it to."
                ),
                "affected_rule_ids": [
                    *promotion.antecedent_rule_ids,
                    promotion.qualifier_rule_id,
                ],
                "recommendation": (
                    "Check the sentence. If the second record qualifies the thing the "
                    "first one acts on, it belongs in that record as a further "
                    "attribute rather than beside it. If it genuinely obliges someone "
                    "in their own right, leave both. Do not compose a new record from "
                    "the two: whichever survives has to quote one passage of the "
                    "source."
                ),
                "source": "deterministic",
            }
        )
    return findings


def _definition_effect_findings(rules: list[CanonicalRule]) -> list[dict]:
    """Report definitions that carry an authorization effect.

    A definition establishes vocabulary; it authorizes nothing. `EffectType`
    used to offer only allow/deny/require_action, so `_RULE_TYPE_MAP` had
    nowhere truthful to send `definition` and sent it to `allow`. The rule
    then asserted a permission its source never granted.

    That was not merely untidy, because a definition is often phrased
    negatively. Observed in the Saudi Labor Law extraction: "The periods
    designated for rest, prayers, and meals SHALL NOT BE INCLUDED in the
    actual working hours" became `allow: "be included in the actual working
    hours"` — the exact inverse of the source. Two separate AI reviews
    reported this as two findings ("definitions modeled with allow effects"
    and "semantic polarity errors"); they are one defect, and the polarity
    reversal is the symptom rather than the cause.

    Severity distinguishes latent from active, because the difference is real.
    While a definition stays non-executable the evaluator returns NOT_APPLICABLE
    and nothing acts on the false permission. Supplying a `trusted_config` is
    what makes a rule executable, so the first config that covers a definition's
    vocabulary is also what turns this from a labelling error into an evaluator
    returning ALLOW for text that says "shall not".

    `EffectType.INFORMATIONAL` now exists precisely for this case, and
    `_RULE_TYPE_MAP` sends `definition`/`classification` there instead of
    `allow` — see `formulation_mapping.py`. This check stays, unchanged, as a
    regression/backfill guard: rows extracted (or mapped) before that fix,
    or any future rule_type wrongly routed to allow/deny, still surface here
    at the review boundary rather than being approved unnoticed.
    """

    offenders = [
        r
        for r in rules
        if r.rule_type.value == "definition" and r.effect.type.value in {"allow", "deny"}
    ]
    if not offenders:
        return []

    executable = [r for r in offenders if r.machine_executable]
    by_effect = collections.Counter(r.effect.type.value for r in offenders)
    effects = ", ".join(f"{name} ({count})" for name, count in by_effect.most_common())

    if executable:
        exposure = (
            f"{len(executable)} of them are evaluated by comparison, so the evaluator can "
            f"already return that effect for text that may say the opposite."
        )
    else:
        exposure = (
            "None of them are evaluated by comparison, so nothing acts on the effect "
            "today — a judge reading the record would see the effect beside a "
            "definition that authorizes nothing."
        )

    return [
        {
            "severity": "high" if executable else "medium",
            "category": "definition_carries_effect",
            "finding": (
                f"{len(offenders)} definition rule(s) carry an authorization effect "
                f"[{effects}]. A definition establishes vocabulary and authorizes "
                f"nothing, and where its source is phrased negatively the effect "
                f"states the inverse of the text. {exposure}"
            ),
            "affected_rule_ids": [r.rule_id for r in offenders[:20]],
            "recommendation": (
                "Check these against their source text first: a definition whose "
                "wording is negative ('shall not be included', 'may not be deemed') "
                "now reads as a permission to do the thing the source excludes. "
                "New extraction maps definition/classification rules to the neutral "
                "informational effect. Re-extract or safely backfill these legacy rows "
                "before any trusted_config can make them executable, and keep this "
                "finding as a regression guard."
            ),
            "source": "deterministic",
        }
    ]


def _eligibility_polarity_findings(rules: list[CanonicalRule]) -> list[dict]:
    """Report `eligibility`-type rules whose `deny` effect names a grant, not a loss.

    Observed in the Saudi Labor Law extraction: six rules titled "... shall be
    exempted from the implementation of the provisions of this Law" were
    formulated with `rule_type: eligibility`, `effect.type: "deny"`,
    `effect.action: "be exempted from the implementation of the provisions of
    this Law"`. `effect.type` and `effect.action` are read together as one
    sentence by the evaluator (`_apply_combining_algorithm` puts a satisfied
    `deny` rule's action straight into `denied_actions`), so this reads as
    "denied: be exempted..." — i.e. the Law's provisions DO apply — the
    literal opposite of the source, which grants the exemption.

    Root cause: the single `RuleType.ELIGIBILITY` schema value covers both
    directions via the AI-facing `CanonicalRuleType.ELIGIBILITY` (→ `allow`)
    and `.INELIGIBILITY` (→ `deny`) in `_RULE_TYPE_MAP`. The formulator picked
    `ineligibility` for a grant-shaped exemption because the prompt's own
    worked example (fixed alongside this check) told it to. See
    policy_formulator_v1.md Section 14/15.1 (POLARITY TEST) for the
    GRANT-SHAPED vs. LOSS-SHAPED negation heuristic this guards against
    regressing.

    This is a structural, keyword-based heuristic (grant-shaped verbs paired
    with a `deny` effect), not a semantic proof: it can miss an inversion
    phrased without any of these verbs, and could in principle false-positive
    on a genuinely-intended denial that happens to reuse one of these words.
    It exists as a regression/backfill guard, the same way
    `_definition_effect_findings` guards its own polarity defect: rows
    formulated before the prompt fix, or any future slip, still surface here
    at the review boundary rather than being approved unnoticed.
    """

    grant_shaped_markers = (
        "exempt",
        "excus",
        "immune",
        "not subject to",
        "not bound by",
        "released from",
        "relieved of",
        "waived",
    )
    offenders = [
        r
        for r in rules
        if r.rule_type.value == "eligibility"
        and r.effect.type.value == "deny"
        and any(marker in r.effect.action.lower() for marker in grant_shaped_markers)
    ]
    if not offenders:
        return []

    return [
        {
            "severity": "high",
            "category": "eligibility_polarity_inversion",
            "finding": (
                f"{len(offenders)} eligibility rule(s) have effect.type='deny' but "
                f"effect.action names a grant (e.g. an exemption/release from a "
                f"burden), which reads as denying that grant — the opposite of what "
                f"the source establishes."
            ),
            "affected_rule_ids": [r.rule_id for r in offenders[:20]],
            "recommendation": (
                "Re-run formulation for these rules (or edit them manually) so a "
                "grant-shaped outcome (an exemption, a release from a burden) is "
                "classified eligibility/allow, not ineligibility/deny. See "
                "policy_formulator_v1.md Section 15.1 (POLARITY TEST)."
            ),
            "source": "deterministic",
        }
    ]


def _degenerate_predicate_findings(rules: list[CanonicalRule]) -> list[dict]:
    """Report rules whose canonical predicate is punctuation, not a relationship.

    Observed in the Saudi Labor Law extraction: a definition sourced from
    "Minor: Any person of 15 and below 18 years of age" was formulated with
    `predicate: ":"` — the source's own delimiter, echoed back as though it
    were the semantic relationship between subject and object, instead of
    being resolved to a copula such as "is defined as" (see the formulator
    prompt's Section 19.2). A predicate with no alphanumeric characters can
    never be a real relationship; that is always a decomposition slip, not a
    property of the source text, so this stays as a regression/backfill
    guard the same way `_definition_effect_findings` guards its own defect —
    rows formulated before the prompt fix, or any future slip, still surface
    here rather than being approved unnoticed.

    Reuses `formulation_mapping._is_separator_predicate` — the same
    punctuation-only test that already makes `_title_for`/`_effect_action`
    skip a degenerate predicate when building display strings — so "what
    counts as degenerate" has exactly one definition. That existing helper
    only cleans the *derived* title/effect text; it doesn't fix or report on
    the underlying stored `predicate` field itself, which is what this
    finding surfaces to reviewers.
    """

    offenders = []
    for r in rules:
        canonical = getattr(getattr(r, "formulation", None), "canonical", None)
        predicate = getattr(getattr(canonical, "rule", None), "predicate", None)
        if predicate is not None and _is_separator_predicate(predicate):
            offenders.append(r)

    if not offenders:
        return []

    return [
        {
            "severity": "medium",
            "category": "degenerate_predicate",
            "finding": (
                f"{len(offenders)} rule(s) have a predicate that is empty or pure punctuation "
                f'(e.g. ":"), echoing the source\'s delimiter instead of naming the '
                f"subject/object relationship."
            ),
            "affected_rule_ids": [r.rule_id for r in offenders[:20]],
            "recommendation": (
                "Re-run formulation for these rules (or edit them manually) so the predicate "
                'names the relationship in words (e.g. "is defined as", "means", "shall submit") '
                "rather than repeating source punctuation."
            ),
            "source": "deterministic",
        }
    ]


def _non_blocking_ambiguity_findings(rules: list[CanonicalRule]) -> list[dict]:
    """One finding for the non-blocking ambiguity backlog, not one per rule.

    A per-rule finding is right when each row needs its own decision. Ambiguity
    that the extractor flagged for human judgment is a queue with a known size,
    and emitting one row per rule pushes genuinely distinct problems (duplicate
    ids, conflicting effects) off the end of a report that is read top-down.
    """
    flagged = [r for r in rules if r.ambiguity_status.value not in ("none", "blocking")]
    if not flagged:
        return []
    by_status = collections.Counter(r.ambiguity_status.value for r in flagged)
    breakdown = ", ".join(f"{count} {status}" for status, count in sorted(by_status.items()))
    return [
        {
            "severity": "medium",
            "category": "ambiguity",
            "finding": (
                f"{len(flagged)} of {len(rules)} rule(s) need human judgment on wording ({breakdown})."
            ),
            "affected_rule_ids": [r.rule_id for r in flagged],
            "recommendation": (
                "Work these through the Review Queue. This records that the source wording needs a "
                "human decision — it is not an extraction failure."
            ),
            "source": "deterministic",
        }
    ]



async def _run_ai_review(rules: list[CanonicalRule], findings: list[dict], policy_set_key: str) -> bool:
    """Append AI-review findings to `findings` in place, tagged source=ai_review.

    Best-effort: on any failure the deterministic findings already collected
    remain valid and are returned as-is (never fails the whole report).

    Returns True only when the review actually ran to completion. Callers must
    record *this* rather than the flag they passed in: a failed review produces
    a report with fewer findings, which reads as a cleaner policy set unless the
    report says the review never happened. When the review was expected and did
    not run, a finding is appended so the gap is visible in the report itself
    and not only in the server log.
    """
    settings = get_settings()
    if not rules:
        return False
    if not settings.ai_enabled:
        findings.append(
            {
                "severity": "medium",
                "category": "review_coverage",
                "finding": "AI review was requested but AI is disabled, so only deterministic checks ran.",
                "affected_rule_ids": [],
                "recommendation": "Enable AI to get ambiguity, conflict and gap findings.",
                "source": "deterministic",
            }
        )
        return False
    try:
        ai_client = AzureOpenAIClient(settings)
        rule_summaries = [_quality_rule_context(rule) for rule in rules]
        user_content = json.dumps(
            {
                "approved_rules": rule_summaries,
                "deterministic_findings_already_found": findings,
            },
            indent=2,
            default=str,
        )
        raw = await ai_client.chat(
            [
                {"role": "system", "content": _AI_REVIEW_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            deployment=settings.azure_openai_deployment,
            json_mode=True,
            # Fixed seed rather than temperature. Probed live against this
            # resource: the quality deployment (gpt-5.6-sol) returns 400 for
            # both `temperature=0` ("Only the default (1) value is supported")
            # and `top_p=0`, and `_run_ai_review` swallows every exception --
            # so passing temperature here would quietly convert every review
            # into a "review did not complete" finding. `seed` is accepted but,
            # measured, changes nothing: see `_AI_REVIEW_SEED`. Two reviews of
            # the same rules are two opinions, not one measurement repeated.
            seed=_AI_REVIEW_SEED,
            # See openai_client.chat() docstring: gpt-5.6-sol is a reasoning
            # model and needs a generous budget or it returns empty content.
            max_tokens=8000,
            timeout=180.0,
        )
        parsed = json.loads(raw)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("findings"), list):
            raise ValueError("AI quality review did not return a findings array")
        valid_rule_ids = {rule.rule_id for rule in rules}
        for raw_finding in parsed["findings"]:
            normalized = _normalize_ai_finding(raw_finding, valid_rule_ids)
            if normalized is not None:
                findings.append(normalized)
        return True
    except Exception as exc:  # noqa: BLE001 - deterministic findings remain valid without AI review
        logger.warning("AI quality review failed for %s: %s", policy_set_key, exc)
        findings.append(
            {
                "severity": "medium",
                "category": "review_coverage",
                "finding": f"AI review did not complete, so only deterministic checks ran: {exc}",
                "affected_rule_ids": [],
                "recommendation": (
                    "Re-run the evaluation. If this repeats on a large policy set, the review sends every "
                    "rule in one request and may be exceeding the model's context window."
                ),
                "source": "deterministic",
            }
        )
        return False


async def evaluate_policy_set_quality(
    session: AsyncSession,
    *,
    policy_set_key: str,
    use_ai_review: bool = True,
    record_run: bool = True,
    triggered_by: str = "",
) -> dict:
    """Perform a quality evaluation of the active published version and record it.

    This costs a full AI review and appends a row to the evaluation history, so
    it belongs behind a deliberate action. Reading the result of a previous
    evaluation is `latest_quality_report`.
    """
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(policy_set_key)
    if policy_set is None:
        raise ValueError(f"policy set '{policy_set_key}' not found")

    version_repo = ApprovedPolicyVersionRepository(session)
    active = await version_repo.get_active_version(policy_set.id)
    if active is None:
        raise ValueError(f"policy set '{policy_set_key}' has no active approved version")

    package = approved_policy_version_to_package(active)
    rules = package.rules

    candidate_repo = CandidateRuleRepository(session)
    pending_candidates = await candidate_repo.list_by_policy_set(policy_set.id, review_status="candidate")

    findings = _deterministic_findings(rules)
    findings.append(
        {
            "severity": "low",
            "category": "review_backlog",
            "finding": f"{len(pending_candidates)} candidate rule(s) awaiting human review",
            "affected_rule_ids": [],
            "recommendation": "Review the pending candidates in the Review Queue." if pending_candidates else "",
            "source": "deterministic",
        }
    )

    if use_ai_review:
        ai_review_used = await _run_ai_review(rules, findings, policy_set_key)
    else:
        ai_review_used = False
    _mark_deterministic_findings(findings)

    run_id = None
    run_at = None
    if record_run:
        run = await QualityRunRepository(session).create(
            policy_set_id=policy_set.id,
            scope="published",
            version_number=active.version_number,
            rule_count=len(rules),
            findings=findings,
            ai_review_used=ai_review_used,
            methodology_version=QUALITY_METHODOLOGY_VERSION,
            triggered_by=triggered_by,
        )
        await session.commit()
        run_id = str(run.id)
        run_at = run.run_at.isoformat()

    return {
        "policy_set_key": policy_set_key,
        "scope": "published",
        "evaluated": True,
        "version_number": active.version_number,
        "rule_count": len(rules),
        "findings": findings,
        "finding_count": len(findings),
        "quality_run_id": run_id,
        "run_at": run_at,
        "ai_review_used": ai_review_used,
        "triggered_by": triggered_by,
        "methodology_version": QUALITY_METHODOLOGY_VERSION,
    }


async def evaluate_candidate_quality(
    session: AsyncSession,
    *,
    policy_set_key: str,
    use_ai_review: bool = True,
    review_statuses: tuple[str, ...] = ("candidate", "approved"),
    record_run: bool = True,
    triggered_by: str = "",
) -> dict:
    """Evaluate quality of AI-extracted candidate rules *before* they are published.

    This lets a reviewer see structural + AI-flagged issues (duplicate ids,
    ambiguity, conflicting effects, gaps, redundancy) on freshly-extracted
    candidates while they are still in the "candidate"/"approved" (unpublished)
    state, instead of only being able to run a quality check after publish.
    Rejected and already-published candidates are excluded by default.
    """
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(policy_set_key)
    if policy_set is None:
        raise ValueError(f"policy set '{policy_set_key}' not found")

    candidate_repo = CandidateRuleRepository(session)
    candidates = []
    for status in review_statuses:
        candidates.extend(await candidate_repo.list_by_policy_set(policy_set.id, review_status=status))

    rules: list[CanonicalRule] = []
    parse_errors: list[dict] = []
    for c in candidates:
        try:
            rules.append(CanonicalRule.model_validate(c.payload_json))
        except Exception as exc:  # noqa: BLE001 - a bad candidate shouldn't abort the whole report
            parse_errors.append(
                {
                    "severity": "high",
                    "category": "invalid_candidate_payload",
                    "finding": f"Candidate rule '{c.id}' failed schema validation: {exc}",
                    "affected_rule_ids": [str(c.id)],
                    "recommendation": "Reject or manually correct this candidate; it cannot be published as-is.",
                    "source": "deterministic",
                }
            )

    findings = _deterministic_findings(rules) + parse_errors

    if use_ai_review:
        ai_review_used = await _run_ai_review(rules, findings, policy_set_key)
    else:
        ai_review_used = False
    _mark_deterministic_findings(findings)

    run_id = None
    run_at = None
    if record_run:
        run = await QualityRunRepository(session).create(
            policy_set_id=policy_set.id,
            scope="candidates",
            version_number=None,
            rule_count=len(rules),
            findings=findings,
            ai_review_used=ai_review_used,
            methodology_version=QUALITY_METHODOLOGY_VERSION,
            triggered_by=triggered_by,
        )
        await session.commit()
        run_id = str(run.id)
        run_at = run.run_at.isoformat()

    return {
        "policy_set_key": policy_set_key,
        "scope": "candidates",
        "evaluated": True,
        "version_number": None,
        "rule_count": len(rules),
        "candidate_statuses_included": list(review_statuses),
        "findings": findings,
        "finding_count": len(findings),
        "quality_run_id": run_id,
        "run_at": run_at,
        "ai_review_used": ai_review_used,
        "triggered_by": triggered_by,
        "methodology_version": QUALITY_METHODOLOGY_VERSION,
    }


# ---------------------------------------------------------------------------
# Reading a previous evaluation
#
# Evaluating and reading are separate acts. An evaluation costs a full AI review
# and appends to the history the Quality page compares runs against, so it can
# only be asked for deliberately. Everything below reads what a previous
# evaluation recorded and touches neither the model nor the database.
# ---------------------------------------------------------------------------


def _report_from_run(run: QualityRun, policy_set_key: str) -> dict:
    """Render a stored run in the same shape a fresh evaluation returns.

    `candidate_statuses_included` is absent here on purpose: the stored row does
    not record which candidate statuses the run covered, and inventing the
    default would state something the record does not.
    """

    findings = list(run.findings_json or [])
    return {
        "policy_set_key": policy_set_key,
        "scope": run.scope,
        "evaluated": True,
        "version_number": run.version_number,
        "rule_count": run.rule_count,
        "findings": findings,
        "finding_count": len(findings),
        "quality_run_id": str(run.id),
        "run_at": run.run_at.isoformat(),
        "ai_review_used": run.ai_review_used,
        "triggered_by": run.triggered_by,
        "methodology_version": run.methodology_version,
    }


def never_evaluated_report(policy_set_key: str, scope: str) -> dict:
    """The answer when nothing has ever been evaluated for this scope.

    `findings` is null rather than `[]`, and `evaluated` is false. An empty list
    would be indistinguishable from a completed evaluation that found nothing,
    which is the opposite conclusion: one says the policy set was examined and
    is clean, the other says nobody has looked. Every other field is null for
    the same reason -- a `rule_count` of 0 would read as a measurement.
    """

    return {
        "policy_set_key": policy_set_key,
        "scope": scope,
        "evaluated": False,
        "version_number": None,
        "rule_count": None,
        "findings": None,
        "finding_count": None,
        "quality_run_id": None,
        "run_at": None,
        "ai_review_used": None,
        "triggered_by": None,
        "methodology_version": None,
        "detail": (
            f"No quality evaluation has been recorded for the {scope} rules of "
            f"policy set '{policy_set_key}'. Run one to produce a result."
        ),
    }


async def latest_quality_report(
    session: AsyncSession, *, policy_set_key: str, scope: str
) -> dict:
    """The most recent recorded evaluation for this scope, or the absence of one.

    Reads only. No AI call, no write -- the caller gets what was recorded, not a
    fresh opinion.
    """

    policy_set = await PolicySetRepository(session).get_by_key(policy_set_key)
    if policy_set is None:
        raise ValueError(f"policy set '{policy_set_key}' not found")

    runs = await QualityRunRepository(session).list_by_policy_set(
        policy_set.id, scope=scope, limit=1
    )
    if not runs:
        return never_evaluated_report(policy_set_key, scope)
    return _report_from_run(runs[0], policy_set_key)
