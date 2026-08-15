"""A name has to tell one rule from the next, and stay out of the record's way.

Seven rules can come out of one passage, four of them alike. If the handles
shown beside them read the same, the handle has cost a reader attention and
returned nothing. So distinctness is not a quality here, it is the feature.

These are shape tests. Every record below is invented -- a made-up subject in
two scripts -- because a test written against a real document's words would
pass by recognising that document. What is asserted is that the rule holds for
records the corpus has never seen.

The prompt is read as a string, the way `test_an_explanation_explains_the_record`
reads its own: an instruction is the part of this module that a model actually
executes, and it is not covered by anything that runs the code.
"""

from __future__ import annotations

import ast
import json
import re
import unicodedata
from collections import OrderedDict
from pathlib import Path

import pytest

from policy_platform.infrastructure.assistants import rule_namer
from policy_platform.infrastructure.assistants.policy_explainer import RuleFacts
from policy_platform.infrastructure.assistants.rule_namer import (
    DECLINE_REPLY,
    MAX_NAME_CHARS,
    MAX_NAME_WORDS,
    UNAVAILABLE_DECLINED,
    UNAVAILABLE_NAMED_A_ROUTE,
    UNAVAILABLE_NOT_DISTINCT,
    UNAVAILABLE_REPLY_UNUSABLE,
    UNAVAILABLE_RESTATES_RECORD,
    UNAVAILABLE_UNANSWERED,
    build_source,
    chunk_rules,
    digest_of,
    generate_names,
    validate_name,
)

MODULE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "policy_platform"
    / "infrastructure"
    / "assistants"
    / "rule_namer.py"
)


def _rule(title: str, **stated: str) -> RuleFacts:
    return RuleFacts(
        rule_id="AI-0000000001",
        title=title,
        stated=OrderedDict(stated),
        effect="permit",
        stated_text="the document's own sentence, which is never shown to the model",
    )


#: Invented records in two scripts. Long enough that a short phrase about them
#: is shorter than they are, which is what a handle has to be.
LATIN = _rule(
    "Kestrel Bay mooring turns",
    who="the harbour warden",
    what="records each mooring turn in the tide register before the turn begins",
)
ARABIC = _rule(
    "دفتر المراسي في خليج القطرس",
    who="حارس الميناء",
    what="يقيد كل دورة رسو في سجل المد قبل بدء الدورة بوقت كاف",
)

LATIN_SCRIPTS = build_source(["A heading"], [LATIN]).scripts
ARABIC_SCRIPTS = build_source(["عنوان"], [ARABIC]).scripts


class TestWhatCountsAsAName:
    def test_a_short_purpose_is_accepted(self) -> None:
        name, code = validate_name(
            "Warden's tide register upkeep", rule=LATIN, source_scripts=LATIN_SCRIPTS
        )
        assert code is None
        assert name == "Warden's tide register upkeep"

    def test_an_arabic_purpose_is_accepted_under_an_arabic_heading(self) -> None:
        name, code = validate_name(
            "مسؤولية القيد في الدفتر", rule=ARABIC, source_scripts=ARABIC_SCRIPTS
        )
        assert code is None
        assert name == "مسؤولية القيد في الدفتر"

    def test_a_reply_in_a_script_the_heading_does_not_use_is_refused(self) -> None:
        """The heading decides the language. Both directions, so neither script
        is the one this module quietly prefers."""

        _, code = validate_name(
            "Register upkeep", rule=ARABIC, source_scripts=ARABIC_SCRIPTS
        )
        assert code == UNAVAILABLE_REPLY_UNUSABLE

        _, code = validate_name(
            "مسؤولية القيد", rule=LATIN, source_scripts=LATIN_SCRIPTS
        )
        assert code == UNAVAILABLE_REPLY_UNUSABLE

    def test_the_word_that_declines_is_not_an_unusable_reply(self) -> None:
        """Asked and answered, versus asked and nothing came back. A reader is
        told different things by the two, so the code has to differ."""

        _, code = validate_name(DECLINE_REPLY, rule=LATIN, source_scripts=LATIN_SCRIPTS)
        assert code == UNAVAILABLE_DECLINED

        _, code = validate_name("", rule=LATIN, source_scripts=LATIN_SCRIPTS)
        assert code == UNAVAILABLE_REPLY_UNUSABLE

    def test_a_phrase_lifted_from_the_record_is_refused(self) -> None:
        """A handle that repeats the record is the record, shown twice."""

        _, code = validate_name(
            "records each mooring turn", rule=LATIN, source_scripts=LATIN_SCRIPTS
        )
        assert code == UNAVAILABLE_RESTATES_RECORD

    def test_a_phrase_no_shorter_than_the_record_is_refused(self) -> None:
        long_enough = "Upkeep of the register kept beside every mooring in this bay"
        assert len(long_enough) <= MAX_NAME_CHARS
        short = _rule("Turns", what="logged")
        _, code = validate_name(long_enough, rule=short, source_scripts=LATIN_SCRIPTS)
        assert code == UNAVAILABLE_RESTATES_RECORD

    def test_a_phrase_past_the_shape_is_refused(self) -> None:
        for reply in (
            "x " * (MAX_NAME_WORDS + 1),
            "a" * (MAX_NAME_CHARS + 1),
            "Mooring turns, section 4",  # a term of the rule, not a handle
            'Warden and "the register"',  # styled as a quotation
        ):
            _, code = validate_name(reply, rule=LATIN, source_scripts=LATIN_SCRIPTS)
            assert code == UNAVAILABLE_REPLY_UNUSABLE, reply

    def test_a_phrase_naming_how_the_rule_is_decided_is_refused(self) -> None:
        """A handle says what a rule is for. How its test is decided is a
        property of the rule, shown where the rule is shown, and a handle
        repeating it would put the same fact in two places -- and put it in
        the one place a reader is scanning rather than reading.

        The phrase is assembled here rather than written out, for the reason
        the route guard gives: this file would otherwise carry the words it
        exists to keep out of the interface.
        """

        route = " ".join(["machine", "executable"])
        _, code = validate_name(
            f"Warden upkeep {route}", rule=LATIN, source_scripts=LATIN_SCRIPTS
        )
        assert code == UNAVAILABLE_NAMED_A_ROUTE

    def test_a_handle_may_join_the_several_things_one_rule_covers(self) -> None:
        """A rule can govern more than one thing at once, and then the shortest
        honest handle for it is a list. Refusing the separator would push the
        model into either dropping one of them or writing a longer phrase that
        avoids the punctuation, and both are worse than the comma.

        Asked of Unicode rather than written out, so the assertion covers a
        script whose comma this file does not contain.
        """

        separators = [
            mark
            for mark in rule_namer.FORBIDDEN_PUNCTUATION
            if "COMMA" in (unicodedata.name(mark, "") or "")
        ]
        assert separators, "the shared set holds no separator to allow"
        for mark in separators:
            name, code = validate_name(
                f"Warden upkeep{mark} deputy countersigning",
                rule=LATIN,
                source_scripts=LATIN_SCRIPTS,
            )
            assert code is None, mark
            assert name is not None and mark in name

    def test_a_handle_may_not_be_punctuated_like_a_sentence(self) -> None:
        """The separator is allowed and nothing else is: a reader must not be
        able to mistake a handle for the rule."""

        for mark in rule_namer.NAME_PUNCTUATION:
            _, code = validate_name(
                f"Warden upkeep{mark} deputy countersigning",
                rule=LATIN,
                source_scripts=LATIN_SCRIPTS,
            )
            assert code == UNAVAILABLE_REPLY_UNUSABLE, mark

    def test_a_separator_at_the_edge_is_dropped_rather_than_refused(self) -> None:
        """It joins the phrase to nothing, so the phrase is still the phrase."""

        for mark in rule_namer._LIST_SEPARATORS:
            name, code = validate_name(
                f"{mark} Warden tide register upkeep{mark}",
                rule=LATIN,
                source_scripts=LATIN_SCRIPTS,
            )
            assert code is None, mark
            assert name == "Warden tide register upkeep"


class _Replies:
    """A client that answers with what it was told to, and counts the asks."""

    def __init__(self, *replies: str) -> None:
        self._replies = list(replies)
        self.asks = 0
        self.sent: list[str] = []

    async def chat(self, messages, **_kwargs) -> str:
        self.asks += 1
        self.sent.append(json.dumps(messages, ensure_ascii=False))
        return self._replies[min(self.asks - 1, len(self._replies) - 1)]


def _reply(**names: str) -> str:
    return json.dumps({"names": names}, ensure_ascii=False)


class TestNamesWithinAPolicyAreDistinct:
    async def test_a_repeated_phrase_is_refused_rather_than_stored(self) -> None:
        siblings = [
            _rule("Kestrel Bay mooring turns", who="the harbour warden", what="records the turn"),
            _rule("Kestrel Bay mooring turns", who="the deputy warden", what="countersigns it"),
        ]
        client = _Replies(_reply(**{"1": "Register upkeep", "2": "register  UPKEEP"}))

        attempts = await generate_names(
            build_source(["A heading"], siblings), client=client
        )

        assert [a.name for a in attempts] == ["Register upkeep", None]
        assert attempts[1].unavailable_code == UNAVAILABLE_NOT_DISTINCT

    async def test_distinctness_holds_across_two_requests(self) -> None:
        """A policy too large for one request is still one policy."""

        taken: set[str] = set()
        first = await generate_names(
            build_source(["A heading"], [LATIN]),
            client=_Replies(_reply(**{"1": "Register upkeep"})),
            taken=taken,
        )
        second = await generate_names(
            build_source(["A heading"], [_rule("Another turn", what="logged elsewhere too")]),
            client=_Replies(_reply(**{"1": "Register Upkeep"})),
            taken=taken,
        )

        assert first[0].name == "Register upkeep"
        assert second[0].name is None
        assert second[0].unavailable_code == UNAVAILABLE_NOT_DISTINCT

    async def test_a_record_left_unanswered_is_not_a_failure_of_the_others(self) -> None:
        client = _Replies(_reply(**{"1": "Register upkeep"}))
        attempts = await generate_names(
            build_source(["A heading"], [LATIN, _rule("Another turn", what="logged elsewhere")]),
            client=client,
        )
        assert attempts[0].name == "Register upkeep"
        assert attempts[1].unavailable_code == UNAVAILABLE_UNANSWERED

    async def test_an_unusable_reply_is_asked_once_more(self) -> None:
        client = _Replies("not json at all", _reply(**{"1": "Register upkeep"}))
        attempts = await generate_names(build_source(["A heading"], [LATIN]), client=client)
        assert client.asks == rule_namer.ASK_ATTEMPTS
        assert attempts[0].name == "Register upkeep"

    async def test_one_unusable_record_does_not_cost_its_siblings_their_names(
        self,
    ) -> None:
        """Measured on the live corpus, the commonest unusable reply is a phrase
        written in a language the heading does not use, and the same request
        asked again does not repeat it. So the ask is repeated -- and a record
        already named keeps the name it was given, because re-deciding a good
        answer on a second sample would make the names depend on the batch."""

        siblings = [LATIN, _rule("Another turn", what="logged elsewhere entirely")]
        client = _Replies(
            _reply(**{"1": "Register upkeep", "2": "지속계약 직원 채용"}),
            _reply(**{"1": "A different phrase", "2": "Deputy countersigning"}),
        )

        attempts = await generate_names(
            build_source(["A heading"], siblings), client=client
        )

        assert client.asks == 2
        assert [a.name for a in attempts] == ["Register upkeep", "Deputy countersigning"]

    async def test_a_record_the_model_declined_is_not_asked_about_again(self) -> None:
        """It was asked, and answered. Asking again is this module disagreeing
        with the answer it got."""

        siblings = [LATIN, _rule("Another turn", what="logged elsewhere entirely")]
        client = _Replies(
            _reply(**{"1": "Register upkeep", "2": DECLINE_REPLY}),
            _reply(**{"1": "Register upkeep", "2": "Deputy countersigning"}),
        )

        attempts = await generate_names(
            build_source(["A heading"], siblings), client=client
        )

        assert client.asks == 1
        assert attempts[1].name is None
        assert attempts[1].unavailable_code == UNAVAILABLE_DECLINED

    async def test_a_policy_settles_on_one_language_across_its_requests(self) -> None:
        """A bilingual passage permits either script, and a policy too large for
        one request would otherwise let each request choose for itself. Measured
        on the live corpus, that put two languages of handle on one card.

        Neither script is named as the one to keep: whichever the policy wrote
        first is the one it holds to, so this behaves the same whichever way
        round the document is.
        """

        bilingual = _rule(
            "Kestrel Bay mooring turns دفتر المراسي",
            who="the harbour warden حارس الميناء",
            what="records each turn يقيد كل دورة رسو في سجل المد",
        )
        for first, second in (
            ("Register upkeep", "قيد الدورات"),
            ("قيد الدورات", "Register upkeep"),
        ):
            settled: set[str] = set()
            opening = await generate_names(
                build_source(["A heading عنوان"], [bilingual]),
                client=_Replies(_reply(**{"1": first})),
                settled_scripts=settled,
            )
            later = await generate_names(
                build_source(["A heading عنوان"], [bilingual]),
                client=_Replies(_reply(**{"1": second})),
                settled_scripts=settled,
            )

            assert opening[0].name == first
            assert later[0].name is None
            assert later[0].unavailable_code == UNAVAILABLE_REPLY_UNUSABLE

    async def test_settling_never_narrows_a_policy_to_no_language_at_all(self) -> None:
        """A request whose passage shares no script with what the policy has
        written so far is named on its own terms rather than refused wholesale."""

        settled = {"HANGUL"}
        attempts = await generate_names(
            build_source(["A heading"], [LATIN]),
            client=_Replies(_reply(**{"1": "Register upkeep"})),
            settled_scripts=settled,
        )
        assert attempts[0].name == "Register upkeep"

    async def test_a_failing_call_names_nothing_and_raises_nothing(self) -> None:
        class Broken:
            async def chat(self, *_args, **_kwargs) -> str:
                raise RuntimeError("the call did not complete")

        attempts = await generate_names(build_source(["A heading"], [LATIN]), client=Broken())
        assert [a.name for a in attempts] == [None]
        assert attempts[0].unavailable_code == rule_namer.UNAVAILABLE_MODEL_FAILED


class TestWhatOneRequestCosts:
    def test_the_same_record_twice_has_one_digest(self) -> None:
        """A document read twice produces the same record twice. Naming it
        once and storing that name for both is the difference between paying
        for a corpus and paying for it again."""

        again = _rule(
            LATIN.title, **{key: value for key, value in LATIN.stated.items()}
        )
        assert digest_of(again) == digest_of(LATIN)

    def test_two_records_differing_in_one_field_have_different_digests(self) -> None:
        other = _rule(LATIN.title, who="the deputy warden", what="countersigns the entry")
        assert digest_of(other) != digest_of(LATIN)

    def test_a_record_is_never_split_across_requests(self) -> None:
        groups = chunk_rules([LATIN, ARABIC, LATIN], max_chars=1)
        assert [len(group) for group in groups] == [1, 1, 1]
        assert sum(len(group) for group in groups) == 3


class TestTheInstruction:
    """Read as text. Nothing that runs this module checks what it asks for."""

    @staticmethod
    def _prompt() -> str:
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                target = node.targets[0]
                if isinstance(target, ast.Name) and target.id == "_SYSTEM_PROMPT":
                    return ast.literal_eval(node.value)
        raise AssertionError("the prompt is not where this test looks for it")

    def test_it_asks_for_a_purpose_and_forbids_restating(self) -> None:
        prompt = self._prompt().casefold()
        assert "what that rule is for" in prompt
        assert "do not restate" in prompt

    def test_it_asks_for_phrases_no_reader_could_confuse(self) -> None:
        assert "mistake" in self._prompt().casefold()

    def test_the_language_rule_is_stated_last(self) -> None:
        """Where it was put deliberately: a model weighs the last instruction
        heaviest, and this is the one whose loss shows up as a name in the
        wrong language on an Arabic card."""

        paragraphs = [p for p in self._prompt().split("\n\n") if p.strip()]
        assert "language" in paragraphs[-1].casefold()

    def test_it_names_no_subject_of_its_own(self) -> None:
        """The instruction has to read identically for a document about
        anything. A word here that belongs to one domain is this module
        deciding in advance what documents are about."""

        prompt = self._prompt().casefold()
        for word in ("employee", "policy", "leave", "salary", "contract", "safety"):
            assert not re.search(rf"\b{word}", prompt), word

    def test_it_says_nothing_about_how_a_rule_is_decided(self) -> None:
        prompt = self._prompt().casefold()
        for word in ("deterministic", "computable", "judge", "threshold", "comparison"):
            assert word not in prompt, word


@pytest.mark.parametrize("value", [MAX_NAME_CHARS, MAX_NAME_WORDS])
def test_the_shape_is_a_property_of_a_line_not_of_a_corpus(value: int) -> None:
    """A ceiling here is about how much text a person scans. If one of these
    ever equals something counted in a document, it has stopped being that."""

    assert value > 0
