"""One canonical reading of text, and a catalogue built only from the records.

WHAT M1 CHANGES

Two things that had drifted apart are made one, and a third is built on top.

  1. **One canonicaliser.** Several places asked the same question of two
     strings — *are these the same name?* — and each had its own answer. The
     retrieval tokeniser answered it with ``\\w+`` and a case fold; the fact-key
     path answered it with Unicode normalisation. The two disagreed on every
     input where it mattered, and the disagreement was invisible in English:

       * a combining mark is not a word character, so the tokeniser did not
         merely fail to match Arabic carrying tashkeel against the same word
         without it — it *split the word* into four fragments, and the fragments
         matched nothing;
       * Devanagari came apart at its vowel signs, so ``कितना`` scored as ``क``
         and ``तन``;
       * tatweel, fullwidth forms, ligatures and presentation forms each made a
         second spelling of one word.

     All of that is Unicode, none of it is a language, and none of it is fixed by
     knowing what a document is about.

  2. **The tokeniser delegates to it**, so retrieval and identity can no longer
     answer that question two ways.

  3. **A closed selector catalogue.** The set of facts the retained records
     themselves declare, indexed by canonical key, with every spelling each one
     appears under and the rules that declare it. It exists for a later stage to
     check that a named selector is a thing the policy turns on rather than
     something composed for the occasion — which it can only do if nothing from a
     scenario, from a model, or from this repository's own vocabulary can get in.

WHY THE TESTS LOOK LIKE THIS

The canonicaliser is tested by exact keys rather than by comparing two sides:
comparing only proves the two agree, and would still pass if both collapsed to
the empty string or to a row of hyphens where the letters used to be. The
distinction that matters most is between marks that may be dropped and marks that
may not — dropping a Devanagari vowel sign would fold words that mean different
things onto one key, and collapsing distinct things is worse than failing to
match — so that has a test of its own on both sides.

The catalogue is tested across unrelated subjects and one invented vocabulary,
for the same reason every acceptance in this repository is: a rule that
recognised subjects rather than structure would pass the corpus it was written
against and fail the next one, undetectably.
"""
from __future__ import annotations

import ast
import inspect
import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "******localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "******localhost:5433/test")

from policy_platform.infrastructure.assistants import ai_case_intent  # noqa: E402
from policy_platform.infrastructure.projection import policy_rule_slice  # noqa: E402
from policy_platform.infrastructure.projection import text_canonical  # noqa: E402

canonical_key = text_canonical.canonical_key
canonical_tokens = text_canonical.canonical_tokens


# --------------------------------------------------------------------------- #
# 1. One canonical reading, exact keys, every script the corpus can hold.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        # Latin composed and decomposed: one word to a reader, two code point
        # sequences to a comparison that does not normalise.
        ("caf\u00e9", "café"),
        ("cafe\u0301", "café"),
        ("dur\u00e9e", "durée"),
        ("dure\u0301e", "durée"),
        # Arabic bare, pointed, stretched, and set in presentation forms.
        ("\u0627\u0644\u0633\u0627\u0639\u0627\u062a", "الساعات"),
        ("\u0627\u0644\u0652\u0633\u064e\u0627\u0639\u064e\u0627\u062a", "الساعات"),
        ("\u0645\u062f\u0629", "مدة"),
        ("\u0645\u062f\u0640\u0640\u0640\u0629", "مدة"),
        ("\ufeb3\ufe8e\ufecb\ufe94", "ساعة"),
        ("\u0633\u0627\u0639\u0629", "ساعة"),
        # Compatibility spellings: fullwidth letters and a typographic ligature.
        ("\uff37\uff45\uff45\uff4b\uff4c\uff59\u3000\uff28\uff4f\uff55\uff52\uff53", "weekly-hours"),
        ("Weekly Hours", "weekly-hours"),
        ("\ufb01le number", "file-number"),
        ("file number", "file-number"),
        # Greek, and a case fold that decomposes as it folds.
        ("\u03a9\u03bc\u03ad\u03b3\u03b1", "ωμέγα"),
        ("\u1f68\u03bc\u03ad\u03b3\u03b1", "ὠμέγα"),
        ("\u0130stanbul", "istanbul"),
        ("istanbul", "istanbul"),
        ("Gr\u00fcn Stra\u00dfe", "grün-strasse"),
        # Separators of every kind collapse to one, and never lead or trail.
        ("  Which  tier   this is.  ", "which-tier-this-is"),
        ("Which tier \u2014 this is", "which-tier-this-is"),
        ("subscriber_tier", "subscriber-tier"),
        ("Value (in units)", "value-in-units"),
        ("...", ""),
        ("\u064e\u064f\u0650", ""),
    ],
)
def test_the_canonical_key_of_one_name_is_the_same_however_it_is_written(
    written: str, expected: str
) -> None:
    """Exact keys, asserted rather than merely compared.

    Non-ASCII letters are preserved throughout: a rule that reached for ASCII
    would key every Arabic name to the same empty string, and a caller keying
    state on it would collide every question with every other.
    """

    assert canonical_key(written) == expected


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("\u0915\u093f\u0924\u0928\u093e", "\u0915\u0924\u0928"),
        ("\u0915\u093e\u092e", "\u0915\u092e"),
        ("\u0aa4\u0abe\u0ab0\u0ac0\u0a96", "\u0aa4\u0ab0\u0a96"),
    ],
)
def test_spacing_marks_that_carry_meaning_are_not_folded_away(
    left: str, right: str
) -> None:
    """The distinction the mark rule is written by category to preserve.

    Non-spacing marks may be dropped: a name spelled with tashkeel and one
    without are the same name. Spacing marks may not: in these scripts they *are*
    the vowels, and folding them away would put two words that mean different
    things under one key. Failing to match is recoverable; silently deciding two
    different things are one is not.
    """

    assert canonical_key(left) != canonical_key(right)
    assert canonical_key(left) and canonical_key(right), "neither may be erased"


def test_the_normalisation_sequence_is_stable_in_both_directions() -> None:
    """Folding can itself denormalise, which is why the form is applied twice.

    A single pass leaves inputs whose folded form is not normal, and two spellings
    that should have met then do not. This is the property that makes the whole
    module safe to compare with, so it is asserted rather than assumed.
    """

    import unicodedata

    for written in ("\u0130stanbul", "\u1e9e", "\ufb01le", "\u0132", "\u01c5"):
        folded = text_canonical.fold(written)
        assert folded == unicodedata.normalize("NFKC", folded)
        assert folded == text_canonical.fold(folded), "folding is idempotent"


def test_tokens_apply_the_same_reading_and_a_floor_that_is_not_a_word_list() -> None:
    """The token list is the same runs, with a length floor and nothing else."""

    assert canonical_tokens("The  weekly-hours cap is 30.", min_chars=2) == [
        "the",
        "weekly",
        "hours",
        "cap",
        "is",
        "30",
    ]
    # The floor is a length, applied identically in every script.
    assert canonical_tokens("a bb ccc", min_chars=2) == ["bb", "ccc"]
    assert canonical_tokens("a bb ccc", min_chars=1) == ["a", "bb", "ccc"]


# --------------------------------------------------------------------------- #
# 2. Retrieval reads text the same way identity does.
# --------------------------------------------------------------------------- #


def test_the_retrieval_tokeniser_is_the_shared_canonicaliser() -> None:
    """Not "equivalent to": the same function, so the two cannot drift again.

    Two implementations that agree today are two implementations, and the defect
    this replaces is exactly what happens when one of them is changed.
    """

    for written in (
        "\u0627\u0644\u0652\u0633\u064e\u0627\u0639\u064e\u0627\u062a \u0627\u0644\u0645\u0642\u0631\u0631\u0629",
        "Weekly Hours, and the cap.",
        "\u0915\u093f\u0924\u0928\u093e \u0938\u092e\u092f",
    ):
        assert policy_rule_slice._tokens(written) == canonical_tokens(
            written, min_chars=policy_rule_slice._MIN_TOKEN_CHARS
        )


@pytest.mark.parametrize(
    ("marked", "bare"),
    [
        (
            "\u0627\u0644\u0652\u0633\u064e\u0627\u0639\u064e\u0627\u062a",
            "\u0627\u0644\u0633\u0627\u0639\u0627\u062a",
        ),
        ("\u0645\u062f\u0640\u0640\u0640\u0629", "\u0645\u062f\u0629"),
        ("cafe\u0301", "caf\u00e9"),
    ],
)
def test_a_marked_spelling_is_one_token_and_meets_its_unmarked_self(
    marked: str, bare: str
) -> None:
    """The stored-text half of the defect, stated as the scorer sees it.

    Before, the marked spelling was not one token that failed to match — it was
    several tokens that could not match anything, so the *record's own words* were
    read wrongly before any question reached them.

    This is a claim about reading stored text, not about answering a question in
    two languages. What is indexed and what is queried are decided upstream; the
    tokeniser's job is only to read whatever text it is handed correctly, and a
    record is held verbatim in whatever language its document was written in.
    """

    assert policy_rule_slice._tokens(marked) == policy_rule_slice._tokens(bare)
    assert len(policy_rule_slice._tokens(marked)) == 1


def test_a_word_whose_vowels_are_spacing_marks_survives_tokenising() -> None:
    """The same guard, on stored text in another script: one word stays one word."""

    assert policy_rule_slice._tokens("\u0915\u093f\u0924\u0928\u093e") == ["कितना"]


def test_retrieval_takes_one_query_and_offers_no_second_language_channel() -> None:
    """The boundary, pinned where it would be easiest to erode.

    The tempting repair for a question and a record in different languages is to
    pass both spellings of the question and match either — a second parameter, a
    list of queries, a "fall back to the original" flag. Each is a bilingual
    matcher growing inside the scorer, where it would be invisible, untestable per
    language, and impossible to reason about once two of them disagreed.

    So retrieval takes exactly one query string. Whatever is done about language
    happens before this is called and is the business of the stage that owns it;
    this asserts only that no side channel exists here for it to leak through.
    """

    import inspect as _inspect

    score = _inspect.signature(policy_rule_slice.score_rules).parameters
    positional = [
        name
        for name, parameter in score.items()
        if parameter.kind is not _inspect.Parameter.KEYWORD_ONLY
    ]
    assert positional == ["payload", "scenario"], positional
    # The corpus side may be handed in, and only the corpus side. What arrives
    # here is the record's *own* text rendered into the one language the query is
    # in — never a second spelling of the question — so it is keyword-only, and
    # the name check below is what holds it to that.
    scored_query_like = [
        name
        for name in score
        if any(token in name for token in ("scenario", "query", "question"))
    ]
    assert scored_query_like == ["scenario"], scored_query_like

    select = _inspect.signature(policy_rule_slice.select_rules_for_scenario).parameters
    query_like = [
        name
        for name in select
        if any(token in name for token in ("scenario", "query", "question", "text"))
    ]
    assert query_like == ["scenario"], query_like
    # `from __future__ import annotations` leaves these as strings, so compare by
    # name rather than by object and accept either form.
    annotation = select["scenario"].annotation
    assert annotation in (str, "str"), f"one query, one string, not {annotation!r}"

    # And nothing in the module offers a second one under another name.
    source = _inspect.getsource(policy_rule_slice)
    for side_channel in (
        "original_query",
        "source_query",
        "queries",
        "scenario_original",
        "scenario_translated",
        "fallback_query",
    ):
        assert side_channel not in source, f"a second query channel named {side_channel!r}"


def _numbered_payload(count: int, *, subject: str) -> dict:
    """A policy large enough to be sliced, with rows that differ by one word."""

    return {
        "envelope": {"provision_id": "prov", "provision_key": "k"},
        "spans": {
            f"S{index}": {"text": f"Row {index} of the {subject} schedule applies to band {index}."}
            for index in range(count)
        },
        "facts": {},
        "rules": [
            {
                "rule_id": f"R-{index}",
                "rule_type": "obligation",
                "evaluation_mode": "deterministic",
                "required_facts": [],
                "evidence_refs": [f"S{index}"],
            }
            for index in range(count)
        ],
    }


def test_selection_stays_deterministic_and_within_its_budget() -> None:
    """The canonicaliser changed how text is read, not how much is selected.

    Scores move — that is the point — but the two properties a receipt reports
    must not: the same payload and question select the same rules every run, and
    never more than the budget.
    """

    payload = _numbered_payload(40, subject="numbered")
    policy = {"provision_id": "prov", "provision_key": "k", "heading_path": ["1"]}

    runs = [
        policy_rule_slice.select_rules_for_scenario(
            payload, policy=policy, scenario="which band applies to row 7?"
        )
        for _ in range(5)
    ]
    first_ids = runs[0][1]["selected_rule_ids"]
    for _, selection in runs:
        assert selection["selected_rule_ids"] == first_ids, "selection must not vary"
        assert len(selection["selected_rule_ids"]) <= policy_rule_slice.SELECTED_RULE_BUDGET
        assert selection["selected_rules"] == len(selection["selected_rule_ids"])


def test_scoring_is_a_pure_function_of_the_payload_and_the_question() -> None:
    """No randomness, no clock, no ordering that depends on anything else."""

    payload = _numbered_payload(30, subject="numbered")
    scores = [policy_rule_slice.score_rules(payload, "band 3") for _ in range(4)]
    assert all(row == scores[0] for row in scores)


# --------------------------------------------------------------------------- #
# 3. A catalogue that can only contain what the records declare.
# --------------------------------------------------------------------------- #


def _record(
    provision_key: str,
    *,
    rule_id: str,
    required: list[dict] | None = None,
    facts: dict | None = None,
    rule_facts: list[dict] | None = None,
    attributes: dict | None = None,
) -> dict:
    return {
        "policy": {"provision_id": f"prov-{provision_key}", "provision_key": provision_key},
        "payload": {
            "envelope": {"provision_id": f"prov-{provision_key}", "provision_key": provision_key},
            "spans": {"S1": {"text": "A sentence the document wrote."}},
            "facts": facts or {},
            "rules": [
                {
                    "rule_id": rule_id,
                    "rule_type": "obligation",
                    "evaluation_mode": "ai_ready",
                    "required_facts": required or [],
                    "facts": rule_facts or [],
                    "attributes": attributes or {},
                    "evidence_refs": ["S1"],
                }
            ],
        },
    }


#: Four policies with nothing in common but their structure. The last is written
#: in vocabulary that exists in no language, so a catalogue that recognised
#: subjects rather than slots has nothing at all to recognise.
_DOMAIN_RECORDS = [
    _record(
        "pricing",
        rule_id="R-RATE",
        required=[{"name": "subscriber-tier", "phrase": "the tier the subscription is on"}],
    ),
    _record(
        "approval",
        rule_id="R-APPROVAL",
        required=[{"name": "request-value", "phrase": "the value of the request"}],
    ),
    _record(
        "inspection",
        rule_id="R-INSPECTION",
        facts={"F1": {"name": "vessel-class", "source_phrase": "the class the vessel is registered in"}},
        rule_facts=[{"ref": "F1", "roles": ["subject"]}],
    ),
    _record(
        "invented",
        rule_id="R-GLOMMAGE",
        attributes={
            "applies": [
                {"attribute": "quandle-habitus", "text": "whether the quandle is zorbic or plerric"}
            ]
        },
    ),
]


def _catalogue(records: list[dict]) -> dict:
    return ai_case_intent.selector_catalogue(records)


def test_the_catalogue_finds_the_selector_each_unrelated_record_declares() -> None:
    """Four subjects, one reading — from slots, never from what the slots say."""

    catalogue = _catalogue(_DOMAIN_RECORDS)
    keys = {entry["key"] for entry in catalogue["selectors"]}

    assert {"subscriber-tier", "request-value", "vessel-class", "quandle-habitus"} <= keys
    by_key = {entry["key"]: entry for entry in catalogue["selectors"]}
    assert by_key["subscriber-tier"]["rule_ids"] == ["R-RATE"]
    assert by_key["vessel-class"]["rule_ids"] == ["R-INSPECTION"]
    assert by_key["quandle-habitus"]["rule_ids"] == ["R-GLOMMAGE"]
    assert catalogue["records_indexed"] == 4
    assert catalogue["rules_indexed"] == 4


def test_a_selector_the_records_never_named_is_not_in_the_catalogue() -> None:
    """The closure that makes the catalogue worth having.

    A later stage checks a named selector against this. If a name the scenario
    invented could reach it, the check would pass exactly the thing it exists to
    catch.
    """

    catalogue = _catalogue(_DOMAIN_RECORDS)
    keys = {entry["key"] for entry in catalogue["selectors"]}

    for absent in ("weekly-hours", "which-breach-this-is", "anything-at-all"):
        assert absent not in keys
        assert absent not in catalogue["alias_index"]


def test_every_spelling_of_one_fact_collapses_onto_one_entry() -> None:
    """A name, a phrase and an internal id are one thing, not three questions."""

    catalogue = _catalogue(
        [
            _record(
                "one",
                rule_id="R-ONE",
                facts={
                    "hours#ab12": {
                        "name": "Weekly Hours",
                        "source_phrase": "hours worked in the week",
                    }
                },
                rule_facts=[{"ref": "hours#ab12"}],
                required=[{"name": "weekly hours"}],
            )
        ]
    )

    entries = [e for e in catalogue["selectors"] if e["key"] == "weekly-hours"]
    assert len(entries) == 1, "one fact, one entry"
    (entry,) = entries
    assert entry["name"] == "weekly hours", "the declared name outranks a phrase or an id"
    assert "hours worked in the week" in entry["aliases"]
    assert "hours#ab12" in entry["aliases"]
    # And every spelling resolves back to it, which is what a later stage needs.
    for alias_key in entry["alias_keys"]:
        assert catalogue["alias_index"][alias_key] == "weekly-hours"


def test_two_declarations_that_key_alike_merge_and_keep_both_rule_ids() -> None:
    """A key collision is one entry carrying both origins, never two entries."""

    catalogue = _catalogue(
        [
            _record("a", rule_id="R-A", required=[{"name": "Subscriber Tier"}]),
            _record("b", rule_id="R-B", required=[{"name": "subscriber_tier"}]),
        ]
    )

    entries = [e for e in catalogue["selectors"] if e["key"] == "subscriber-tier"]
    assert len(entries) == 1
    assert entries[0]["rule_ids"] == ["R-A", "R-B"]
    assert entries[0]["aliases"] == ["Subscriber Tier", "subscriber_tier"]


def test_the_catalogue_is_the_same_object_however_many_times_it_is_built() -> None:
    """Determinism, asserted where a validator will depend on it.

    A catalogue whose naming or ordering moved between runs would let a plan be
    accepted once and refused the next time over the same records, with nothing
    changed but iteration order.
    """

    built = [_catalogue(_DOMAIN_RECORDS) for _ in range(5)]
    for other in built[1:]:
        assert other == built[0]


def test_a_name_wins_over_a_phrase_and_a_phrase_over_an_internal_id() -> None:
    """Which spelling names an entry is decided by slot, then by document order.

    An id is a handle the projection minted, not what the document called the
    thing, so it never becomes the name while anything else is available — but it
    is still an alias, so a caller holding one can resolve it.
    """

    only_id = _catalogue(
        [_record("x", rule_id="R-X", facts={"F9": {"source_phrase": ""}}, rule_facts=[{"ref": "F9"}])]
    )
    assert [e["name"] for e in only_id["selectors"]] == ["F9"]

    with_phrase = _catalogue(
        [
            _record(
                "y",
                rule_id="R-Y",
                facts={"F9": {"source_phrase": "the length of service"}},
                rule_facts=[{"ref": "F9"}],
            )
        ]
    )
    (entry,) = with_phrase["selectors"]
    assert entry["name"] == "the length of service"
    assert entry["key"] == "the-length-of-service"
    assert "F9" in entry["aliases"]


def test_no_rule_id_in_the_catalogue_names_a_rule_that_is_not_there() -> None:
    """Rule ids are closed here for the same reason citations are.

    A later stage will tell a reviewer which rules are waiting on a selector. An
    id that named nothing in the records would send them after a rule nobody read
    — a fabrication wearing a different field name.

    Asserted as the invariant rather than against one fixture: every id the
    catalogue emits, over every record shape in this file, must be one the records
    actually declare.
    """

    for records in (
        _DOMAIN_RECORDS,
        [_DOMAIN_RECORDS[0]],
        [
            _record(
                "mixed",
                rule_id="R-MIXED",
                required=[{"name": "a-selector"}],
                facts={"F1": {"name": "another-selector"}},
                rule_facts=[{"ref": "F1"}],
                attributes={"outcome": [{"attribute": "a-third", "fact_ref": "F1"}]},
            )
        ],
    ):
        declared = {
            str(rule["rule_id"])
            for record in records
            for rule in record["payload"]["rules"]
            if rule.get("rule_id")
        }
        catalogue = _catalogue(records)
        for entry in catalogue["selectors"]:
            assert set(entry["rule_ids"]) <= declared, entry
            assert len(set(entry["rule_ids"])) == len(entry["rule_ids"]), "no id twice"


def test_a_fact_declared_only_in_the_dictionary_carries_the_rules_that_use_it() -> None:
    """A dictionary entry nothing points at is still catalogued, with no rule ids.

    It is something the record names, so a later stage may legitimately resolve a
    selector to it; but claiming a rule turns on it when none says so would be
    this layer inventing a relationship the projection never recorded.
    """

    catalogue = _catalogue(
        [
            _record(
                "unused",
                rule_id="R-USES-NOTHING",
                facts={
                    "F-USED": {"name": "used-selector"},
                    "F-SPARE": {"name": "spare-selector"},
                },
                rule_facts=[{"ref": "F-USED"}],
            )
        ]
    )

    by_key = {entry["key"]: entry for entry in catalogue["selectors"]}
    assert by_key["used-selector"]["rule_ids"] == ["R-USES-NOTHING"]
    assert by_key["spare-selector"]["rule_ids"] == [], "no rule said it turns on this"


def test_the_catalogue_reads_unicode_the_same_way_everything_else_does() -> None:
    """One spelling pointed, one bare, one stretched — one selector."""

    catalogue = _catalogue(
        [
            _record(
                "ar",
                rule_id="R-AR",
                required=[
                    {
                        "name": "\u0627\u0644\u0652\u0633\u064e\u0627\u0639\u064e\u0627\u062a",
                        "phrase": "\u0627\u0644\u0640\u0640\u0633\u0627\u0639\u0627\u062a",
                    }
                ],
            )
        ]
    )

    (entry,) = catalogue["selectors"]
    assert entry["key"] == "الساعات"
    assert len(entry["alias_keys"]) == 1, "two spellings, one key"


def test_a_declaration_with_nothing_to_key_on_is_skipped_not_given_a_blank_key() -> None:
    """A blank key would collect every unnameable thing under one identifier."""

    catalogue = _catalogue(
        [_record("blank", rule_id="R-BLANK", required=[{"name": "..."}, {"name": "  "}])]
    )
    assert catalogue["selectors"] == []
    assert catalogue["alias_index"] == {}


# --------------------------------------------------------------------------- #
# 4. The delegation did not move behaviour that was not asked to move.
# --------------------------------------------------------------------------- #


def test_the_declared_name_map_still_reads_only_declared_required_facts() -> None:
    """The catalogue knows more than this map is allowed to use.

    Widening what may rename a caller's fact — to a phrase lifted from a sentence,
    or to an attribute — is a behaviour change, and it belongs to the stage that
    asks for it rather than to a refactor meant to unify how text is read.
    """

    rules = [
        {
            "rule_id": "R-ONE",
            "required_facts": [{"name": "weekly-hours"}],
            "attributes": {"applies": [{"attribute": "employment-status", "text": "a phrase"}]},
        }
    ]

    names = ai_case_intent._rule_fact_names(rules)

    assert names == {"weekly-hours": "weekly-hours"}
    assert "employment-status" not in names, "an attribute does not rename a caller's fact"


def test_an_attribute_never_renames_a_required_fact_declared_only_by_phrase() -> None:
    """The regression: the weakest declared slot still beats the strongest other one.

    A rule may declare the fact it needs with a ``phrase`` and no ``name``. An
    attribute that canonicalises to the same key ranks *above* that phrase in the
    catalogue's naming order — quite correctly, because the catalogue is choosing
    what to call a selector across every slot that mentions it.

    This map is not that question. It answers "what did the rule call the fact it
    declared", and an attribute did not declare anything. Reading the entry's name
    handed the caller the attribute's casing and spelling for a fact the rule had
    named in its own words, which is a spelling no rule ever used.
    """

    rules = [
        {
            "rule_id": "R-ONE",
            "required_facts": [{"phrase": "weekly hours"}],
            "attributes": {"applies": [{"attribute": "Weekly_Hours"}]},
        }
    ]

    assert ai_case_intent._rule_fact_names(rules) == {"weekly-hours": "weekly hours"}


@pytest.mark.parametrize(
    "attribute",
    ["Weekly_Hours", "WEEKLY HOURS", "weekly  hours", "Weekly-Hours", "weekly.hours"],
)
def test_no_spelling_of_a_same_key_attribute_displaces_the_declared_phrase(
    attribute: str,
) -> None:
    """Every way the attribute could be written lands on the same key and still loses.

    The failure was not about one spelling. Any attribute that canonicalises alike
    outranked the phrase, so the test is written over the spellings rather than
    against the one that happened to be found.
    """

    rules = [
        {
            "rule_id": "R-ONE",
            "required_facts": [{"phrase": "weekly hours"}],
            "attributes": {"outcome": [{"attribute": attribute}]},
        }
    ]

    assert ai_case_intent._rule_fact_names(rules) == {"weekly-hours": "weekly hours"}


def test_a_declared_name_still_wins_over_the_phrase_beside_it() -> None:
    """Control: within the declared slots, the stronger one is still chosen.

    The repair narrows *which* slots may name a fact. It must not also flatten the
    order among the slots that may — a rule that gives both a name and a phrase is
    named by the name, as it always was.
    """

    rules = [
        {
            "rule_id": "R-ONE",
            "required_facts": [{"name": "weekly-hours", "phrase": "the hours worked in a week"}],
            "attributes": {"applies": [{"attribute": "Weekly Hours"}]},
        }
    ]

    assert ai_case_intent._rule_fact_names(rules) == {"weekly-hours": "weekly-hours"}


def test_an_attribute_on_a_different_key_is_absent_and_disturbs_nothing() -> None:
    """Control: the fix is about collision, not about attributes in general.

    An attribute that keys to something else was never in this map and still is
    not, and its presence leaves the declared fact exactly as it was — so the
    repair cannot be passing by suppressing attributes wholesale.
    """

    with_attribute = ai_case_intent._rule_fact_names(
        [
            {
                "rule_id": "R-ONE",
                "required_facts": [{"phrase": "weekly hours"}],
                "attributes": {"applies": [{"attribute": "employment-status"}]},
            }
        ]
    )
    without = ai_case_intent._rule_fact_names(
        [{"rule_id": "R-ONE", "required_facts": [{"phrase": "weekly hours"}]}]
    )

    assert with_attribute == without == {"weekly-hours": "weekly hours"}


def test_the_earliest_declaration_still_names_the_fact() -> None:
    """The pre-catalogue tie-break, recorded rather than re-derived.

    Two rules declaring one key: the first names it. The required-fact traversal
    writes that down as it walks and nothing afterwards may move it, so this holds
    however the catalogue later chooses to display the entry.
    """

    names = ai_case_intent._rule_fact_names(
        [
            {"rule_id": "R-ONE", "required_facts": [{"phrase": "weekly hours"}]},
            {"rule_id": "R-TWO", "required_facts": [{"name": "Weekly-Hours"}]},
        ]
    )

    assert names == {"weekly-hours": "weekly hours"}


def test_a_name_that_is_only_whitespace_names_nothing_and_does_not_fall_through() -> None:
    """The edge the old rule had, reproduced because callers may depend on it.

    The choice between name and phrase is made on the raw values. A name of spaces
    is a true value, so it wins the choice — and then strips to nothing, so the
    declaration names nothing at all rather than falling back to the phrase beside
    it. Tidying that into "use the name if it has content" would start naming facts
    the old code left unnamed.

    This case is also why the answer cannot be read back from the alias list: the
    blank was never an alias, so nothing downstream can see that it won.
    """

    assert (
        ai_case_intent._rule_fact_names(
            [{"rule_id": "R", "required_facts": [{"name": "   ", "phrase": "weekly hours"}]}]
        )
        == {}
    )


def test_a_name_with_no_keyable_characters_also_names_nothing() -> None:
    """The same shape with punctuation instead of spaces.

    The name wins the choice, survives stripping, and then yields no key — so the
    declaration is skipped. The phrase beside it is not consulted, and the
    catalogue's own entry for that phrase is left without a compatibility name,
    which is precisely how the old code behaved.
    """

    rules = [{"rule_id": "R", "required_facts": [{"name": "...", "phrase": "weekly hours"}]}]

    assert ai_case_intent._rule_fact_names(rules) == {}
    # The catalogue still knows about the phrase — it is a spelling the record
    # used — it simply carries no compatibility name for it.
    (entry,) = ai_case_intent.selector_catalogue([{"rules": rules}])["selectors"]
    assert entry["key"] == "weekly-hours"
    assert entry["required_primary"] == ""


def test_a_bare_declaration_is_its_own_name() -> None:
    """A required fact that is a value rather than an object names itself."""

    assert ai_case_intent._rule_fact_names(
        [{"rule_id": "R", "required_facts": ["Weekly Hours"]}]
    ) == {"weekly-hours": "Weekly Hours"}


def test_no_earlier_alias_can_seed_the_compatibility_name() -> None:
    """Attributes and dictionary entries are walked first, and must not leak in.

    The fact dictionary is read before the rules and attributes after them, and
    both can land on a key a required fact also declares. Neither may create a
    compatibility name, and neither may replace one: the field is written only by
    the required-fact traversal.
    """

    rules = [
        {
            "rule_id": "R",
            "facts": [{"ref": "F1"}],
            "attributes": {"applies": [{"attribute": "Weekly Hours"}]},
        }
    ]
    catalogue = ai_case_intent.selector_catalogue(
        [{"facts": {"F1": {"name": "weekly-hours"}}, "rules": rules}]
    )

    (entry,) = catalogue["selectors"]
    assert entry["key"] == "weekly-hours"
    assert entry["required_primary"] == "", "no rule declared it as required"
    assert ai_case_intent._rule_fact_names(rules) == {}


# --------------------------------------------------------------------------- #
# 4c. The compatibility projection against a reference, over generated shapes.
# --------------------------------------------------------------------------- #


def _pre_m1_rule_fact_names(rules: list[dict]) -> dict[str, str]:
    """The naming rule exactly as it was before the catalogue existed.

    Transcribed here rather than imported, because the point is to compare the new
    implementation against the old *behaviour*: a reference that shared code with
    the thing under test would agree with it by construction.

    It calls the current key function on purpose. M1 changed how a key is derived
    and that change has its own preservation tests; what is under test here is
    only which spelling is chosen, so the keying is held constant between the two
    sides.
    """

    names: dict[str, str] = {}
    for rule in rules or []:
        for required in (rule or {}).get("required_facts") or []:
            if isinstance(required, dict):
                name = str(required.get("name") or required.get("phrase") or "").strip()
            else:
                name = str(required or "").strip()
            key = ai_case_intent._fact_key(name)
            if key and key not in names:
                names[key] = name
    return names


#: Fragments with no meaning in any language, combined into names. Nonsense on
#: purpose: a generator seeded with real subjects would prove the two agree about
#: one corpus, which is the thing this repository keeps having to unlearn. The
#: Unicode members are here because they are where a naming rule and a keying rule
#: can disagree — marks that fold away, a stretch that means nothing, a
#: compatibility spelling, a script with no case.
_FRAGMENTS = (
    "zorb",
    "plerric",
    "quandle",
    "frem",
    "vorr",
    "glom",
    "durn",
    "habitus",
    "Zorb",
    "ZORB",
    "zo rb",
    "zo-rb",
    "zo_rb",
    "zo.rb",
    " zorb ",
    "zorb?",
    "\u0632\u0648\u0631\u0628",
    "\u0632\u0640\u0640\u0648\u0631\u0628",
    "\u0632\u064e\u0648\u0652\u0631\u0628",
    "\uff5a\uff4f\uff52\uff42",
    "z\u00f6rb",
    "zo\u0308rb",
    "\u03b6\u03bf\u03c1\u03b2",
    "\u0915\u093f\u0924",
    "",
    "   ",
    "...",
    "\u064e\u064f",
    "42",
)


def _generated_rules(random_source) -> list[dict]:
    """One randomly shaped rules list, including the shapes that broke this twice.

    Deliberately generates the awkward ones often: a declaration whose name is
    blank or unkeyable, two declarations that collide on a key, and attributes and
    dictionary entries placed to collide with a required fact — since those are
    where a naming rule reconstructed from anything but the declaration itself goes
    wrong.
    """

    def _fragment() -> str:
        return random_source.choice(_FRAGMENTS)

    def _required() -> object:
        shape = random_source.random()
        if shape < 0.12:
            return _fragment()
        if shape < 0.16:
            return random_source.choice([None, 0, 42, True])
        entry: dict = {}
        if random_source.random() < 0.75:
            entry["name"] = _fragment()
        if random_source.random() < 0.75:
            entry["phrase"] = _fragment()
        if random_source.random() < 0.2:
            entry["unit"] = _fragment()
        return entry

    rules: list[dict] = []
    for index in range(random_source.randint(0, 4)):
        if random_source.random() < 0.05:
            rules.append(None)  # type: ignore[arg-type]
            continue
        rule: dict = {"rule_id": f"R-{index}"}
        if random_source.random() < 0.85:
            rule["required_facts"] = [
                _required() for _ in range(random_source.randint(0, 3))
            ]
        if random_source.random() < 0.5:
            rule["attributes"] = {
                random_source.choice(("applies", "outcome")): [
                    {"attribute": _fragment(), "text": _fragment()}
                    for _ in range(random_source.randint(0, 2))
                ]
            }
        if random_source.random() < 0.3:
            rule["facts"] = [{"ref": _fragment()} for _ in range(random_source.randint(0, 2))]
        rules.append(rule)
    return rules


def test_the_compatibility_projection_matches_the_old_rule_over_generated_shapes() -> None:
    """The property, over enough shapes that the awkward ones actually occur.

    Two hand-written repairs passed the cases they were written against and were
    still wrong, each in a way nobody had thought to write a case for. Examples
    prove a rule handles the examples; only a comparison against the old behaviour
    over shapes nobody chose proves it handles the ones nobody thought of.

    Exact mapping equality — same keys, same spellings, same omissions.
    """

    import random

    random_source = random.Random(20250830)
    interesting = 0

    for iteration in range(20_000):
        rules = _generated_rules(random_source)
        expected = _pre_m1_rule_fact_names(rules)
        actual = ai_case_intent._rule_fact_names(rules)
        assert actual == expected, (
            f"iteration {iteration} diverged\n"
            f"  rules:    {rules!r}\n"
            f"  expected: {expected!r}\n"
            f"  actual:   {actual!r}"
        )
        if expected:
            interesting += 1

    # A generator that produced nothing nameable would pass on silence.
    assert interesting > 10_000, (
        f"only {interesting} shapes named anything; the generator is not exercising the rule"
    )


def test_the_generator_reaches_the_shapes_that_broke_this_before() -> None:
    """Guard the guard: the property above is only worth its runtime if the
    awkward shapes actually appear in it."""

    import random

    random_source = random.Random(20250830)
    blank_name_with_phrase = 0
    unkeyable_name_with_phrase = 0
    attribute_collides_with_required = 0

    for _ in range(4_000):
        rules = _generated_rules(random_source)
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            required_keys = set()
            for required in rule.get("required_facts") or []:
                if not isinstance(required, dict):
                    continue
                name, phrase = required.get("name"), required.get("phrase")
                if name and not str(name).strip() and phrase:
                    blank_name_with_phrase += 1
                if name and str(name).strip() and not ai_case_intent._fact_key(name) and phrase:
                    unkeyable_name_with_phrase += 1
                primary = ai_case_intent._declared_primary(required)
                if ai_case_intent._fact_key(primary):
                    required_keys.add(ai_case_intent._fact_key(primary))
            for slot in (rule.get("attributes") or {}).values():
                for attribute in slot or []:
                    if ai_case_intent._fact_key(attribute.get("attribute")) in required_keys:
                        attribute_collides_with_required += 1

    assert blank_name_with_phrase > 20, blank_name_with_phrase
    assert unkeyable_name_with_phrase > 20, unkeyable_name_with_phrase
    assert attribute_collides_with_required > 20, attribute_collides_with_required


def test_the_catalogue_is_unchanged_by_the_compatibility_field() -> None:
    """The other half: M3's view did not move.

    `required_primary` is additive. Aliases, their provenance, the sources list,
    rule-id closure and the alias index are all as they were, and the catalogue is
    still identical between builds.
    """

    records = [
        {
            "rules": [
                {
                    "rule_id": "R-ONE",
                    "required_facts": [{"phrase": "weekly hours"}],
                    "attributes": {"applies": [{"attribute": "Weekly_Hours"}]},
                }
            ]
        }
    ]
    catalogue = ai_case_intent.selector_catalogue(records)
    (entry,) = catalogue["selectors"]

    assert entry["name"] == "Weekly_Hours", "display naming is still independently ranked"
    assert entry["required_primary"] == "weekly hours", "compatibility naming is its own field"
    assert entry["aliases"] == ["weekly hours", "Weekly_Hours"]
    assert entry["alias_sources"] == [["required_fact_phrase"], ["attribute"]]
    assert entry["sources"] == ["required_fact_phrase", "attribute"]
    assert entry["rule_ids"] == ["R-ONE"]
    assert catalogue["alias_index"] == {"weekly-hours": "weekly-hours"}
    assert ai_case_intent.selector_catalogue(records) == catalogue, "still deterministic"


def test_the_catalogue_still_keeps_every_alias_and_says_where_each_came_from() -> None:
    """The other half of the repair: M3 loses nothing.

    The projection narrowed; the catalogue did not. It still gathers the attribute
    spelling, still resolves it through ``alias_index``, and now records which slot
    contributed each alias — which is what let the narrowing be expressed as "the
    strongest *declared* alias" rather than as a second traversal of the rules.
    """

    catalogue = ai_case_intent.selector_catalogue(
        [
            {
                "rules": [
                    {
                        "rule_id": "R-ONE",
                        "required_facts": [{"phrase": "weekly hours"}],
                        "attributes": {"applies": [{"attribute": "Weekly_Hours"}]},
                    }
                ]
            }
        ]
    )

    (entry,) = catalogue["selectors"]
    assert entry["aliases"] == ["weekly hours", "Weekly_Hours"]
    assert entry["alias_sources"] == [["required_fact_phrase"], ["attribute"]]
    assert len(entry["alias_sources"]) == len(entry["aliases"]), "one provenance per alias"
    assert catalogue["alias_index"]["weekly-hours"] == "weekly-hours"


def test_the_key_a_caller_stores_state_against_is_unchanged_by_the_collision() -> None:
    """What the repair must not have moved, checked where a caller reads it.

    ``_rule_fact_names`` decides which *spelling* is echoed back, and a spelling
    that changed would be cosmetic. The identifier is not cosmetic: callers store
    state against it and compare one reply to the next by it. So the emitted key is
    asserted identical with the colliding attribute present and absent, on both
    fields that carry it.
    """

    parsed = {
        "status": "missing_required_facts",
        "answer": "The rules set out alternatives and one value is outstanding.",
        "verdict": "",
        "cited_rule_ids": ["R-ONE"],
        "missing_required_facts": ["Weekly Hours"],
        "missing_required_facts_detail": [
            {
                "fact": "Weekly Hours",
                "label": "Hours worked in the week",
                "why_needed": "The outcome is set separately for each.",
                "required_by_rule_ids": ["R-ONE"],
            }
        ],
        "declined": False,
        "note": "",
    }
    base_rule = {
        "rule_id": "R-ONE",
        "required_facts": [{"phrase": "weekly hours"}],
        "evidence_refs": ["S1"],
    }
    colliding = dict(base_rule, attributes={"applies": [{"attribute": "Weekly_Hours"}]})
    spans = {"S1": {"text": "A sentence the document wrote."}}

    without = ai_case_intent._decision_from_parsed(parsed, rules=[base_rule], spans=spans)
    with_attribute = ai_case_intent._decision_from_parsed(parsed, rules=[colliding], spans=spans)

    assert without["missing_required_facts"] == ["weekly hours"]
    assert with_attribute["missing_required_facts"] == without["missing_required_facts"]
    assert (
        with_attribute["missing_information"][0]["fact"]
        == without["missing_information"][0]["fact"]
        == "weekly hours"
    )
    # And the prose beside it is still the gather's, untouched by any of this.
    assert with_attribute["missing_information"][0]["label"] == "Hours worked in the week"


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("Weekly Hours", "weekly-hours"),
        ("weekly_hours", "weekly-hours"),
        ("Which tier?", "which-tier"),
        ("Value (in units)", "value-in-units"),
        ("caf\u00e9", "café"),
        ("cafe\u0301", "café"),
        ("\u0627\u0644\u0652\u0633\u064e\u0627\u0639\u064e\u0627\u062a", "الساعات"),
        ("\u0130stanbul", "istanbul"),
        ("Gr\u00fcn Stra\u00dfe", "grün-strasse"),
        ("\u064e\u064f\u0650", ""),
    ],
)
def test_every_key_the_fact_path_produced_before_it_delegated_is_unchanged(
    written: str, expected: str
) -> None:
    """The delegation is a move, not a change.

    Keys already reached callers and are already stored against their state, so a
    key that shifted would silently orphan it.
    """

    assert ai_case_intent._fact_key(written) == expected


# --------------------------------------------------------------------------- #
# 4b. The identifier side of the translation boundary.
# --------------------------------------------------------------------------- #


def test_a_key_is_never_a_translation_of_the_name_it_came_from() -> None:
    """The invariant a translating layer will be built against.

    This version processes internally in one language, and a boundary elsewhere
    will carry a question in and an answer back out. That boundary has to know
    what it may rewrite. Identifiers it may not: they are derived from the
    records, and a record holds the document's own sentences verbatim, so a
    document written in one script yields keys in that script no matter what
    language the pipeline reasons in or the reviewer asked in.

    Asserted here rather than left implicit because the failure is silent. A
    translated key still looks like a key: it would resolve against nothing in the
    catalogue, orphan whatever state a caller had stored against it, and match no
    earlier reply — with no error anywhere to say why.
    """

    arabic = "\u0627\u0644\u0633\u0627\u0639\u0627\u062a"
    key = canonical_key(arabic)

    assert key == arabic, "the key keeps its own script"
    assert not key.isascii(), "nothing here transliterates or renders into ASCII"
    # And it is the same key the fact path and the catalogue would produce, so the
    # boundary sees one identifier rather than three spellings of one.
    assert ai_case_intent._fact_key(arabic) == key
    (entry,) = _catalogue(
        [_record("ar", rule_id="R-AR", required=[{"name": arabic}])]
    )["selectors"]
    assert entry["key"] == key


def test_two_different_names_in_one_script_stay_two_keys() -> None:
    """Folding spellings together must not fold meanings together.

    A canonicaliser that reached for a language — transliterating, stripping to
    ASCII, or mapping through a lexicon — would collapse names that a document
    distinguishes. That is the failure mode a translating layer would inherit if
    this module were ever asked to do its job.
    """

    names = (
        "\u0627\u0644\u0633\u0627\u0639\u0627\u062a",
        "\u0627\u0644\u0623\u064a\u0627\u0645",
        "\u0627\u0644\u0645\u062f\u0629",
    )
    keys = [canonical_key(name) for name in names]

    assert len(set(keys)) == len(names), "distinct names, distinct keys"
    assert all(keys), "and none of them erased"


def test_the_key_does_not_move_when_the_prose_beside_it_does() -> None:
    """Identifier and prose are independent, which is what makes the split usable.

    A boundary rewrites the human label and leaves the key alone. If the key were
    a function of the prose, that rewrite would move it — so the two are proved
    independent here, on the one structure that carries both.
    """

    record = _record("split", rule_id="R-SPLIT", required=[{"name": "subscriber-tier"}])
    (entry,) = _catalogue([record])["selectors"]

    assert entry["key"] == "subscriber-tier"
    # Whatever wording a reader is eventually shown, the identifier is derived
    # from the record's declared name and from nothing else.
    for prose in ("Which tier?", "\u0623\u064a \u0641\u0626\u0629\u061f", "Quelle formule ?"):
        assert canonical_key("subscriber-tier") == entry["key"]
        assert canonical_key(prose) != entry["key"]


def test_the_canonicaliser_exposes_no_language_of_its_own() -> None:
    """No detection, no branch on script, and nothing to configure per language.

    The interface a translating layer integrates against is deliberately narrow:
    give it a string, get an identifier. If it took a language, a locale or a
    direction, the boundary would have to decide what to pass and would get it
    wrong for the mixed strings this corpus actually contains.
    """

    import inspect as _inspect

    for function in (
        text_canonical.canonical_key,
        text_canonical.canonical_tokens,
        text_canonical.canonical_runs,
        text_canonical.fold,
    ):
        parameters = list(_inspect.signature(function).parameters)
        assert "language" not in parameters
        assert "locale" not in parameters
        assert "script" not in parameters

    # A string that mixes scripts is one input, not a decision about which
    # language it is: both halves survive into the key.
    mixed = canonical_key("tier \u0627\u0644\u0633\u0627\u0639\u0627\u062a 3")
    assert mixed == "tier-\u0627\u0644\u0633\u0627\u0639\u0627\u062a-3"


# --------------------------------------------------------------------------- #
# 5. The guard: structure only, in the code as well as in the behaviour.
# --------------------------------------------------------------------------- #

#: Subjects, ids and headings from the incident that prompted this work, plus
#: unrelated subjects a keyword fix might reach for.
#:
#: Ordinary English that happens to appear in the incident is deliberately not
#: listed. "absence" and "occurrence" are both in these modules already, in
#: sentences about the absence of evidence and the earliest occurrence in
#: document order — neither is a subject, and a guard that fought the language
#: would be worked around rather than obeyed. What is listed is vocabulary that
#: could only be here because someone was writing for one corpus.
_BORROWED = (
    "attendance",
    "penalty",
    "sanction",
    "disciplinary",
    "employee",
    "salary",
    "deduction",
    "excuse",
    "laptop",
    "vacation",
    "sick leave",
    "handbook",
    "what will happen to me",
    "didnt attend",
    "no execuse",
    "contract year",
)

_IDENTIFIERS = (
    ("the acronym AIS", re.compile(r"\bAIS\b")),
    ("a concrete rule id", re.compile(r"\bAI-[0-9a-f]{6,}\b", re.I)),
    (
        "a uuid",
        re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I),
    ),
)

_OWNED_MODULES = (text_canonical, policy_rule_slice)

#: The surfaces this milestone authored, which are the ones the guard binds in
#: full. `policy_rule_slice` is listed by its *tokenising path* rather than whole:
#: its module docstring carries a long provenance narrative, including the
#: identifier of the decision whose behaviour prompted the budget rules and the
#: subject of the policy that was observed. That is history a reader benefits
#: from, it is not a branch, and erasing it would cost more than it protects.
#:
#: What must be clean is anything that decides how text is read. A subject or an
#: identifier *there* would be a rule tuned to one corpus, which is the thing this
#: guard exists to catch.
def _canonical_reading_surfaces() -> dict[str, str]:
    return {
        "text_canonical (whole module)": inspect.getsource(text_canonical),
        "policy_rule_slice._tokens": inspect.getsource(policy_rule_slice._tokens),
        "ai_case_intent.selector_catalogue": inspect.getsource(ai_case_intent.selector_catalogue),
        "ai_case_intent._fact_key": inspect.getsource(ai_case_intent._fact_key),
        "ai_case_intent._rule_fact_names": inspect.getsource(ai_case_intent._rule_fact_names),
        "ai_case_intent._catalogue_records": inspect.getsource(ai_case_intent._catalogue_records),
    }


def test_no_part_of_the_canonical_reading_path_names_a_subject_or_an_incident() -> None:
    """Grep half of the guard, over every surface that decides how text is read.

    These must hold for any corpus, so they name none — not in the code and not in
    the comments, because a docstring that told a reader to watch for one subject
    would be an invitation to write the branch next time.
    """

    for name, source in _canonical_reading_surfaces().items():
        lowered = source.lower()
        for word in _BORROWED:
            assert word not in lowered, f"{name} names {word!r}"
        for label, pattern in _IDENTIFIERS:
            assert not pattern.search(source), f"{name} names {label}"


def test_the_shared_canonicaliser_names_no_subject_anywhere_in_the_module() -> None:
    """The one module that is bound in whole, prose included.

    It is new, it is small, it is shared by everything that compares two strings,
    and it has no provenance to carry. There is no reason for a subject to appear
    anywhere in it, so none is allowed anywhere in it.
    """

    source = inspect.getsource(text_canonical)
    lowered = source.lower()
    for word in _BORROWED:
        assert word not in lowered
    for _, pattern in _IDENTIFIERS:
        assert not pattern.search(source)


def test_the_canonicaliser_carries_no_vocabulary_at_all() -> None:
    """AST half of the guard, and the strictest claim this milestone makes.

    Every string constant reachable in this module is checked against what a
    character rule is allowed to be: a normal form, a Unicode general category, a
    separator, or nothing. A word here would be a language rule wearing a
    canonicaliser's clothes — it would work for the corpus it was written against
    and fail silently for the next one — and it would be easy to add and hard to
    see in review, which is exactly what a test is for.

    Docstrings are excluded because they are the explanation, not the rule; the
    grep guard above covers what they may say.
    """

    tree = ast.parse(Path(inspect.getfile(text_canonical)).read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                docstrings.add(doc)

    allowed_categories = {"Mn", "Me", "Mc"}
    allowed_other = {"", "-", " ", "NFKC"}

    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        value = node.value
        if value in docstrings:
            continue
        if value in allowed_categories or value in allowed_other:
            continue
        # Anything else may only be a single code point: a character rule names
        # characters. Tatweel is a letter modifier and so is alphanumeric, which
        # is exactly why the test is written by *length* rather than by category —
        # a rule about which characters carry distinction cannot also be the thing
        # that decides which characters are allowed to be named.
        assert len(value) == 1, (
            f"the canonicaliser carries the literal {value!r}, which is a word rather "
            "than a character rule"
        )


def test_no_owned_module_parses_prose_or_branches_on_a_pattern() -> None:
    """Reading text with a pattern is how the split-word defect got in.

    ``\\w+`` is a claim about what a word is, and it is wrong in most of the
    scripts this corpus contains. The canonicaliser replaces it with Unicode
    categories, so neither it nor the tokeniser imports the regular-expression
    machinery any more, and neither may quietly get it back.
    """

    for module in _OWNED_MODULES:
        source = inspect.getsource(module)
        tree = ast.parse(source)
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            node.module.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert "re" not in imported, f"{module.__name__} imports the regular-expression module"

    catalogue_source = inspect.getsource(ai_case_intent.selector_catalogue)
    assert "spans" not in catalogue_source, (
        "the catalogue reads declared slots, never the document's sentences"
    )
