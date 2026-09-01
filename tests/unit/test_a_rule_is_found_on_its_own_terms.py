"""A rule is found on its own terms, and the ranking that finds it is deterministic.

THE DEFECT THIS FILE HOLDS

A provision that is really a schedule carries one document and one vector over a
bounded amount of its text. Past that bound its rows are not ranked low — they
are **absent**. A question about the fortieth row of a seventy-four-row schedule
could therefore only reach that schedule through whatever its opening rows
happened to say, and when they said nothing relevant the provision that answers
the question was never retrieved at all. The reviewer was told no policy bore on
their case.

WHAT IS ASSERTED HERE

  * **A row can raise the provision that holds it**, including a provision the
    policy-level ranking did not return at all.
  * **Three rankings, one order.** The relevance ranking over the rendered
    corpus, the rule index's own ranking, and a quantity-compatibility ranking
    are fused by reciprocal rank with ties broken on document order — so one
    question against one version and one index always selects one set of rules.
  * **Quantities are compared as quantities.** A question stating three of
    something matches a row covering two to six of the same thing, and does not
    match a row covering two to six of something else. No unit is named anywhere
    in the code that does it.
  * **Diversity is a reserve, not a filter.** A passage's second rule stays
    reachable when it outranks the first rule of a weaker passage, which the
    unbounded ordering made impossible.
  * **The ceiling holds on every path.** At most fifteen rules reach a gather,
    context included, for every corpus size from one rule to seventy-four.
  * **Nothing here knows a domain.** The corpora below are a berthing tariff, a
    veterinary licence, a procurement threshold, an Arabic allowance schedule and
    a vocabulary that means nothing at all. Every assertion references the
    fixture, never a word in it, and a guard at the end reads the shipped modules
    and fails if a subject, a heading or a language ever appears in the code that
    ranks or indexes.
"""
from __future__ import annotations

import os
import random
from typing import Any

import pytest

os.environ.setdefault("DATABASE_URL", "******localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "******localhost:5433/test")

from policy_platform.infrastructure.assistants import ai_case_project  # noqa: E402
from policy_platform.infrastructure.assistants.ai_case_language import (  # noqa: E402
    ENGLISH_PROJECTION_PROFILE,
    INDEX_PROJECTION_UNAVAILABLE,
)
from policy_platform.infrastructure.projection import policy_rule_slice as rule_slice  # noqa: E402
from policy_platform.infrastructure.search.policy_index import (  # noqa: E402
    CONTENT_TYPE_RULE,
    policy_document_id,
    policy_rule_document_id,
)
from tests.fixtures.search_stubs import manifest_ids  # noqa: E402

pytestmark = pytest.mark.anyio

_PV = "33333333-3333-4333-8333-333333333333"
_POLICY = {"provision_id": "prov-x", "provision_key": "x", "heading_path": ["H"]}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ── five corpora, none of which this file understands ────────────────


class Corpus:
    """One synthetic governance corpus, described only in its own words.

    Every assertion below references these fields and never their values, so a
    sixth corpus requires no change to a single test.

    TWO TEXTS PER ROW, AND WHY

    ``row`` is the document's own sentence, in whatever language the document was
    written in. ``projected_row`` is what the index holds for it: the same row
    rendered into the language the pipeline matches in. They are one string for a
    corpus already written in that language — which is exactly what a faithful
    rendering of it produces — and two for a corpus that is not.

    That split is the whole shape of this milestone, so the fixtures carry it
    rather than pretending it away. It is also what keeps every query below in
    one language: a question is scored against the **projection**, never against
    the source, so the query-side fields (``subject``, ``distinctive``, ``unit``,
    ``other_unit``, ``second_obligation``) are in the processing language for
    every corpus, including the one whose source is not.
    """

    def __init__(
        self,
        name: str,
        *,
        row: str,
        projected_row: str | None = None,
        filler: str,
        projected_filler: str | None = None,
        subject: str,
        distinctive: str,
        unit: str,
        other_unit: str,
        second_obligation: str,
    ) -> None:
        self.name = name
        #: A schedule row as the document writes it, taking a low bound, a high
        #: bound and an ordinal. Never scored against a question.
        self.row = row
        #: The same row as the index holds it. Identity when the document is
        #: already in the processing language.
        self.projected_row = projected_row or row
        #: A sentence every row shares, so the weighting has boilerplate to
        #: discount, and its projection.
        self.filler = filler
        self.projected_filler = projected_filler or filler
        #: Words every projected row shares. A question written only in these
        #: cannot carry a selection, because the weighting discounts a term every
        #: rule carries to nothing — which is the property that makes a schedule
        #: of near-identical rows separable at all.
        self.subject = subject
        #: A code one row carries and no other does. A code, deliberately: a
        #: faithful rendering copies one rather than translating it, which is
        #: what the projection's own preservation check enforces, so it is the
        #: one kind of token that is identical on both sides for every corpus.
        self.distinctive = distinctive
        #: The unit the schedule measures in as the *projection* states it, and
        #: one it does not. Both are query-side.
        self.unit = unit
        self.other_unit = other_unit
        #: A second, differently-governing obligation resting on the same passage.
        self.second_obligation = second_obligation


PORT = Corpus(
    "maritime-berthing",
    row="Occupancy of a commercial berth between {low} and {high} tides in band {n} is charged the extended tariff.",
    subject="Occupancy commercial berth extended tariff band",
    distinctive="QZX-4417",
    unit="tides",
    other_unit="cranes",
    second_obligation="The harbour master records the occupancy in the berthing register before the vessel departs.",
    filler="This provision is issued under the standing authority of the port and is reviewed on the ordinary cycle.",
)

VET = Corpus(
    "veterinary-licensing",
    row="Supervision of between {low} and {high} assistants at tier {n} requires a supplementary endorsement.",
    subject="Supervision assistants supplementary endorsement tier",
    distinctive="QZX-8802",
    unit="assistants",
    other_unit="premises",
    second_obligation="The supervising practitioner files the endorsement with the registrar within the reporting cycle.",
    filler="This provision is issued under the standing authority of the council and is reviewed on the ordinary cycle.",
)

PROCUREMENT = Corpus(
    "procurement-thresholds",
    row="An award of between {low} and {high} units in category {n} is referred to the tender board.",
    subject="award units referred tender board category",
    distinctive="QZX-1290",
    unit="units",
    other_unit="months",
    second_obligation="The contracting officer records the referral in the award register before the notice is issued.",
    filler="This provision is issued under the standing authority of the board and is reviewed on the ordinary cycle.",
)

#: A corpus whose **source** is not in the processing language. It is here to
#: prove the one thing this milestone turns on: the document keeps its own words,
#: the index holds a projection of them, and the question — which is always in
#: the processing language, because the boundary reduced it before anything
#: retrieved — is scored against the projection and never against the source.
#: No question in this file is written in this corpus' language.
NON_ENGLISH_SOURCE = Corpus(
    "arabic-source-allowance",
    row="يصرف بدل يتراوح بين {low} و {high} وحدة في الفئة {n} وفق جدول البدلات.",
    projected_row="An allowance of between {low} and {high} units in band {n} is paid under the allowance schedule.",
    filler="يصدر هذا البند بموجب الصلاحية القائمة ويراجع في الدورة الاعتيادية المقررة.",
    projected_filler=(
        "This clause is issued under the standing authority in force and is reviewed on the ordinary cycle."
    ),
    subject="allowance paid band allowance schedule units",
    distinctive="QZX-3106",
    unit="units",
    other_unit="months",
    second_obligation="The competent authority records the payment in the financial register before the cycle closes.",
)

INVENTED = Corpus(
    "invented-vocabulary",
    row="A grelvin holding between {low} and {high} morticles in tier {n} must lodge a farnstable.",
    subject="grelvin morticles farnstable lodge tier",
    distinctive="QZX-7734",
    unit="morticles",
    other_unit="quorls",
    second_obligation="The brellow records the farnstable in the varnic ledger before the drangel closes.",
    filler="This clause is issued under the standing warrant of the brellow and is reviewed on the ordinary cycle.",
)

CORPORA = (PORT, VET, PROCUREMENT, NON_ENGLISH_SOURCE, INVENTED)


def _payload(
    corpus: Corpus,
    *,
    rows: int,
    step: int = 4,
    second_obligation_on: int | None = None,
    distinctive_on: int | None = None,
    provision_key: str = "x",
) -> dict:
    """A graduated schedule: `rows` rules, each covering its own band.

    Row *n* covers ``[n*step + 1, n*step + step]`` of the corpus' unit, so a
    question stating a value picks out exactly one row by arithmetic — the shape
    a real schedule has, without this file naming a real one.

    ``second_obligation_on`` adds a second, differently-governing rule resting on
    the **same source passage** as that row, which is what the evidence-diversity
    reserve is measured against. ``distinctive_on`` gives one row words no other
    row carries, which is what a lexical ranking needs to have anything to say.
    """

    rules: list[dict] = []
    spans: dict[str, dict] = {}
    for index in range(rows):
        low = index * step + 1
        high = index * step + step
        span_id = f"s{index}"
        text = corpus.row.format(low=low, high=high, n=index) + " " + corpus.filler
        if distinctive_on == index:
            text = f"{text} {corpus.distinctive}"
        spans[span_id] = {"text": text}
        rules.append(
            {
                "rule_id": f"R-{index}",
                "evidence_refs": [span_id],
                "effect": {"type": "REQUIRE", "action": f"refer {index}"},
                "rule_type": "obligation",
                "modality": "must",
            }
        )
        if second_obligation_on == index:
            rules.append(
                {
                    "rule_id": f"R-{index}-b",
                    # The same passage, deliberately: two obligations cut from
                    # one sentence are two rules and neither is a copy.
                    "evidence_refs": [span_id],
                    "effect": {"type": "REQUIRE", "action": corpus.second_obligation},
                    "rule_type": "record_keeping",
                    "modality": "must",
                }
            )

    return {
        "envelope": {
            "policy_version_id": _PV,
            "version_number": 1,
            "provision_key": provision_key,
            "heading_path": ["Schedule"],
        },
        "rules": rules,
        "spans": spans,
        "facts": {},
    }


def _projections_of(
    corpus: Corpus,
    payload: dict,
    *,
    step: int = 4,
    distinctive_on: int | None = None,
) -> dict[str, str]:
    """What the index holds for each rule: the row rendered into one language.

    Built from the corpus' projected templates rather than from the payload's own
    spans, because the payload's spans are the **document's** text and are never
    what a question is scored against. For a corpus already written in the
    processing language the two are the same string — which is exactly what a
    faithful rendering of it produces — and for one that is not they differ,
    which is the difference this file exists to exercise.

    The construction parameters are passed rather than read back off the payload,
    so nothing a test needs ends up inside the record production code measures
    and hands to a gather.
    """

    projections: dict[str, str] = {}
    for rule in payload["rules"]:
        rule_id = str(rule["rule_id"])
        if rule_id.endswith("-b"):
            projections[rule_id] = corpus.second_obligation
            continue
        index = int(rule_id.split("-")[1])
        text = (
            corpus.projected_row.format(low=index * step + 1, high=index * step + step, n=index)
            + " "
            + corpus.projected_filler
        )
        if distinctive_on == index:
            text = f"{text} {corpus.distinctive}"
        projections[rule_id] = text
    return projections


# ── quantities ───────────────────────────────────────────────────────


@pytest.mark.parametrize("corpus", CORPORA, ids=lambda c: c.name)
def test_a_stated_value_matches_a_band_that_covers_it(corpus: Corpus):
    """Three of something is inside two-to-six of the same thing. No unit is named.

    Compared against the **projection**, because that is what a question is ever
    scored against. The document's own row says the same thing in its own words
    and is never put beside a question.
    """

    text = corpus.projected_row.format(low=2, high=6, n=0)
    asked = rule_slice.quantity_scalars(f"3 {corpus.unit}")

    assert asked, "the question stated no quantity this could compare"
    assert rule_slice.quantity_compatible(asked, text)


@pytest.mark.parametrize("corpus", CORPORA, ids=lambda c: c.name)
def test_a_value_outside_the_band_is_not_compatible(corpus: Corpus):
    text = corpus.projected_row.format(low=2, high=6, n=0)
    assert not rule_slice.quantity_compatible(
        rule_slice.quantity_scalars(f"9 {corpus.unit}"), text
    )


@pytest.mark.parametrize("corpus", CORPORA, ids=lambda c: c.name)
def test_a_matching_number_in_the_wrong_unit_gets_nothing(corpus: Corpus):
    """The check is about quantities, not about numbers."""

    text = corpus.projected_row.format(low=2, high=6, n=0)
    assert not rule_slice.quantity_compatible(
        rule_slice.quantity_scalars(f"3 {corpus.other_unit}"), text
    )


def test_a_bare_number_states_no_quantity():
    """A clause reference is not a duration, and matching one against the other
    is how a numeric rank turns into noise."""

    assert rule_slice.quantity_scalars("15") == []
    assert not rule_slice.quantity_compatible(
        rule_slice.quantity_scalars("15"), "a band between 2 and 6 hours"
    )


def test_units_match_on_a_string_relation_and_not_on_a_vocabulary():
    """One generic relation, bounded in both directions."""

    assert rule_slice.units_match("day", "days")
    assert rule_slice.units_match("assistant", "assistants")
    assert not rule_slice.units_match("day", "hours")
    # Too short to conclude anything from a shared prefix.
    assert not rule_slice.units_match("m", "months")
    # Too far apart in length to be one word said twice.
    assert not rule_slice.units_match("ton", "tonnages")


@pytest.mark.parametrize("corpus", CORPORA, ids=lambda c: c.name)
def test_a_value_selects_the_band_that_covers_it_out_of_seventy_four(corpus: Corpus):
    """The measured shape, without the measured document.

    Seventy-four graduated bands, a question stating one value and none of the
    row's other words. The row whose band covers the value is read; the ones
    either side of it are not selected for their numbers.
    """

    payload = _payload(corpus, rows=74, step=4)
    target = 9  # band 9 covers 37..40
    asked = f"{target * 4 + 2} {corpus.unit}"

    _record, selection = rule_slice.select_rules_for_scenario(
        payload,
        policy=_POLICY,
        scenario=asked,
        rule_projections=_projections_of(corpus, payload),
        rule_index_state=rule_slice.RULE_INDEX_UNAVAILABLE,
    )

    assert f"R-{target}" in selection["selected_rule_ids"]
    assert selection["quantity_candidates"] >= 1
    assert selection["selected_rules"] <= rule_slice.SELECTED_RULE_BUDGET


def test_every_question_in_this_file_is_in_the_processing_language():
    """The scope rule, pinned rather than remembered.

    A corpus may be written in any language — that is the point of one of the
    fixtures below being written in a script none of these questions use. A
    *question* may not be: the boundary reduces every question to the processing
    language before anything retrieves, and what a question is scored against is
    the projection, never the source. So the query-side fields are required to be
    in that language on every corpus, and the source-side ones are free.

    This is what stops a fixture drifting back into asking a question in the
    document's language, which would exercise a path the platform no longer has
    and which nothing may be run against a live service.
    """

    for corpus in CORPORA:
        for field in ("subject", "distinctive", "unit", "other_unit", "second_obligation"):
            value = getattr(corpus, field)
            assert value.isascii(), (
                f"{corpus.name}.{field} is a query-side field and is not in the "
                f"processing language: {value!r}"
            )
        for field in ("projected_row", "projected_filler"):
            assert getattr(corpus, field).isascii(), (
                f"{corpus.name}.{field} is what a question is scored against and "
                "must be in the processing language"
            )

    # And at least one corpus really is written in another script, or the rule
    # above is a claim about nothing.
    assert any(not corpus.row.isascii() for corpus in CORPORA)
    assert any(corpus.projected_row != corpus.row for corpus in CORPORA)


# ── fusion ───────────────────────────────────────────────────────────


def test_reciprocal_rank_fusion_prefers_what_more_than_one_ranking_placed():
    """A candidate two rankings placed outranks one only a single ranking placed first."""

    lexical = {1: 0, 2: 1}
    vector = {2: 0, 3: 1}
    fused = rule_slice.fuse_rankings([lexical, vector])

    assert fused[2] > fused[1]
    assert fused[2] > fused[3]
    # Silence is not a penalty: a candidate no ranking placed simply is not here.
    assert 4 not in fused


def test_fusion_is_a_pure_function_and_ties_break_on_document_order():
    """A receipt naming selected rules is worth nothing if they can change."""

    a = rule_slice.fuse_rankings([{5: 0, 2: 0}])
    b = rule_slice.fuse_rankings([{2: 0, 5: 0}])
    assert a == b
    assert sorted(a, key=lambda i: (-a[i], i)) == [2, 5]


@pytest.mark.parametrize("corpus", CORPORA, ids=lambda c: c.name)
def test_the_rule_index_can_reach_a_row_the_question_shares_no_words_with(corpus: Corpus):
    """What the vector arm is for: a paraphrase, or a misspelling, that lexical loses.

    The question is written so that the target row's distinguishing words are
    absent or misspelled. Lexical alone therefore cannot place it — and the rule
    index, which ranked the row on meaning rather than on characters, can.
    """

    payload = _payload(corpus, rows=40, step=4)
    target = 22
    unreachable_by_words = "qqqq wwww eeee"

    lexical_only, lexical_selection = rule_slice.select_rules_for_scenario(
        payload,
        policy=_POLICY,
        scenario=unreachable_by_words,
        rule_projections=_projections_of(corpus, payload),
        rule_index_state=rule_slice.RULE_INDEX_UNAVAILABLE,
    )
    assert lexical_selection["method"] == rule_slice.METHOD_DOCUMENT_ORDER
    assert f"R-{target}" not in lexical_selection["selected_rule_ids"]

    with_index, index_selection = rule_slice.select_rules_for_scenario(
        payload,
        policy=_POLICY,
        scenario=unreachable_by_words,
        rule_projections=_projections_of(corpus, payload),
        rule_hits={f"R-{target}": 0},
        rule_index_state=rule_slice.RULE_INDEX_MATCHED,
    )
    assert index_selection["method"] == rule_slice.METHOD_HYBRID_RULE
    assert f"R-{target}" in index_selection["selected_rule_ids"]
    assert index_selection["rule_index_hits"] == 1


@pytest.mark.parametrize("corpus", CORPORA, ids=lambda c: c.name)
def test_the_method_names_the_rankings_that_actually_ran(corpus: Corpus):
    """Three claims of three different sizes, and none of them is interchangeable."""

    payload = _payload(corpus, rows=30, distinctive_on=3)
    projections = _projections_of(corpus, payload, distinctive_on=3)
    asked = corpus.distinctive

    _r, matched = rule_slice.select_rules_for_scenario(
        payload,
        policy=_POLICY,
        scenario=asked,
        rule_projections=projections,
        rule_hits={"R-3": 0},
        rule_index_state=rule_slice.RULE_INDEX_MATCHED,
    )
    assert matched["method"] == rule_slice.METHOD_HYBRID_RULE
    assert matched["lexical_candidates"] >= 1

    _r, degraded = rule_slice.select_rules_for_scenario(
        payload,
        policy=_POLICY,
        scenario=asked,
        rule_projections=projections,
        rule_index_state=rule_slice.RULE_INDEX_DEGRADED,
    )
    assert degraded["method"] == rule_slice.METHOD_RELEVANCE_V3
    assert degraded["rule_index_hits"] == 0

    _r, unconsulted = rule_slice.select_rules_for_scenario(
        payload, policy=_POLICY, scenario=asked
    )
    assert unconsulted["method"] == rule_slice.METHOD_RELEVANCE

    # And a question the corpus shares no distinguishing word with falls to
    # document order on every one of those paths, which is the only honest
    # reading of "nothing placed".
    _r, nothing = rule_slice.select_rules_for_scenario(
        payload,
        policy=_POLICY,
        scenario="qqqq wwww eeee",
        rule_projections=projections,
        rule_index_state=rule_slice.RULE_INDEX_MATCHED,
    )
    assert nothing["method"] == rule_slice.METHOD_DOCUMENT_ORDER
    assert nothing["fused_candidates"] == 0


def test_a_rule_the_index_has_no_projection_for_is_counted_rather_than_cross_matched():
    """One language on both sides, and the shortfall is disclosed rather than papered over."""

    payload = _payload(PORT, rows=20)
    partial = dict(list(_projections_of(PORT, payload).items())[:5])

    _record, selection = rule_slice.select_rules_for_scenario(
        payload,
        policy=_POLICY,
        scenario=PORT.subject,
        rule_projections=partial,
        rule_index_state=rule_slice.RULE_INDEX_MATCHED,
    )

    assert selection["rules_without_projection"] == 15
    # Every selected rule is one the projection covered, or one the index or the
    # quantity rank placed — never one scored against its own language.
    assert set(selection["selected_rule_ids"]) <= set(partial)


# ── evidence diversity ───────────────────────────────────────────────


def test_the_quota_is_half_the_budget_rounded_up():
    assert rule_slice.evidence_diversity_quota(15) == 8
    assert rule_slice.evidence_diversity_quota(1) == 1
    assert rule_slice.evidence_diversity_quota(4) == 2


def test_the_reserve_guarantees_distinct_passages_without_taking_every_slot():
    """The reserve fills first and stops; the rest is filled on fused rank alone."""

    # Twelve candidates over three passages, fused order as given.
    candidates = list(range(12))
    groups = [index // 4 for index in candidates]

    ordered = rule_slice.order_with_evidence_quota(
        candidates, groups, quota=2, budget=6
    )

    assert ordered[:2] == [0, 4]  # one from each of the first two passages
    # And everything else follows in fused order, including passage members the
    # unbounded ordering would have pushed behind every other passage's first.
    assert ordered[2:6] == [1, 2, 3, 5]


@pytest.mark.parametrize("corpus", CORPORA, ids=lambda c: c.name)
def test_a_second_strongly_relevant_rule_from_one_passage_stays_reachable(corpus: Corpus):
    """The starvation this replaced, stated as the case it broke.

    Two obligations rest on one row. Both bear on the question. Under an
    unbounded diversity ordering the second is offered only after the first rule
    of *every* other passage — which, in a schedule, is never. Under a reserve it
    competes on rank once the reserve is filled, and is read.
    """

    payload = _payload(corpus, rows=30, second_obligation_on=7)
    projections = _projections_of(corpus, payload)

    _record, selection = rule_slice.select_rules_for_scenario(
        payload,
        policy=_POLICY,
        scenario=corpus.subject,
        rule_projections=projections,
        # Both rules of the shared passage are ranked highly by the index, which
        # is the situation the reserve has to survive.
        rule_hits={"R-7": 0, "R-7-b": 1},
        rule_index_state=rule_slice.RULE_INDEX_MATCHED,
    )

    assert "R-7" in selection["selected_rule_ids"]
    assert "R-7-b" in selection["selected_rule_ids"], (
        "a second obligation resting on a passage already covered was unreachable"
    )
    assert selection["selected_rules"] <= rule_slice.SELECTED_RULE_BUDGET


@pytest.mark.parametrize("corpus", CORPORA, ids=lambda c: c.name)
def test_repeated_source_text_with_different_semantics_is_not_a_duplicate(corpus: Corpus):
    """Two rules cut from one sentence are two rules. Collapsing is for copies."""

    payload = _payload(corpus, rows=20, second_obligation_on=3)
    representatives, copies = rule_slice.distinct_rule_representatives(payload)

    assert copies == {}, "two differently-governing rules were treated as one"
    assert len(representatives) == len(payload["rules"])


@pytest.mark.parametrize("corpus", CORPORA, ids=lambda c: c.name)
def test_an_exact_copy_is_still_collapsed(corpus: Corpus):
    """Strictness unchanged: identical in everything compared is one rule said twice."""

    payload = _payload(corpus, rows=20)
    twin = dict(payload["rules"][4])
    twin["rule_id"] = "R-4-copy"
    payload["rules"].append(twin)

    representatives, copies = rule_slice.distinct_rule_representatives(payload)

    assert len(representatives) == len(payload["rules"]) - 1
    assert any("R-4-copy" == payload["rules"][i]["rule_id"] for group in copies.values() for i in group)


# ── the ceiling, over every corpus size ──────────────────────────────


@pytest.mark.parametrize("corpus", CORPORA, ids=lambda c: c.name)
def test_no_corpus_size_from_one_to_seventy_four_puts_more_than_the_budget_in_front(
    corpus: Corpus,
):
    """The invariant, checked at every size rather than at a chosen one.

    Randomised links, so context has something to pull in at every size, and a
    fixed seed so a failure is reproducible. Context fills the slots the
    selection left and never extends the budget — the number a receipt reports as
    the ceiling is the number that held.
    """

    rng = random.Random(20260830)
    for rows in range(1, 75):
        payload = _payload(corpus, rows=rows)
        ids = [rule["rule_id"] for rule in payload["rules"]]
        for rule in payload["rules"]:
            others = [i for i in ids if i != rule["rule_id"]]
            rule["related_rule_ids"] = rng.sample(others, min(3, len(others)))

        record, selection = rule_slice.select_rules_for_scenario(
            payload,
            policy=_POLICY,
            scenario=f"{corpus.subject} 6 {corpus.unit}",
            rule_projections=_projections_of(corpus, payload),
            rule_hits={ids[0]: 0} if ids else None,
            rule_index_state=rule_slice.RULE_INDEX_MATCHED,
        )

        selected = len(record["rules"])
        assert selected <= rule_slice.SELECTED_RULE_BUDGET, rows
        assert selection["selected_rules"] == selected == len(selection["selected_rule_ids"])
        assert selection["rules_discarded"] == selection["total_rules"] - selected
        assert selection["total_rules"] == len(payload["rules"])
        # The record is closed: every span it carries is pointed at by a rule it
        # carries, so nothing is in front of the model that no citation resolves to.
        referenced = {
            ref for rule in record["rules"] for ref in (rule.get("evidence_refs") or [])
        }
        assert set(record["spans"]) == referenced


@pytest.mark.parametrize("corpus", CORPORA, ids=lambda c: c.name)
def test_the_same_question_against_the_same_index_selects_the_same_rules(corpus: Corpus):
    """Deterministic, including its disclosure counters."""

    payload = _payload(corpus, rows=50, second_obligation_on=11)
    projections = _projections_of(corpus, payload)
    hits = {"R-11": 0, "R-30": 1, "R-11-b": 2}

    runs = [
        rule_slice.select_rules_for_scenario(
            payload,
            policy=_POLICY,
            scenario=f"{corpus.subject} 45 {corpus.unit}",
            rule_projections=projections,
            rule_hits=hits,
            rule_index_state=rule_slice.RULE_INDEX_MATCHED,
        )[1]
        for _ in range(8)
    ]

    assert all(run == runs[0] for run in runs)


# ── the two searches, and what a rule hit can do ─────────────────────


def _policy_hit(key: str, score: float, *, version: str = _PV) -> dict:
    return {
        "id": policy_document_id(policy_version_id=version, provision_key=key),
        "@search.score": score,
        "policy_id": key,
        "document_version": version,
        "content_type": "policy",
    }


def _rule_hit(key: str, rule_id: str, *, ordinal: int = 0, version: str = _PV) -> dict:
    return {
        "id": policy_rule_document_id(
            policy_version_id=version, provision_key=key, rule_id=rule_id
        ),
        "content_type": CONTENT_TYPE_RULE,
        "rule_id": rule_id,
        "rule_ordinal": ordinal,
        "provision_key": key,
        "parent_document_id": policy_document_id(
            policy_version_id=version, provision_key=key
        ),
        "document_version": version,
        "retrieval_text": f"projection of {rule_id}",
        # The live rule query is semantic. A rule-only parent may be rescued only
        # when this independently calibrated score clears the precision gate.
        "@search.rerankerScore": 3.0,
    }


def test_a_hit_is_a_rule_hit_only_when_the_document_says_so():
    """Read from the document, never inferred from which query returned it.

    A filter is a request; a content type is a fact. Counting a document as a
    rule because it came back from a rule-scoped query would be trusting the
    filter to have been applied.
    """

    assert ai_case_project.is_rule_hit(_rule_hit("k", "R-1"))
    assert not ai_case_project.is_rule_hit(_policy_hit("k", 0.5))
    assert not ai_case_project.is_rule_hit({"id": "x"})


# ── the gate, on the path a reviewer and an auditor both take ────────


class _Settings:
    ai_enabled = True
    search_enabled = True
    azure_openai_deployment = "slow"
    azure_openai_fast_deployment = "fast"


class _Embed:
    def __init__(self, settings: Any) -> None:
        pass

    async def embed(self, inputs: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in inputs]


def _unprojected_search():
    class _Client:
        def __init__(self, settings: Any) -> None:
            pass

        async def index_exists(self, *a: Any, **k: Any) -> bool:
            return True

        async def vector_search(self, *a: Any, **k: Any) -> list[dict]:
            raise AssertionError(
                "an index with no usable projection must not be queried at all"
            )

        async def find_ids_by_filter(self, *a: Any, **k: Any) -> list[str]:
            return manifest_ids(k.get("filter_expr", ""), ready=False)

    return _Client


def _two_kind_search(*, policy_hits: list[dict], rule_hits: list[dict], seen: list[dict]):
    """A search that answers each scoped query with the documents of that kind.

    Which query it is answering is read from the filter the caller composed,
    which is the same thing the live service reads. `seen` records every call so
    a test can assert what was asked and how often.
    """

    class _Client:
        def __init__(self, settings: Any) -> None:
            pass

        async def index_exists(self, *a: Any, **k: Any) -> bool:
            return True

        async def vector_search(self, index: str, **kwargs: Any) -> list[dict]:
            seen.append(dict(kwargs))
            expression = kwargs.get("filter_expr") or ""
            if f"content_type eq '{CONTENT_TYPE_RULE}'" in expression:
                return [
                    hit
                    for hit in rule_hits
                    if "provision_key eq" not in expression
                    or f"provision_key eq '{hit['provision_key']}'" in expression
                ]
            return list(policy_hits)

        async def find_ids_by_filter(self, *a: Any, **k: Any) -> list[str]:
            return manifest_ids(k.get("filter_expr", ""))

    return _Client


@pytest.mark.parametrize("corpus", CORPORA, ids=lambda c: c.name)
async def test_a_provision_reached_only_by_a_late_row_is_retained_and_read(
    corpus: Corpus, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The end of the recall defect, asserted through the decider rather than a helper.

    Two provisions. The policy-level ranking returns the small one and never
    returns the schedule at all — which is exactly what happens when the row that
    answers the question sits past what one policy document's retrieval text can
    carry, because the row is then not in that document to be matched. A rule
    document for the late row is returned by the rule-level ranking, the schedule
    is raised into the retained set on that row's rank, and the row itself is one
    of the rules a gather is given.

    One question, one embedding, and the provision is not lost.
    """

    schedule = _payload(corpus, rows=60, distinctive_on=47, provision_key="schedule")
    small = _payload(corpus, rows=2, provision_key="small")
    projections = _projections_of(corpus, schedule, distinctive_on=47)
    seen: list[dict] = []
    gathered: list[list[dict]] = []

    # The schedule's own document carries only what fits, and the late row is
    # past it: the projection the policy document would be matched on does not
    # contain the row that answers the question.
    late_projection = projections["R-47"]
    policy_document_projection = " \n".join(
        projections[f"R-{index}"] for index in range(8)
    )
    assert corpus.distinctive not in policy_document_projection
    # And the question is in the processing language whatever language the
    # document was written in — the boundary reduced it before anything
    # retrieved, so the source is never what a query is compared against.
    assert corpus.distinctive.isascii()

    async def _load(session: Any, policy_set_id: Any) -> dict:
        return {
            "has_published_version": True,
            "active_version_id": _PV,
            "active_version_number": 1,
            "candidates": [
                _project_candidate("small", small),
                _project_candidate("schedule", schedule),
            ],
            "excluded": [],
        }

    async def _spy(records: list[dict], **kwargs: Any) -> dict:
        gathered.append(records)
        return {"intent": "informational", "informational": None, "decision": None}

    monkeypatch.setattr(ai_case_project, "get_settings", lambda: _Settings())
    monkeypatch.setattr(ai_case_project, "load_project_scope", _load)
    monkeypatch.setattr(ai_case_project, "AzureOpenAIClient", _Embed)
    monkeypatch.setattr(ai_case_project, "answer_case_over_policies", _spy)
    monkeypatch.setattr(
        ai_case_project,
        "AzureSearchClient",
        _two_kind_search(
            # The schedule is absent from the policy-level ranking entirely.
            policy_hits=[_policy_hit("small", 0.8)],
            rule_hits=[
                dict(
                    _rule_hit("schedule", "R-47", ordinal=47),
                    retrieval_text=late_projection,
                )
            ],
            seen=seen,
        ),
    )

    class _Project:
        id = "set-1"
        key = "a-project"

    result = await ai_case_project.answer_project_case(
        object(), policy_set=_Project(), scenario=corpus.distinctive
    )

    retained = {
        entry["provision_key"] for entry in result["considered"] if entry.get("retained")
    }
    assert "schedule" in retained, "a provision reachable only by one of its rows was lost"
    assert result["retrieval"]["policies_elevated_by_rule"] >= 1
    assert result["retrieval"]["rule_documents_matched"] >= 1
    assert result["retrieval"]["projection_profile"] == ENGLISH_PROJECTION_PROFILE

    # The row itself is one of the rules the gather was given, not merely the
    # provision that holds it.
    schedule_record = next(
        record for record in gathered[0] if record["policy"]["provision_key"] == "schedule"
    )
    assert "R-47" in {rule["rule_id"] for rule in schedule_record["payload"]["rules"]}

    selection = next(
        entry["rule_selection"]
        for entry in result["considered"]
        if entry["provision_key"] == "schedule"
    )
    assert selection["method"] == rule_slice.METHOD_HYBRID_RULE
    assert selection["selected_rules"] <= rule_slice.SELECTED_RULE_BUDGET

    # One question, one embedding, and every query carried the question itself.
    assert {call["query_text"] for call in seen} == {corpus.distinctive}
    assert all(call["vector"] == [0.1, 0.2, 0.3] for call in seen)


def _project_candidate(provision_key: str, payload: dict) -> dict:
    envelope = payload["envelope"]
    return {
        "provision_id": f"prov-{provision_key}",
        "provision_key": provision_key,
        "heading_path": list(envelope.get("heading_path") or []),
        "rules": len(payload["rules"]),
        "policy_version_id": _PV,
        "version_number": 1,
        "search_document_id": policy_document_id(
            policy_version_id=_PV, provision_key=provision_key
        ),
        "payload": {**payload, "envelope": {**envelope, "provision_key": provision_key}},
    }


async def _run_project_scope(monkeypatch, *, search, scenario="a question"):
    """Drive the decider over one candidate against a given search client."""

    async def _load(session: Any, policy_set_id: Any) -> dict:
        return {
            "has_published_version": True,
            "active_version_id": _PV,
            "active_version_number": 1,
            "candidates": [_project_candidate("only", _payload(PORT, rows=2))],
            "excluded": [],
        }

    async def _spy(records: list[dict], **kwargs: Any) -> dict:
        return {"intent": "informational", "informational": None, "decision": None}

    monkeypatch.setattr(ai_case_project, "get_settings", lambda: _Settings())
    monkeypatch.setattr(ai_case_project, "load_project_scope", _load)
    monkeypatch.setattr(ai_case_project, "AzureOpenAIClient", _Embed)
    monkeypatch.setattr(ai_case_project, "answer_case_over_policies", _spy)
    monkeypatch.setattr(ai_case_project, "AzureSearchClient", search)

    class _Project:
        id = "set-1"
        key = "a-project"

    return await ai_case_project.answer_project_case(
        object(), policy_set=_Project(), scenario=scenario
    )


async def test_an_index_holding_only_a_manifest_is_empty_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The manifest is a record of a build, not a document a query ranks.

    The readiness gate guarantees a manifest exists on every path that reaches
    the "why did nothing come back" probe. A probe that asked "does this project
    hold anything at all" without scoping to policy documents would therefore
    always answer yes, and `index_empty` would stop being reachable — a project
    whose corpus really is empty would be reported as stale instead, and the
    repair a reader was offered would be for a different problem.
    """

    probes: list[str] = []

    class _OnlyAManifest:
        def __init__(self, settings: Any) -> None:
            pass

        async def index_exists(self, *a: Any, **k: Any) -> bool:
            return True

        async def vector_search(self, *a: Any, **k: Any) -> list[dict]:
            return []

        async def find_ids_by_filter(self, index: str, **kwargs: Any) -> list[str]:
            expression = kwargs.get("filter_expr", "")
            probes.append(expression)
            if "manifest_state" in expression:
                return ["a-manifest"]
            # Every other lookup is scoped to policy documents and finds none.
            return []

    result = await _run_project_scope(monkeypatch, search=_OnlyAManifest)

    assert result["retrieval"]["status"] == ai_case_project.RETRIEVAL_INDEX_EMPTY
    assert result["evaluation"] is None
    # The probes really were scoped, which is what makes the answer above possible.
    content_probes = [p for p in probes if "manifest_state" not in p]
    assert content_probes
    assert all("content_type eq 'policy'" in probe for probe in content_probes)


async def test_a_probe_that_itself_fails_is_reported_as_a_failure_not_as_emptiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """"The index is empty" is a claim. A probe that did not run cannot make it."""

    class _ProbeExplodes:
        def __init__(self, settings: Any) -> None:
            self._asked = 0

        async def index_exists(self, *a: Any, **k: Any) -> bool:
            return True

        async def vector_search(self, *a: Any, **k: Any) -> list[dict]:
            return []

        async def find_ids_by_filter(self, index: str, **kwargs: Any) -> list[str]:
            if "manifest_state" in kwargs.get("filter_expr", ""):
                return ["a-manifest"]
            raise RuntimeError("the probe could not be made")

    result = await _run_project_scope(monkeypatch, search=_ProbeExplodes)

    assert result["retrieval"]["status"] == ai_case_project.RETRIEVAL_FAILED
    assert result["evaluation"] is None


async def test_a_project_with_no_usable_projection_refuses_rather_than_answering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal, and the reason it is a refusal and not an empty result.

    A rendered question matched against an unrendered corpus scores near zero on
    every policy — which reads exactly like "nothing here bears on your
    question". There is no point downstream at which those can still be told
    apart, so the query is never made and the caller is told which of the two it
    is.
    """

    async def _load(session: Any, policy_set_id: Any) -> dict:
        return {
            "has_published_version": True,
            "active_version_id": _PV,
            "active_version_number": 1,
            "candidates": [
                {
                    "provision_id": "p-1",
                    "provision_key": "k-1",
                    "heading_path": ["A"],
                    "rules": 1,
                    "policy_version_id": _PV,
                    "version_number": 1,
                    "search_document_id": policy_document_id(
                        policy_version_id=_PV, provision_key="k-1"
                    ),
                    "payload": {"envelope": {}, "rules": [{}]},
                }
            ],
            "excluded": [],
        }

    monkeypatch.setattr(ai_case_project, "get_settings", lambda: _Settings())
    monkeypatch.setattr(ai_case_project, "load_project_scope", _load)
    monkeypatch.setattr(ai_case_project, "AzureOpenAIClient", _Embed)
    monkeypatch.setattr(ai_case_project, "AzureSearchClient", _unprojected_search())

    class _Project:
        id = "set-1"
        key = "project-key"

    with pytest.raises(ai_case_project.IndexProjectionUnavailable) as raised:
        await ai_case_project.answer_project_case(
            object(), policy_set=_Project(), scenario="anything at all"
        )

    assert raised.value.code == INDEX_PROJECTION_UNAVAILABLE
    assert raised.value.readiness.profile == ENGLISH_PROJECTION_PROFILE
    assert raised.value.readiness.ready is False
    # It is a `RuntimeError`, so a caller that has not been taught about it still
    # answers 503 rather than 500.
    assert isinstance(raised.value, RuntimeError)


# ── the guard over the shipped code lives on its own ─────────────────
#
# `test_no_m2_code_is_shaped_around_a_corpus.py` parses every module this
# milestone authored or touched and fails if a subject, a document, an
# organisation, an identifier, a measured magnitude or a vocabulary appears in
# executable code. It used to be three weaker checks at the end of this file,
# over three modules; it is one file over eleven now, and duplicating a subset
# of it here would be two places to update and one of them silently weaker.
#
# What stays here is the half a guard over the code cannot do: proving the
# behaviour itself on corpora that have nothing to do with one another, which is
# what the parametrisation over `CORPORA` above is for.
