"""Flavour 2 — the lean, model-facing projection of one policy.

The JSON tab renders two flavours of the same policy:

* **Flavour 1** is the full canonical record — every field, every notation, the
  whole provenance apparatus. It is the record of what was extracted and it is
  what a reviewer audits. `policyCards.ts` / `policyExport.ts` own it and it is
  unchanged.
* **Flavour 2** (this module) is a lean projection chosen for a model to read.
  It is the input the case-testing mechanism sends to an LLM, so it keeps the
  operative meaning of every rule and drops everything that only repeats it in
  another notation or only records how the extraction ran.

Why one module, server-side
----------------------------
The case-testing mechanism builds this payload server-side and the JSON tab
shows the same thing client-side. If the projection were written twice — once
in Python and once in TypeScript — the two would drift, and a model would then
be tested against a payload no reviewer ever saw. So the projection lives here,
once, and the tab fetches it from the API rather than rebuilding it.

The representation, chosen on measured evidence (677 live rules)
---------------------------------------------------------------
Every rule carries several restatements of itself: the canonical
subject/predicate/object formulation, a DMN/FEEL projection, and an XACML
projection. Only one can be the carrier, and the measurement is decisive:

* the **canonical formulation** exists on **677/677 = 100 %** of live rules, on
  both the AI-ready and the deterministic route, and it retains the document's
  verbatim source phrase — the thing grounding rests on;
* an **executable DMN decision table** exists on **0/677**; every DMN block is a
  `semantic_projection` that only restates the canonical in another notation;
* an **executable XACML projection** compiles only for the deterministic
  minority (**7/677 ≈ 1 %**) and is derived on read, never stored.

A representation that exists for 1 % of rules cannot carry the whole policy, so
DMN and XACML are dropped as redundant second notations. The canonical
formulation is the carrier, and it is also the shape the app's own display
contract already uses — attribute name, the document's words verbatim, and the
identifier a case supplies a value for — so the model reads the policy the same
way the reviewer sees it.

Re-derived, never read back
---------------------------
`attributes` and `fact_model` are recomputed here from `formulation.canonical`
with the very functions the API's read path uses (`published_facts`,
`attributes_for`), never read from the stored copy in `payload_json`, which can
be stale. This mirrors `candidate_rules._with_decision_readiness` exactly, so
the lean payload can never disagree with the served record about the same rule.

What identity is kept, and the one trade-off
--------------------------------------------
The user's identity set is explicit: **rule id, policy id, and the search / AI
document id are enough.** Run history is dropped. The one clause-level id kept
is `search_document_id` (`{document_version_id}_{clause_id}`) — the Azure AI
Search key the AI route already grounds against. It is worth keeping because it
is the retrieval handle a cited answer resolves through. What is *dropped* with
it is the sub-clause character span (`start_offset`/`end_offset`): an answer can
be traced to a **clause** (and its search document) but not to a character range
within it. The verbatim `source_text` is preserved uncut, so the span remains
findable by string search anyway.

Names are never carried (constraint 8)
--------------------------------------
A rule's generated display name lives in a separate display-name table and is
resolved by the UI at render time. It is never in `payload_json`, and this
module reads only `payload_json`, so no generated name can enter the lean
payload. Every rule is carried by `rule_id`; the interface resolves the name.

Contract with the case-intent agent
------------------------------------
`case_payload_for_provision(session, provision_id)` is the entry point the
case-testing mechanism calls directly (no HTTP hop). The whole persistence stack
is async, so it is an ``async def`` taking an ``AsyncSession`` — the name, path,
parameters and returned shape are exactly as agreed; only the ``async`` keyword
differs from the ``def`` in the brief. `build_case_payload` is a pure,
session-free core so the shape can be tested without a database.
"""
from __future__ import annotations

import uuid
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.contracts.policy import (
    CanonicalRule,
    PolicyAttribute,
    PolicyAttributes,
    PolicyFact,
    attributes_for,
    evaluation_mode_for,
)
from policy_platform.domain.models import CandidateRule, DocumentProvision
from policy_platform.infrastructure.extraction.policy_facts import published_facts
from policy_platform.infrastructure.search.indexing import clause_search_document_id

#: Names the flavour so a consumer can tell the two JSON shapes apart at a
#: glance, and records which representation technique was chosen and why the
#: payload looks the way it does.
FLAVOR = "lean"
REPRESENTATION = "canonical"


def _plain(value: object) -> object:
    """A JSON-native scalar for an enum member, unchanged for anything else."""

    return value.value if isinstance(value, Enum) else value


def _attribute_payload(attribute: PolicyAttribute) -> dict:
    """One attribute, verbatim, with its explicit absences preserved.

    `text` is the document's words and is never trimmed to fit (constraint 4).
    `fact` and `data_type` keep their `None` rather than being dropped: a `None`
    `fact` says the document supplies the value itself (a statement, not a gap),
    and a `None` `data_type` says the phrase never named a kind — collapsing
    either into an omitted key would erase the distinction (constraint 5).
    """

    return {
        "attribute": attribute.attribute,
        "text": attribute.text,
        "fact": attribute.fact,
        "data_type": attribute.data_type,
    }


def _fact_payload(fact: PolicyFact) -> dict:
    """One fact, named by the sentence and carrying the sentence, verbatim.

    `source_phrase` is the document's wording and is kept uncut (constraint 4);
    `data_type` keeps its `None` (unstated), same reasoning as the attribute.
    """

    return {
        "name": fact.name,
        "source_phrase": fact.source_phrase,
        "roles": list(fact.roles),
        "data_type": fact.data_type,
    }


def _grounding(rule: CanonicalRule) -> list[dict]:
    """Where each rule is grounded: its clause's Azure AI Search key.

    Built from the rule's own embedded evidence, so no clause-table join is
    needed. A reference with no `clause_id` carries no grounding key and is
    omitted rather than emitted as a null-keyed row.
    """

    grounding: list[dict] = []
    for ref in rule.evidence:
        if not ref.clause_id:
            continue
        grounding.append(
            {
                "search_document_id": clause_search_document_id(
                    ref.document_version_id, ref.clause_id
                ),
                "clause_id": ref.clause_id,
            }
        )
    return grounding


def lean_rule(rule: CanonicalRule) -> dict:
    """Project one rule to its lean, model-facing shape.

    `attributes` and `facts` are re-derived from `formulation.canonical` with
    the same functions the API read path uses, never read from the possibly
    stale stored copy — mirroring `candidate_rules._with_decision_readiness`.
    A hand-authored rule with no formulation has nothing to re-derive from, so
    its own stored `attributes`/`fact_model` stand and its `source_text` is
    empty, exactly as the API leaves it.
    """

    canonical = None
    if rule.formulation is not None and rule.formulation.canonical is not None:
        canonical = rule.formulation.canonical

    if canonical is not None:
        facts = published_facts(canonical.rule, rule.required_facts)
        attributes = attributes_for(canonical.rule, facts)
        source_text = canonical.source_text
    else:
        facts = list(rule.fact_model)
        attributes = rule.attributes
        source_text = ""

    if not isinstance(attributes, PolicyAttributes):  # defensive: attributes_for always returns one
        attributes = PolicyAttributes()

    payload: dict = {
        # Identity only — never a name (constraint 8). The UI resolves the
        # display name from a separate table at render time.
        "rule_id": rule.rule_id,
        "rule_type": _plain(rule.rule_type),
        # Derived from the condition, so it can never disagree with the tree.
        "evaluation_mode": _plain(evaluation_mode_for(rule)),
        "ambiguity_status": _plain(rule.ambiguity_status),
        # The document's sentence, verbatim and uncut (constraint 4) — the
        # anchor every answer is checked against.
        "source_text": source_text,
        "effect": {"type": _plain(rule.effect.type), "action": rule.effect.action},
        "attributes": {
            "applies": [_attribute_payload(a) for a in attributes.applies],
            "outcome": [_attribute_payload(a) for a in attributes.outcome],
        },
        "facts": [_fact_payload(f) for f in facts],
        "grounding": _grounding(rule),
    }

    # Exceptions are operative carve-outs, so their prose is kept verbatim and
    # their structured limit keeps its explicit None. Omitted entirely when the
    # rule states none: an empty list and an absent key both mean "no
    # exceptions" here, so nothing is lost by leaving it out (unlike the scalar
    # nulls above, which do carry a distinction).
    exceptions = [
        {
            "exception_id": exc.exception_id,
            "description": exc.description,
            "limit_value": exc.limit_value,
            "limit_unit": exc.limit_unit,
        }
        for exc in rule.exceptions
    ]
    if exceptions:
        payload["exceptions"] = exceptions

    # Non-blocking advice, kept verbatim when present for the same reason.
    advice = [{"advice_id": item.advice_id, "text": item.text} for item in rule.advice]
    if advice:
        payload["advice"] = advice

    return payload


def build_case_payload(
    *,
    policy_set_id: str,
    provision_id: str,
    provision_key: str,
    heading_path: list[str],
    rules: list[CanonicalRule],
) -> dict:
    """Assemble the lean policy: identity, the document's headings, and rules.

    A *policy* with its rules nested (constraint 2), not a bag of rules. Pure
    and session-free so the projected shape can be tested without a database.
    """

    return {
        "flavor": FLAVOR,
        "representation": REPRESENTATION,
        "policy_set_id": policy_set_id,
        "provision_id": provision_id,
        "provision_key": provision_key,
        # Copied verbatim from the document; the only prose the provision holds.
        "heading_path": list(heading_path or []),
        "rule_count": len(rules),
        "rules": [lean_rule(rule) for rule in rules],
    }


async def case_payload_for_provision(session: AsyncSession, provision_id) -> dict | None:
    """The lean payload for one provision's current (non-superseded) rules.

    Returns ``None`` when the provision id is unknown, so a caller can answer a
    404 without this module importing anything web-facing. Rules are loaded in
    the same order the review surface uses (`created_at`), filtered to the
    current set (`superseded_at IS NULL`), exactly as every other read means.
    """

    pid = provision_id if isinstance(provision_id, uuid.UUID) else uuid.UUID(str(provision_id))

    provision = await session.get(DocumentProvision, pid)
    if provision is None:
        return None

    stmt = (
        select(CandidateRule)
        .where(CandidateRule.provision_id == pid)
        .where(CandidateRule.superseded_at.is_(None))
        .order_by(CandidateRule.created_at)
    )
    result = await session.execute(stmt)
    candidates = list(result.scalars().all())

    rules = [CanonicalRule.model_validate(candidate.payload_json) for candidate in candidates]

    return build_case_payload(
        policy_set_id=str(provision.policy_set_id),
        provision_id=str(provision.id),
        provision_key=provision.provision_key,
        heading_path=provision.heading_path_json,
        rules=rules,
    )
