"""A rule is counted once in ``grounding_projection_v1`` — however many spans ground it.

This is the projection's guard against the counting fault the review surfaces
were audited for: a policy card showed "10 rules" for a policy holding nine,
because a rule stated in more than one passage was rendered — and counted — once
per passage. Occurrences were counted where distinct rules were meant.

The projection can commit the same error in its own idiom. A rule is grounded in
its ``evidence`` — one clause it is quoted from, and any number of supporting
clauses. A rule grounded across three clauses "appears in" three spans. If the
projection ever emitted one ``rules`` entry per span, or let a shared span pull a
rule into the list twice, it would count grounding occurrences where the user
asked for rules. These invariants pin the opposite: **one candidate rule yields
exactly one entry in ``rules``, and the set of rendered rule ids equals the set
of distinct input rule ids** — while every span the rule is grounded in is
preserved and none is dropped.

They complement, and do not restate, the notation-de-duplication invariants in
``test_the_lean_flavour_keeps_meaning_not_notation.py``: those prove a source
string two rules share is *stored* once; these prove a rule many spans ground is
*counted* once.

Constraint 1: every count asserted here is the fixture's own — taken with
``len(...)`` over the rules and evidence this test constructs, or by set-equality
against those same inputs. No observed corpus count, and no policy name, is
written into the logic or the assertions. A test that passed because a corpus
happened to hold a particular number of rules would be the very defect the audit
exists to find.
"""
from __future__ import annotations

from policy_platform.contracts.conditions import AllCondition
from policy_platform.contracts.policy import EvidenceReference
from policy_platform.infrastructure.projection.policy_case_payload import build_case_payload
from tests.fixtures.factories import make_rule

_EMPTY = AllCondition(all=[])


def _ref(clause_id: str, *, document_version_id: str = "v-1", text_hash: str) -> EvidenceReference:
    """One evidence reference — a clause a rule is grounded in.

    ``source_hash`` is distinct per clause so a preserved span can be told apart
    from its neighbours, which is what proves no membership was silently folded
    into another.
    """

    return EvidenceReference(
        document_version_id=document_version_id,
        source_hash=text_hash,
        page=7,
        section="3. Conditions of Work",
        clause_id=clause_id,
        start_offset=0,
        end_offset=40,
    )


def _grounded(rule_id: str, *, source_text: str, evidence: list[EvidenceReference]):
    """A rule grounded in one or more clauses, built the shape extraction writes.

    No formulation is attached: the number of spans a rule is grounded in is a
    property of its ``evidence`` alone, so the counting invariant is exercised
    without one. (``test_the_lean_flavour_keeps_meaning_not_notation.py`` already
    covers the formulated path in depth.)
    """

    return make_rule(rule_id, _EMPTY).model_copy(
        update={"description": source_text, "evidence": evidence}
    )


def _payload(rules):
    return build_case_payload(
        policy_set_id="set-1",
        provision_id="prov-1",
        provision_key="key-1",
        heading_path=["A heading the document wrote"],
        rules=rules,
    )


def test_a_rule_grounded_in_many_clauses_is_one_rule_with_every_span_kept() -> None:
    """One rule, grounded across three distinct clauses, projects to one entry.

    The rule "appears in" three spans, but it is one rule and must be counted
    once. Every clause it is grounded in survives as its own span — the count
    falls to one rule without any of its grounding being dropped to get there.
    """

    evidence = [
        _ref("E000010", text_hash="a" * 16),
        _ref("E000020", text_hash="b" * 16),
        _ref("E000030", text_hash="c" * 16),
    ]
    rule = _grounded(
        "AI-manyspans1",
        source_text="Conduct is governed by the standard set out across these clauses.",
        evidence=evidence,
    )

    payload = _payload([rule])

    # Counted once: one candidate rule in, one rule out — not one per span.
    assert len(payload["rules"]) == 1
    projected = payload["rules"][0]
    assert projected["rule_id"] == "AI-manyspans1"

    # Every clause it is grounded in is preserved — as many refs as the rule
    # carried evidence, all distinct, each resolving to a span in the dictionary.
    refs = projected["evidence_refs"]
    assert len(refs) == len(evidence)
    assert len(set(refs)) == len(evidence)
    assert set(refs) <= set(payload["spans"])

    # Each clause kept its own provenance — nothing folded into a neighbour.
    kept_hashes = {payload["spans"][ref]["source_hash"] for ref in refs}
    assert kept_hashes == {"a" * 16, "b" * 16, "c" * 16}


def test_distinct_rules_are_rendered_once_each_even_when_they_share_a_span() -> None:
    """The set of rendered rule ids equals the set of distinct input rule ids.

    The direct analogue of the card fault: distinct rules in, the same distinct
    rules out — no rule rendered twice because it shares a clause with another,
    and none dropped. One rule here is grounded across two clauses and two others
    share a single clause, so both hazards — a rule with many spans, and a span
    with many rules — are present at once.
    """

    shared = _ref("E000099", text_hash="s" * 16)
    rules = [
        _grounded(
            "AI-distinct01",
            source_text="Records are retained for the statutory period.",
            evidence=[_ref("E000010", text_hash="a" * 16), _ref("E000020", text_hash="b" * 16)],
        ),
        _grounded("AI-distinct02", source_text="A shared clause.", evidence=[shared]),
        _grounded("AI-distinct03", source_text="A shared clause.", evidence=[shared]),
    ]

    payload = _payload(rules)

    rendered_ids = [r["rule_id"] for r in payload["rules"]]
    input_ids = [r.rule_id for r in rules]

    # Every distinct rule rendered exactly once — none inflated by a shared span
    # or by spanning several clauses, none dropped.
    assert len(payload["rules"]) == len(rules)
    assert set(rendered_ids) == set(input_ids)
    assert len(rendered_ids) == len(set(rendered_ids))


def test_repeating_a_clause_in_one_rules_evidence_still_yields_one_rule() -> None:
    """Evidence that leans on a clause more than once is still one rule.

    Extraction can record a clause as both the quoted anchor and a supporting
    reference. The projection keeps those as distinct grounding — a span carrying
    the quote and a text-free "also grounded here" marker are different states a
    reader must be able to tell apart, so this file does not assert they collapse
    (the notation-de-duplication tests own span shape). What it does assert is the
    counting truth: repeated grounding is detail about *one* rule, never a second
    one. The entry count follows the rule, not the length of its evidence list.
    """

    same = _ref("E000042", text_hash="d" * 16)
    rule = _grounded(
        "AI-repeatclr1",
        source_text="A clause a rule leans on more than once.",
        evidence=[same, same],
    )

    payload = _payload([rule])

    rendered_ids = [r["rule_id"] for r in payload["rules"]]
    assert rendered_ids == ["AI-repeatclr1"]
    assert len(rendered_ids) == len(set(rendered_ids))
