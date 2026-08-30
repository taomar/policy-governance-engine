"""A projection is checked against the record it renders, or it is not matched.

WHAT THIS FILE HOLDS

A corpus that was *transported* successfully is not a corpus that is *faithful*.
A rendering call that returned, an embedding that returned and an upload that was
acknowledged are facts about carriage; none of them is a fact about meaning. The
gap between the two is the whole reason this gate exists, and it is a quiet gap:
a substituted rendering is a well-formed document of the right shape, in the
right index, under the right profile, and it retrieves. It is simply about
something else.

So this file asserts the claim the gate is for — **a projection that is not a
rendering of its source is caught, and one that is is not** — and the three
properties that make the claim worth anything:

  * **Per document, not per corpus.** A mean over a schedule of good rows would
    absorb the one row that is about something else entirely, and that row is
    precisely the one a question about it would retrieve. Any one pair below the
    floor fails the corpus, and the finding names the document.
  * **The semantic half earns its place.** The deterministic checks cannot see a
    substitution that preserves every number and identifier. The corruption in
    `test_a_substituted_rendering_is_caught_when_nothing_deterministic_can_see_it`
    passes every structural check there is, and is still refused.
  * **"Could not check" is never "checked".** A validation nobody could perform
    is exactly as much evidence as one that failed, and neither opens the gate.

WHAT THE EMBEDDING STUB IS, AND IS NOT

`_TokenSpaceClient` is a deterministic, offline stand-in: a bag-of-tokens vector,
so identical text scores 1.0 and disjoint vocabulary scores ~0. It stands in for
a multilingual embedding and makes no claim to behave like one. What is under
test here is the **gate's logic** — whether a low-scoring pair is detected,
attributed to its document and allowed to fail the corpus — and not the quality
of any real embedding, which a stub cannot speak to and which this file therefore
never asserts.

NOTHING HERE NAMES A DOMAIN

The fixtures are a mooring fee, a kennel inspection and a stationery threshold.
What is asserted is the relationship between a record, its projection and what
the gate concludes, which must hold for any governance corpus.
"""
from __future__ import annotations

import asyncio
import os
import re
import zlib

import pytest

os.environ.setdefault("DATABASE_URL", "******localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "******localhost:5433/test")

from policy_platform.infrastructure.projection.policy_rule_slice import (  # noqa: E402
    LARGE_POLICY_RULE_THRESHOLD,
)
from policy_platform.infrastructure.quality.projection_faithfulness import (  # noqa: E402
    FINDING_AUTHORITATIVE_RECORD_EMBEDDED,
    FINDING_DOCUMENT_MISSING,
    FINDING_DOCUMENT_REPEATED,
    FINDING_DOCUMENT_UNEXPECTED,
    FINDING_EMBEDDING_COUNT_MISMATCH,
    FINDING_EMBEDDING_UNAVAILABLE,
    FINDING_PARENT_LINK_MISSING,
    FINDING_PROFILE_MISMATCH,
    FINDING_PROJECTED_TEXT_EMPTY,
    FINDING_RULE_DOCUMENTS_MISSING,
    FINDING_RULE_DOCUMENTS_UNEXPECTED,
    FINDING_SIMILARITY_BELOW_FLOOR,
    FINDING_VERSION_MISMATCH,
    PROJECTION_QUALITY_PROFILE,
    QUALITY_FAILED,
    QUALITY_PASSED,
    QUALITY_UNAVAILABLE,
    ProjectedRecord,
    known_quality_profile,
    quality_profile,
    validate_projection,
)

_PROFILE = "policy-english-projection-v1"
_VERSION = "22222222-2222-4222-8222-222222222222"


def _run(coro):
    return asyncio.run(coro)


# ── a deterministic stand-in for a multilingual embedding ────────────


_BUCKETS = 512


def _vector(text: str) -> list[float]:
    """A bag-of-tokens vector, stable across processes.

    `zlib.crc32` rather than `hash`, because `hash` on a str is salted per
    process: a test whose pass depended on it would pass and fail on the same
    code for reasons no one could reproduce.
    """

    buckets = [0.0] * _BUCKETS
    for token in re.findall(r"[a-z]+", text.lower()):
        buckets[zlib.crc32(token.encode()) % _BUCKETS] += 1.0
    return buckets


class _TokenSpaceClient:
    """Embeds by vocabulary overlap. Identical text scores 1.0."""

    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, texts):
        self.calls += 1
        return [_vector(text) for text in texts]


class _MiscountingClient:
    """Returns a reply that cannot be aligned with what it was given."""

    async def embed(self, texts):
        return [_vector(text) for text in texts][:-1]


class _RefusingClient:
    async def embed(self, texts):
        raise RuntimeError("the deployment refused")


# ── the corpus under test ────────────────────────────────────────────


#: Deliberately digit-free. Numbers and identifiers are what the deterministic
#: preservation check can see, so a corpus without them is the one that isolates
#: the semantic half: anything caught here was caught by meaning alone.
_PARENT_TEXT = (
    "A vessel occupying a berth beyond the permitted period owes a mooring fee "
    "to the harbour authority for each further period begun."
)
_RULE_TEXTS = {
    "rule-a": (
        "A kennel operator must admit an inspector to any part of the premises "
        "where animals are kept, at any reasonable hour."
    ),
    "rule-b": (
        "Stationery ordered above the departmental threshold requires written "
        "approval from the head of procurement before the order is placed."
    ),
}

_PARENT_ID = "doc-parent"


def _documents(*, profile: str = _PROFILE, overrides: dict | None = None) -> list[dict]:
    """The set an untouched build of the corpus above would have produced."""

    docs = [
        {
            "id": _PARENT_ID,
            "policy_version_id": _VERSION,
            "projection_profile": profile,
            "content_type": "policy",
            "parent_document_id": None,
            "retrieval_text": _PARENT_TEXT,
        }
    ]
    for key, text in _RULE_TEXTS.items():
        docs.append(
            {
                "id": f"doc-{key}",
                "policy_version_id": _VERSION,
                "projection_profile": profile,
                "content_type": "rule",
                "parent_document_id": _PARENT_ID,
                "retrieval_text": text,
            }
        )
    for document in docs:
        document.update((overrides or {}).get(str(document["id"]), {}))
    return docs


def _records(*, rule_count: int = LARGE_POLICY_RULE_THRESHOLD + 1) -> list[ProjectedRecord]:
    records = [
        ProjectedRecord(
            document_id=_PARENT_ID,
            policy_version_id=_VERSION,
            source_text=_PARENT_TEXT,
            provision_rule_count=rule_count,
        )
    ]
    for key, text in _RULE_TEXTS.items():
        records.append(
            ProjectedRecord(
                document_id=f"doc-{key}",
                policy_version_id=_VERSION,
                source_text=text,
                parent_document_id=_PARENT_ID,
            )
        )
    return records


def _validate(*, documents=None, records=None, client=None, **kwargs):
    return _run(
        validate_projection(
            records=_records() if records is None else records,
            documents=_documents() if documents is None else documents,
            expected_profile=_PROFILE,
            openai_client=_TokenSpaceClient() if client is None else client,
            **kwargs,
        )
    )


def _codes(report) -> set[str]:
    return {finding.code for finding in report.findings}


# ── the claim ────────────────────────────────────────────────────────


class TestAnUnmodifiedProjectionPasses:
    def test_a_faithful_corpus_passes_with_no_findings(self) -> None:
        """The control. Without it, every failing assertion below is worthless:
        a gate that refused everything would satisfy them all."""

        report = _validate()

        assert report.state == QUALITY_PASSED
        assert report.passed is True
        assert report.findings == ()
        assert report.structural_findings == 0
        assert report.below_floor == 0
        assert report.checked_documents == len(_RULE_TEXTS) + 1
        assert report.minimum_similarity == pytest.approx(1.0)
        assert report.mean_similarity == pytest.approx(1.0)

    def test_an_empty_corpus_passes_because_nothing_in_it_can_be_wrong(self) -> None:
        """A project with no published policies is a coherent thing to have, and
        it is not a validation failure. Refusing it would make "no policies yet"
        indistinguishable from "the corpus is corrupt"."""

        report = _validate(documents=[], records=[])

        assert report.state == QUALITY_PASSED
        assert report.checked_documents == 0
        assert report.minimum_similarity is None


class TestASeededCorruptionIsCaught:
    def test_a_substituted_rendering_is_caught_when_nothing_deterministic_can_see_it(
        self,
    ) -> None:
        """THE CENTRAL CASE.

        One rule document carries a rendering of a *different* rule. The document
        is well-formed, under the right profile, for the right version, linked to
        the right parent, non-empty, and carries no number or identifier for the
        preservation check to find missing. Every deterministic check passes. It
        is still refused, and it is refused by meaning."""

        documents = _documents(
            overrides={"doc-rule-a": {"retrieval_text": _RULE_TEXTS["rule-b"]}}
        )
        report = _validate(documents=documents)

        assert report.state == QUALITY_FAILED
        assert report.passed is False
        # Proven by the semantic half alone: nothing structural fired.
        assert report.structural_findings == 0
        assert _codes(report) == {FINDING_SIMILARITY_BELOW_FLOOR}
        assert report.below_floor == 1

    def test_the_finding_names_the_rule_document_and_not_its_policy(self) -> None:
        """Per-rule, which is the whole point. A policy-level score would hide
        exactly the row-level substitution that citation-integrity checks cannot
        see — the parent is untouched and would report healthy."""

        documents = _documents(
            overrides={"doc-rule-a": {"retrieval_text": _RULE_TEXTS["rule-b"]}}
        )
        report = _validate(documents=documents)

        named = [f.document_id for f in report.findings if f.code == FINDING_SIMILARITY_BELOW_FLOOR]
        assert named == ["doc-rule-a"]
        assert _PARENT_ID not in named

    def test_one_bad_row_fails_the_corpus_rather_than_being_averaged_away(self) -> None:
        """Any one pair below the floor fails it. Two faithful rows either side
        of a substituted one must not carry it."""

        documents = _documents(
            overrides={"doc-rule-a": {"retrieval_text": _RULE_TEXTS["rule-b"]}}
        )
        report = _validate(documents=documents)

        assert report.state == QUALITY_FAILED
        # The mean is still high — which is precisely why it is not the test.
        assert report.mean_similarity is not None
        assert report.mean_similarity > quality_profile().minimum_pair_similarity
        assert report.minimum_similarity is not None
        assert report.minimum_similarity < quality_profile().minimum_pair_similarity

    def test_every_pair_is_scored_even_once_one_has_already_failed(self) -> None:
        """A report that stopped at the first finding would send an operator
        round a loop of one repair per run against a corpus of thousands."""

        documents = _documents(
            overrides={"doc-rule-a": {"retrieval_text": _RULE_TEXTS["rule-b"]}}
        )
        report = _validate(documents=documents)

        assert report.checked_documents == len(_RULE_TEXTS) + 1


class TestTheDeterministicHalf:
    """The checks that need no model, each seeded on its own."""

    def test_a_document_the_build_expected_and_the_index_does_not_hold(self) -> None:
        documents = [d for d in _documents() if d["id"] != "doc-rule-b"]
        report = _validate(documents=documents)

        assert report.state == QUALITY_FAILED
        assert FINDING_DOCUMENT_MISSING in _codes(report)

    def test_a_document_the_index_holds_that_the_build_did_not_expect(self) -> None:
        documents = _documents()
        documents.append(
            {
                "id": "doc-left-over",
                "policy_version_id": _VERSION,
                "projection_profile": _PROFILE,
                "parent_document_id": None,
                "retrieval_text": _PARENT_TEXT,
            }
        )
        report = _validate(documents=documents)

        assert FINDING_DOCUMENT_UNEXPECTED in _codes(report)

    def test_one_key_twice_is_a_corpus_short_by_one(self) -> None:
        documents = _documents()
        documents.append(dict(documents[1]))
        report = _validate(documents=documents)

        assert FINDING_DOCUMENT_REPEATED in _codes(report)

    def test_a_rendering_under_a_superseded_contract(self) -> None:
        documents = _documents(
            overrides={"doc-rule-a": {"projection_profile": "policy-english-projection-v0"}}
        )
        report = _validate(documents=documents)

        assert FINDING_PROFILE_MISMATCH in _codes(report)

    def test_a_document_built_for_another_version(self) -> None:
        documents = _documents(
            overrides={"doc-rule-a": {"policy_version_id": "33333333-3333-4333-8333-333333333333"}}
        )
        report = _validate(documents=documents)

        assert FINDING_VERSION_MISMATCH in _codes(report)

    def test_a_rule_document_whose_parent_never_landed(self) -> None:
        documents = _documents(overrides={"doc-rule-a": {"parent_document_id": "doc-absent"}})
        report = _validate(documents=documents)

        assert FINDING_PARENT_LINK_MISSING in _codes(report)

    def test_an_indexed_document_with_no_retrieval_text(self) -> None:
        documents = _documents(overrides={"doc-rule-a": {"retrieval_text": "   "}})
        report = _validate(documents=documents)

        assert FINDING_PROJECTED_TEXT_EMPTY in _codes(report)

    def test_the_index_may_not_become_a_second_copy_of_the_record(self) -> None:
        """An index document holds identifiers, counts, headings, retrieval text
        and a vector. A mapping is the shape of the authoritative record, and a
        citation must resolve to one place, not two."""

        documents = _documents(
            overrides={"doc-rule-a": {"spans": [{"text": "the source sentence"}]}}
        )
        report = _validate(documents=documents)

        assert FINDING_AUTHORITATIVE_RECORD_EMBEDDED in _codes(report)

    def test_a_schedule_whose_rows_got_no_documents_of_their_own(self) -> None:
        """Complete by count, unreachable in exactly the part that needed the
        split."""

        report = _validate(
            documents=[d for d in _documents() if d["parent_document_id"] is None],
            records=[r for r in _records() if r.parent_document_id is None],
        )

        assert FINDING_RULE_DOCUMENTS_MISSING in _codes(report)

    def test_a_provision_small_enough_to_read_whole_carrying_rule_documents(self) -> None:
        report = _validate(records=_records(rule_count=LARGE_POLICY_RULE_THRESHOLD))

        assert FINDING_RULE_DOCUMENTS_UNEXPECTED in _codes(report)

    def test_the_manifest_is_excluded_rather_than_counted_as_a_stray(self) -> None:
        """It is the statement *about* the content, so counting it would make
        every corpus one document larger than itself."""

        documents = _documents()
        documents.append(
            {
                "id": "doc-manifest",
                "policy_version_id": _VERSION,
                "projection_profile": _PROFILE,
                "parent_document_id": None,
                "retrieval_text": "",
            }
        )
        report = _validate(documents=documents, ignore_document_ids=("doc-manifest",))

        assert report.state == QUALITY_PASSED
        assert report.findings == ()


class TestCouldNotCheckIsNeverChecked:
    def test_no_embedding_deployment_is_unavailable_and_not_a_pass(self) -> None:
        report = _run(
            validate_projection(
                records=_records(),
                documents=_documents(),
                expected_profile=_PROFILE,
                openai_client=None,
            )
        )

        assert report.state == QUALITY_UNAVAILABLE
        assert report.passed is False
        assert _codes(report) == {FINDING_EMBEDDING_UNAVAILABLE}

    def test_a_service_that_refused_is_unavailable_and_not_a_pass(self) -> None:
        report = _validate(client=_RefusingClient())

        assert report.state == QUALITY_UNAVAILABLE
        assert report.passed is False
        assert FINDING_EMBEDDING_UNAVAILABLE in _codes(report)

    def test_a_reply_that_cannot_be_aligned_fails_closed(self) -> None:
        """No pair in that batch can be attributed, so every one of them is a
        finding rather than a best guess at which survived."""

        report = _validate(client=_MiscountingClient())

        assert report.state == QUALITY_UNAVAILABLE
        assert _codes(report) == {FINDING_EMBEDDING_COUNT_MISMATCH}
        assert report.checked_documents == 0

    def test_a_proven_failure_outranks_a_missing_check(self) -> None:
        """A corpus whose set is wrong is failed on evidence and stays failed
        whether or not the embeddings arrived. Reporting `unavailable` would send
        an operator to fix a deployment instead of rebuilding a corpus."""

        documents = [d for d in _documents() if d["id"] != "doc-rule-b"]
        report = _run(
            validate_projection(
                records=_records(),
                documents=documents,
                expected_profile=_PROFILE,
                openai_client=_RefusingClient(),
            )
        )

        assert report.state == QUALITY_FAILED


class TestTheReportCarriesNoText:
    def test_no_field_of_the_payload_holds_a_word_of_the_corpus(self) -> None:
        """A finding names a document by a key this platform generated. The one
        way this gate could leak policy text is a field that can hold prose, so
        the assertion is over the whole serialised payload."""

        documents = _documents(
            overrides={"doc-rule-a": {"retrieval_text": _RULE_TEXTS["rule-b"]}}
        )
        report = _validate(documents=documents)
        payload = repr(report.as_payload())

        for text in (_PARENT_TEXT, *_RULE_TEXTS.values()):
            for word in ("vessel", "kennel", "stationery", "harbour", "inspector"):
                assert word not in payload.lower(), f"{word!r} reached the report"
            assert text not in payload

    def test_the_payload_carries_the_verdict_the_gate_is_read_for(self) -> None:
        report = _validate()
        payload = report.as_payload()

        assert set(payload) == {
            "state",
            "profile",
            "checked_documents",
            "structural_findings",
            "below_floor",
            "minimum_similarity",
            "mean_similarity",
            "validated_at",
            "findings",
        }
        assert payload["profile"] == PROJECTION_QUALITY_PROFILE


class TestTheProfileIsAName:
    def test_a_profile_this_build_does_not_carry_is_refused_rather_than_defaulted(
        self,
    ) -> None:
        """Falling back would mean validating under one statement of quality
        while recording another, which is the one way this could lie."""

        assert known_quality_profile(PROJECTION_QUALITY_PROFILE) is True
        assert known_quality_profile("policy-projection-quality-v99") is False
        assert known_quality_profile(None) is False

        with pytest.raises(ValueError):
            quality_profile("policy-projection-quality-v99")

    def test_the_verdict_records_the_profile_it_was_reached_under(self) -> None:
        report = _validate()

        assert report.profile == PROJECTION_QUALITY_PROFILE
