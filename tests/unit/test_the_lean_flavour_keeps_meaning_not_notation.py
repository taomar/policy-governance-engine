"""Flavour 2 — ``grounding_projection_v1`` keeps a rule's meaning and de-duplicates its notation.

The lean payload is what a model reads when the case-testing mechanism asks it
to judge a case, so the properties pinned here are the ones that decide whether
that judgement can be trusted. They are written as **relative invariants** —
compared against the source record or checked for internal consistency — never
against a corpus count. The projection removes *structural duplication* (the
same words stored once and referenced) and must never remove *content*.

The invariants (numbered as in the specification):

  1. every rule and passage in the record is represented in the projection —
     asserted by comparison against the source, not against a number;
  2. every source span keeps its hash, page, section and offsets;
  3. a canonical rule keeps its modality, action, exceptions, outcome, scope,
     dates, required facts and evidence — its operative meaning, unchanged;
  4. no evidence reference is orphaned — every ref resolves to a span, and every
     span is referenced (bidirectional);
  6. the compact transport form is a deterministic serialization of the same
     governed dict, so it can never become a second source of truth;
  7. each repeated source string exists exactly once across the payload — the
     direct test of the whole exercise;
  8. DMN/XACML cannot silently contradict the canonical, because no second
     notation of the rule is carried — only a `dmn_status`.

Plus the standing constraints: the document's words survive **uncut**
(constraint 4); no generated rule *name* is anywhere in the payload — a rule is
carried by `rule_id` (constraint 8); and absent / empty / default stay distinct
where the distinction carries meaning (constraint 5).

Constraint 1: every size or count asserted here is the fixture's own, taken with
`len(...)` or set-equality. No observed corpus count, and no policy name, is
written into the logic or the assertions.
"""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from policy_platform.contracts.conditions import AllCondition
from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    CanonicalRuleType,
    RuleFormulation,
)
from policy_platform.contracts.policy import (
    EvidenceReference,
    RuleException,
    RuleLineage,
)
from policy_platform.domain.models import (
    Base,
    CandidateRule,
    DocumentProvision,
    DocumentVersion,
    ExtractionRun,
    PolicySet,
    SourceDocument,
)
from policy_platform.infrastructure.projection.policy_case_payload import (
    PROJECTION,
    REPRESENTATION,
    build_case_payload,
    case_payload_for_provision,
    to_compact,
    to_pretty,
)
from tests.fixtures.factories import make_rule


# JSONB and UUID are Postgres-only. Compiling them for SQLite lets the real
# tables be created, so the real columns and the real query run under the test.
@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


_EMPTY = AllCondition(all=[])

# A distinctive, name-like string parked in `title` — the payload field closest
# to a generated name. It must never surface in the lean projection.
_NAME_LIKE = "NAMED-BY-APP::do-not-emit"


def _formulated(
    rule_id: str,
    *,
    source_text: str,
    subject: str,
    modality: str = "must",
    predicate: str | None = "comply with",
    object_: str | None = None,
    threshold: str | None = None,
    unit: str | None = None,
    clause_id: str = "E000050",
    document_version_id: str = "version-1",
    exceptions: list[RuleException] | None = None,
    **rule_overrides,
):
    """A real rule with a canonical formulation and one piece of evidence.

    Built the way extraction writes them — a canonical subject/predicate/object
    the read path derives attributes and facts from — so the projection runs
    over the same shapes it meets in production, not a hand-shaped stub. A
    name-like `title` and real run history ride along, so the tests can prove
    they are left behind.
    """

    canonical = CanonicalPolicy(
        source_text=source_text,
        rule=CanonicalPolicyRule(
            rule_type=CanonicalRuleType.OBLIGATION,
            subject=subject,
            modality=modality,
            predicate=predicate,
            object=object_,
            threshold=threshold,
            unit=unit,
        ),
    )
    update = {
        "title": _NAME_LIKE,
        "description": source_text,
        "formulation": RuleFormulation(canonical=canonical),
        "evidence": [
            EvidenceReference(
                document_version_id=document_version_id,
                source_hash="h" * 16,
                page=7,
                section="3. Conditions of Work",
                clause_id=clause_id,
                start_offset=3,
                end_offset=99,
            )
        ],
        "lineage": RuleLineage(
            extraction_run_id="run-should-not-survive",
            deployment_name="gpt-should-not-survive",
            prompt_version="p-should-not-survive",
            source_elements=clause_id,
        ),
        "exceptions": exceptions or [],
    }
    update.update(rule_overrides)
    return make_rule(rule_id, _EMPTY).model_copy(update=update)


def _one(rule, **envelope):
    """Project a single rule and return the whole ``grounding_projection_v1``."""

    return build_case_payload(
        policy_set_id=envelope.get("policy_set_id", "set-1"),
        provision_id=envelope.get("provision_id", "prov-1"),
        provision_key=envelope.get("provision_key", "key-1"),
        heading_path=envelope.get("heading_path", ["A heading the document wrote"]),
        rules=[rule],
    )


def _keys_everywhere(node) -> set[str]:
    """Every dict key appearing anywhere in a nested structure."""

    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(key)
            found |= _keys_everywhere(value)
    elif isinstance(node, list):
        for item in node:
            found |= _keys_everywhere(item)
    return found


def _strings_everywhere(node) -> list[str]:
    """Every string value appearing anywhere in a nested structure.

    Keys are structure, not content, so they are not collected; only values are.
    Used to prove a source string is stored exactly once.
    """

    out: list[str] = []
    if isinstance(node, dict):
        for value in node.values():
            out += _strings_everywhere(value)
    elif isinstance(node, list):
        for item in node:
            out += _strings_everywhere(item)
    elif isinstance(node, str):
        out.append(node)
    return out


def _primary_span(payload: dict, rule: dict) -> dict:
    """The span a rule is quoted from — its first evidence reference."""

    return payload["spans"][rule["evidence_refs"][0]]


# --------------------------------------------------------------------------- #
# Constraint 4 — the document's words survive the projection uncut.
# --------------------------------------------------------------------------- #
def test_the_verbatim_source_survives_the_projection_uncut() -> None:
    """A long exact quote comes back byte-for-byte through its span, not trimmed.

    Equality, not containment: a truncation that kept the opening and dropped
    the tail would pass a substring check while losing exactly the clause a
    verdict might turn on. The quote is resolved the way a consumer resolves it —
    through the rule's `evidence_refs` into the span dictionary.
    """

    subject = "An employee's conduct"
    quote = (
        "The guiding policy relating to conditions of work is that the quality of "
        "work and the atmosphere in which it is done be consistent with the "
        "reputation of the institution as a leading centre of learning, and that "
        f"{subject.lower()} be governed by that same standard at all times."
    )

    payload = _one(_formulated("AI-verbatim01", source_text=quote, subject=subject))
    rule = payload["rules"][0]

    # The anchor quote, whole, resolved through the grounding reference.
    assert _primary_span(payload, rule)["text"] == quote

    # The attribute carrying the subject references a fact whose source phrase is
    # the document's words, verbatim.
    applies = {a["attribute"]: a for a in rule["attributes"]["applies"]}
    subject_ref = applies["subject"]["fact_ref"]
    assert payload["facts"][subject_ref]["source_phrase"] == subject


# --------------------------------------------------------------------------- #
# Constraint 8 — a generated name never enters the lean payload.
# --------------------------------------------------------------------------- #
def test_no_generated_rule_name_appears_anywhere_in_the_lean_payload() -> None:
    """Rules are carried by id; no name-like field or value leaks through.

    Two guards. Structural: none of the keys a *rule name* would ride in
    (`title`, `display_name`, `rule_name`, ...) exists anywhere in the payload.
    Textual: the distinctive name-like string parked in each rule's `title` is
    absent from the serialized JSON. Together they show the projection reads the
    record's operative content and leaves its labels behind.

    Note `name` is deliberately not banned: `PolicyFact.name` is a stable
    identifier derived from the document's own phrase (carried beside it as
    `source_phrase`), not a generated rule label — that is content, not a name.
    """

    payload = build_case_payload(
        policy_set_id="set-1",
        provision_id="prov-1",
        provision_key="key-1",
        heading_path=["A heading the document wrote"],
        rules=[
            _formulated("AI-name0001", source_text="A must comply.", subject="A"),
            _formulated("AI-name0002", source_text="B must comply.", subject="B"),
        ],
    )

    # Every rule is carried, by id.
    assert [rule["rule_id"] for rule in payload["rules"]] == ["AI-name0001", "AI-name0002"]

    keys = _keys_everywhere(payload)
    for banned in ("title", "display_name", "generated_name", "rule_name", "group_label"):
        assert banned not in keys, f"a name-carrying key {banned!r} leaked into the lean payload"

    # No rule carries a name or its source sentence at its own top level: a rule
    # is identified by `rule_id`, and its words live once in the span dictionary.
    # (`description` still appears on an *exception*, where it is that carve-out's
    # own verbatim text — content, not a rule name.)
    for rule in payload["rules"]:
        assert "title" not in rule
        assert "description" not in rule

    serialized = to_compact(payload)
    assert _NAME_LIKE not in serialized
    # `rule_id` is the identity that is kept, so it is present.
    assert "AI-name0001" in serialized


# --------------------------------------------------------------------------- #
# Constraint 5 — absent / empty / default stay distinct where meaning turns on it.
# --------------------------------------------------------------------------- #
def test_a_facts_data_type_stays_an_explicit_null_not_an_omitted_key() -> None:
    """A fact whose phrase named no kind keeps `data_type: null`, not absence.

    "the document named no type here" and "this field was never carried" are
    different claims; dropping the key would collapse them into one.
    """

    payload = _one(
        _formulated("AI-fourstate1", source_text="The employee must comply.", subject="the employee")
    )
    subject_fact = next(iter(payload["facts"].values()))

    assert "data_type" in subject_fact
    assert subject_fact["data_type"] is None


def test_required_facts_is_emitted_even_when_empty_on_an_ai_rule() -> None:
    """`required_facts: []` is meaningful on an AI-ready rule, so it is emitted.

    The rule's test is words, not named quantities — there are no required facts
    *because the rule needs none*, which is not the same as the field never being
    computed. Omitting it would let a reader infer the latter (constraint 5).
    """

    payload = _one(_formulated("AI-reqfacts01", source_text="Attend punctually.", subject="staff"))
    rule = payload["rules"][0]

    assert "required_facts" in rule
    assert rule["required_facts"] == []


def test_a_pure_carve_out_exception_keeps_its_null_limit() -> None:
    """An exception with no numeric limit keeps `limit_value: null`, not gone.

    "up to 15 days" and "a carve-out with no stated ceiling" are different
    exceptions; the projection preserves the structured limit's explicit absence
    rather than dropping the keys and making the two read alike.
    """

    payload = _one(
        _formulated(
            "AI-exception1",
            source_text="Attendance is required, except where excused.",
            subject="attendance",
            exceptions=[
                RuleException(exception_id="ex-open", description="where excused"),
                RuleException(
                    exception_id="ex-capped",
                    description="up to 15 days for a sick family member",
                    limit_value=15.0,
                    limit_unit="days",
                ),
            ],
        )
    )
    rule = payload["rules"][0]

    by_id = {item["exception_id"]: item for item in rule["exceptions"]}
    # The prose is kept verbatim.
    assert by_id["ex-open"]["description"] == "where excused"
    # The open carve-out keeps its null limit, key and all.
    assert "limit_value" in by_id["ex-open"]
    assert by_id["ex-open"]["limit_value"] is None
    # The capped one keeps its stated magnitude.
    assert by_id["ex-capped"]["limit_value"] == 15.0
    assert by_id["ex-capped"]["limit_unit"] == "days"


# --------------------------------------------------------------------------- #
# Structure — a lean *policy* (constraint 2), the four sections, the identity.
# --------------------------------------------------------------------------- #
def test_the_projection_declares_its_identity_and_four_sections() -> None:
    """The wrapper is a policy: its flavour, its envelope, and its dictionaries.

    And the envelope carries the identity the user scoped in — policy id,
    provision id, and (through the spans) the search/AI document id — with the
    heading path copied verbatim.
    """

    payload = _one(
        _formulated("AI-struct001", source_text="X must comply.", subject="X",
                    clause_id="E000123", document_version_id="ver-77"),
        heading_path=["10. Some Heading The Document Wrote"],
        policy_set_id="set-9",
        provision_id="prov-9",
        provision_key="prov-key-9",
    )

    assert payload["projection"] == PROJECTION
    assert payload["representation"] == REPRESENTATION == "canonical"
    assert set(payload) >= {"projection", "representation", "envelope", "spans", "facts", "rules"}

    envelope = payload["envelope"]
    assert envelope["policy_set_id"] == "set-9"
    assert envelope["provision_id"] == "prov-9"
    assert envelope["provision_key"] == "prov-key-9"
    assert envelope["heading_path"] == ["10. Some Heading The Document Wrote"]

    # The one clause-level id kept for tracing: the clause's Azure AI Search key,
    # computed from the rule's own evidence.
    span = _primary_span(payload, payload["rules"][0])
    assert span["clause_id"] == "E000123"
    assert span["search_document_id"] == "ver-77_E000123"


def test_run_history_and_second_notations_are_gone() -> None:
    """Everything chosen out is gone: run history, second notations, versioning.

    The drop list, made executable. Each key here is either a restatement of the
    rule in another notation (dmn table / xacml / raw canonical), the executable
    projection, or run/versioning provenance the user scoped out — none of it
    operative meaning, all of it recoverable from Flavour 1.
    """

    payload = _one(_formulated("AI-drop00001", source_text="Y must comply.", subject="Y"))
    keys = _keys_everywhere(payload)

    for dropped in (
        # Redundant second representations of the same rule.
        "dmn_decisions",
        "decision_table",
        "semantic_projection",
        "xacml_view",
        "xacml",
        "formulation",
        "condition_provenance",
        "decision_readiness",
        # Run history / provenance the identity set excludes.
        "lineage",
        "extraction_run_id",
        "deployment_name",
        "prompt_version",
        "machine_executable",
        "review_status",
        "category",
    ):
        assert dropped not in keys, f"{dropped!r} should not survive into the lean payload"

    rule = payload["rules"][0]
    # What is kept on a rule: identity, route, the operative meaning, the DMN
    # status, and the grounding references.
    assert set(rule) >= {
        "rule_id",
        "rule_type",
        "evaluation_mode",
        "ambiguity_status",
        "effect",
        "attributes",
        "facts",
        "required_facts",
        "evidence_refs",
        "dmn_status",
    }


def test_a_hand_authored_rule_without_a_formulation_projects_without_error() -> None:
    """A rule that never went through the formulator has no canonical to derive
    from; it projects with no facts and no grounding rather than failing."""

    payload = _one(make_rule("AI-handmade01", _EMPTY))
    rule = payload["rules"][0]

    assert rule["rule_id"] == "AI-handmade01"
    assert rule["attributes"] == {"applies": [], "outcome": []}
    assert rule["facts"] == []
    assert rule["evidence_refs"] == []


# --------------------------------------------------------------------------- #
# Invariant 3 — the canonical rule keeps its operative meaning, unchanged.
# --------------------------------------------------------------------------- #
def test_the_canonical_meaning_survives_modality_action_exceptions_outcome() -> None:
    """Modality, action, the outcome table and the carve-out all come through.

    These are the things a verdict turns on; a projection that dropped or altered
    any of them would change what the rule means (constraint 2 / invariant 3).
    """

    source = make_rule("AI-meaning001", _EMPTY, effect_action="grant_leave")
    rule_in = _formulated(
        "AI-meaning001",
        source_text="A manager must approve leave over ten days.",
        subject="a manager",
        modality="must",
        exceptions=[RuleException(exception_id="ex-1", description="emergencies")],
    ).model_copy(update={"effect": source.effect})

    rule = _one(rule_in)["rules"][0]

    assert rule["modality"] == "must"
    assert rule["effect"]["action"] == "grant_leave"
    assert rule["effect"]["type"] == source.effect.type.value
    assert [e["exception_id"] for e in rule["exceptions"]] == ["ex-1"]
    # The outcome table is present (the modality rides there), keeping the rule's
    # deontic force.
    assert rule["attributes"]["outcome"]


# --------------------------------------------------------------------------- #
# Invariant 7 — each repeated source string exists exactly once.
# --------------------------------------------------------------------------- #
def test_a_source_string_two_rules_share_is_stored_exactly_once() -> None:
    """Two rules grounded in the same clause text carry it once, by reference.

    This is the direct test of the whole exercise: the sentence lives once, in
    the span dictionary, and both rules point at it. The count is taken over the
    payload's own string values, not against any corpus number.
    """

    sentence = "Attendance records are retained for the statutory retention period."
    payload = build_case_payload(
        policy_set_id="set-1",
        provision_id="prov-1",
        provision_key="key-1",
        heading_path=["A heading"],
        rules=[
            _formulated("AI-share0001", source_text=sentence, subject="records",
                        clause_id="E000050", document_version_id="v-1"),
            _formulated("AI-share0002", source_text=sentence, subject="retention",
                        clause_id="E000050", document_version_id="v-1"),
        ],
    )

    # Exactly one span carries the sentence, and it appears once in the payload.
    carrying = [s for s in payload["spans"].values() if s.get("text") == sentence]
    assert len(carrying) == 1
    assert _strings_everywhere(payload).count(sentence) == 1

    # Both rules point at that one span.
    ref0 = payload["rules"][0]["evidence_refs"][0]
    ref1 = payload["rules"][1]["evidence_refs"][0]
    assert ref0 == ref1


def test_a_fact_two_rules_share_is_stored_once_and_referenced_by_both() -> None:
    """A repeated fact phrase lives once in the dictionary; rules reference it.

    The phrase the user saw twice — once in an attribute, once in the fact model
    — is now one stored string pointed at from both places.
    """

    phrase = "the employee"
    payload = build_case_payload(
        policy_set_id="set-1",
        provision_id="prov-1",
        provision_key="key-1",
        heading_path=["A heading"],
        rules=[
            _formulated("AI-fact00001", source_text="First clause.", subject=phrase),
            _formulated("AI-fact00002", source_text="Second clause.", subject=phrase),
        ],
    )

    applies0 = {a["attribute"]: a for a in payload["rules"][0]["attributes"]["applies"]}
    applies1 = {a["attribute"]: a for a in payload["rules"][1]["attributes"]["applies"]}
    ref0 = applies0["subject"]["fact_ref"]
    ref1 = applies1["subject"]["fact_ref"]

    # Both rules reference one dictionary entry, and the phrase is stored once.
    assert ref0 == ref1
    assert ref0 in payload["facts"]
    assert _strings_everywhere(payload).count(phrase) == 1


# --------------------------------------------------------------------------- #
# Invariant 4 — no evidence reference is orphaned (bidirectional).
# --------------------------------------------------------------------------- #
def test_every_evidence_ref_resolves_and_every_span_is_referenced() -> None:
    """Refs and spans are in exact correspondence — none dangling, none unused.

    A ref that resolved to nothing would ground an answer in a passage the
    payload does not carry; a span nothing referenced would be dead weight. Both
    are failures the projection must not commit.
    """

    payload = build_case_payload(
        policy_set_id="set-1",
        provision_id="prov-1",
        provision_key="key-1",
        heading_path=["A heading"],
        rules=[
            _formulated("AI-ref000001", source_text="One.", subject="a", clause_id="E1"),
            _formulated("AI-ref000002", source_text="Two.", subject="b", clause_id="E2"),
            _formulated("AI-ref000003", source_text="Three.", subject="c", clause_id="E3"),
        ],
    )

    referenced = {ref for rule in payload["rules"] for ref in rule["evidence_refs"]}
    spans = set(payload["spans"])

    # Every ref resolves to a span.
    assert referenced <= spans
    # And every span is referenced — nothing orphaned either way.
    assert spans == referenced


# --------------------------------------------------------------------------- #
# Invariant 2 — every source span keeps its hash, page, section and offsets.
# --------------------------------------------------------------------------- #
def test_the_span_keeps_hash_page_section_and_offsets() -> None:
    """The clause's provenance is preserved on the span (once), not dropped.

    Preserved on the span rather than repeated on every rule that cites it —
    de-duplication, not loss (constraints 3 and 4).
    """

    payload = _one(
        _formulated("AI-prov00001", source_text="A clause.", subject="thing",
                    clause_id="E000123", document_version_id="ver-9")
    )
    span = _primary_span(payload, payload["rules"][0])

    assert span["source_hash"] == "h" * 16
    assert span["page"] == 7
    assert span["section"] == "3. Conditions of Work"
    assert span["start_offset"] == 3
    assert span["end_offset"] == 99


# --------------------------------------------------------------------------- #
# Invariant 8 — DMN/XACML cannot silently contradict the canonical.
# --------------------------------------------------------------------------- #
def test_dmn_collapses_to_a_status_with_no_second_notation_to_contradict() -> None:
    """The DMN block becomes a status; no table, no restatement is carried.

    The block never held a decision table in the corpus and its semantic
    projection only restates the canonical, so neither is carried. What remains
    is a status string — a real per-rule signal that cannot disagree with a rule
    it does not restate.
    """

    rule = _one(_formulated("AI-dmn000001", source_text="Z must comply.", subject="Z"))["rules"][0]

    assert isinstance(rule["dmn_status"], str)
    keys = _keys_everywhere(rule)
    assert "decision_table" not in keys
    assert "semantic_projection" not in keys
    assert "xacml" not in keys


# --------------------------------------------------------------------------- #
# The envelope — values every rule shares are stored once; overrides only differ.
# --------------------------------------------------------------------------- #
def test_shared_values_are_hoisted_to_the_envelope_and_not_repeated() -> None:
    """The dates and the document id every rule shares live once.

    When two rules agree, the value is in the envelope and neither rule repeats
    it. A rule carries one of these back only when it *differs* — which is the
    whole point of the envelope.
    """

    payload = build_case_payload(
        policy_set_id="set-1",
        provision_id="prov-1",
        provision_key="key-1",
        heading_path=["A heading"],
        rules=[
            _formulated("AI-env000001", source_text="One.", subject="a", document_version_id="v-1"),
            _formulated("AI-env000002", source_text="Two.", subject="b", document_version_id="v-1"),
        ],
    )

    envelope = payload["envelope"]
    # The shared document id and effective date are hoisted.
    assert envelope["document_version_id"] == "v-1"
    assert "effective_from" in envelope
    # Drafting provenance is dropped, not hoisted, so it is absent even here.
    assert "authority" not in envelope

    # And no rule repeats the shared values.
    for rule in payload["rules"]:
        assert "authority" not in rule
        assert "effective_from" not in rule
        assert "document_version_id" not in rule


def test_a_real_difference_between_rules_is_never_erased() -> None:
    """When rules disagree on a value, de-duplication must not flatten them.

    The envelope hoists only what *every* rule shares, so a field the rules
    disagree on stays off the envelope and each rule carries its own — the
    outlier's distinct effective date survives intact rather than being
    silently unified with its sibling's.
    """

    from datetime import date

    payload = build_case_payload(
        policy_set_id="set-1",
        provision_id="prov-1",
        provision_key="key-1",
        heading_path=["A heading"],
        rules=[
            _formulated("AI-ovr000001", source_text="One.", subject="a"),
            _formulated(
                "AI-ovr000002",
                source_text="Two.",
                subject="b",
                effective_from=date(2030, 1, 1),
            ),
        ],
    )

    envelope = payload["envelope"]
    # Nothing shared to hoist, so the disputed date stays off the envelope.
    assert "effective_from" not in envelope

    first, second = payload["rules"]
    # Each rule keeps its own value; the difference is preserved, not collapsed.
    assert second["effective_from"] == "2030-01-01"
    assert "effective_from" in first
    assert first["effective_from"] != second["effective_from"]


def test_drafting_provenance_authority_is_never_carried() -> None:
    """The `authority` marker is drafting provenance, so it is dropped entirely.

    It records who drafted a candidate and at what draft rank — not the policy's
    meaning — so it belongs with run history, not with the content a model reads.
    It must appear neither in the envelope nor on any rule, even when every rule
    shares it, the case where hoisting would otherwise have kept a single copy.
    """

    payload = build_case_payload(
        policy_set_id="set-1",
        provision_id="prov-1",
        provision_key="key-1",
        heading_path=["A heading"],
        rules=[
            _formulated("AI-prov00001", source_text="One.", subject="a"),
            _formulated("AI-prov00002", source_text="Two.", subject="b"),
        ],
    )

    assert "authority" not in payload["envelope"]
    for rule in payload["rules"]:
        assert "authority" not in rule


# --------------------------------------------------------------------------- #
# Invariant 6 — the compact transport form is a deterministic serialization.
# --------------------------------------------------------------------------- #
def test_the_compact_form_is_a_deterministic_view_never_a_second_source() -> None:
    """Compact bytes parse back to the same governed dict, byte-stable each time.

    The compact form is generated from the dict, so it can never drift into a
    second source of truth: parsing it yields exactly the dict it came from, and
    serializing twice yields the same bytes.
    """

    payload = _one(_formulated("AI-compact001", source_text="A must comply.", subject="A"))

    compact = to_compact(payload)
    # No indentation — it is the transport form.
    assert "\n" not in compact
    # Deterministic, and a faithful view of the same dict.
    assert to_compact(payload) == compact
    assert json.loads(compact) == payload
    # The pretty diagnostic form is the same content, just indented.
    assert json.loads(to_pretty(payload)) == payload


def test_arabic_source_text_survives_uncut_and_unescaped() -> None:
    """Mixed Arabic/English source is preserved exactly (constraint 9).

    The transport serializer must not escape non-ASCII — an escaped payload would
    read as gibberish to a model and hide whether the words survived.
    """

    arabic = "يجب على الموظف الالتزام بقواعد السلوك المهني في جميع الأوقات."
    payload = _one(_formulated("AI-arabic001", source_text=arabic, subject="الموظف"))

    span = _primary_span(payload, payload["rules"][0])
    assert span["text"] == arabic
    # Present literally in the transport bytes, not as \uXXXX escapes.
    assert arabic in to_compact(payload)


# --------------------------------------------------------------------------- #
# Invariant 1 — at policy scale every live rule and passage is represented.
# --------------------------------------------------------------------------- #
async def _session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    return maker(), engine


_SET_ID = uuid.UUID("00000000-0000-4000-8000-0000000000c1")
_VERSION_ID = uuid.UUID("00000000-0000-4000-8000-0000000000c2")
_RUN_ID = uuid.UUID("00000000-0000-4000-8000-0000000000c3")
_DOC_ID = uuid.UUID("00000000-0000-4000-8000-0000000000c4")
_PROVISION_ID = uuid.UUID("00000000-0000-4000-8000-0000000000c5")
_OTHER_PROVISION_ID = uuid.UUID("00000000-0000-4000-8000-0000000000c6")


async def _seed(session: AsyncSession, *, live_rule_ids: list[str]) -> None:
    """One provision carrying `live_rule_ids`, plus two rules that must NOT come
    back: one superseded, one filed under a different provision."""

    session.add(PolicySet(id=_SET_ID, key="scale-guard", name="scale-guard", owner="guard"))
    session.add(SourceDocument(id=_DOC_ID, title="Handbook", owner="guard", policy_set_id=_SET_ID))
    session.add(
        DocumentVersion(
            id=_VERSION_ID,
            document_id=_DOC_ID,
            version_number=1,
            content_hash="c" * 64,
            storage_path="/handbook.pdf",
        )
    )
    session.add(ExtractionRun(id=_RUN_ID, document_version_id=_VERSION_ID, status="succeeded"))
    for provision_id in (_PROVISION_ID, _OTHER_PROVISION_ID):
        session.add(
            DocumentProvision(
                id=provision_id,
                policy_set_id=_SET_ID,
                document_version_id=_VERSION_ID,
                provision_key=f"key-{provision_id.hex[-2:]}",
                heading_path_json=["10. A Heading"],
                heading_element_ids_json=["E000050"],
                first_sequence=0,
            )
        )

    counter = 0
    for rule_id in live_rule_ids:
        counter += 1
        session.add(
            CandidateRule(
                id=uuid.UUID(int=counter),
                policy_set_id=_SET_ID,
                extraction_run_id=_RUN_ID,
                provision_id=_PROVISION_ID,
                rule_type="obligation",
                review_status="candidate",
                delta_status="new",
                payload_json=_formulated(
                    rule_id, source_text=f"{rule_id} states something.", subject=rule_id
                ).model_dump(mode="json"),
            )
        )

    # A superseded rule in the same provision — current reads exclude it.
    from datetime import datetime, timezone

    session.add(
        CandidateRule(
            id=uuid.UUID(int=9001),
            policy_set_id=_SET_ID,
            extraction_run_id=_RUN_ID,
            provision_id=_PROVISION_ID,
            rule_type="obligation",
            review_status="candidate",
            delta_status="changed",
            superseded_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            payload_json=_formulated(
                "AI-superseded", source_text="Old wording.", subject="old"
            ).model_dump(mode="json"),
        )
    )
    # A live rule under a different provision — not this policy.
    session.add(
        CandidateRule(
            id=uuid.UUID(int=9002),
            policy_set_id=_SET_ID,
            extraction_run_id=_RUN_ID,
            provision_id=_OTHER_PROVISION_ID,
            rule_type="obligation",
            review_status="candidate",
            delta_status="new",
            payload_json=_formulated(
                "AI-elsewhere", source_text="Another policy.", subject="other"
            ).model_dump(mode="json"),
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_every_live_rule_and_passage_is_present_in_the_projection() -> None:
    """No rule or passage is silently dropped at policy scale (invariant 1).

    Set-equality over rule ids and over passage texts, not a length check: it
    fails on a drop of any size and on any extra, which is the property a
    reviewer needs when the empty place a lost rule leaves is indistinguishable
    from a policy that never wrote it. The superseded rule and the other
    provision's rule are the negative controls — the current set is exactly this
    provision's live rules. Compared against the seeded source, never a number.
    """

    # A fixture large enough that rules outnumber anything a stray default page
    # would keep. The exact number is the fixture's own; no corpus size appears.
    live_rule_ids = [f"AI-scale{index:04d}" for index in range(37)]

    session, engine = await _session()
    try:
        await _seed(session, live_rule_ids=live_rule_ids)

        payload = await case_payload_for_provision(session, _PROVISION_ID)

        assert payload is not None
        # Every live rule, and only those.
        returned = {rule["rule_id"] for rule in payload["rules"]}
        assert returned == set(live_rule_ids)
        assert "AI-superseded" not in returned
        assert "AI-elsewhere" not in returned

        # Every rule's passage is represented in the span dictionary.
        passages = {span["text"] for span in payload["spans"].values() if "text" in span}
        assert passages == {f"{rule_id} states something." for rule_id in live_rule_ids}
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_an_unknown_provision_yields_none_not_an_empty_policy() -> None:
    """A provision id that resolves to nothing returns `None`, so a caller can
    answer a 404 rather than serve an empty policy that looks real."""

    session, engine = await _session()
    try:
        await _seed(session, live_rule_ids=["AI-only0001"])
        missing = uuid.UUID("00000000-0000-4000-8000-0000000000ff")

        assert await case_payload_for_provision(session, missing) is None
    finally:
        await session.close()
        await engine.dispose()
