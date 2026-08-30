"""Two copies of one policy are one policy, and the budget must count it once.

THE DEFECT THIS FILE HOLDS

Receipt `76a5e936-7ea4-4cc3-828a-0fb099c2ee5b`, question "What do the policies say
about laptop replacement eligibility, and is my 26-month-old laptop eligible
now?". The information track answered. The verdict came back
`not_settled_by_rules`.

The retention budget is five, and the five retained were: two copies of `2.1
Standard entitlement`, two copies of `4.2 Accidental damage`, and `4.4
Lost/stolen`. `3.1 Standard refresh interval` — the provision that decides
whether a 26-month-old laptop is eligible — ranked sixth and was discarded
`outside_budget`. The duplicated provisions carried different provision ids and
different provision keys because they were extracted from two document versions,
and their published records were identical once identity and provenance were
removed.

Nothing ranked wrongly and nothing was hidden. The budget is a budget of
*distinct policies to read*, and it was being spent on copies. A reviewer was told
the rules do not settle their case when the rule that settles it was never read.

WHAT IS ASSERTED HERE

  * an exact duplicate carrying different ids, keys, document versions and span
    references is collapsed, and the slot it would have taken goes to the next
    distinct policy — the one the live receipt never reached;
  * the collapse is *content*, never a heading: the same heading with a changed
    rule, a changed source sentence, a changed effective window, a narrowed scope
    or a different authority survives as its own policy and is read;
  * the choice of representative and the resulting receipt are deterministic,
    including when two copies score identically and the index returns them in
    either order;
  * the disclosure stays honest — every raw candidate is still in `considered`,
    each collapsed copy keeps its own rank and score, carries
    `duplicate_policy_content`, and names the representative that stood in for
    it — and the receipt and decision hash agree with it;
  * the two later narrowings are untouched: rule slicing above fifteen rules and
    the payload-budget fitting behave exactly as they did.

Nothing here names a real document. What is asserted is the *relationship*
between duplicated content, the budget and what was evaluated, which must hold
for any governance corpus.
"""
from __future__ import annotations

import json
import os
from typing import Any

import pytest

os.environ.setdefault("DATABASE_URL", "******localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "******localhost:5433/test")

from policy_platform.contracts.conditions import AllCondition  # noqa: E402
from policy_platform.contracts.formulation import CanonicalPolicy, RuleFormulation  # noqa: E402
from policy_platform.contracts.policy import (  # noqa: E402
    EvidenceReference,
    PolicyAuthority,
    PolicyScope,
    RequiredFact,
)
from policy_platform.infrastructure.assistants import ai_case_intent, ai_case_project  # noqa: E402
from policy_platform.infrastructure.projection import policy_rule_slice as rule_slice  # noqa: E402
from policy_platform.infrastructure.projection.policy_case_payload import (  # noqa: E402
    build_case_payload,
)
from policy_platform.infrastructure.projection.policy_semantic_identity import (  # noqa: E402
    policy_semantic_core,
    policy_semantic_fingerprint,
)
from policy_platform.infrastructure.projection.published_case_payload import (  # noqa: E402
    governing_extras_for_group,
)
from policy_platform.infrastructure.search.policy_index import policy_document_id  # noqa: E402
from tests.fixtures.factories import make_rule  # noqa: E402
from tests.fixtures.search_stubs import manifest_ids  # noqa: E402

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


#: The active published version every candidate below belongs to.
_PV = "33333333-3333-4333-8333-333333333333"

#: Two document versions. The duplicated provisions were extracted from these
#: two, which is why every id, key and span reference differs between the copies
#: while the words and the terms do not.
_DOC_A = "11111111-1111-4111-8111-111111111111"
_DOC_B = "22222222-2222-4222-8222-222222222222"

_ENTITLEMENT = "2.1 Standard entitlement"
_REFRESH = "3.1 Standard refresh interval"


def _policy_rules(
    *,
    marker: str,
    document_version_id: str,
    source_text: str,
    effective_from: str = "2024-01-01",
    effective_to: str | None = None,
    scope: PolicyScope | None = None,
    authority: PolicyAuthority | None = None,
    required_fact: str | None = None,
) -> list:
    """One policy's rules, with every identity token tied to `marker`/document.

    `marker` drives the rule ids and clause ids, so two calls that differ only in
    `marker` and `document_version_id` produce records that share every governing
    term and no identifier at all — which is exactly the corpus shape that caused
    the defect.
    """

    from datetime import date

    def _date(value: str | None):
        return None if value is None else date.fromisoformat(value)

    rule = make_rule(
        f"AI-{marker}-0",
        condition=AllCondition(all=[]),
        effective_from=_date(effective_from),
        effective_to=_date(effective_to),
        scope=scope,
        authority=authority,
    )
    update: dict[str, Any] = {
        "title": "Standard entitlement",
        "description": "What the policy provides.",
        "formulation": RuleFormulation(canonical=CanonicalPolicy(source_text=source_text)),
        "evidence": [
            EvidenceReference(
                document_version_id=document_version_id,
                source_hash=f"{marker[:1]}" * 16,
                page=3,
                section="section 2.1",
                clause_id=f"C-{marker}-0",
                start_offset=0,
                end_offset=10,
            )
        ],
    }
    if required_fact:
        update["required_facts"] = [
            RequiredFact(name=required_fact, data_type="number", unit="months")
        ]
    return [rule.model_copy(update=update)]


def _published(
    provision_key: str,
    *,
    heading: str,
    marker: str,
    document_version_id: str,
    source_text: str,
    **kwargs: Any,
) -> tuple[dict, dict]:
    """A published policy payload plus the governing extras the payload omits.

    Mirrors what `published_case_payloads_with_extras` returns, including the
    envelope rewrite the published projection performs, so the fingerprint under
    test sees the same shape production hands it.
    """

    rules = _policy_rules(
        marker=marker,
        document_version_id=document_version_id,
        source_text=source_text,
        **kwargs,
    )
    payload = build_case_payload(
        policy_set_id="set-1",
        provision_id=f"prov-{marker}",
        provision_key=provision_key,
        heading_path=[heading],
        rules=rules,
    )
    envelope = payload["envelope"]
    envelope["policy_version_id"] = _PV
    envelope["version_number"] = 2
    return payload, governing_extras_for_group(rules)


def _candidate(provision_key: str, published: tuple[dict, dict]) -> dict:
    payload, extras = published
    envelope = payload.get("envelope") or {}
    return {
        "provision_id": envelope.get("provision_id") or f"prov-{provision_key}",
        "provision_key": provision_key,
        "heading_path": list(envelope.get("heading_path") or []),
        "rules": len(payload.get("rules") or []),
        "policy_version_id": _PV,
        "search_document_id": policy_document_id(
            policy_version_id=_PV, provision_key=provision_key
        ),
        "payload": payload,
        "governing_extras": extras,
    }


def _hit(provision_key: str, score: float) -> dict:
    return {
        "id": policy_document_id(policy_version_id=_PV, provision_key=provision_key),
        "@search.score": score,
        "policy_id": provision_key,
        "document_version": _PV,
    }


class _Settings:
    ai_enabled = True
    search_enabled = True
    azure_openai_deployment = "slow"
    azure_openai_fast_deployment = "fast"
    azure_search_authoring_index = "policy-authoring"


class _NamespacePolicySet:
    def __init__(self, set_id: str, key: str) -> None:
        self.id = set_id
        self.key = key


class _StubEmbedClient:
    def __init__(self, settings: Any) -> None:
        pass

    async def embed(self, inputs: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in inputs]


def _search_client(ranked: list[tuple[str, float]]):
    class _Client:
        def __init__(self, settings: Any) -> None:
            pass

        async def index_exists(self, *a: Any, **k: Any) -> bool:
            return True

        async def vector_search(self, *a: Any, **k: Any) -> list[dict]:
            return [_hit(key, score) for key, score in ranked]

        async def find_ids_by_filter(self, *a: Any, **k: Any) -> list[str]:
            return manifest_ids(k.get("filter_expr", ""))

    return _Client


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    *,
    candidates: list[dict],
    ranked: list[tuple[str, float]],
) -> list[list[dict]]:
    scope = {
        "has_published_version": True,
        "active_version_id": _PV,
        "active_version_number": 2,
        "candidates": candidates,
        "excluded": [],
    }

    async def _load(session: Any, policy_set_id: Any) -> dict:
        return scope

    gathered: list[list[dict]] = []

    async def _spy(
        records: list[dict], *, scenario: str, reasoning_effort: str = "medium", **kw: Any
    ) -> dict:
        gathered.append(records)
        return {
            "intent": ai_case_intent.DECISION,
            "information_requested": True,
            "verdict_requested": True,
            "classification_reasoning": "asks what the policies say and how the case comes out",
            "classifier_version": ai_case_intent.NEEDS_CLASSIFIER_VERSION,
            "informational": {
                "status": ai_case_intent.ANSWERED,
                "answered": True,
                "answer": "The policies set an entitlement and a refresh interval.",
                "citations": [],
                "note": "",
                "grounding": {"prompt_version": ai_case_intent.PROMPT_VERSION},
            },
            "decision": {
                "status": ai_case_intent.ANSWERED,
                "verdict": "eligible",
                "answer": "A 26-month-old laptop is past the refresh interval.",
                "missing_required_facts": [],
                "missing_information": [],
                "citations": [],
                "note": "",
                "grounding": {"prompt_version": ai_case_intent.PROMPT_VERSION},
            },
            "reasoning_effort": reasoning_effort,
        }

    monkeypatch.setattr(ai_case_project, "get_settings", lambda: _Settings())
    monkeypatch.setattr(ai_case_project, "load_project_scope", _load)
    monkeypatch.setattr(ai_case_project, "AzureOpenAIClient", _StubEmbedClient)
    monkeypatch.setattr(ai_case_project, "AzureSearchClient", _search_client(ranked))
    monkeypatch.setattr(ai_case_project, "answer_case_over_policies", _spy)
    return gathered


_QUESTION = (
    "What do the policies say about laptop replacement eligibility, "
    "and is my 26-month-old laptop eligible now?"
)


async def _run(scenario: str = _QUESTION) -> dict:
    return await ai_case_project.answer_project_case(
        object(), policy_set=_NamespacePolicySet("set-1", "hardware"), scenario=scenario
    )


def _entitlement(key: str, marker: str, document_version_id: str, **kwargs: Any):
    """The provision the live corpus held twice, parameterised by its copy."""

    return _published(
        key,
        heading=_ENTITLEMENT,
        marker=marker,
        document_version_id=document_version_id,
        source_text=(
            "Each employee is entitled to one standard laptop issued at the "
            "commencement of employment and maintained by the organisation."
        ),
        **kwargs,
    )


# ── the fingerprint, on its own ──────────────────────────────────────


def test_two_copies_across_document_versions_fingerprint_the_same() -> None:
    """The identity that must be seen through, stated directly.

    Different provision ids, different provision keys, different document
    versions, different rule ids, different clause ids, different source hashes —
    and therefore different span-dictionary keys and different `evidence_refs`.
    Every one of those is provenance. What the policy requires is identical, so
    the fingerprint must be.
    """

    left, left_extras = _entitlement("2760dd", "entitlement-a", _DOC_A)
    right, right_extras = _entitlement("5f0db9", "entitlement-b", _DOC_B)

    # The fixture is only worth something if the identifiers really do differ.
    assert left["envelope"]["provision_key"] != right["envelope"]["provision_key"]
    assert left["rules"][0]["rule_id"] != right["rules"][0]["rule_id"]
    assert left["rules"][0]["evidence_refs"] != right["rules"][0]["evidence_refs"]
    assert set(left["spans"]) != set(right["spans"])

    assert policy_semantic_fingerprint(
        left, governing_extras=left_extras
    ) == policy_semantic_fingerprint(right, governing_extras=right_extras)

    # And what was compared holds the words, not the tokens that point at them.
    core = policy_semantic_core(left, governing_extras=left_extras)
    serialized = json.dumps(core, sort_keys=True)
    assert "Each employee is entitled to one standard laptop" in serialized
    for token in (
        _DOC_A,
        "prov-entitlement-a",
        "2760dd",
        left["rules"][0]["rule_id"],
        left["rules"][0]["evidence_refs"][0],
    ):
        assert token not in serialized, f"{token} is identity and must not be compared"


@pytest.mark.parametrize(
    ("field", "changed"),
    [
        ("source_text", {"source_text": "Each employee is entitled to two standard laptops."}),
        ("effective_from", {"effective_from": "2025-06-01"}),
        ("effective_to", {"effective_to": "2026-12-31"}),
        ("scope", {"scope": PolicyScope(organizational_units=["field-operations"])}),
        ("authority", {"authority": PolicyAuthority(level="board", owner="CIO", rank=1)}),
        ("required_facts", {"required_fact": "laptop-age-months"}),
    ],
)
def test_the_same_heading_with_different_terms_is_a_different_policy(
    field: str, changed: dict
) -> None:
    """Heading is one component of the fingerprint and never the test.

    Each case below shares the heading `2.1 Standard entitlement` and differs in
    exactly one governing respect. Collapsing any of them would answer a case
    from one document's terms while a differently-binding version went unread —
    the failure that would make this repair worse than the defect it fixes.
    `authority` is in this list deliberately: the lean record does not carry it,
    so it reaches the comparison beside the payload rather than inside it.
    """

    base_kwargs: dict[str, Any] = {}
    if "source_text" in changed:
        base_kwargs["source_text"] = (
            "Each employee is entitled to one standard laptop issued at the "
            "commencement of employment and maintained by the organisation."
        )

    left, left_extras = _entitlement("2760dd", "entitlement-a", _DOC_A)
    right, right_extras = _published(
        "5f0db9",
        heading=_ENTITLEMENT,
        marker="entitlement-b",
        document_version_id=_DOC_B,
        source_text=changed.get(
            "source_text",
            "Each employee is entitled to one standard laptop issued at the "
            "commencement of employment and maintained by the organisation.",
        ),
        **{k: v for k, v in changed.items() if k != "source_text"},
    )

    assert left["envelope"]["heading_path"] == right["envelope"]["heading_path"]
    assert policy_semantic_fingerprint(
        left, governing_extras=left_extras
    ) != policy_semantic_fingerprint(right, governing_extras=right_extras), (
        f"a change of {field} under the same heading was collapsed away"
    )


def test_the_fingerprint_is_stable_across_repeated_computation() -> None:
    """A fingerprint that varied between calls would make the receipt vary too."""

    payload, extras = _entitlement("2760dd", "entitlement-a", _DOC_A)
    digests = {policy_semantic_fingerprint(payload, governing_extras=extras) for _ in range(5)}
    assert len(digests) == 1


# ── what the live corpus forced out of the comparison ────────────────
#
# Each of the three below was found by running the fingerprint over the real
# hw-policy corpus and reading why the receipt's own pair would not collapse.
# They are asserted here so that a later change that puts any of them back into
# the comparison fails loudly rather than quietly re-opening the crowd-out.


def _table_policy(
    provision_key: str,
    *,
    marker: str,
    document_version_id: str,
    rows: list[str],
) -> tuple[dict, dict]:
    """A role-profile table: independent rows, one rule each."""

    from datetime import date

    rules = []
    for index, row in enumerate(rows):
        rule = make_rule(
            f"AI-{marker}-{index}",
            condition=AllCondition(all=[]),
            effect_action=row,
            effective_from=date(2024, 1, 1),
        )
        rules.append(
            rule.model_copy(
                update={
                    "title": f"Row {index}",
                    "description": f"Row {index}.",
                    "formulation": RuleFormulation(canonical=CanonicalPolicy(source_text=row)),
                    "evidence": [
                        EvidenceReference(
                            document_version_id=document_version_id,
                            source_hash="e" * 16,
                            page=2,
                            section="table 2.1",
                            clause_id=f"C-{marker}-{index}",
                            start_offset=0,
                            end_offset=10,
                        )
                    ],
                }
            )
        )
    payload = build_case_payload(
        policy_set_id="set-1",
        provision_id=f"prov-{marker}",
        provision_key=provision_key,
        heading_path=[_ENTITLEMENT],
        rules=rules,
    )
    payload["envelope"]["policy_version_id"] = _PV
    return payload, governing_extras_for_group(rules)


_ROWS = [
    "Executive | Any catalogue laptop | Included | Catalogue",
    "Engineering | Performance laptop, 16-inch | Included | USD 2,400",
    "General office | Standard laptop, 14-inch | On request | USD 1,150",
]


def test_the_order_the_rows_were_extracted_in_is_not_a_term_of_the_policy() -> None:
    """`2.1 Standard entitlement` is a table, and it was extracted twice.

    Its rows came out in two different orders and were otherwise word for word
    identical. The rules a policy imposes are what it governs; the sequence an
    extractor emitted them in is provenance of the run, so rules are compared as
    a multiset.
    """

    left = _table_policy("2760dd", marker="a", document_version_id=_DOC_A, rows=_ROWS)
    right = _table_policy(
        "5f0db9",
        marker="b",
        document_version_id=_DOC_B,
        rows=[_ROWS[2], _ROWS[0], _ROWS[1]],
    )

    assert [r["effect"]["action"] for r in left[0]["rules"]] != [
        r["effect"]["action"] for r in right[0]["rules"]
    ], "the fixture must actually reorder the rows or this asserts nothing"

    assert policy_semantic_fingerprint(
        left[0], governing_extras=left[1]
    ) == policy_semantic_fingerprint(right[0], governing_extras=right[1])


def test_a_multiset_and_not_a_set_so_a_row_stated_twice_still_differs() -> None:
    """Order is dropped; multiplicity is not.

    A policy that states a rule twice is not the same policy as one that states
    it once, and a set comparison would have said it was.
    """

    once = _table_policy("once", marker="a", document_version_id=_DOC_A, rows=_ROWS)
    twice = _table_policy(
        "twice", marker="b", document_version_id=_DOC_B, rows=[*_ROWS, _ROWS[0]]
    )

    assert policy_semantic_fingerprint(
        once[0], governing_extras=once[1]
    ) != policy_semantic_fingerprint(twice[0], governing_extras=twice[1])


_TARGET_A = "A device issued before the refresh date is retained until that date."
_TARGET_B = "A device issued before the refresh date is surrendered immediately."


def _two_rule_policy(
    provision_key: str,
    *,
    marker: str,
    document_version_id: str,
    second_text: str,
    links: dict[str, list[str]] | None = None,
    second_links: dict[str, list[str]] | None = None,
) -> tuple[dict, dict]:
    """A policy of two rules, the first optionally linking to the second.

    Ids are derived from `marker`, so two calls differing only in `marker` and
    `document_version_id` produce policies whose rules carry no identifier in
    common — which is the only way to test that a link is compared by what it
    points at rather than by what it is called.
    """

    rules = [
        *_policy_rules(
            marker=f"{marker}-src",
            document_version_id=document_version_id,
            source_text="A colleague in scope is entitled to one primary device.",
        ),
        *_policy_rules(
            marker=f"{marker}-tgt",
            document_version_id=document_version_id,
            source_text=second_text,
        ),
    ]
    payload = build_case_payload(
        policy_set_id="set-1",
        provision_id=f"prov-{marker}",
        provision_key=provision_key,
        heading_path=[_ENTITLEMENT],
        rules=rules,
    )
    payload["envelope"]["policy_version_id"] = _PV

    target_id = payload["rules"][1]["rule_id"]
    source_id = payload["rules"][0]["rule_id"]

    def _resolve(values: list[str]) -> list[str]:
        table = {"TARGET": target_id, "SOURCE": source_id, "SELF": source_id}
        return [table.get(value, value) for value in values]

    payload["rules"][0] = {
        **payload["rules"][0],
        **{key: _resolve(values) for key, values in (links or {}).items()},
    }
    if second_links is not None:
        payload["rules"][1] = {
            **payload["rules"][1],
            **{
                key: [target_id if v == "SELF" else _resolve([v])[0] for v in values]
                for key, values in second_links.items()
            },
        }
    return payload, governing_extras_for_group(rules)


def _linked_policy(
    provision_key: str, marker: str, document_version_id: str, *, target_text: str
) -> tuple[dict, dict]:
    """A policy whose first rule supersedes its second."""

    return _two_rule_policy(
        provision_key,
        marker=marker,
        document_version_id=document_version_id,
        second_text=target_text,
        links={"supersedes_rule_ids": ["TARGET"]},
    )


def _cyclic_policy(
    provision_key: str,
    marker: str,
    document_version_id: str,
    *,
    second_text: str,
    self_reference: bool = False,
) -> tuple[dict, dict]:
    """Two rules that supersede each other, or one that supersedes itself."""

    if self_reference:
        return _two_rule_policy(
            provision_key,
            marker=marker,
            document_version_id=document_version_id,
            second_text=second_text,
            links={"supersedes_rule_ids": ["SELF"]},
            second_links={"related_rule_ids": ["TARGET"]},
        )
    return _two_rule_policy(
        provision_key,
        marker=marker,
        document_version_id=document_version_id,
        second_text=second_text,
        links={"supersedes_rule_ids": ["TARGET"]},
        second_links={"supersedes_rule_ids": ["SOURCE"]},
    )


def test_relationship_targets_are_compared_by_what_they_point_at() -> None:
    """A link is a term, so it is compared — but by target semantics, not by id.

    Two extractions of one policy name the same target rule under two different
    ids. Comparing the raw ids would refuse every cross-version duplicate, so the
    target is resolved to the target rule's own link-free identity: what the link
    points *at*, rather than what it is called.
    """

    left, left_extras = _linked_policy("2760dd", "a", _DOC_A, target_text=_TARGET_A)
    right, right_extras = _linked_policy("5f0db9", "b", _DOC_B, target_text=_TARGET_A)

    # The fixture must really use different ids or this proves nothing.
    assert (
        left["rules"][0]["supersedes_rule_ids"] != right["rules"][0]["supersedes_rule_ids"]
    )

    assert policy_semantic_fingerprint(
        left, governing_extras=left_extras
    ) == policy_semantic_fingerprint(right, governing_extras=right_extras)


def test_the_same_number_of_links_to_different_rules_does_not_collapse() -> None:
    """The control that count-only comparison fails.

    Both policies supersede exactly one rule. One displaces a rule permitting a
    thing; the other displaces a rule forbidding it. A fingerprint that compared
    how *many* links there are — or that dropped the links — would call these one
    policy and answer a case from whichever copy ranked first.
    """

    left, left_extras = _linked_policy("2760dd", "a", _DOC_A, target_text=_TARGET_A)
    right, right_extras = _linked_policy("5f0db9", "b", _DOC_B, target_text=_TARGET_B)

    assert len(left["rules"][0]["supersedes_rule_ids"]) == len(
        right["rules"][0]["supersedes_rule_ids"]
    ) == 1, "both must supersede exactly one rule or the count is not what differs"

    assert policy_semantic_fingerprint(
        left, governing_extras=left_extras
    ) != policy_semantic_fingerprint(right, governing_extras=right_extras)


def test_a_link_recorded_on_only_one_side_does_not_collapse() -> None:
    """Whether a rule displaces anything at all is a term of that rule.

    The live corpus has extractions that differ in exactly this way, and the
    earlier repair dropped the links to make them collapse. That was wrong: a
    rule that supersedes something and one that supersedes nothing are two
    different rules, and no amount of the rest matching makes them one. The cost
    is a forgone collapse, which is a budget slot; the alternative cost is an
    answer drawn from a policy that does not govern.
    """

    left, left_extras = _linked_policy("2760dd", "a", _DOC_A, target_text=_TARGET_A)
    right, right_extras = _linked_policy("5f0db9", "b", _DOC_B, target_text=_TARGET_A)
    right["rules"][0] = {**right["rules"][0], "supersedes_rule_ids": []}

    assert policy_semantic_fingerprint(
        left, governing_extras=left_extras
    ) != policy_semantic_fingerprint(right, governing_extras=right_extras)


def test_supersession_and_mere_relation_are_not_interchangeable() -> None:
    """Displacing a rule and being read beside it are different claims."""

    left, left_extras = _linked_policy("2760dd", "a", _DOC_A, target_text=_TARGET_A)
    right, right_extras = _linked_policy("5f0db9", "b", _DOC_B, target_text=_TARGET_A)
    source = right["rules"][0]
    right["rules"][0] = {
        **source,
        "supersedes_rule_ids": [],
        "related_rule_ids": list(source["supersedes_rule_ids"]),
    }

    assert policy_semantic_fingerprint(
        left, governing_extras=left_extras
    ) != policy_semantic_fingerprint(right, governing_extras=right_extras)


def test_a_link_leaving_the_policy_is_never_proven_equivalent() -> None:
    """An unresolvable target is exactly where nothing has been proven.

    A link to a rule that is not one of this policy's own cannot be resolved to
    any semantics, so its raw id stands. Two copies naming that outside rule
    under two ids therefore do not collapse. That is a deliberate false negative:
    it forgoes a collapse rather than asserting an equivalence the record does
    not support.
    """

    left, left_extras = _linked_policy("2760dd", "a", _DOC_A, target_text=_TARGET_A)
    right, right_extras = _linked_policy("5f0db9", "b", _DOC_B, target_text=_TARGET_A)
    left["rules"][0] = {**left["rules"][0], "supersedes_rule_ids": ["OUTSIDE-1"]}
    right["rules"][0] = {**right["rules"][0], "supersedes_rule_ids": ["OUTSIDE-2"]}

    assert policy_semantic_fingerprint(
        left, governing_extras=left_extras
    ) != policy_semantic_fingerprint(right, governing_extras=right_extras)

    # And the same outside id on both sides is the one case that can still match.
    right["rules"][0] = {**right["rules"][0], "supersedes_rule_ids": ["OUTSIDE-1"]}
    assert policy_semantic_fingerprint(
        left, governing_extras=left_extras
    ) == policy_semantic_fingerprint(right, governing_extras=right_extras)


def test_a_cycle_of_links_terminates_and_still_discriminates() -> None:
    """Two rules that supersede each other must not hang or lose their meaning.

    Resolution is one pass against link-free identities, so a cycle — including a
    rule that names itself — terminates by construction. It must also still tell
    two different cycles apart, which is what the second half asserts.
    """

    left, left_extras = _cyclic_policy("2760dd", "a", _DOC_A, second_text=_TARGET_A)
    right, right_extras = _cyclic_policy("5f0db9", "b", _DOC_B, second_text=_TARGET_A)

    # Terminates, and two copies of one cycle are one policy.
    assert policy_semantic_fingerprint(
        left, governing_extras=left_extras
    ) == policy_semantic_fingerprint(right, governing_extras=right_extras)

    # A self-reference is a cycle of one and must also terminate.
    selfref, selfref_extras = _cyclic_policy(
        "self", "c", _DOC_A, second_text=_TARGET_A, self_reference=True
    )
    assert selfref["rules"][0]["supersedes_rule_ids"] == [selfref["rules"][0]["rule_id"]], (
        "the fixture must really point the rule at itself"
    )
    assert policy_semantic_fingerprint(selfref, governing_extras=selfref_extras)

    # And a cycle whose other member governs differently is a different policy.
    other, other_extras = _cyclic_policy("5f0db9", "b", _DOC_B, second_text=_TARGET_B)
    assert policy_semantic_fingerprint(
        left, governing_extras=left_extras
    ) != policy_semantic_fingerprint(other, governing_extras=other_extras)


def test_a_boolean_term_of_the_rule_is_still_compared() -> None:
    """`is_explicit_override` is a term, not a reference, and is never dropped."""

    left, left_extras = _entitlement("2760dd", "entitlement-a", _DOC_A)
    right, right_extras = _entitlement("5f0db9", "entitlement-b", _DOC_B)
    right["rules"][0] = {**right["rules"][0], "is_explicit_override": True}

    assert policy_semantic_fingerprint(
        left, governing_extras=left_extras
    ) != policy_semantic_fingerprint(right, governing_extras=right_extras)


def test_two_parses_of_one_sentence_are_one_rule() -> None:
    """The last thing keeping the receipt's own pair apart, and why it is dropped.

    `attributes`, the rule's `facts` usages and the `decision_readiness`
    entries merged into `required_facts` are all re-derived from the rule's
    canonical parse on every projection. Two extractions of the entitlement rule
    agreed on the sentence, the effect, the type and every stored required fact,
    and disagreed only on whether "appropriate to their role profile" was a
    `constraint` or "in scope" a `condition`. That is the parse differing.

    Safe only because the sentence itself is still compared verbatim — which the
    second half of this test pins down.
    """

    left, left_extras = _entitlement("2760dd", "entitlement-a", _DOC_A)
    right, right_extras = _entitlement("5f0db9", "entitlement-b", _DOC_B)

    right["rules"][0]["attributes"] = {
        "applies": [{"attribute": "condition", "text": "in scope", "data_type": None}],
        "outcome": [],
    }
    right["rules"][0]["facts"] = [{"ref": "something-else", "roles": ["subject"]}]
    right["rules"][0]["required_facts"] = [
        *right["rules"][0]["required_facts"],
        {"phrase": "in scope", "role": "condition", "required": True},
    ]
    left["rules"][0]["required_facts"] = [
        *left["rules"][0]["required_facts"],
        {"phrase": "appropriate to their role profile", "role": "constraint", "required": True},
    ]

    assert policy_semantic_fingerprint(
        left, governing_extras=left_extras
    ) == policy_semantic_fingerprint(right, governing_extras=right_extras)

    # The sentence is the ground truth and is not excluded with the parse.
    right["spans"][next(iter(right["spans"]))]["text"] = "Each employee is entitled to two laptops."
    assert policy_semantic_fingerprint(
        left, governing_extras=left_extras
    ) != policy_semantic_fingerprint(right, governing_extras=right_extras)


def test_a_stored_required_fact_is_a_term_and_is_still_compared() -> None:
    """Only the derived readiness entries are dropped, never the real ones.

    A `RequiredFact` carries a name, a type and a unit that the document's terms
    determine — it is what a case must supply before a verdict can be reached, so
    two policies demanding different facts are different policies.
    """

    left, left_extras = _entitlement("2760dd", "entitlement-a", _DOC_A)
    right, right_extras = _entitlement(
        "5f0db9", "entitlement-b", _DOC_B, required_fact="laptop-age-months"
    )

    assert policy_semantic_fingerprint(
        left, governing_extras=left_extras
    ) != policy_semantic_fingerprint(right, governing_extras=right_extras)


# ── the collapse, and the budget slot it frees ───────────────────────


def _live_shaped_candidates() -> list[dict]:
    """The live receipt's corpus: two duplicated provisions and three singles.

    Six candidates for five slots, and the sixth by rank is the one that decides
    the case — which is exactly why it never got read.
    """

    return [
        _candidate("2760dd", _entitlement("2760dd", "entitlement-a", _DOC_A)),
        _candidate("5f0db9", _entitlement("5f0db9", "entitlement-b", _DOC_B)),
        _candidate(
            "acc-a",
            _published(
                "acc-a",
                heading="4.2 Accidental damage",
                marker="damage-a",
                document_version_id=_DOC_A,
                source_text="Accidental damage is assessed against the schedule of contributions.",
            ),
        ),
        _candidate(
            "acc-b",
            _published(
                "acc-b",
                heading="4.2 Accidental damage",
                marker="damage-b",
                document_version_id=_DOC_B,
                source_text="Accidental damage is assessed against the schedule of contributions.",
            ),
        ),
        _candidate(
            "lost",
            _published(
                "lost",
                heading="4.4 Lost/stolen",
                marker="lost",
                document_version_id=_DOC_A,
                source_text="A lost or stolen device must be reported before a replacement is issued.",
            ),
        ),
        _candidate(
            "refresh",
            _published(
                "refresh",
                heading=_REFRESH,
                marker="refresh",
                document_version_id=_DOC_A,
                source_text=(
                    "A standard laptop is eligible for replacement once twenty-four "
                    "months have elapsed since it was issued."
                ),
                required_fact="laptop-age-months",
            ),
        ),
    ]


_LIVE_RANKING = [
    ("2760dd", 0.90),
    ("5f0db9", 0.89),
    ("acc-a", 0.88),
    ("acc-b", 0.87),
    ("lost", 0.86),
    ("refresh", 0.85),
]


async def test_a_duplicate_frees_the_slot_the_deciding_policy_needed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live defect, and the repair, in one assertion.

    Five slots, six policies, and two of the six are copies. Before the collapse
    the copies took two slots and `3.1 Standard refresh interval` ranked sixth
    and was never read, so the verdict could not be settled. After it, the budget
    counts four distinct policies, the refresh interval is inside it, and the
    rule that decides a 26-month-old laptop reaches the gather.
    """

    candidates = _live_shaped_candidates()
    gathered = _wire(monkeypatch, candidates=candidates, ranked=_LIVE_RANKING)

    result = await _run()

    evaluated = [record["policy"]["provision_key"] for record in gathered[0]]
    assert "refresh" in evaluated, "the provision that decides the case was still not read"
    # One of each duplicated pair, both singles, and nothing twice.
    assert evaluated == ["2760dd", "acc-a", "lost", "refresh"]
    assert len(evaluated) <= ai_case_project.RETRIEVAL_POLICY_BUDGET

    retrieval = result["retrieval"]
    assert retrieval["policies_duplicate_collapsed"] == 2
    assert retrieval["policies_retained"] == 4
    assert retrieval["policy_budget"] == ai_case_project.RETRIEVAL_POLICY_BUDGET

    # The narrowing that used to hide the answer is gone: nothing is outside the
    # retention budget any more, because nothing is spent twice.
    by_key = {entry["provision_key"]: entry for entry in result["considered"]}
    assert by_key["refresh"]["retained"] is True
    assert by_key["refresh"].get("discard_reason") is None


async def test_every_raw_candidate_stays_visible_and_names_its_representative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A collapse a reviewer cannot see is the failure this module exists to stop.

    A duplicate is not deleted from the report and is not reported as unmatched:
    it surfaced, it ranked where it ranked, and its terms *were* read — in the
    representative it names. Saying less than that would either hide a narrowing
    or claim this record reached a gather it never reached.
    """

    candidates = _live_shaped_candidates()
    _wire(monkeypatch, candidates=candidates, ranked=_LIVE_RANKING)

    result = await _run()

    considered = result["considered"]
    assert len(considered) == len(candidates), "a raw candidate vanished from the report"

    by_key = {entry["provision_key"]: entry for entry in considered}
    collapsed = by_key["5f0db9"]
    assert collapsed["retained"] is False
    assert collapsed["discard_reason"] == ai_case_project.DISCARD_DUPLICATE_POLICY_CONTENT
    assert collapsed["duplicate_of_provision_key"] == "2760dd"
    # Its own rank and score, not the representative's: it really did surface there.
    assert collapsed["best_rank"] == 1
    assert collapsed["best_score"] == pytest.approx(0.89)
    # And it is never credited with having been read.
    assert collapsed["matched_policies"] == 0
    assert "rule_selection" not in collapsed

    representative = by_key["2760dd"]
    assert representative["retained"] is True
    assert representative.get("duplicate_of_provision_key") is None

    # The counts stay consistent with the lists they summarise.
    retrieval = result["retrieval"]
    assert retrieval["policies_considered"] == len(considered)
    assert retrieval["policies_retained"] == len([e for e in considered if e["retained"]])
    assert retrieval["policies_discarded"] == len([e for e in considered if not e["retained"]])
    assert retrieval["policies_retained"] + retrieval["policies_discarded"] == len(considered)
    # The duplicate collapse is a subset of the discards, reported in its own right.
    assert retrieval["policies_duplicate_collapsed"] <= retrieval["policies_discarded"]
    assert ai_case_project.DISCARD_DUPLICATE_POLICY_CONTENT in retrieval["reason"]
    assert "2760dd" in retrieval["reason"]


async def test_a_policy_only_sharing_a_heading_is_still_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The collapse must never cost a reviewer a materially different policy.

    Two provisions under `2.1 Standard entitlement` whose rules differ. Both are
    retained and both are evaluated; nothing is collapsed and the count says so.
    """

    candidates = [
        _candidate("2760dd", _entitlement("2760dd", "entitlement-a", _DOC_A)),
        _candidate(
            "5f0db9",
            _published(
                "5f0db9",
                heading=_ENTITLEMENT,
                marker="entitlement-b",
                document_version_id=_DOC_B,
                source_text="Each employee is entitled to two standard laptops.",
            ),
        ),
    ]
    gathered = _wire(
        monkeypatch, candidates=candidates, ranked=[("2760dd", 0.9), ("5f0db9", 0.8)]
    )

    result = await _run()

    assert [r["policy"]["provision_key"] for r in gathered[0]] == ["2760dd", "5f0db9"]
    assert result["retrieval"]["policies_duplicate_collapsed"] == 0
    assert result["retrieval"]["policies_retained"] == 2
    assert ai_case_project.DISCARD_DUPLICATE_POLICY_CONTENT not in json.dumps(
        result["considered"]
    )


async def test_identical_words_under_different_authority_are_both_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Provenance is erased; the terms under which words bind never are.

    The lean record the model reads does not carry authority, so this is the one
    governing field that has to reach the comparison from beside the payload. If
    it did not, two statements issued by two owners at two precedence ranks would
    be collapsed into one and a reviewer would be answered from whichever copy
    happened to rank first.
    """

    candidates = [
        _candidate(
            "board",
            _entitlement(
                "board",
                "entitlement-a",
                _DOC_A,
                authority=PolicyAuthority(level="board", owner="CIO", rank=1),
            ),
        ),
        _candidate(
            "unit",
            _entitlement(
                "unit",
                "entitlement-b",
                _DOC_B,
                authority=PolicyAuthority(level="unit", owner="IT-Ops", rank=4),
            ),
        ),
    ]
    gathered = _wire(monkeypatch, candidates=candidates, ranked=[("board", 0.9), ("unit", 0.9)])

    result = await _run()

    assert [r["policy"]["provision_key"] for r in gathered[0]] == ["board", "unit"]
    assert result["retrieval"]["policies_duplicate_collapsed"] == 0


# ── determinism ──────────────────────────────────────────────────────


async def test_the_representative_does_not_depend_on_the_order_of_a_tie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two copies of one policy score identically far more often than not.

    If the tie were resolved by whichever order the index happened to return, the
    receipt — and therefore the decision hash — would differ between two runs of
    the same question against the same version. The tie is broken by search
    document id, so the same pair yields the same representative either way, and
    the group still holds its best-ranked position so nothing is reordered.
    """

    left = _candidate("2760dd", _entitlement("2760dd", "entitlement-a", _DOC_A))
    right = _candidate("5f0db9", _entitlement("5f0db9", "entitlement-b", _DOC_B))
    other = _candidate(
        "lost",
        _published(
            "lost",
            heading="4.4 Lost/stolen",
            marker="lost",
            document_version_id=_DOC_A,
            source_text="A lost or stolen device must be reported before a replacement is issued.",
        ),
    )

    outcomes = []
    for ranked in (
        [("2760dd", 0.9), ("5f0db9", 0.9), ("lost", 0.5)],
        [("5f0db9", 0.9), ("2760dd", 0.9), ("lost", 0.5)],
    ):
        gathered = _wire(monkeypatch, candidates=[left, right, other], ranked=ranked)
        result = await _run()
        evaluated = [r["policy"]["provision_key"] for r in gathered[0]]
        by_key = {e["provision_key"]: e for e in result["considered"]}
        outcomes.append(
            (
                evaluated,
                by_key["2760dd"]["retained"],
                by_key["5f0db9"]["retained"],
                by_key["5f0db9"].get("duplicate_of_provision_key")
                or by_key["2760dd"].get("duplicate_of_provision_key"),
            )
        )

    assert outcomes[0] == outcomes[1], "the representative moved when the tie order moved"

    # And the winner is the documented one: among copies tied on score, the
    # lowest search document id. Asserting the rule rather than a fixture value
    # is what makes this a test of determinism and not of a hash.
    expected = min(
        (left["search_document_id"], left["provision_key"]),
        (right["search_document_id"], right["provision_key"]),
    )[1]
    assert outcomes[0][0] == [expected, "lost"]
    assert outcomes[0][3] == expected


def test_collapsing_is_a_pure_function_of_the_hits_and_the_candidates() -> None:
    """The pass itself, called directly and twice, with the same answer both times."""

    candidates = _live_shaped_candidates()
    by_search_id = {c["search_document_id"]: c for c in candidates}
    hits = [_hit(key, score) for key, score in _LIVE_RANKING]

    first = ai_case_project.collapse_duplicate_policies(hits, by_search_id)
    second = ai_case_project.collapse_duplicate_policies(hits, by_search_id)

    assert first == second
    distinct, duplicates = first
    assert len(distinct) == 4
    assert len(duplicates) == 2
    # Ranked order is preserved: collapsing never moves a policy past one that
    # outranked it.
    assert distinct == [
        policy_document_id(policy_version_id=_PV, provision_key=key)
        for key in ("2760dd", "acc-a", "lost", "refresh")
    ]


def test_a_hit_with_no_candidate_payload_is_never_collapsed() -> None:
    """Matching on absence would discard a policy for what was not recorded.

    A hit the published payloads cannot place is not "the same as" another hit
    that also cannot be placed. Both stand on their own, exactly as they did
    before this pass existed.
    """

    hits = [_hit("ghost-a", 0.9), _hit("ghost-b", 0.8)]
    distinct, duplicates = ai_case_project.collapse_duplicate_policies(hits, {})

    assert duplicates == {}
    assert len(distinct) == 2


# ── the receipt, and what it seals ───────────────────────────────────


async def test_the_collapse_reaches_the_audited_receipt_and_its_seal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A receipt must say the corpus held one policy twice, and which stood in.

    The seal covers `retained` and `discard_reason` for every considered policy,
    so a decision made after collapsing a duplicate cannot be confused with one
    made by reading both copies, or with one where the duplicate ranked out on
    relevance. And a collapsed policy seals no rule ids, because none of its
    rules were read.
    """

    from datetime import datetime, timezone

    from policy_platform.application.policy_case_decision import Caller, build_envelope
    from policy_platform.contracts.case_decision import (
        PolicySetRef,
        compute_decision_hash_v2,
        decision_hash_preimage_v2,
    )

    candidates = _live_shaped_candidates()
    _wire(monkeypatch, candidates=candidates, ranked=_LIVE_RANKING)

    response = await _run()

    now = datetime(2026, 8, 30, 3, 0, tzinfo=timezone.utc)
    envelope = build_envelope(
        decision_id="d-1",
        correlation_id="c-1",
        idempotency_key=None,
        project=PolicySetRef(id="s-1", key="hardware", name="Hardware"),
        caller=Caller(identity="a@b.c", role="viewer", authentication_source="token"),
        scenario=_QUESTION,
        reasoning_effort="medium",
        requested_provision_id=None,
        received_at=now,
        decided_at=now,
        latency_ms=1,
        response=response,
        context={},
    )

    # The verdict the live receipt could not reach.
    assert envelope.outcome.verdict == "answered"
    assert envelope.verdict is not None
    assert envelope.verdict.reached is True

    assert envelope.retrieval.policies_duplicate_collapsed == 2

    refs = {ref.provision_key: ref for ref in envelope.considered}
    assert len(refs) == len(candidates), "the receipt dropped a raw candidate"

    collapsed = refs["5f0db9"]
    assert collapsed.retained is False
    assert collapsed.discard_reason == ai_case_project.DISCARD_DUPLICATE_POLICY_CONTENT
    assert collapsed.duplicate_of_provision_key == "2760dd"
    assert collapsed.rule_selection is None, "no rule of a collapsed copy was read"
    assert refs["2760dd"].retained is True
    assert refs["refresh"].retained is True

    sealed = {p["provision_key"]: p for p in decision_hash_preimage_v2(envelope)["policies"]}
    assert sealed["5f0db9"]["retained"] is False
    assert sealed["5f0db9"]["discard_reason"] == (
        ai_case_project.DISCARD_DUPLICATE_POLICY_CONTENT
    )
    assert sealed["5f0db9"]["selected_rule_ids"] is None
    assert sealed["refresh"]["retained"] is True

    # A decision that had read both copies, or had dropped the duplicate on
    # relevance instead, is a different decision and must not share this seal.
    baseline = envelope.decision_hash
    envelope.considered[1].discard_reason = ai_case_project.DISCARD_OUTSIDE_BUDGET
    assert compute_decision_hash_v2(envelope) != baseline


# ── the later narrowings, untouched ──────────────────────────────────


async def test_rule_slicing_and_the_payload_budget_still_behave(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The collapse runs before them and must change neither.

    A large policy is still read rule by rule above the threshold, and a whole
    record that will not fit beside what is already admitted is still set aside
    for size rather than trimmed. Both are asserted here against a corpus that
    also contains a collapsed duplicate, because the interesting failure is the
    three narrowings interfering, not any one of them alone.
    """

    def _bulky(key: str, marker: str, document_version_id: str, *, rules: int, bulk: int):
        from datetime import date

        made = []
        for index in range(rules):
            rule = make_rule(f"AI-{marker}-{index}", condition=AllCondition(all=[]))
            made.append(
                rule.model_copy(
                    update={
                        "title": f"Row {index}",
                        "description": f"Row {index} of {key}.",
                        "formulation": RuleFormulation(
                            canonical=CanonicalPolicy(
                                source_text=(
                                    f"Row {index}. Where a device is affected in the manner this row "
                                    "describes, the responsible authority shall record the matter and "
                                    "apply the measure set out in the corresponding column of the "
                                    "schedule, having regard to any prior occurrence."
                                )
                                * bulk
                            )
                        ),
                        "evidence": [
                            EvidenceReference(
                                document_version_id=document_version_id,
                                source_hash="h" * 16,
                                page=index + 1,
                                section=f"section {index}",
                                clause_id=f"C-{marker}-{index}",
                                start_offset=0,
                                end_offset=10,
                            )
                        ],
                        "effective_from": date(2024, 1, 1),
                    }
                )
            )
        payload = build_case_payload(
            policy_set_id="set-1",
            provision_id=f"prov-{marker}",
            provision_key=key,
            heading_path=["Schedule of measures"],
            rules=made,
        )
        payload["envelope"]["policy_version_id"] = _PV
        return payload, governing_extras_for_group(made)

    table = _bulky("table", "table", _DOC_A, rules=40, bulk=1)
    huge = _bulky("huge", "huge", _DOC_A, rules=12, bulk=400)

    candidates = [
        _candidate("2760dd", _entitlement("2760dd", "entitlement-a", _DOC_A)),
        _candidate("5f0db9", _entitlement("5f0db9", "entitlement-b", _DOC_B)),
        _candidate("table", table),
        _candidate("huge", huge),
    ]
    assert len(table[0]["rules"]) > rule_slice.LARGE_POLICY_RULE_THRESHOLD

    gathered = _wire(
        monkeypatch,
        candidates=candidates,
        ranked=[("2760dd", 0.9), ("5f0db9", 0.89), ("table", 0.88), ("huge", 0.5)],
    )

    result = await _run()
    retrieval = result["retrieval"]

    # All three narrowings happened, and each is reported in its own right.
    assert retrieval["policies_duplicate_collapsed"] == 1
    assert retrieval["policies_rule_sliced"] == 1
    assert retrieval["policies_over_payload_budget"] == 1

    by_key = {entry["provision_key"]: entry for entry in result["considered"]}
    selection = by_key["table"]["rule_selection"]
    assert selection["sliced"] is True
    assert selection["total_rules"] == 40
    assert selection["selected_rules"] < selection["total_rules"]
    assert selection["selected_rules"] <= rule_slice.SELECTED_RULE_BUDGET
    assert by_key["5f0db9"]["discard_reason"] == (
        ai_case_project.DISCARD_DUPLICATE_POLICY_CONTENT
    )
    assert by_key["huge"]["discard_reason"] == ai_case_project.DISCARD_OUTSIDE_PAYLOAD_BUDGET
    # The size narrowing still strips the selection of what it set aside.
    assert "rule_selection" not in by_key["huge"]

    evaluated = [r["policy"]["provision_key"] for r in gathered[0]]
    assert evaluated == ["2760dd", "table"]
    assert result["size"]["oversize"] is False
