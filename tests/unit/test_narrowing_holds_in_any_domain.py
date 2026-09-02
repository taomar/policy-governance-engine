"""The narrowing must hold for any corpus, in any language, under any names.

WHY THIS FILE EXISTS SEPARATELY

The regression files beside this one hold the concrete incidents — annual
vacation against a penalties table, and laptop replacement against a duplicated
entitlement. Those are worth keeping: they are what actually failed, and a test
that names the failure it prevents is readable years later.

But a concrete regression can pass for the wrong reason. If any of the three
narrowings were keyed — even accidentally — to a heading, a word in the question,
an identifier, or a script, the incident tests would still pass while the product
worked only for the corpus it was debugged against. Constraint 1 says the
platform names no domain; this file is what makes that checkable.

So everything here is synthetic and deliberately unrelated to any incident:

  * **maritime port tariffs** — berthing and pilotage charges;
  * **veterinary practice licensing** — premises registration and inspection;
  * **a corpus whose source is written in Arabic** — because none of the three
    narrowings may work better in one script than another.

    Its **documents** are in Arabic and its **question is not**, and that is the
    shape the platform actually has rather than a convenience: a question is
    reduced to the one language the pipeline reasons in before anything
    retrieves, and what it is scored against is the corpus' projection into that
    language. A question written in the document's own language would exercise a
    path this platform no longer has. No question in this file is written in one,
    and none of these fixtures is run against a live service.

Each domain is run through the same assertions, and the assertions are about
*relationships* — a duplicate frees a slot, materially different policies under
one heading both survive, no record exceeds the rule budget — never about a
particular string. Two further controls prove the negative directly: renaming
every identifier in a corpus changes nothing, and a heading carries no privilege
of its own.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any

import pytest

os.environ.setdefault("DATABASE_URL", "******localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "******localhost:5433/test")

from policy_platform.contracts.conditions import AllCondition  # noqa: E402
from policy_platform.contracts.formulation import CanonicalPolicy, RuleFormulation  # noqa: E402
from policy_platform.contracts.policy import (  # noqa: E402
    Effect,
    EffectType,
    EvidenceReference,
    PolicyAuthority,
    PolicyScope,
    RuleType,
)
from policy_platform.infrastructure.assistants import ai_case_intent, ai_case_project  # noqa: E402
from policy_platform.infrastructure.projection import policy_rule_slice as rule_slice  # noqa: E402
from policy_platform.infrastructure.projection.policy_case_payload import (  # noqa: E402
    build_case_payload,
)
from policy_platform.infrastructure.projection.policy_semantic_identity import (  # noqa: E402
    policy_normative_group_key,
    policy_semantic_fingerprint,
    rule_semantic_fingerprints,
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


_PV = "44444444-4444-4444-8444-444444444444"
_DOC_A = "55555555-5555-4555-8555-555555555555"
_DOC_B = "66666666-6666-4666-8666-666666666666"


class Domain:
    """One synthetic governance corpus, described only in its own words.

    Nothing outside this class knows what any of these strings mean. The tests
    below reference the fields, never the values, so adding a fourth domain
    requires no change to a single assertion.
    """

    def __init__(
        self,
        name: str,
        *,
        deciding_heading: str,
        deciding_sentence: str,
        duplicated_heading: str,
        duplicated_sentence: str,
        variant_sentence: str,
        filler_heading: str,
        filler_sentence: str,
        question: str,
        row_sentence: str,
    ) -> None:
        self.name = name
        self.deciding_heading = deciding_heading
        self.deciding_sentence = deciding_sentence
        self.duplicated_heading = duplicated_heading
        self.duplicated_sentence = duplicated_sentence
        #: Same heading as the duplicated policy, materially different terms.
        self.variant_sentence = variant_sentence
        self.filler_heading = filler_heading
        self.filler_sentence = filler_sentence
        self.question = question
        #: Templated per row to build a large policy of independent rows.
        self.row_sentence = row_sentence

    def __repr__(self) -> str:  # pragma: no cover - test ids only
        return self.name


PORT = Domain(
    "maritime-port-tariffs",
    deciding_heading="Berthing charges",
    deciding_sentence=(
        "A vessel occupying a commercial berth beyond thirty-six hours is charged the "
        "extended occupancy tariff for each subsequent twelve-hour period."
    ),
    duplicated_heading="Pilotage assignment",
    duplicated_sentence=(
        "A vessel entering the inner harbour is assigned one licensed pilot for the "
        "duration of the transit."
    ),
    variant_sentence=(
        "A vessel entering the inner harbour is assigned two licensed pilots for the "
        "duration of the transit."
    ),
    filler_heading="Waste reception",
    filler_sentence="Garbage is landed at the reception facility before departure clearance.",
    question="our vessel has occupied the commercial berth for forty hours, what tariff applies",
    row_sentence=(
        "Tariff line {n}. Where a vessel of the class described in this line uses the "
        "facility, the harbour master shall record the movement and levy the charge set "
        "against that class in the published schedule."
    ),
)

VET = Domain(
    "veterinary-practice-licensing",
    deciding_heading="Premises inspection interval",
    deciding_sentence=(
        "Registered premises are inspected once every twenty-four months, and a premises "
        "beyond that interval is treated as unregistered until inspected."
    ),
    duplicated_heading="Registration allowance",
    duplicated_sentence=(
        "A qualified practitioner may hold the registration of one premises at any time."
    ),
    variant_sentence=(
        "A qualified practitioner may hold the registration of three premises at any time."
    ),
    filler_heading="Controlled substance storage",
    filler_sentence="Controlled substances are held in a fixed cabinet with a bound register.",
    question="our premises was last inspected twenty-six months ago, is the registration still valid",
    row_sentence=(
        "Schedule entry {n}. Where a practitioner acts in the manner described in this "
        "entry, the registrar shall note the matter and apply the sanction recorded "
        "beside that entry in the schedule."
    ),
)

ARABIC = Domain(
    "arabic-source-housing-allowance",
    deciding_heading="مدة الاستحقاق",
    deciding_sentence="يستحق الموظف بدل السكن بعد مرور أربعة وعشرين شهرا على مباشرته العمل.",
    duplicated_heading="أصل الاستحقاق",
    duplicated_sentence="يمنح الموظف المستحق وحدة سكنية واحدة تناسب درجته الوظيفية.",
    variant_sentence="يمنح الموظف المستحق وحدتين سكنيتين تناسبان درجته الوظيفية.",
    filler_heading="تسليم المفاتيح",
    filler_sentence="تسلم المفاتيح إلى الموظف بعد توقيع محضر الاستلام.",
    #: The **question** is in the processing language even though the document is
    #: not, because that is the only shape the platform now has: the boundary
    #: reduces every question before anything retrieves, and what a question is
    #: scored against is the corpus' projection rather than its own sentences.
    #: A question written in the document's language would exercise a path that
    #: no longer exists, and is not run against a live service at all.
    question="I have been in post for twenty-six months, am I entitled to the housing allowance now",
    row_sentence=(
        "البند {n}. إذا تصرف الموظف على النحو الموصوف في هذا البند فعلى الجهة المختصة "
        "تدوين الواقعة وتطبيق الإجراء المقرر أمام هذا البند في الجدول."
    ),
)

DOMAINS = [PORT, VET, ARABIC]


# ── fixture construction, entirely parameterised ─────────────────────


def _rules(
    *,
    marker: str,
    document_version_id: str,
    sentences: list[str],
    effective_from: str = "2024-01-01",
) -> list:
    made = []
    for index, sentence in enumerate(sentences):
        rule = make_rule(
            f"R-{marker}-{index}",
            condition=AllCondition(all=[]),
            effective_from=date.fromisoformat(effective_from),
        )
        made.append(
            rule.model_copy(
                update={
                    "title": f"{marker} {index}",
                    "description": f"{marker} clause {index}.",
                    "formulation": RuleFormulation(
                        canonical=CanonicalPolicy(source_text=sentence)
                    ),
                    "evidence": [
                        EvidenceReference(
                            document_version_id=document_version_id,
                            source_hash="a" * 16,
                            page=index + 1,
                            section=f"s{index}",
                            clause_id=f"C-{marker}-{index}",
                            start_offset=0,
                            end_offset=10,
                        )
                    ],
                }
            )
        )
    return made


def _published(
    provision_key: str,
    *,
    heading: str,
    marker: str,
    document_version_id: str,
    sentences: list[str],
    effective_from: str = "2024-01-01",
) -> tuple[dict, dict]:
    made = _rules(
        marker=marker,
        document_version_id=document_version_id,
        sentences=sentences,
        effective_from=effective_from,
    )
    payload = build_case_payload(
        policy_set_id="set-x",
        provision_id=f"prov-{marker}",
        provision_key=provision_key,
        heading_path=[heading],
        rules=made,
    )
    payload["envelope"]["policy_version_id"] = _PV
    return payload, governing_extras_for_group(made)


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


class _Settings:
    ai_enabled = True
    search_enabled = True
    azure_openai_deployment = "slow"
    azure_openai_secondary_deployment = "fast"
    azure_search_authoring_index = "policy-authoring"


class _PolicySet:
    def __init__(self, set_id: str, key: str) -> None:
        self.id = set_id
        self.key = key


class _Embed:
    def __init__(self, settings: Any) -> None:
        pass

    async def embed(self, inputs: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in inputs]


def _search(ranked: list[tuple[str, float]]):
    class _Client:
        def __init__(self, settings: Any) -> None:
            pass

        async def index_exists(self, *a: Any, **k: Any) -> bool:
            return True

        async def vector_search(self, *a: Any, **k: Any) -> list[dict]:
            return [
                {
                    "id": policy_document_id(policy_version_id=_PV, provision_key=key),
                    "@search.score": score,
                    "policy_id": key,
                    "document_version": _PV,
                }
                for key, score in ranked
            ]

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
        "active_version_number": 1,
        "candidates": candidates,
        "excluded": [],
    }

    async def _load(session: Any, policy_set_id: Any) -> dict:
        return scope

    gathered: list[list[dict]] = []

    async def _spy(records, *, scenario: str, reasoning_effort: str = "medium", **kw: Any):
        gathered.append(records)
        return {
            "intent": ai_case_intent.DECISION,
            "information_requested": False,
            "verdict_requested": True,
            "classification_reasoning": "asks how the case comes out",
            "classifier_version": ai_case_intent.NEEDS_CLASSIFIER_VERSION,
            "informational": None,
            "decision": {
                "status": ai_case_intent.ANSWERED,
                "verdict": "eligible",
                "answer": "answered",
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
    monkeypatch.setattr(ai_case_project, "AzureOpenAIClient", _Embed)
    monkeypatch.setattr(ai_case_project, "AzureSearchClient", _search(ranked))
    monkeypatch.setattr(ai_case_project, "answer_case_over_policies", _spy)
    return gathered


async def _run(scenario: str) -> dict:
    return await ai_case_project.answer_project_case(
        object(), policy_set=_PolicySet("set-x", "proj"), scenario=scenario
    )


def _crowded_corpus(domain: Domain) -> list[dict]:
    """A budget's worth of policies, two of which are one policy said twice.

    Six candidates for five slots. The policy that decides the question ranks
    last, so it is read only if the copies stop taking two slots.
    """

    dup_a = _published(
        "dup-a",
        heading=domain.duplicated_heading,
        marker="dupa",
        document_version_id=_DOC_A,
        sentences=[domain.duplicated_sentence],
    )
    dup_b = _published(
        "dup-b",
        heading=domain.duplicated_heading,
        marker="dupb",
        document_version_id=_DOC_B,
        sentences=[domain.duplicated_sentence],
    )
    return [
        _candidate("dup-a", dup_a),
        _candidate("dup-b", dup_b),
        *[
            _candidate(
                f"fill-{i}",
                _published(
                    f"fill-{i}",
                    heading=f"{domain.filler_heading} {i}",
                    marker=f"fill{i}",
                    document_version_id=_DOC_A,
                    sentences=[f"{domain.filler_sentence} ({i})"],
                ),
            )
            for i in range(3)
        ],
        _candidate(
            "deciding",
            _published(
                "deciding",
                heading=domain.deciding_heading,
                marker="dec",
                document_version_id=_DOC_A,
                sentences=[domain.deciding_sentence],
            ),
        ),
    ]


_CROWDED_RANKING = [
    ("dup-a", 0.90),
    ("dup-b", 0.89),
    ("fill-0", 0.88),
    ("fill-1", 0.87),
    ("fill-2", 0.86),
    ("deciding", 0.85),
]


# ── the three narrowings, in every domain ────────────────────────────


def test_every_question_is_in_the_processing_language_whatever_the_corpus_is() -> None:
    """The scope rule, pinned rather than remembered.

    A corpus may be written in any script — one of the three below is, and that
    is the point of it. A *question* may not be: by the time anything retrieves,
    the boundary has already reduced the question to the one language this
    pipeline reasons in, and what it is scored against is the corpus' projection
    into that language.

    So the question fields are held to it and the document fields are not. This
    is what stops a fixture drifting back into asking in the document's language,
    which would exercise a path the platform no longer has and which is not run
    against a live service at all.
    """

    for domain in DOMAINS:
        assert domain.question.isascii(), (
            f"{domain.name} asks its question in the document's language: {domain.question!r}"
        )

    # And at least one corpus really is written in another script, or the rule
    # above is a claim about nothing.
    assert any(not domain.deciding_sentence.isascii() for domain in DOMAINS)
    assert any(not domain.row_sentence.isascii() for domain in DOMAINS)


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
async def test_a_duplicate_frees_a_budget_slot_in_any_domain(
    domain: Domain, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Crowd-out is a property of the budget, not of any corpus.

    Nothing here is a laptop or a leave day. The relationship asserted is the
    one that failed live: when the corpus holds one policy twice, the copies must
    not consume two of the slots, and the policy that decides the question — last
    by rank — must be read.
    """

    candidates = _crowded_corpus(domain)
    gathered = _wire(monkeypatch, candidates=candidates, ranked=_CROWDED_RANKING)

    result = await _run(domain.question)

    evaluated = [r["policy"]["provision_key"] for r in gathered[0]]
    assert "deciding" in evaluated, "the policy that decides the question was not read"
    assert len(evaluated) <= ai_case_project.RETRIEVAL_POLICY_BUDGET
    assert result["retrieval"]["policies_duplicate_collapsed"] == 1

    by_key = {e["provision_key"]: e for e in result["considered"]}
    assert by_key["dup-b"]["discard_reason"] == (
        ai_case_project.DISCARD_DUPLICATE_POLICY_CONTENT
    )
    assert by_key["dup-b"]["duplicate_of_provision_key"] == "dup-a"
    # Every raw candidate is still reported.
    assert len(result["considered"]) == len(candidates)


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
async def test_one_heading_over_different_terms_is_two_policies_in_any_domain(
    domain: Domain, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control that a heading match must never be enough.

    The two policies share a heading and differ in one governing sentence — one
    pilot or two, one premises or three, one unit or two. Both must be read, and
    the collapse count must say plainly that nothing was collapsed.
    """

    candidates = [
        _candidate(
            "same-a",
            _published(
                "same-a",
                heading=domain.duplicated_heading,
                marker="sa",
                document_version_id=_DOC_A,
                sentences=[domain.duplicated_sentence],
            ),
        ),
        _candidate(
            "same-b",
            _published(
                "same-b",
                heading=domain.duplicated_heading,
                marker="sb",
                document_version_id=_DOC_B,
                sentences=[domain.variant_sentence],
            ),
        ),
    ]
    assert (
        candidates[0]["heading_path"] == candidates[1]["heading_path"]
    ), "the fixture must really share a heading"

    gathered = _wire(
        monkeypatch, candidates=candidates, ranked=[("same-a", 0.9), ("same-b", 0.8)]
    )

    result = await _run(domain.question)

    assert [r["policy"]["provision_key"] for r in gathered[0]] == ["same-a", "same-b"]
    assert result["retrieval"]["policies_duplicate_collapsed"] == 0


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
@pytest.mark.parametrize("effective_from", ["2024-01-01", "2025-07-01"])
def test_only_an_exact_governing_match_collapses_in_any_domain(
    domain: Domain, effective_from: str
) -> None:
    """Equivalence is content, and content includes when the terms bind."""

    left = _published(
        "l",
        heading=domain.duplicated_heading,
        marker="l",
        document_version_id=_DOC_A,
        sentences=[domain.duplicated_sentence],
    )
    same = _published(
        "r",
        heading=domain.duplicated_heading,
        marker="r",
        document_version_id=_DOC_B,
        sentences=[domain.duplicated_sentence],
        effective_from=effective_from,
    )

    equal = policy_semantic_fingerprint(
        left[0], governing_extras=left[1]
    ) == policy_semantic_fingerprint(same[0], governing_extras=same[1])
    assert equal is (effective_from == "2024-01-01")


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
def test_no_record_exceeds_the_rule_budget_in_any_domain(domain: Domain) -> None:
    """The slice ceiling is not a property of one penalties table.

    A large policy of independent rows, every row naming every other row as
    context — the worst case for a budget that context could extend. Whatever
    the language or the vocabulary, the record holds at most the budget.
    """

    count = 60
    sentences = [domain.row_sentence.format(n=i) for i in range(count)]
    payload, _ = _published(
        "rows",
        heading=domain.filler_heading,
        marker="rows",
        document_version_id=_DOC_A,
        sentences=sentences,
    )
    ids = [r["rule_id"] for r in payload["rules"]]
    payload["rules"] = [
        {**rule, "related_rule_ids": [i for i in ids if i != rule["rule_id"]]}
        for rule in payload["rules"]
    ]
    policy = {"provision_id": "p", "provision_key": "rows", "heading_path": ["h"]}

    for scenario in (domain.question, domain.row_sentence.format(n=3), "", "zzzz"):
        record, selection = rule_slice.select_rules_for_scenario(
            payload, policy=policy, scenario=scenario
        )
        assert len(record["rules"]) <= rule_slice.SELECTED_RULE_BUDGET, scenario
        assert selection["selected_rules"] == len(record["rules"])
        assert len(selection["selected_rule_ids"]) == selection["selected_rules"]
        assert selection["rules_discarded"] == count - selection["selected_rules"]
        read = {r["rule_id"] for r in record["rules"]}
        assert read.isdisjoint(selection["context_rules_omitted"])


# ── the negatives, proven directly ───────────────────────────────────


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
async def test_renaming_every_identifier_changes_nothing(
    domain: Domain, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No decision may turn on a project, provision, document or rule id.

    The same corpus is run twice, the second time with every identifier it
    contains replaced. Which policies are read, which are collapsed, and which
    representative each names must be identical — otherwise something is keyed to
    a name rather than to content.
    """

    async def _outcome(prefix: str) -> tuple[list[str], list[tuple[str, str | None]]]:
        candidates = _crowded_corpus(domain)
        if prefix:
            for candidate in candidates:
                payload = candidate["payload"]
                payload["envelope"]["provision_id"] = f"{prefix}{candidate['provision_id']}"
                payload["rules"] = [
                    {**rule, "rule_id": f"{prefix}{rule['rule_id']}"}
                    for rule in payload["rules"]
                ]
                candidate["provision_id"] = f"{prefix}{candidate['provision_id']}"
        gathered = _wire(monkeypatch, candidates=candidates, ranked=_CROWDED_RANKING)
        result = await _run(domain.question)
        read = [r["policy"]["provision_key"] for r in gathered[0]]
        report = [
            (e["provision_key"], e.get("duplicate_of_provision_key"))
            for e in result["considered"]
        ]
        return read, report

    baseline = await _outcome("")
    renamed = await _outcome("XX-")

    assert baseline == renamed


async def test_a_heading_carries_no_privilege_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Heading is one component of content, never a shortcut in either direction.

    Two controls in one: policies with *no* heading at all still collapse when
    their terms match, and policies whose headings differ do not collapse even
    though every other governing field is identical. Neither a present heading
    nor a matching one is what decides.
    """

    def _corpus(headings: tuple[str, str]) -> list[dict]:
        return [
            _candidate(
                "a",
                _published(
                    "a",
                    heading=headings[0],
                    marker="a",
                    document_version_id=_DOC_A,
                    sentences=[PORT.duplicated_sentence],
                ),
            ),
            _candidate(
                "b",
                _published(
                    "b",
                    heading=headings[1],
                    marker="b",
                    document_version_id=_DOC_B,
                    sentences=[PORT.duplicated_sentence],
                ),
            ),
        ]

    # No heading at all, identical terms: collapses on content alone.
    _wire(monkeypatch, candidates=_corpus(("", "")), ranked=[("a", 0.9), ("b", 0.8)])
    blank = await _run(PORT.question)
    assert blank["retrieval"]["policies_duplicate_collapsed"] == 1

    # Different headings, identical terms: the heading is content and is compared.
    _wire(
        monkeypatch,
        candidates=_corpus((PORT.duplicated_heading, VET.duplicated_heading)),
        ranked=[("a", 0.9), ("b", 0.8)],
    )
    differing = await _run(PORT.question)
    assert differing["retrieval"]["policies_duplicate_collapsed"] == 0


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
def test_selection_reads_the_policys_own_words_not_a_vocabulary(
    domain: Domain,
) -> None:
    """No question's wording is privileged, and a total miss is still bounded.

    A scenario quoting one row selects that row; a scenario sharing no term with
    the policy selects nothing on relevance and falls back to document order,
    disclosing the miss. Both paths respect the budget, in every script.
    """

    count = 40
    distinctive = "QQQZZZ"
    sentences = [domain.row_sentence.format(n=i) for i in range(count)]
    sentences[7] = f"{distinctive} {sentences[7]}"
    payload, _ = _published(
        "rows",
        heading=domain.filler_heading,
        marker="rows",
        document_version_id=_DOC_A,
        sentences=sentences,
    )
    policy = {"provision_id": "p", "provision_key": "rows", "heading_path": ["h"]}

    _, hit = rule_slice.select_rules_for_scenario(
        payload, policy=policy, scenario=distinctive
    )
    assert hit["method"] == rule_slice.METHOD_RELEVANCE
    assert "R-rows-7" in hit["selected_rule_ids"], "the row quoting the question was not selected"
    assert hit["selected_rules"] <= rule_slice.SELECTED_RULE_BUDGET

    _, miss = rule_slice.select_rules_for_scenario(
        payload, policy=policy, scenario="\u2603\u2603\u2603"
    )
    assert miss["method"] == rule_slice.METHOD_DOCUMENT_ORDER
    assert miss["selected_rules"] <= rule_slice.SELECTED_RULE_BUDGET
    assert miss["sliced"] is True


# ── duplicate rules inside one policy ────────────────────────────────


def _rows_policy(
    domain: Domain,
    *,
    sentences: list[str],
    marker: str = "rows",
    document_version_id: str = _DOC_A,
    mutate: Any = None,
) -> tuple[dict, dict]:
    """A large policy built from an explicit list of row sentences."""

    payload, extras = _published(
        "rows",
        heading=domain.filler_heading,
        marker=marker,
        document_version_id=document_version_id,
        sentences=sentences,
    )
    if mutate is not None:
        mutate(payload)
    return payload, extras


_POLICY = {"provision_id": "p", "provision_key": "rows", "heading_path": ["h"]}


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
def test_a_repeated_rule_cannot_take_a_second_selection_slot(domain: Domain) -> None:
    """The AIS-shaped defect, stated as a relationship and in three domains.

    Twenty rows, but the first four are the same row said four times and the rest
    are distinct. Every one of them answers the question equally well. If copies
    could take slots, the selection would spend them restating one row; here the
    slots must go to twenty distinct rules, and the copies must be named as
    represented rather than counted as read.
    """

    repeated = domain.row_sentence.format(n=0)
    distinct = [domain.row_sentence.format(n=i) for i in range(1, 25)]
    sentences = [repeated, repeated, repeated, repeated, *distinct]

    payload, _ = _rows_policy(domain, sentences=sentences)
    record, selection = rule_slice.select_rules_for_scenario(
        payload, policy=_POLICY, scenario=domain.row_sentence.format(n=0)
    )

    read_ids = [r["rule_id"] for r in record["rules"]]
    assert len(read_ids) == len(set(read_ids))
    # The copies were never candidates, so at most one of the four is present.
    copies = {"R-rows-0", "R-rows-1", "R-rows-2", "R-rows-3"}
    assert len(copies & set(read_ids)) <= 1, "a repeated rule took more than one slot"
    # Document order picks the representative, deterministically.
    assert copies & set(read_ids) == {"R-rows-0"}

    assert selection["duplicate_rules_collapsed"] == 3
    assert set(selection["represented_rule_ids"]) == {"R-rows-1", "R-rows-2", "R-rows-3"}

    # The arithmetic stays truthful against the *whole* policy.
    assert selection["total_rules"] == len(sentences)
    assert selection["selected_rules"] == len(record["rules"])
    assert selection["rules_discarded"] == (
        selection["total_rules"] - selection["selected_rules"]
    )
    # And a represented rule is never also claimed as read.
    assert set(selection["represented_rule_ids"]).isdisjoint(selection["selected_rule_ids"])


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
def test_every_slot_the_budget_buys_holds_a_different_rule(domain: Domain) -> None:
    """The harm, measured the way the QA measured it.

    The reported failure was not "a duplicate appeared" but "twenty-five ids
    stood for seven rows" — seventy-two per cent of the budget spent restating
    what the record already said, and the rule that decided the case just outside
    what was left. So the property worth asserting is about *distinct* rules: a
    budget of fifteen must buy fifteen different rules whenever the policy has
    that many to give, however many times any of them is repeated.
    """

    distinctive = "QQQZZZ"
    # Twenty rows answer the question, ten do not, and the first is repeated
    # eight times. The term must not appear on *every* row or its weight clamps
    # to zero and the fallback path runs instead of the relevance path.
    bearing = [f"{distinctive} {domain.row_sentence.format(n=i)}" for i in range(20)]
    other = [domain.row_sentence.format(n=i) for i in range(20, 30)]
    sentences = [bearing[0]] * 8 + bearing[1:] + other

    payload, _ = _rows_policy(domain, sentences=sentences)
    record, selection = rule_slice.select_rules_for_scenario(
        payload, policy=_POLICY, scenario=distinctive
    )

    texts = [
        (payload["spans"].get(ref) or {}).get("text")
        for rule in record["rules"]
        for ref in (rule.get("evidence_refs") or [])[:1]
    ]
    assert len(texts) == len(set(texts)), "two slots hold the same row"
    assert len(set(texts)) == rule_slice.SELECTED_RULE_BUDGET, (
        "the budget did not buy a full set of distinct rules"
    )
    assert selection["duplicate_rules_collapsed"] == 7
    assert selection["method"] == rule_slice.METHOD_RELEVANCE


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
@pytest.mark.parametrize(
    "field",
    ["effect_action", "effect_type", "rule_type", "effective_from", "scope", "authority"],
)
def test_one_sentence_under_different_terms_stays_two_rules(
    domain: Domain, field: str
) -> None:
    """Never text or title alone.

    Two rows quoting the identical sentence, differing in exactly one governing
    field. Collapsing either into the other would answer a case from terms that
    do not bind it — the same failure as collapsing two policies on a shared
    heading, one level down.
    """

    sentence = domain.row_sentence.format(n=0)
    made = _rules(marker="rows", document_version_id=_DOC_A, sentences=[sentence, sentence])

    changed = {
        "effect_action": {"effect": Effect(type=EffectType.ALLOW, action="a different action")},
        "effect_type": {"effect": Effect(type=EffectType.DENY, action="allow_action")},
        "rule_type": {"rule_type": RuleType.PROHIBITION},
        "effective_from": {"effective_from": date(2025, 7, 1)},
        "scope": {"scope": PolicyScope(organizational_units=["a-unit"])},
        "authority": {"authority": PolicyAuthority(level="board", owner="registrar", rank=1)},
    }[field]
    made[1] = made[1].model_copy(update=changed)

    payload = build_case_payload(
        policy_set_id="set-x",
        provision_id="prov-rows",
        provision_key="rows",
        heading_path=[domain.filler_heading],
        rules=made,
    )
    # `authority` is governing but the lean record does not carry it, so it
    # reaches the comparison beside the payload — exactly as it does for whole
    # policies. Passing it is what makes this control meaningful rather than a
    # documented gap.
    extras = governing_extras_for_group(made)
    fingerprints = rule_semantic_fingerprints(payload, governing_extras=extras)

    assert fingerprints[0] != fingerprints[1], (
        f"two rules differing in {field} were treated as one"
    )
    representatives, _ = rule_slice.distinct_rule_representatives(
        payload, governing_extras=extras
    )
    assert representatives == [0, 1], "a materially different rule was collapsed away"

    # And the identical pair still collapses, so the control is not just strict.
    same = _rules(marker="rows", document_version_id=_DOC_A, sentences=[sentence, sentence])
    same_payload = build_case_payload(
        policy_set_id="set-x",
        provision_id="prov-rows",
        provision_key="rows",
        heading_path=[domain.filler_heading],
        rules=same,
    )
    identical = rule_semantic_fingerprints(
        same_payload, governing_extras=governing_extras_for_group(same)
    )
    assert identical[0] == identical[1]


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
def test_duplicate_rules_are_told_apart_by_what_their_links_point_at(
    domain: Domain,
) -> None:
    """Relationship semantics apply between rules of one policy too.

    Two rows quoting one sentence, each superseding a different row. They are two
    rules. Two rows superseding rows that themselves govern identically are one
    rule, even though the ids they name differ.
    """

    sentence = domain.row_sentence.format(n=0)
    target_a = domain.duplicated_sentence
    target_b = domain.variant_sentence

    def _build(second_target: str) -> dict:
        payload, _ = _rows_policy(
            domain, sentences=[sentence, sentence, target_a, second_target]
        )
        ids = [r["rule_id"] for r in payload["rules"]]
        payload["rules"][0] = {**payload["rules"][0], "supersedes_rule_ids": [ids[2]]}
        payload["rules"][1] = {**payload["rules"][1], "supersedes_rule_ids": [ids[3]]}
        return payload

    # Different target semantics: two rules.
    differing = _build(target_b)
    fp = rule_semantic_fingerprints(differing)
    assert fp[0] != fp[1], "rules superseding materially different rules were merged"
    assert rule_slice.distinct_rule_representatives(differing)[0] == [0, 1, 2, 3]

    # Same target semantics under different ids: one rule.
    matching = _build(target_a)
    fp = rule_semantic_fingerprints(matching)
    assert matching["rules"][0]["supersedes_rule_ids"] != (
        matching["rules"][1]["supersedes_rule_ids"]
    ), "the fixture must name different ids or this proves nothing"
    assert fp[0] == fp[1]
    representatives, copies = rule_slice.distinct_rule_representatives(matching)
    assert 1 in copies.get(0, [])


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
def test_a_link_to_a_copy_is_followed_to_the_rule_that_stands_for_it(
    domain: Domain,
) -> None:
    """Context must not re-admit a rule the collapse just removed.

    A selected rule names a duplicate as context. The rule it names is in the
    record — under the representative's id — so the link is followed there rather
    than pulling a second copy back in.
    """

    distinctive = "QQQZZZ"
    context_sentence = domain.duplicated_sentence
    sentences = [
        f"{distinctive} {domain.row_sentence.format(n=0)}",
        context_sentence,
        context_sentence,
        *[domain.row_sentence.format(n=i) for i in range(1, 30)],
    ]
    payload, _ = _rows_policy(domain, sentences=sentences)
    ids = [r["rule_id"] for r in payload["rules"]]
    # Point the selected rule at the *second* copy, which is the one collapsed.
    payload["rules"][0] = {**payload["rules"][0], "related_rule_ids": [ids[2]]}

    record, selection = rule_slice.select_rules_for_scenario(
        payload, policy=_POLICY, scenario=distinctive
    )

    read = [r["rule_id"] for r in record["rules"]]
    assert "R-rows-0" in read
    assert "R-rows-1" in read, "the link was not followed to the representative"
    assert "R-rows-2" not in read, "a collapsed copy was re-admitted as context"
    assert len(read) == len(set(read))
    assert len(read) <= rule_slice.SELECTED_RULE_BUDGET
    assert selection["selected_rules"] == len(read)


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
def test_collapsing_rules_never_lifts_the_budget_in_any_domain(domain: Domain) -> None:
    """Freed slots go to distinct rules, never past the ceiling.

    A policy that is mostly copies, every rule naming every other as context —
    the combination of both duplicate layers and the context closure at once.
    """

    repeated = domain.row_sentence.format(n=0)
    sentences = [repeated] * 30 + [domain.row_sentence.format(n=i) for i in range(1, 40)]
    payload, _ = _rows_policy(domain, sentences=sentences)
    ids = [r["rule_id"] for r in payload["rules"]]
    payload["rules"] = [
        {**rule, "related_rule_ids": [i for i in ids if i != rule["rule_id"]]}
        for rule in payload["rules"]
    ]

    for scenario in (domain.question, repeated, "", "zzzz"):
        record, selection = rule_slice.select_rules_for_scenario(
            payload, policy=_POLICY, scenario=scenario
        )
        read = [r["rule_id"] for r in record["rules"]]
        assert len(read) <= rule_slice.SELECTED_RULE_BUDGET, scenario
        assert len(read) == len(set(read)), "a copy reached the record"
        assert selection["selected_rules"] == len(read)
        assert len(selection["selected_rule_ids"]) == selection["selected_rules"]
        assert selection["rules_discarded"] == (
            selection["total_rules"] - selection["selected_rules"]
        )
        assert selection["duplicate_rules_collapsed"] == 29
        assert set(selection["represented_rule_ids"]).isdisjoint(read)


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
def test_the_representative_is_document_order_and_repeats(domain: Domain) -> None:
    """Deterministic without a tie-break, and identical across runs."""

    repeated = domain.row_sentence.format(n=0)
    sentences = [
        domain.row_sentence.format(n=9),
        repeated,
        repeated,
        *[domain.row_sentence.format(n=i) for i in range(1, 25)],
    ]
    payload, _ = _rows_policy(domain, sentences=sentences)

    runs = [
        rule_slice.select_rules_for_scenario(
            payload, policy=_POLICY, scenario=repeated
        )[1]
        for _ in range(3)
    ]
    assert runs[0]["selected_rule_ids"] == runs[1]["selected_rule_ids"] == runs[2]["selected_rule_ids"]
    assert runs[0]["represented_rule_ids"] == runs[1]["represented_rule_ids"]

    representatives, copies = rule_slice.distinct_rule_representatives(payload)
    assert 1 in representatives and 2 not in representatives, "not the earliest occurrence"
    assert copies[1] == [2]


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
def test_a_small_policy_is_still_handed_over_byte_for_byte(domain: Domain) -> None:
    """The collapse is a *selection* rule, and a small policy selects nothing.

    A policy at or under the threshold goes to the gather exactly as it always
    has — the same object, unedited — even when it repeats a rule. That is
    deliberate rather than an oversight: nothing is being narrowed, no slot is
    being competed for, and editing the ordinary case to remove a redundancy the
    document actually contains would make the record disagree with the policy a
    reviewer reads. The receipt says so plainly: nothing was collapsed, because
    nothing was selected.
    """

    repeated = domain.row_sentence.format(n=0)
    sentences = [repeated, repeated, domain.row_sentence.format(n=1)]
    assert len(sentences) <= rule_slice.LARGE_POLICY_RULE_THRESHOLD

    payload, extras = _rows_policy(domain, sentences=sentences)
    record, selection = rule_slice.select_rules_for_scenario(
        payload, policy=_POLICY, scenario=repeated, governing_extras=extras
    )

    assert record is payload, "a policy under the threshold was rebuilt"
    assert selection["sliced"] is False
    assert selection["method"] == rule_slice.METHOD_WHOLE_POLICY
    assert selection["selected_rules"] == len(sentences)
    assert selection["rules_discarded"] == 0
    assert selection["duplicate_rules_collapsed"] == 0
    assert selection["represented_rule_ids"] == []


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
def test_one_sentence_extracted_into_several_rules_stays_several_rules(
    domain: Domain,
) -> None:
    """The false positive the live corpora are actually full of.

    A paragraph often states more than one thing, and extraction emits one rule
    per obligation — so the *same sentence* backs a permission and a prohibition,
    or an obligation and a routing rule. Both live projects are full of this: 34
    same-text groups covering 85 rules in one, 71 groups covering 151 in the
    other, and in every sample the rules differ in effect, type or modality.

    Collapsing on text would have merged a rule that permits with a rule that
    forbids, on the strength of them quoting one line. This is why equivalence is
    never text or title alone, and it is the single most important thing this
    module must keep getting right.
    """

    sentence = domain.row_sentence.format(n=0)
    made = _rules(marker="rows", document_version_id=_DOC_A, sentences=[sentence] * 3)
    made[1] = made[1].model_copy(
        update={
            "effect": Effect(type=EffectType.DENY, action="is not permitted"),
            "rule_type": RuleType.PROHIBITION,
        }
    )
    made[2] = made[2].model_copy(
        update={
            "effect": Effect(type=EffectType.REQUIRE_ACTION, action="must be recorded"),
            "rule_type": RuleType.OBLIGATION,
        }
    )
    payload = build_case_payload(
        policy_set_id="set-x",
        provision_id="prov-rows",
        provision_key="rows",
        heading_path=[domain.filler_heading],
        rules=made,
    )
    extras = governing_extras_for_group(made)

    # One sentence, three rules, three identities.
    texts = {
        (payload["spans"].get(r["evidence_refs"][0]) or {}).get("text")
        for r in payload["rules"]
    }
    assert len(texts) == 1, "the fixture must really share one sentence"
    fingerprints = rule_semantic_fingerprints(payload, governing_extras=extras)
    assert len(set(fingerprints)) == 3, "rules sharing a sentence were merged"

    representatives, copies = rule_slice.distinct_rule_representatives(
        payload, governing_extras=extras
    )
    assert representatives == [0, 1, 2]
    assert copies == {}


# ── diversity ordering, which is never a claim of equality ───────────


def _linked_pair(domain: Domain, *, related: bool) -> list[dict]:
    """Two copies of one policy that differ only in the drafter's reading aids.

    The live hardware shape: every sentence, effect, date, scope and required
    fact identical, and one copy carrying `related_rule_ids` the other does not.
    Not provably identical — so never collapsed — and yet requiring the same
    thing, so reading both before anything else wastes the budget.
    """

    left = _published(
        "pair-a",
        heading=domain.duplicated_heading,
        marker="pa",
        document_version_id=_DOC_A,
        sentences=[domain.duplicated_sentence, domain.filler_sentence],
    )
    right = _published(
        "pair-b",
        heading=domain.duplicated_heading,
        marker="pb",
        document_version_id=_DOC_B,
        sentences=[domain.duplicated_sentence, domain.filler_sentence],
    )
    if related:
        ids = [r["rule_id"] for r in right[0]["rules"]]
        right[0]["rules"][0] = {**right[0]["rules"][0], "related_rule_ids": [ids[1]]}
    return [_candidate("pair-a", left), _candidate("pair-b", right)]


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
async def test_a_near_copy_is_deferred_without_being_called_a_duplicate(
    domain: Domain, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(a) The live shape: not identical, still not worth two of five slots.

    The pair differs in one copy's `related_rule_ids`, so the exact fingerprint
    refuses to call them the same policy — correctly, and that refusal is
    asserted here so this test fails if equality is ever loosened to make the
    ordering unnecessary. The diversity ordering then offers the second copy
    after every distinct group, and the policy that decides the question takes
    the slot it would have had.
    """

    pair = _linked_pair(domain, related=True)
    fillers = [
        _candidate(
            f"fill-{i}",
            _published(
                f"fill-{i}",
                heading=f"{domain.filler_heading} {i}",
                marker=f"f{i}",
                document_version_id=_DOC_A,
                sentences=[f"{domain.filler_sentence} ({i})"],
            ),
        )
        for i in range(3)
    ]
    deciding = _candidate(
        "deciding",
        _published(
            "deciding",
            heading=domain.deciding_heading,
            marker="dec",
            document_version_id=_DOC_A,
            sentences=[domain.deciding_sentence],
        ),
    )
    candidates = [pair[0], *fillers[:2], pair[1], fillers[2], deciding]

    # Equality must still refuse: the ordering exists because it does.
    assert policy_semantic_fingerprint(
        pair[0]["payload"], governing_extras=pair[0]["governing_extras"]
    ) != policy_semantic_fingerprint(
        pair[1]["payload"], governing_extras=pair[1]["governing_extras"]
    )
    # And the normative group must still hold them together.
    assert policy_normative_group_key(
        pair[0]["payload"], governing_extras=pair[0]["governing_extras"]
    ) == policy_normative_group_key(
        pair[1]["payload"], governing_extras=pair[1]["governing_extras"]
    )

    ranked = [
        ("pair-a", 0.90),
        ("fill-0", 0.89),
        ("fill-1", 0.88),
        ("pair-b", 0.87),
        ("fill-2", 0.86),
        ("deciding", 0.85),
    ]
    gathered = _wire(monkeypatch, candidates=candidates, ranked=ranked)

    result = await _run(domain.question)

    evaluated = [r["policy"]["provision_key"] for r in gathered[0]]
    assert "deciding" in evaluated, "the deciding policy still did not get a slot"
    assert "pair-a" in evaluated and "pair-b" not in evaluated
    assert len(evaluated) <= ai_case_project.RETRIEVAL_POLICY_BUDGET

    by_key = {e["provision_key"]: e for e in result["considered"]}
    deferred = by_key["pair-b"]
    # Deferred is not duplicate, and says so in every field a reader looks at.
    assert deferred["discard_reason"] == ai_case_project.DISCARD_OUTSIDE_BUDGET
    assert deferred["discard_reason"] != ai_case_project.DISCARD_DUPLICATE_POLICY_CONTENT
    assert deferred.get("duplicate_of_provision_key") is None
    # Its own rank and score are untouched — nothing was renumbered to hide this.
    assert deferred["best_rank"] == 3
    assert deferred["best_score"] == pytest.approx(0.87)

    retrieval = result["retrieval"]
    assert retrieval["policies_duplicate_collapsed"] == 0
    assert retrieval["policies_diversity_deferred"] == 1
    assert retrieval["policy_selection_order"] == ai_case_project.POLICY_SELECTION_ORDER
    # Every raw candidate remains visible.
    assert len(result["considered"]) == len(candidates)


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
@pytest.mark.parametrize("difference", ["effect", "supersedes", "authority"])
async def test_materially_different_policies_never_share_a_diversity_group(
    domain: Domain, difference: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(b) The ordering must not defer something that says a different thing.

    Same heading, and a difference in what the policy does: a different effect, a
    different rule displaced, or a different authority. Each must fall in its own
    group and be read on its own rank — deferring any of them would lose a
    reviewer the terms that govern their case, which is worse than the crowding
    the ordering exists to fix.
    """

    base_sentences = [domain.duplicated_sentence, domain.filler_sentence]
    left = _published(
        "grp-a",
        heading=domain.duplicated_heading,
        marker="ga",
        document_version_id=_DOC_A,
        sentences=base_sentences,
    )

    if difference == "effect":
        right = _published(
            "grp-b",
            heading=domain.duplicated_heading,
            marker="gb",
            document_version_id=_DOC_B,
            sentences=[domain.variant_sentence, domain.filler_sentence],
        )
    elif difference == "supersedes":
        right = _published(
            "grp-b",
            heading=domain.duplicated_heading,
            marker="gb",
            document_version_id=_DOC_B,
            sentences=base_sentences,
        )
        ids = [r["rule_id"] for r in right[0]["rules"]]
        right[0]["rules"][0] = {**right[0]["rules"][0], "supersedes_rule_ids": [ids[1]]}
    else:
        made = _rules(
            marker="gb", document_version_id=_DOC_B, sentences=base_sentences
        )
        made[0] = made[0].model_copy(
            update={"authority": PolicyAuthority(level="board", owner="registrar", rank=1)}
        )
        payload = build_case_payload(
            policy_set_id="set-x",
            provision_id="prov-gb",
            provision_key="grp-b",
            heading_path=[domain.duplicated_heading],
            rules=made,
        )
        payload["envelope"]["policy_version_id"] = _PV
        right = (payload, governing_extras_for_group(made))

    assert policy_normative_group_key(
        left[0], governing_extras=left[1]
    ) != policy_normative_group_key(right[0], governing_extras=right[1]), (
        f"a difference of {difference} was treated as the same normative content"
    )

    candidates = [_candidate("grp-a", left), _candidate("grp-b", right)]
    gathered = _wire(
        monkeypatch, candidates=candidates, ranked=[("grp-a", 0.9), ("grp-b", 0.8)]
    )
    result = await _run(domain.question)

    assert [r["policy"]["provision_key"] for r in gathered[0]] == ["grp-a", "grp-b"]
    assert result["retrieval"]["policies_diversity_deferred"] == 0
    assert result["retrieval"]["policies_duplicate_collapsed"] == 0


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
def test_the_diversity_group_ignores_only_the_reading_aid(domain: Domain) -> None:
    """The key's whole contract, asserted directly rather than through retrieval."""

    plain = _published(
        "a",
        heading=domain.duplicated_heading,
        marker="a",
        document_version_id=_DOC_A,
        sentences=[domain.duplicated_sentence, domain.filler_sentence],
    )
    with_related = _published(
        "b",
        heading=domain.duplicated_heading,
        marker="b",
        document_version_id=_DOC_B,
        sentences=[domain.duplicated_sentence, domain.filler_sentence],
    )
    ids = [r["rule_id"] for r in with_related[0]["rules"]]
    with_related[0]["rules"][0] = {
        **with_related[0]["rules"][0],
        "related_rule_ids": [ids[1]],
    }

    # `related_rule_ids` is withheld from the ordering key...
    assert policy_normative_group_key(
        plain[0], governing_extras=plain[1]
    ) == policy_normative_group_key(with_related[0], governing_extras=with_related[1])
    # ...and never from equality.
    assert policy_semantic_fingerprint(
        plain[0], governing_extras=plain[1]
    ) != policy_semantic_fingerprint(with_related[0], governing_extras=with_related[1])


# ── evidence diversity inside one policy ─────────────────────────────


def _multi_rule_sentence_policy(domain: Domain) -> tuple[dict, dict]:
    """One passage carrying four genuinely different rules, plus other passages.

    The schedule shape: a sentence that states several obligations, extracted
    into one rule each. They are four rules — one permits, one forbids, one
    obliges, one routes — so they may never be collapsed, and all four match the
    question equally well.
    """

    distinctive = "QQQZZZ"
    shared = f"{distinctive} {domain.row_sentence.format(n=0)}"
    others = [f"{distinctive} {domain.row_sentence.format(n=i)}" for i in range(1, 6)]
    quiet = [domain.filler_sentence + f" ({i})" for i in range(10)]

    made = _rules(
        marker="rows",
        document_version_id=_DOC_A,
        sentences=[shared] * 4 + others + quiet,
    )
    variants = [
        (EffectType.ALLOW, "is permitted", RuleType.PERMISSION),
        (EffectType.DENY, "is not permitted", RuleType.PROHIBITION),
        (EffectType.REQUIRE_ACTION, "must be recorded", RuleType.OBLIGATION),
        (EffectType.REQUIRE_ACTION, "is referred to the registrar", RuleType.ROUTING),
    ]
    for index, (etype, action, rtype) in enumerate(variants):
        made[index] = made[index].model_copy(
            update={"effect": Effect(type=etype, action=action), "rule_type": rtype}
        )

    payload = build_case_payload(
        policy_set_id="set-x",
        provision_id="prov-rows",
        provision_key="rows",
        heading_path=[domain.filler_heading],
        rules=made,
    )
    payload["envelope"]["policy_version_id"] = _PV
    return payload, governing_extras_for_group(made)


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
def test_distinct_source_rows_are_covered_before_a_second_rule_from_one_row(
    domain: Domain,
) -> None:
    """(c) Four rules on one sentence must not take four slots before others.

    They are not collapsed — asserted here, because collapsing them would merge a
    permission with a prohibition. They are *ordered*: the best of the shared
    passage is taken, then the other matching passages, and only then the shared
    passage's remaining rules.
    """

    payload, extras = _multi_rule_sentence_policy(domain)

    # Not duplicates. Four distinct rules on one sentence.
    fingerprints = rule_semantic_fingerprints(payload, governing_extras=extras)
    assert len(set(fingerprints[:4])) == 4
    representatives, copies = rule_slice.distinct_rule_representatives(
        payload, governing_extras=extras
    )
    assert copies == {}, "genuinely different rules were collapsed"

    distinctive = "QQQZZZ"
    record, selection = rule_slice.select_rules_for_scenario(
        payload, policy=_POLICY, scenario=distinctive, governing_extras=extras
    )

    groups = rule_slice.evidence_group_keys(payload)
    by_id = {str(r["rule_id"]): i for i, r in enumerate(payload["rules"])}
    read_groups = [groups[by_id[str(r["rule_id"])]] for r in record["rules"]]

    # Every matching passage is represented before any passage repeats.
    first_six = read_groups[: len(set(groups[:9]))]
    assert len(set(first_six)) == len(first_six), (
        "a source passage was read twice before another matching passage was read once"
    )
    assert len(set(read_groups)) >= 6, "the other matching passages were crowded out"
    assert selection["method"] == rule_slice.METHOD_RELEVANCE
    assert selection["selected_rules"] <= rule_slice.SELECTED_RULE_BUDGET


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
def test_an_unmatched_row_never_displaces_a_second_matching_rule(
    domain: Domain,
) -> None:
    """(d) Diversity reorders matches; it never promotes a non-match.

    Only two passages bear on the question, one of them carrying four rules. The
    remaining slots must go to that passage's other rules, not to rows that
    scored nothing — a rule that does not bear on the question is not made
    relevant by resting on a passage nobody has read.
    """

    distinctive = "QQQZZZ"
    shared = f"{distinctive} {domain.row_sentence.format(n=0)}"
    second = f"{distinctive} {domain.row_sentence.format(n=1)}"
    quiet = [domain.filler_sentence + f" ({i})" for i in range(20)]

    made = _rules(
        marker="rows", document_version_id=_DOC_A, sentences=[shared] * 4 + [second] + quiet
    )
    for index, action in enumerate(["a", "b", "c", "d"]):
        made[index] = made[index].model_copy(
            update={"effect": Effect(type=EffectType.ALLOW, action=f"action {action}")}
        )
    payload = build_case_payload(
        policy_set_id="set-x",
        provision_id="prov-rows",
        provision_key="rows",
        heading_path=[domain.filler_heading],
        rules=made,
    )
    extras = governing_extras_for_group(made)

    record, selection = rule_slice.select_rules_for_scenario(
        payload, policy=_POLICY, scenario=distinctive, governing_extras=extras
    )

    read = {str(r["rule_id"]) for r in record["rules"]}
    matching = {f"R-rows-{i}" for i in range(5)}
    assert matching <= read, "a matching rule was displaced by an unmatched row"
    assert not (read - matching), "an unmatched row entered the record"
    assert selection["selected_rules"] == 5


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
def test_evidence_diversity_still_respects_the_total_budget(domain: Domain) -> None:
    """(g) The schedule shape end to end: many passages, many rules each, total <= 15."""

    distinctive = "QQQZZZ"
    sentences: list[str] = []
    # Fifteen matching rows carrying four rules each, and five rows that do not
    # match — the term must not be on every rule or its weight clamps to zero and
    # the document-order fallback runs instead of the relevance path.
    for row in range(15):
        sentences += [f"{distinctive} {domain.row_sentence.format(n=row)}"] * 4
    for row in range(15, 20):
        sentences += [domain.row_sentence.format(n=row)] * 4
    made = _rules(marker="rows", document_version_id=_DOC_A, sentences=sentences)
    for index in range(len(made)):
        made[index] = made[index].model_copy(
            update={"effect": Effect(type=EffectType.ALLOW, action=f"action {index}")}
        )
    payload = build_case_payload(
        policy_set_id="set-x",
        provision_id="prov-rows",
        provision_key="rows",
        heading_path=[domain.filler_heading],
        rules=made,
    )
    ids = [r["rule_id"] for r in payload["rules"]]
    payload["rules"] = [
        {**rule, "related_rule_ids": [i for i in ids if i != rule["rule_id"]]}
        for rule in payload["rules"]
    ]
    extras = governing_extras_for_group(made)

    record, selection = rule_slice.select_rules_for_scenario(
        payload, policy=_POLICY, scenario=distinctive, governing_extras=extras
    )

    assert len(record["rules"]) <= rule_slice.SELECTED_RULE_BUDGET
    assert selection["selected_rules"] == len(record["rules"])
    assert selection["rules_discarded"] == (
        selection["total_rules"] - selection["selected_rules"]
    )
    groups = rule_slice.evidence_group_keys(payload)
    by_id = {str(r["rule_id"]): i for i, r in enumerate(payload["rules"])}
    read_groups = [groups[by_id[str(r["rule_id"])]] for r in record["rules"]]
    # Passage diversity is a **reserve**, not a filter. At least the quota's worth
    # of distinct source rows is guaranteed, so one heavily-matching row can never
    # take the whole record; the remaining slots go on fused relevance, so a
    # second rule of a row already covered is reachable when it outranks the first
    # rule of a weaker row. Asserting every slot came from a different row would
    # be asserting the starvation this replaced — in a document with more matching
    # rows than slots, it made a row's second obligation unreadable however well
    # it scored.
    quota = rule_slice.evidence_diversity_quota(rule_slice.SELECTED_RULE_BUDGET)
    assert len(set(read_groups)) >= min(quota, len(read_groups))
    assert selection["evidence_diversity_quota"] == quota


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
async def test_diversity_ordering_survives_renaming_everything(
    domain: Domain, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(e) No part of the ordering may turn on a name, a heading or a script.

    The same corpus is run twice: once as written, once with every provision id,
    rule id and heading replaced. Which policies are read, which are deferred,
    and every count must be identical — the ordering is a function of what the
    policies require, and of nothing else.
    """

    async def _outcome(rename: bool) -> tuple:
        pair = _linked_pair(domain, related=True)
        deciding = _candidate(
            "deciding",
            _published(
                "deciding",
                heading=domain.deciding_heading,
                marker="dec",
                document_version_id=_DOC_A,
                sentences=[domain.deciding_sentence],
            ),
        )
        fillers = [
            _candidate(
                f"fill-{i}",
                _published(
                    f"fill-{i}",
                    heading=f"{domain.filler_heading} {i}",
                    marker=f"f{i}",
                    document_version_id=_DOC_A,
                    sentences=[f"{domain.filler_sentence} ({i})"],
                ),
            )
            for i in range(3)
        ]
        candidates = [pair[0], *fillers[:2], pair[1], fillers[2], deciding]
        if rename:
            for candidate in candidates:
                payload = candidate["payload"]
                payload["envelope"]["provision_id"] = f"ZZ-{candidate['provision_id']}"
                # Headings are content and are compared — so rename them
                # *consistently* across the corpus, which must not change which
                # policies group together.
                payload["envelope"]["heading_path"] = [
                    f"\u0634-{part}" for part in payload["envelope"]["heading_path"]
                ]
                payload["rules"] = [
                    {**rule, "rule_id": f"ZZ-{rule['rule_id']}"} for rule in payload["rules"]
                ]
                candidate["provision_id"] = f"ZZ-{candidate['provision_id']}"
                candidate["heading_path"] = list(payload["envelope"]["heading_path"])

        ranked = [
            ("pair-a", 0.90),
            ("fill-0", 0.89),
            ("fill-1", 0.88),
            ("pair-b", 0.87),
            ("fill-2", 0.86),
            ("deciding", 0.85),
        ]
        gathered = _wire(monkeypatch, candidates=candidates, ranked=ranked)
        result = await _run(domain.question)
        return (
            [r["policy"]["provision_key"] for r in gathered[0]],
            [
                (e["provision_key"], e["retained"], e.get("discard_reason"), e["best_rank"])
                for e in result["considered"]
            ],
            result["retrieval"]["policies_diversity_deferred"],
            result["retrieval"]["policies_duplicate_collapsed"],
        )

    assert await _outcome(False) == await _outcome(True)


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
def test_per_row_authority_does_not_reintroduce_order_dependence(
    domain: Domain,
) -> None:
    """Governing extras are attached to their rule, and compared only there.

    The rules of a policy are compared as a sorted multiset precisely so that the
    order an extractor emitted them in cannot decide identity. Carrying the
    per-row `authority` and `priority` *also* as positional lists beside them
    would put that order straight back in: the same rules in a different order,
    with authority varying row to row, would have equal rules and unequal lists.

    Here two policies hold the same three rules under three different
    authorities, one enumerated in reverse. Both the exact fingerprint and the
    normative group key must match — and the second half of the test proves the
    fixture is not trivially equal by moving one authority to a different rule,
    which must break both.
    """

    sentences = [
        domain.duplicated_sentence,
        domain.deciding_sentence,
        domain.filler_sentence,
    ]
    authorities = [
        PolicyAuthority(level="board", owner="alpha", rank=1),
        PolicyAuthority(level="unit", owner="beta", rank=4),
        PolicyAuthority(level="local", owner="gamma", rank=7),
    ]

    def _policy(order: list[int], marker: str, document_version_id: str):
        made = _rules(
            marker=marker,
            document_version_id=document_version_id,
            sentences=[sentences[i] for i in order],
        )
        made = [
            rule.model_copy(update={"authority": authorities[i], "priority": i})
            for rule, i in zip(made, order)
        ]
        payload = build_case_payload(
            policy_set_id="set-x",
            provision_id=f"prov-{marker}",
            provision_key=marker,
            heading_path=[domain.duplicated_heading],
            rules=made,
        )
        payload["envelope"]["policy_version_id"] = _PV
        return payload, governing_extras_for_group(made)

    forward = _policy([0, 1, 2], "fwd", _DOC_A)
    reversed_ = _policy([2, 1, 0], "rev", _DOC_B)

    # The fixture must really vary authority row to row, or nothing is proven.
    assert len({a.owner for a in authorities}) == 3
    assert forward[1]["authority"] != reversed_[1]["authority"], (
        "the extras must differ positionally or this asserts nothing"
    )

    assert policy_semantic_fingerprint(
        forward[0], governing_extras=forward[1]
    ) == policy_semantic_fingerprint(
        reversed_[0], governing_extras=reversed_[1]
    ), "reordering rows with per-row authority broke the exact fingerprint"

    assert policy_normative_group_key(
        forward[0], governing_extras=forward[1]
    ) == policy_normative_group_key(
        reversed_[0], governing_extras=reversed_[1]
    ), "reordering rows with per-row authority broke the normative group"

    # Attribution is preserved: give one sentence a different authority and the
    # two policies must part company again.
    moved = _policy([0, 1, 2], "moved", _DOC_B)
    moved[1]["authority"][0] = {"level": "local", "owner": "gamma", "rank": 7}
    assert policy_semantic_fingerprint(
        forward[0], governing_extras=forward[1]
    ) != policy_semantic_fingerprint(moved[0], governing_extras=moved[1])
    assert policy_normative_group_key(
        forward[0], governing_extras=forward[1]
    ) != policy_normative_group_key(moved[0], governing_extras=moved[1])


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
def test_a_rule_without_extras_is_told_apart_from_one_with_them(
    domain: Domain,
) -> None:
    """Absent and present must not collapse together inside a rule's identity."""

    sentences = [domain.duplicated_sentence, domain.filler_sentence]
    made = _rules(marker="a", document_version_id=_DOC_A, sentences=sentences)
    payload = build_case_payload(
        policy_set_id="set-x",
        provision_id="prov-a",
        provision_key="a",
        heading_path=[domain.duplicated_heading],
        rules=made,
    )

    without = rule_semantic_fingerprints(payload)
    with_extras = rule_semantic_fingerprints(
        payload, governing_extras=governing_extras_for_group(made)
    )
    assert without != with_extras, "an absent extras set fingerprinted as a present one"


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
def test_extras_that_do_not_line_up_still_make_two_policies_differ(
    domain: Domain,
) -> None:
    """The alignment guard must fail safe, not fail silent.

    Extras that cannot be attributed rule by rule are compared as a whole rather
    than dropped — otherwise removing the positional component would have turned
    a false negative into a false match.
    """

    sentences = [domain.duplicated_sentence, domain.filler_sentence]
    made = _rules(marker="a", document_version_id=_DOC_A, sentences=sentences)
    payload = build_case_payload(
        policy_set_id="set-x",
        provision_id="prov-a",
        provision_key="a",
        heading_path=[domain.duplicated_heading],
        rules=made,
    )

    # A list of the wrong length cannot be attributed to any rule.
    left = policy_semantic_fingerprint(payload, governing_extras={"authority": ["x"]})
    right = policy_semantic_fingerprint(payload, governing_extras={"authority": ["y"]})
    assert left != right, "unattributable extras were dropped instead of compared"


@pytest.mark.parametrize("domain", DOMAINS, ids=lambda d: d.name)
async def test_diversity_deferred_counts_only_what_the_ordering_displaced(
    domain: Domain, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The count must mean what the prose beside it says.

    Three controls in one, because the number is only meaningful against all of
    them:

    * **no groups** — nothing shares normative content, so the ordering is a
      no-op and the count is zero;
    * **a group whose second member ranked outside the budget anyway** — it was
      deferred, but nothing displaced it, so the count is still zero;
    * **a group whose second member ranked inside the budget** — it was pushed
      out, so the count is one and the receipt's claim that it "ranked inside the
      retention budget" is true.
    """

    def _filler(index: int) -> dict:
        return _candidate(
            f"fill-{index}",
            _published(
                f"fill-{index}",
                heading=f"{domain.filler_heading} {index}",
                marker=f"f{index}",
                document_version_id=_DOC_A,
                sentences=[f"{domain.filler_sentence} ({index})"],
            ),
        )

    async def _deferred_count(candidates: list[dict], ranked: list[tuple[str, float]]) -> int:
        _wire(monkeypatch, candidates=candidates, ranked=ranked)
        result = await _run(domain.question)
        return result["retrieval"]["policies_diversity_deferred"]

    budget = ai_case_project.RETRIEVAL_POLICY_BUDGET

    # 1. Nothing groups: a pure no-op ordering.
    distinct = [_filler(i) for i in range(budget + 2)]
    assert await _deferred_count(
        distinct, [(f"fill-{i}", 0.9 - i / 100) for i in range(budget + 2)]
    ) == 0

    # 2. A group whose second member never had a slot to lose. The pair's second
    #    copy ranks last, well outside the budget.
    pair = _linked_pair(domain, related=True)
    tail = [pair[0], *[_filler(i) for i in range(budget - 1)], pair[1]]
    tail_ranked = [("pair-a", 0.99)] + [
        (f"fill-{i}", 0.9 - i / 100) for i in range(budget - 1)
    ] + [("pair-b", 0.10)]
    assert await _deferred_count(tail, tail_ranked) == 0, (
        "a candidate that ranked outside the budget was counted as displaced"
    )

    # 3. A group whose second member did have a slot, and lost it.
    pair = _linked_pair(domain, related=True)
    inside = [pair[0], *[_filler(i) for i in range(budget - 2)], pair[1], _filler(99)]
    inside_ranked = [("pair-a", 0.99)] + [
        (f"fill-{i}", 0.9 - i / 100) for i in range(budget - 2)
    ] + [("pair-b", 0.5), ("fill-99", 0.4)]
    assert await _deferred_count(inside, inside_ranked) == 1


def test_the_domains_here_share_no_vocabulary_with_the_incidents() -> None:
    """The guard on this file itself.

    If a later edit reintroduced incident vocabulary here, these domains would
    stop being independent evidence and this file would quietly become a second
    copy of the regression beside it.
    """

    incident_terms = {
        "laptop",
        "vacation",
        "annual leave",
        "penalt",
        "violation",
        "refresh",
        "entitlement",
        "device",
        "hardware",
        "ais",
    }
    for domain in DOMAINS:
        blob = " ".join(
            [
                domain.deciding_heading,
                domain.deciding_sentence,
                domain.duplicated_heading,
                domain.duplicated_sentence,
                domain.variant_sentence,
                domain.filler_heading,
                domain.filler_sentence,
                domain.question,
                domain.row_sentence,
            ]
        ).lower()
        for term in incident_terms:
            assert term not in blob, f"{domain.name} borrows incident vocabulary: {term}"
