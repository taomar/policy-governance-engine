"""Flavour 2 — the lean projection keeps a rule's meaning and drops its notation.

The lean payload is what a model reads when the case-testing mechanism asks it
to judge a case. So the properties pinned here are the ones that decide whether
that judgement can be trusted:

  * the document's own words survive **uncut** — the quote is the ground truth a
    verdict is checked against, and a projection that trimmed it to save bytes
    would have destroyed the one thing that makes the answer checkable
    (constraint 4);
  * no generated rule *name* is anywhere in the payload — a cited rule is cited
    by `rule_id`, and the interface resolves the name, so a name that drifted
    into the payload would let a model quote a label no reviewer wrote
    (constraint 8);
  * at policy scale every live rule is present — a lean form that silently
    dropped a rule would test the model against a policy missing a clause, and
    the empty place would look exactly like a policy that never stated it
    (constraint 10);
  * an absent `fact` stays an explicit `null`, not an omitted key — "the
    document supplies this value itself" and "the schema never carried this"
    are different claims and must not collapse into one (constraint 5).

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
    FLAVOR,
    REPRESENTATION,
    build_case_payload,
    case_payload_for_provision,
    lean_rule,
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
):
    """A real rule with a canonical formulation and one piece of evidence.

    Built the way extraction writes them — a canonical subject/predicate/object
    the read path derives attributes and facts from — so the projection runs
    over the same shapes it meets in production, not a hand-shaped stub.
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
    return make_rule(rule_id, _EMPTY).model_copy(
        update={
            # A name-like label in the record, plus real run history — both of
            # which the lean form must leave behind.
            "title": _NAME_LIKE,
            "description": source_text,
            "formulation": RuleFormulation(canonical=canonical),
            "evidence": [
                EvidenceReference(
                    document_version_id=document_version_id,
                    source_hash="h" * 16,
                    page=7,
                    section="ignored heading",
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


# --------------------------------------------------------------------------- #
# Constraint 4 — the document's words survive the projection uncut.
# --------------------------------------------------------------------------- #
def test_the_verbatim_source_survives_the_projection_uncut() -> None:
    """A long exact quote comes back byte-for-byte, not trimmed to a budget.

    Equality, not containment: a truncation that kept the opening and dropped
    the tail would pass a substring check while losing exactly the clause a
    verdict might turn on.
    """

    subject = "An employee's conduct"
    quote = (
        "The guiding policy relating to conditions of work is that the quality of "
        "work and the atmosphere in which it is done be consistent with the "
        "reputation of the institution as a leading centre of learning, and that "
        f"{subject.lower()} be governed by that same standard at all times."
    )

    projected = lean_rule(
        _formulated("AI-verbatim01", source_text=quote, subject=subject)
    )

    # The anchor quote, whole.
    assert projected["source_text"] == quote

    # The attribute carrying the subject shows the document's words, verbatim.
    applies = {attr["attribute"]: attr for attr in projected["attributes"]["applies"]}
    assert applies["subject"]["text"] == subject

    # And the fact named from that phrase keeps the phrase, verbatim, uncut.
    subject_facts = [fact for fact in projected["facts"] if fact["source_phrase"] == subject]
    assert subject_facts, "the subject phrase should name a fact, carried verbatim"


# --------------------------------------------------------------------------- #
# Constraint 8 — a generated name never enters the lean payload.
# --------------------------------------------------------------------------- #
def test_no_generated_rule_name_appears_anywhere_in_the_lean_payload() -> None:
    """Rules are carried by id; no name-like field or value leaks through.

    Two guards. Structural: none of the keys a *rule name* would ride in
    (`title`, `display_name`, `rule_name`, ...) exists anywhere in the payload.
    Textual: the distinctive name-like string parked in each rule's `title` is
    absent from the serialized JSON. Together they show the projection reads
    the record's operative content and leaves its labels behind.

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

    serialized = json.dumps(payload, ensure_ascii=False)
    assert _NAME_LIKE not in serialized
    # `rule_id` is the identity that is kept, so it is present.
    assert "AI-name0001" in serialized


# --------------------------------------------------------------------------- #
# Constraint 5 — absent and stated are different states, kept different.
# --------------------------------------------------------------------------- #
def test_an_absent_fact_stays_an_explicit_null_not_an_omitted_key() -> None:
    """`fact: null` (document supplies the value) is not collapsed to absence.

    A modality names no fact, so its attribute's `fact` is `None`; a subject
    does, so its `fact` is set. The projection must keep the `fact` key on both
    — dropping it on the null one would erase the distinction between "the case
    supplies nothing here" and "this field was never carried".
    """

    projected = lean_rule(
        _formulated(
            "AI-fourstate1",
            source_text="The employee must comply.",
            subject="the employee",
            modality="must",
        )
    )

    applies = {attr["attribute"]: attr for attr in projected["attributes"]["applies"]}
    outcome = {attr["attribute"]: attr for attr in projected["attributes"]["outcome"]}

    # The subject names a fact: key present, value set.
    assert "fact" in applies["subject"]
    assert applies["subject"]["fact"] is not None

    # The modality names none: key present, value explicitly null.
    assert "fact" in outcome["modality"]
    assert outcome["modality"]["fact"] is None

    # `data_type` obeys the same rule: present, null when the phrase states none.
    assert "data_type" in outcome["modality"]
    assert outcome["modality"]["data_type"] is None


def test_a_pure_carve_out_exception_keeps_its_null_limit() -> None:
    """An exception with no numeric limit keeps `limit_value: null`, not gone.

    "up to 15 days" and "a carve-out with no stated ceiling" are different
    exceptions; the projection preserves the structured limit's explicit
    absence rather than dropping the keys and making the two read alike.
    """

    projected = lean_rule(
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

    by_id = {item["exception_id"]: item for item in projected["exceptions"]}
    # The prose is kept verbatim.
    assert by_id["ex-open"]["description"] == "where excused"
    # The open carve-out keeps its null limit, key and all.
    assert "limit_value" in by_id["ex-open"]
    assert by_id["ex-open"]["limit_value"] is None
    # The capped one keeps its stated magnitude.
    assert by_id["ex-capped"]["limit_value"] == 15.0
    assert by_id["ex-capped"]["limit_unit"] == "days"


# --------------------------------------------------------------------------- #
# Structure — a lean *policy* with its rules nested, and only what was chosen.
# --------------------------------------------------------------------------- #
def test_the_lean_policy_declares_its_flavour_identity_and_grounding() -> None:
    """The wrapper is a policy: flavour, identity, headings, rules nested.

    And each rule grounds to its clause's Azure AI Search key, computed from the
    rule's own evidence — the one clause-level id kept for tracing an answer.
    """

    payload = build_case_payload(
        policy_set_id="set-9",
        provision_id="prov-9",
        provision_key="prov-key-9",
        heading_path=["10. Some Heading The Document Wrote"],
        rules=[
            _formulated(
                "AI-struct001",
                source_text="X must comply.",
                subject="X",
                clause_id="E000123",
                document_version_id="ver-77",
            )
        ],
    )

    assert payload["flavor"] == FLAVOR
    assert payload["representation"] == REPRESENTATION == "canonical"
    assert payload["policy_set_id"] == "set-9"
    assert payload["provision_id"] == "prov-9"
    assert payload["provision_key"] == "prov-key-9"
    assert payload["heading_path"] == ["10. Some Heading The Document Wrote"]
    assert payload["rule_count"] == len(payload["rules"]) == 1

    grounding = payload["rules"][0]["grounding"]
    assert grounding == [{"search_document_id": "ver-77_E000123", "clause_id": "E000123"}]


def test_the_lean_rule_drops_run_history_and_redundant_notations() -> None:
    """Everything chosen out is gone: run history, second notations, versioning.

    The drop list, made executable. Each key here is either a restatement of the
    rule in another notation (dmn/xacml/raw canonical), the executable
    projection (condition/required_facts), or run/versioning provenance the user
    scoped out — none of it operative meaning, all of it recoverable from
    Flavour 1.
    """

    rule = lean_rule(
        _formulated("AI-drop00001", source_text="Y must comply.", subject="Y")
    )
    keys = _keys_everywhere(rule)

    for dropped in (
        # Redundant second representations of the same rule.
        "dmn_decisions",
        "xacml_view",
        "formulation",
        "condition",
        "condition_provenance",
        "required_facts",
        "decision_readiness",
        # Run history / provenance / versioning.
        "lineage",
        "schema_version",
        "policy_version_id",
        "rule_revision",
        "authority",
        "machine_executable",
        "review_status",
        # Metadata the identity set excludes.
        "scope",
        "category",
        "tags",
        "related_rule_ids",
        "priority",
        "effective_from",
        "effective_to",
        # Evidence provenance beyond the grounding key.
        "source_hash",
        "start_offset",
        "end_offset",
    ):
        assert dropped not in keys, f"{dropped!r} should not survive into the lean rule"

    # What is kept: identity, the route, the verbatim source, the operative
    # meaning, and the grounding key.
    assert set(rule) >= {
        "rule_id",
        "rule_type",
        "evaluation_mode",
        "ambiguity_status",
        "source_text",
        "effect",
        "attributes",
        "facts",
        "grounding",
    }


def test_a_hand_authored_rule_without_a_formulation_projects_without_error() -> None:
    """A rule that never went through the formulator has no canonical to derive
    from; it projects with an empty source quote rather than failing."""

    projected = lean_rule(make_rule("AI-handmade01", _EMPTY))

    assert projected["rule_id"] == "AI-handmade01"
    assert projected["source_text"] == ""
    assert projected["attributes"] == {"applies": [], "outcome": []}


# --------------------------------------------------------------------------- #
# Constraint 10 — at policy scale, every live rule is present, and only those.
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
async def test_every_live_rule_in_the_record_is_present_in_the_lean_policy() -> None:
    """No rule is silently dropped at policy scale, and no stranger creeps in.

    Set-equality over rule ids, not a length check: it fails on a drop of any
    size and on any extra, which is the property a reviewer needs when the empty
    place a lost rule leaves is indistinguishable from a policy that never wrote
    it. The superseded rule and the other provision's rule are the negative
    controls — the current set is exactly this provision's live rules.
    """

    # A fixture large enough that rules outnumber anything a stray default page
    # would keep. The exact number is the fixture's own; no corpus size appears.
    live_rule_ids = [f"AI-scale{index:04d}" for index in range(37)]

    session, engine = await _session()
    try:
        await _seed(session, live_rule_ids=live_rule_ids)

        payload = await case_payload_for_provision(session, _PROVISION_ID)

        assert payload is not None
        returned = {rule["rule_id"] for rule in payload["rules"]}
        assert returned == set(live_rule_ids)
        # Whole, not a prefix; and nothing extra folded in.
        assert payload["rule_count"] == len(payload["rules"]) == len(live_rule_ids)
        assert "AI-superseded" not in returned
        assert "AI-elsewhere" not in returned
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
