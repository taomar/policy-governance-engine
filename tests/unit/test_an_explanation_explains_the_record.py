"""An explanation explains the record, and can be nothing else.

Four things are checked, and each of them is a way this feature could quietly
become something other than what it was built as.

1. THE DOCUMENT'S WORDS NEVER REACH THE MODEL. That omission is the design, and
   it is the kind of design that is one convenience away from being undone —
   `source_text` is already on the object the request is built from, and adding
   it would look like an improvement. So it is asserted directly, against a
   record whose verbatim text shares no vocabulary with its decomposition.

2. THE PROMPT NAMES NO DECISION ROUTE, and a reply that names one is refused.
   The framing guards in this repository read source files. None of them can see
   a sentence a model writes at runtime, so the runtime check is the only guard
   there is on the words a reviewer actually reads.

3. THE PROMPT HOLDS NO DOMAIN VOCABULARY. A prompt that named subjects would
   make this system work on documents about those subjects and quietly worse on
   every other.

4. AN EXPLANATION THAT IS NOT DOING THE WORK IS REFUSED. Measured before the
   guard existed: three single-rule policies each produced the source sentence
   back with two or three words exchanged. A near-copy of evidence, in our
   voice, beside the evidence, is worse than nothing.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from policy_platform.infrastructure.assistants import policy_explainer as E

_MODULE = Path(E.__file__)


def _prompt_literals() -> list[str]:
    """Every instruction the module states, read off the source rather than run.

    Read from the syntax tree so these hold whether or not a model is reachable:
    what is checked is what this repository asks for, which is a property of the
    file. Constants reached through a call are unwrapped, because the prompt is
    assembled with `.format` and reading only bare constants would silently
    return nothing and pass every assertion below.
    """

    found: list[str] = []
    tree = ast.parse(_MODULE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id.endswith("_PROMPT")
            for target in node.targets
        ):
            continue
        for inner in ast.walk(node.value):
            if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                found.append(inner.value)
    return found


def _record(**overrides) -> dict:
    """One rule's payload, with a source text sharing no words with its parts."""

    payload = {
        "rule_id": "r1",
        "title": "Alpha",
        "formulation": {
            "canonical": {
                "source_text": "ZQXJV WRTPLM KHDFG BNYCS.",
                "rule": {
                    "rule_type": "obligation",
                    "subject": "someone",
                    "modality": "must",
                    "predicate": "do",
                    "object": "a thing",
                },
            }
        },
        "effect": {"action": "a thing follows"},
    }
    payload.update(overrides)
    return payload


class TestTheDocumentsWordsStayWithTheReader:
    def test_the_verbatim_text_is_absent_from_what_the_model_is_sent(self):
        source = E.build_source(["A heading"], [_record(), _record()])
        assert "ZQXJV" not in source.request_body
        assert "WRTPLM" not in source.request_body
        # ... while the decomposition it was drawn from is present, so the
        # assertion above is about the omission and not about an empty request.
        assert "someone" in source.request_body

    def test_the_verbatim_text_is_present_on_what_the_reader_is_given(self):
        source = E.build_source(["A heading"], [_record()])
        assert source.rules[0].stated_text == "ZQXJV WRTPLM KHDFG BNYCS."

    def test_a_rules_own_words_never_enter_the_digest(self):
        """Two records differing only in their verbatim text share a key.

        The digest covers what the model was shown. If the source text ever
        started reaching the request, this would fail — which makes it a
        standing check on the omission rather than a restatement of it.
        """

        first = E.build_source(["H"], [_record(), _record()])
        other = _record()
        other["formulation"]["canonical"]["source_text"] = "Entirely different."
        second = E.build_source(["H"], [other, _record()])
        assert first.digest == second.digest

    def test_editing_the_record_changes_the_key(self):
        first = E.build_source(["H"], [_record(), _record()])
        edited = _record(title="Beta")
        second = E.build_source(["H"], [edited, _record()])
        assert first.digest != second.digest


class TestNoRouteIsNamed:
    def test_the_prompt_names_no_decision_route(self):
        prompts = _prompt_literals()
        assert prompts, "no prompt was found; the guard would pass while blind"
        for text in prompts:
            assert not E._names_a_route(text), text

    @pytest.mark.parametrize(
        "words",
        [
            ("deterministic",),
            ("machine", "executable"),
            ("ai", "ready"),
            ("documentation", "only"),
        ],
    )
    @pytest.mark.parametrize("joiner", [" ", "-", "_"])
    def test_a_reply_naming_a_route_is_refused(self, words, joiner):
        """Built from atoms at runtime so no forbidden phrase is written here.

        `tests/unit/test_no_readiness_framing.py` scans this directory and reads
        a quoted string holding a space as language. Its rule is right, and this
        file plants nothing for it to find.
        """

        term = joiner.join(words)
        source = E.build_source(["H"], [_record(), _record()])
        reply = f"The requirement here is {term} in its handling."
        text, code = E.validate_explanation(reply, source)
        assert text is None
        assert code == E.UNAVAILABLE_NAMED_A_ROUTE

    def test_a_word_merely_containing_a_route_term_is_not_a_match(self):
        # Word-bounded, so an ordinary word is not caught by a substring of it.
        assert not E._names_a_route("The predetermined amount is stated.")

    def test_the_route_vocabulary_is_intact(self):
        # A typo in an atom would blind the checks above with nothing left in
        # the file for a reader to eyeball.
        assert ("ai", "ready") in E._ROUTE_WORDS
        assert ("machine", "executable") in E._ROUTE_WORDS
        assert len(E._ROUTE_WORDS) >= 6
        for words in E._ROUTE_WORDS:
            for word in words:
                assert re.fullmatch(r"[a-z]+", word), word


class TestThePromptNamesNoSubject:
    #: Words that would make this work on one kind of document. Held as a plain
    #: list because each is a single lowercase token, which the sibling framing
    #: guard declines to police and which is what a discriminant looks like.
    FORBIDDEN = (
        "employee",
        "employer",
        "staff",
        "leave",
        "salary",
        "attendance",
        "overtime",
        "recruitment",
        "manpower",
        "discipline",
        "hr",
        "contract",
        "insurance",
        "medical",
        "university",
        "student",
    )

    def test_no_prompt_names_a_subject_a_document_might_be_about(self):
        prompts = _prompt_literals()
        assert prompts
        for text in prompts:
            lowered = text.lower()
            for word in self.FORBIDDEN:
                assert not re.search(rf"\b{word}s?\b", lowered), (word, text)

    def test_no_prompt_names_a_language(self):
        # The rule is "the language the heading is written in", which is a
        # property of the input. Naming one would be naming a document.
        prompts = _prompt_literals()
        for text in prompts:
            lowered = text.lower()
            for word in ("english", "arabic", "french", "spanish"):
                assert word not in lowered, (word, text)

    def test_the_prompt_asks_for_the_language_of_the_source(self):
        joined = " ".join(_prompt_literals()).lower()
        assert "language the heading is written in" in joined

    def test_the_rule_against_adding_is_stated_last(self):
        """Salience, established by measurement rather than by preference.

        The generated-label work carried its language rule mid-prompt and
        produced replies in languages absent from the corpus; the same sentence
        moved to the end eliminated the drift with nothing else changed. So the
        final position belongs to whichever rule would be worst to lose, and
        here that is the rule against adding.
        """

        joined = " ".join(_prompt_literals())
        tail = joined[len(joined) // 2 :].lower()
        assert "say nothing that is not in the record" in tail


class TestAnExplanationEarnsItsPlace:
    def test_a_record_of_one_rule_is_not_sent_to_a_model(self):
        source = E.build_source(["H"], [_record()])
        assert source.covered_rule_count < E.MIN_RULES_TO_ASSEMBLE

    async def test_a_record_of_one_rule_refuses_before_the_call(self):
        source = E.build_source(["H"], [_record()])

        class Never:
            async def chat(self, *a, **k):  # pragma: no cover - must not run
                raise AssertionError("a model was asked to paraphrase one rule")

        attempt = await E.generate_explanation(source, client=Never())
        assert attempt.explanation is None
        assert attempt.unavailable_code == E.UNAVAILABLE_NOTHING_TO_ASSEMBLE

    def test_a_reply_no_shorter_than_the_source_is_refused(self):
        source = E.build_source(["H"], [_record(), _record(rule_id="r2")])
        text, code = E.validate_explanation("x" * 4000, source)
        assert text is None
        assert code == E.UNAVAILABLE_NOT_SHORTER

    def test_the_bound_is_measured_against_the_document_not_the_decomposition(self):
        """The referent, asserted, because getting it wrong made it useless.

        Measured against the decomposed fields, a single record allows an
        explanation about as long as its own source sentence — which is exactly
        the paraphrase the bound exists to refuse.
        """

        long_source = _record()
        long_source["formulation"]["canonical"]["source_text"] = "W" * 900
        source = E.build_source(["H"], [long_source, _record(rule_id="r2")])
        assert source.narrated_length >= 900

    def test_overlapping_source_text_is_counted_once(self):
        # Rules of one passage record overlapping spans. Counting the same
        # sentence four times would quadruple the allowance for no new content.
        same = [_record(), _record(rule_id="r2"), _record(rule_id="r3")]
        source = E.build_source(["H"], same)
        assert source.narrated_length == len("ZQXJV WRTPLM KHDFG BNYCS.")

    def test_a_decline_is_an_answer_and_not_a_failure(self):
        source = E.build_source(["H"], [_record(), _record(rule_id="r2")])
        text, code = E.validate_explanation(E.DECLINE_REPLY, source)
        assert text is None
        assert code == E.UNAVAILABLE_DECLINED

    def test_a_usable_reply_survives_every_check(self):
        source = E.build_source(["H"], [_record(), _record(rule_id="r2")])
        text, code = E.validate_explanation("Someone must do a thing.", source)
        assert text == "Someone must do a thing."
        assert code is None


class TestOutcomesStayDistinguishable:
    def test_a_failure_is_never_kept(self):
        """A transient failure must not become a permanent one.

        A model call that timed out once will likely answer next time. Caching
        the failure would leave the reviewer's button dead for the life of the
        process with nothing on screen to say why.
        """

        E._forget_all()
        source = E.build_source(["H"], [_record(), _record(rule_id="r2")])
        failed = E._attempt(
            source, explanation=None, code=E.UNAVAILABLE_MODEL_FAILED, deployment="d"
        )
        E.remember(failed)
        assert E.cached(source.digest) is None

    def test_an_explanation_is_kept_against_the_record_it_explains(self):
        E._forget_all()
        source = E.build_source(["H"], [_record(), _record(rule_id="r2")])
        ok = E._attempt(source, explanation="A reading.", code=None, deployment="d")
        E.remember(ok)
        assert E.cached(source.digest) is ok

    def test_an_edited_record_never_finds_the_older_reading(self):
        """Staleness cannot arise, rather than being reported when it does."""

        E._forget_all()
        before = E.build_source(["H"], [_record(), _record(rule_id="r2")])
        E.remember(E._attempt(before, explanation="A reading.", code=None, deployment="d"))
        after = E.build_source(["H"], [_record(title="Edited"), _record(rule_id="r2")])
        assert E.cached(after.digest) is None

    def test_the_cache_is_bounded(self):
        E._forget_all()
        for index in range(E.CACHE_ENTRIES + 20):
            source = E.build_source(
                ["H"], [_record(title=f"T{index}"), _record(rule_id="r2")]
            )
            E.remember(
                E._attempt(source, explanation="A reading.", code=None, deployment="d")
            )
        assert len(E._CACHE) == E.CACHE_ENTRIES


class TestTheRecordIsWhatIsReturned:
    def test_a_rule_holding_nothing_is_dropped_rather_than_sent_as_a_blank(self):
        source = E.build_source(["H"], [{}, _record(), _record(rule_id="r2")])
        assert source.rule_count == 2

    def test_a_budget_reports_what_it_could_not_cover(self):
        many = [_record(title=f"Rule {n}" * 40) for n in range(200)]
        source = E.build_source(["H"], many, max_chars=1200)
        assert not source.is_complete
        assert 0 < source.covered_rule_count < 200

    def test_truncation_never_splits_a_rule(self):
        """A budget drops whole rules, so nothing arrives as half a record.

        Half a rule read as a whole one is an explanation of a requirement the
        document never stated, which is the same failure as adding to it.
        """

        many = [_record(title=f"Rule {n}" * 40) for n in range(200)]
        source = E.build_source(["H"], many, max_chars=1200)
        whole = {rule.title for rule in E.build_source(["H"], many).rules}
        for rule in source.rules:
            assert rule.title in whole
            assert rule.stated
            assert rule.effect

    def test_a_field_the_extraction_left_empty_is_not_offered_to_the_model(self):
        payload = _record()
        payload["formulation"]["canonical"]["rule"]["threshold"] = "   "
        source = E.build_source(["H"], [payload, _record(rule_id="r2")])
        assert "threshold" not in source.request_body

    def test_a_field_outside_the_reading_order_still_reaches_the_model(self):
        # The list drives sequence, never inclusion. A field added to the
        # contract later must not be silently withheld from the reader.
        payload = _record()
        payload["formulation"]["canonical"]["rule"]["some_new_field"] = "a value"
        source = E.build_source(["H"], [payload, _record(rule_id="r2")])
        assert "some_new_field" in source.request_body
