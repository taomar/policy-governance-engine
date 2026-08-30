"""The corpus is indexed in the language it is matched in, or it is not matched.

WHAT THIS FILE HOLDS

A question is reduced to one processing language before anything retrieves. If
the corpus it is scored against was never reduced to that language, the match
does not merely go badly — it goes *quietly*: every policy scores near zero, and
a near-zero ranking is indistinguishable from an honest "nothing here bears on
your question". A reviewer would read the second and be given the first.

So the index carries the corpus rendered into the processing language, stamped
with the versioned contract it was rendered under, and it carries one document
whose whole job is to say whether that rendering is complete. This file asserts
the three claims that follow from it:

  * **The rendering is faithful where fidelity is checkable.** Numbers and
    identifiers survive it, a rendering that loses one is refused rather than
    repaired, and the authoritative record is never touched by any of it.
  * **A rule is indexed on its own terms once a provision stops being one
    statement.** Above the threshold each rule is its own document; at or under
    it, none is — and a provision that shrinks back has its rule documents
    removed rather than left behind to be found.
  * **Readiness is written down, and it is written down pessimistically.** The
    manifest goes to `incomplete` before the first upload and to `ready` only
    after the last acknowledgement, so every way a rebuild can be interrupted
    leaves a project that refuses rather than one that answers from part of
    itself.

NOTHING HERE NAMES A DOMAIN

The fixtures are a berthing tariff, a veterinary licence and a procurement
threshold, plus one corpus in Arabic and one in vocabulary that means nothing at
all. What is asserted is the *relationship* between a corpus, its projection and
what can be found — which must hold for any governance corpus in any language,
including one this repository has never seen.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

os.environ.setdefault("DATABASE_URL", "******localhost:5433/test")
os.environ.setdefault("ALEMBIC_DATABASE_URL", "******localhost:5433/test")

from policy_platform.domain.models import PolicyIndexState  # noqa: E402
from policy_platform.infrastructure.assistants.ai_case_language import (  # noqa: E402
    ENGLISH_PROJECTION_PROFILE,
    INDEX_PROJECTION_UNAVAILABLE,
)
from policy_platform.infrastructure.search import english_projection  # noqa: E402
from policy_platform.infrastructure.search.policy_index import (  # noqa: E402
    CONTENT_TYPE_MANIFEST,
    CONTENT_TYPE_POLICY,
    CONTENT_TYPE_RULE,
    MANIFEST_INCOMPLETE,
    MANIFEST_READY,
    POLICY_INDEX_FRESHNESS_CURRENT,
    POLICY_INDEX_FRESHNESS_STALE,
    _document_was_accepted,
    _acknowledged_keys,
    indexable_rules,
    policy_document_id,
    policy_index_definition,
    policy_index_filter,
    policy_index_freshness,
    policy_index_manifest_id,
    policy_index_ready_filter,
    policy_rule_document_id,
    read_projection_readiness,
    rebuild_project_policy_index,
)
from policy_platform.infrastructure.projection.policy_rule_slice import (  # noqa: E402
    LARGE_POLICY_RULE_THRESHOLD,
)
from tests.fixtures.search_stubs import contained_payload, echoing_projection_client  # noqa: E402

_KEY = "an-index-under-test"
_VERSION = "11111111-1111-4111-8111-111111111111"


def _run(coro):
    return asyncio.run(coro)


# ── corpora, in several languages and one that is no language ────────


#: Five source corpora. Each is a list of sentences; nothing outside this map
#: knows what any of them mean, and every assertion below references the map
#: rather than a value, so a sixth can be added without touching a test.
CORPORA: dict[str, list[str]] = {
    "maritime": [
        "A vessel occupying berth B-14 beyond 36 hours is charged the extended tariff.",
        "A vessel entering the inner harbour is assigned 1 licensed pilot for the transit.",
        "Reference SOLAS-74 applies to every vessel over 500 gross tonnes.",
    ],
    "veterinary": [
        "A practice licence under schedule VET-3 is renewed every 24 months.",
        "A practitioner supervising between 2 and 6 assistants files a quarterly return.",
        "Controlled substances are reconciled against register form R-19 each week.",
    ],
    "procurement": [
        "An award above 250000 units requires the approval of the tender board.",
        "A framework agreement under clause 7.2 runs for 48 months.",
        "Supplier code SUP-0042 is suspended pending the outcome of an audit.",
    ],
    "arabic": [
        "يمنح الموظف بدل سكن قدره 12000 وحدة سنويا وفق البند 4.2 من اللائحة.",
        "تجدد رخصة المزاولة كل 24 شهرا بموجب النموذج R-19.",
        "تسري المادة 15 على كل طلب يتجاوز 500 وحدة.",
    ],
    "invented": [
        "A grelvin holding 8 morticles must lodge a farnstable within 3 quorls.",
        "The 12 varnic tiers of a brellow are reconciled against form QQ-31.",
        "A drangel exceeding 90 flunes is escalated under protocol ZX-7.",
    ],
}


def _projection(
    *,
    rule_count: int,
    corpus: str = "maritime",
    version_id: str = _VERSION,
    provision_key: str = "a-provision",
    version_number: int = 3,
) -> dict:
    """One published policy's grounding projection, with `rule_count` rules.

    Each rule rests on a sentence drawn from the corpus, cycled, with its own
    ordinal woven in so the rules are distinguishable without any of them being
    about a subject this file knows.
    """

    sentences = CORPORA[corpus]
    rules = []
    spans = {}
    for index in range(rule_count):
        span_id = f"s{index}"
        spans[span_id] = {"text": f"{sentences[index % len(sentences)]} [{index}]"}
        rules.append(
            {
                "rule_id": f"R-{index}",
                "evidence_refs": [span_id],
                "effect": {"type": "REQUIRE", "action": f"action {index}"},
                "rule_type": "obligation",
                "modality": "must",
            }
        )
    return {
        "envelope": {
            "policy_version_id": version_id,
            "version_number": version_number,
            "provision_key": provision_key,
            "heading_path": ["Handbook", f"Part {version_number}"],
        },
        "rules": rules,
        "spans": spans,
        "facts": {},
    }


def _settings(*, search_enabled=True, ai_enabled=True):
    return SimpleNamespace(
        search_enabled=search_enabled,
        ai_enabled=ai_enabled,
        azure_openai_embedding_dimensions=3,
        azure_openai_fast_deployment="fast",
        azure_openai_deployment="slow",
    )


class RecordingSearch:
    """An index that remembers everything it was asked to do, in order."""

    def __init__(self, existing_ids=(), *, reject: set[str] | None = None):
        self.created: list[dict] = []
        self.uploads: list[list[dict]] = []
        self.deleted: list[list[str]] = []
        self.filters: list[str] = []
        self.existing_ids = list(existing_ids)
        self.reject = reject or set()

    async def create_index(self, definition):
        self.created.append(definition)
        return definition

    async def upload_documents(self, index, documents):
        self.uploads.append(list(documents))
        return {
            "value": [
                {"key": doc["id"], "status": doc["id"] not in self.reject}
                for doc in documents
            ]
        }

    async def find_ids_by_filter(self, index, *, filter_expr, page_size=1000):
        self.filters.append(filter_expr)
        if "manifest_state" in filter_expr:
            return [
                document["id"]
                for document in self.manifests
                if document.get("manifest_state") == MANIFEST_READY
            ]
        return list(self.existing_ids)

    async def delete_documents(self, index, ids):
        self.deleted.append(list(ids))
        return {"value": []}

    # ── what the index ended up holding ─────────────────────────────
    @property
    def documents(self) -> list[dict]:
        return [doc for batch in self.uploads for doc in batch]

    @property
    def manifests(self) -> list[dict]:
        return [d for d in self.documents if d["content_type"] == CONTENT_TYPE_MANIFEST]

    def of_type(self, content_type: str) -> list[dict]:
        return [d for d in self.documents if d["content_type"] == content_type]

    @property
    def content_writes(self) -> list[dict]:
        """Every non-manifest document this index was asked to write."""

        return [
            doc
            for batch in self.uploads
            for doc in batch
            if doc["content_type"] != CONTENT_TYPE_MANIFEST
        ]

    @property
    def final_manifest(self) -> dict:
        return self.manifests[-1]


def _rebuild(projections, *, search=None, client=None, version_number=3, **kwargs):
    search = search or RecordingSearch()
    client = client or echoing_projection_client()()
    outcome = _run(
        rebuild_project_policy_index(
            policy_set_key=_KEY,
            version_number=version_number,
            projections=projections,
            settings=_settings(),
            search_client=search,
            openai_client=client,
            indexed_at=datetime(2026, 8, 30, tzinfo=UTC),
            **kwargs,
        )
    )
    return outcome, search, client


# ── the schema ───────────────────────────────────────────────────────


def test_the_schema_can_hold_all_three_kinds_of_document_and_be_filtered_on_them():
    """One index, three content types, and every field a query needs to filter on.

    A field that is not filterable cannot gate a query, and a gate that cannot be
    expressed as a filter has to be applied after the fact — which means the
    documents it should have excluded were already ranked against the question.
    """

    definition = policy_index_definition("an-index", vector_dimensions=3)
    fields = {field["name"]: field for field in definition["fields"]}

    for name in (
        "content_type",
        "projection_profile",
        "rule_id",
        "rule_ordinal",
        "parent_document_id",
        "provision_key",
        "manifest_state",
        "policy_set_key",
        "policy_version_id",
    ):
        assert name in fields, f"the schema cannot address documents by {name}"
        assert fields[name].get("filterable"), f"{name} cannot gate a query"

    # Retrievable, because the request side reads them off the hit rather than
    # looking anything up a second time.
    for name in ("rule_id", "rule_ordinal", "parent_document_id", "retrieval_text"):
        assert fields[name].get("retrievable"), f"{name} cannot be read off a hit"

    # The vector stays where it was and keeps the dimension it is configured
    # with: a rule document and a policy document are ranked by the same field.
    assert fields["body_vector"]["dimensions"] == 3
    assert fields["body_vector"]["vectorSearchProfile"]


def test_a_filter_scopes_to_one_project_one_kind_and_one_rendering_contract():
    """Every clause is additive, and the unscoped form still selects the project.

    The stale sweep needs "everything this project holds"; a query needs "the
    policy documents of this project rendered under this contract". Both come
    from the same function so a renamed field cannot be remembered in one place
    and forgotten in the other.
    """

    whole = policy_index_filter(_KEY)
    assert "policy_set_key" in whole
    assert "content_type" not in whole

    scoped = policy_index_filter(
        _KEY, content_type=CONTENT_TYPE_RULE, projection_profile="p-1"
    )
    assert f"content_type eq '{CONTENT_TYPE_RULE}'" in scoped
    assert "projection_profile eq 'p-1'" in scoped
    assert whole in scoped  # additive, never a different question

    ready = policy_index_ready_filter(_KEY, projection_profile="p-1")
    assert f"content_type eq '{CONTENT_TYPE_MANIFEST}'" in ready
    assert f"manifest_state eq '{MANIFEST_READY}'" in ready

    # A key carrying a quote is escaped, not concatenated.
    assert "''" in policy_index_filter("o'brien-holdings")


# ── which provisions get rule documents ──────────────────────────────


@pytest.mark.parametrize("corpus", sorted(CORPORA))
def test_a_provision_at_or_under_the_threshold_gets_no_rule_documents(corpus: str):
    """Below the threshold a provision is one statement and its own document carries it."""

    for count in (1, LARGE_POLICY_RULE_THRESHOLD - 1, LARGE_POLICY_RULE_THRESHOLD):
        assert indexable_rules(_projection(rule_count=count, corpus=corpus)) == []

        _outcome, search, _client = _rebuild([_projection(rule_count=count, corpus=corpus)])
        assert search.of_type(CONTENT_TYPE_RULE) == []
        assert len(search.of_type(CONTENT_TYPE_POLICY)) == 1


@pytest.mark.parametrize("corpus", sorted(CORPORA))
def test_one_rule_past_the_threshold_gives_every_rule_its_own_document(corpus: str):
    """The boundary is exact: fifteen rules, none; sixteen, sixteen."""

    over = LARGE_POLICY_RULE_THRESHOLD + 1
    projection = _projection(rule_count=over, corpus=corpus)
    assert len(indexable_rules(projection)) == over

    outcome, search, _client = _rebuild([projection])

    rules = search.of_type(CONTENT_TYPE_RULE)
    assert len(rules) == over
    assert outcome.rule_document_count == over
    assert outcome.policy_document_count == 1
    assert outcome.document_count == over + 1

    # Every rule document names the provision that holds it, and its parent's
    # document id, so a rule hit can raise its policy without a second lookup.
    parent = policy_document_id(policy_version_id=_VERSION, provision_key="a-provision")
    assert {doc["parent_document_id"] for doc in rules} == {parent}
    assert {doc["provision_key"] for doc in rules} == {"a-provision"}
    assert sorted(doc["rule_ordinal"] for doc in rules) == list(range(over))
    assert {doc["document_version"] for doc in rules} == {_VERSION}


def test_a_rule_document_key_is_a_pure_function_of_what_identifies_the_rule():
    """Stable ids are what make a rebuild an overwrite rather than an accumulation."""

    first = policy_rule_document_id(
        policy_version_id=_VERSION, provision_key="p", rule_id="R-1"
    )
    assert first == policy_rule_document_id(
        policy_version_id=_VERSION, provision_key="p", rule_id="R-1"
    )
    # Any of the three moving produces a different document.
    assert first != policy_rule_document_id(
        policy_version_id="other", provision_key="p", rule_id="R-1"
    )
    assert first != policy_rule_document_id(
        policy_version_id=_VERSION, provision_key="q", rule_id="R-1"
    )
    assert first != policy_rule_document_id(
        policy_version_id=_VERSION, provision_key="p", rule_id="R-2"
    )


def test_rebuilding_the_same_corpus_twice_produces_the_same_documents():
    """Idempotent: nothing accumulates, and nothing is deleted that should stay."""

    projection = _projection(rule_count=20)
    _first, search_a, _ = _rebuild([projection])
    live = sorted(
        doc["id"] for doc in search_a.documents if doc["content_type"] != CONTENT_TYPE_MANIFEST
    )

    _second, search_b, _ = _rebuild([projection], search=RecordingSearch(existing_ids=live))
    assert sorted(
        doc["id"] for doc in search_b.documents if doc["content_type"] != CONTENT_TYPE_MANIFEST
    ) == live
    assert search_b.deleted == []  # nothing was stale


def test_a_provision_that_shrinks_below_the_threshold_loses_its_rule_documents():
    """The shrink case, which stable ids make automatic rather than special.

    A schedule edited down to a handful of rules is a provision again. Its rule
    documents are not in the new live set, so the stale sweep removes them — and
    it must, because a row that no longer exists must not be findable.
    """

    large = _projection(rule_count=30)
    _first, search_a, _ = _rebuild([large])
    stale_rule_ids = [doc["id"] for doc in search_a.of_type(CONTENT_TYPE_RULE)]
    assert stale_rule_ids

    small = _projection(rule_count=4)
    indexed = stale_rule_ids + [
        policy_document_id(policy_version_id=_VERSION, provision_key="a-provision")
    ]
    _second, search_b, _ = _rebuild([small], search=RecordingSearch(existing_ids=indexed))

    assert search_b.of_type(CONTENT_TYPE_RULE) == []
    assert search_b.deleted, "the rule documents of a shrunk provision were left behind"
    assert set(stale_rule_ids) <= set(search_b.deleted[0])


def test_a_new_version_removes_the_documents_of_the_one_it_replaces():
    """Version identity is in the key, so superseded documents cannot be reached."""

    old = _projection(rule_count=20, version_id="00000000-0000-4000-8000-000000000000")
    _first, search_a, _ = _rebuild([old], version_number=2)
    old_ids = [
        doc["id"] for doc in search_a.documents if doc["content_type"] != CONTENT_TYPE_MANIFEST
    ]

    new = _projection(rule_count=20, version_id=_VERSION)
    _second, search_b, _ = _rebuild(
        [new], search=RecordingSearch(existing_ids=old_ids), version_number=3
    )

    assert search_b.deleted
    assert set(old_ids) <= set(search_b.deleted[0])
    # And the manifest survives the sweep: it is the record of what just
    # happened, not a document the query side ever ranks.
    assert policy_index_manifest_id(_KEY) not in search_b.deleted[0]


# ── readiness ────────────────────────────────────────────────────────


def test_the_manifest_is_written_incomplete_before_anything_is_uploaded():
    """Every way a rebuild can be interrupted leaves a project that refuses.

    The order is the argument: if `ready` could be written first, or written at
    the same time, an interruption would leave an index that answers queries from
    part of a corpus and says nothing about it.
    """

    _outcome, search, _client = _rebuild([_projection(rule_count=20)])

    states = [doc["manifest_state"] for doc in search.manifests]
    assert states[0] == MANIFEST_INCOMPLETE
    assert states[-1] == MANIFEST_READY

    # And the incomplete one really was first: no content document was uploaded
    # before it.
    first_batch = search.uploads[0]
    assert [doc["content_type"] for doc in first_batch] == [CONTENT_TYPE_MANIFEST]


def test_a_partial_upload_leaves_the_project_unmatchable_and_claims_no_profile():
    """The failure this whole mechanism exists for.

    A batch in which some documents are rejected comes back as a success with
    per-document statuses — not as an error anything can raise. A rebuild that
    counted what it *sent* would mark a short corpus ready.
    """

    projection = _projection(rule_count=20)
    _first, probe, _ = _rebuild([projection])
    one_rule = probe.of_type(CONTENT_TYPE_RULE)[3]["id"]

    outcome, search, _client = _rebuild(
        [projection], search=RecordingSearch(reject={one_rule})
    )

    assert outcome.state == "failed"
    assert outcome.projection_profile is None
    assert outcome.manifest_state == MANIFEST_INCOMPLETE
    assert [doc["manifest_state"] for doc in search.manifests] == [MANIFEST_INCOMPLETE]
    assert MANIFEST_READY not in [doc["manifest_state"] for doc in search.manifests]


def test_a_completed_rebuild_stamps_the_profile_on_every_document():
    """One contract, on the manifest and on every document under it."""

    outcome, search, _client = _rebuild([_projection(rule_count=20)])

    assert outcome.state == "built"
    assert outcome.projection_profile == ENGLISH_PROJECTION_PROFILE
    assert outcome.manifest_state == MANIFEST_READY
    for document in search.documents:
        assert document["projection_profile"] == ENGLISH_PROJECTION_PROFILE
    assert search.final_manifest["expected_rule_documents"] == 20
    assert search.final_manifest["expected_policy_documents"] == 1
    assert search.final_manifest["uploaded_documents"] == 21


def test_readiness_is_a_live_probe_and_a_project_without_one_is_unavailable():
    """Absent, superseded and half-written are one answer, and it is a refusal."""

    class _Ready:
        async def find_ids_by_filter(self, index, *, filter_expr, page_size=1000):
            assert "manifest_state" in filter_expr
            return ["something"]

    class _NotReady:
        async def find_ids_by_filter(self, index, *, filter_expr, page_size=1000):
            return []

    ready = _run(
        read_projection_readiness(_Ready(), "ix", policy_set_key=_KEY)
    )
    assert ready.ready is True
    assert ready.profile == ENGLISH_PROJECTION_PROFILE
    assert ready.state is None

    missing = _run(
        read_projection_readiness(_NotReady(), "ix", policy_set_key=_KEY)
    )
    assert missing.ready is False
    assert missing.state == INDEX_PROJECTION_UNAVAILABLE


def test_an_index_built_under_a_superseded_contract_reads_as_stale():
    """Staleness gained a second axis, and the record can prove this one too."""

    state = PolicyIndexState(
        policy_set_id=None,
        index_name="ix",
        status="built",
        indexed_version_number=4,
        attempted_version_number=4,
        attempted_at=datetime(2026, 8, 30, tzinfo=UTC),
        document_count=3,
    )
    state.projection_profile = ENGLISH_PROJECTION_PROFILE

    assert (
        policy_index_freshness(
            state, 4, expected_projection_profile=ENGLISH_PROJECTION_PROFILE
        ).freshness
        == POLICY_INDEX_FRESHNESS_CURRENT
    )
    assert (
        policy_index_freshness(state, 4, expected_projection_profile="a-later-contract").freshness
        == POLICY_INDEX_FRESHNESS_STALE
    )
    # A caller that does not ask about the profile gets the reading it always had.
    assert policy_index_freshness(state, 4).freshness == POLICY_INDEX_FRESHNESS_CURRENT

    # A row written before projections existed carries none, and that is stale
    # rather than current: it was built, but not in a language a query can match.
    state.projection_profile = None
    assert (
        policy_index_freshness(
            state, 4, expected_projection_profile=ENGLISH_PROJECTION_PROFILE
        ).freshness
        == POLICY_INDEX_FRESHNESS_STALE
    )


# ── the projection itself ────────────────────────────────────────────


@pytest.mark.parametrize("corpus", sorted(CORPORA))
def test_a_projection_carries_every_number_and_identifier_its_source_states(corpus: str):
    """What is checkable about fidelity, checked.

    Meaning cannot be verified here and this does not pretend to. What *can* be
    verified is that the quantities and codes a governance text will be searched
    by came through, and that a rendering which lost one is refused rather than
    accepted and stamped.
    """

    for sentence in CORPORA[corpus]:
        assert english_projection.preservation_failure(sentence, sentence) is None


def test_a_rendering_that_drops_a_number_or_an_identifier_is_refused():
    """Refused, not repaired. Repairing it would be this code deciding what a policy says."""

    source = "An award above 250000 units requires approval under code SUP-0042."

    assert "number" in (
        english_projection.preservation_failure(
            source, "An award above units requires approval under code SUP-0042."
        )
        or ""
    )
    assert "identifier" in (
        english_projection.preservation_failure(
            # The digits survive; the code itself has come apart. That is the
            # failure the identifier check exists for and the number check
            # cannot see.
            source, "An award above 250000 units requires approval under code SUP 0042."
        )
        or ""
    )
    assert "empty" in (english_projection.preservation_failure(source, "   ") or "")
    assert "smaller" in (english_projection.preservation_failure(source * 20, "x" * 5) or "")
    assert "larger" in (
        english_projection.preservation_failure(source, source * 400) or ""
    )


def test_a_number_survives_a_change_of_digit_set():
    """A quantity is the same quantity whichever digits write it."""

    assert (
        english_projection.preservation_failure(
            "تجدد الرخصة كل ٢٤ شهرا بموجب النموذج R-19.",
            "The licence is renewed every 24 months under form R-19.",
        )
        is None
    )


def test_a_rebuild_that_cannot_render_a_policy_leaves_the_index_untouched():
    """No half-rendered corpus, and no partially-stamped index.

    A projection that fails is not a smaller success. Stamping a corpus that is
    in the processing language in part is the one thing the profile must never
    mean, so the whole build fails and nothing is uploaded.
    """

    def _lose_a_number(_key: str, text: str) -> str:
        return "".join(character for character in text if not character.isdigit())

    outcome, search, _client = _rebuild(
        [_projection(rule_count=20)],
        client=echoing_projection_client(corrupt=_lose_a_number)(),
    )

    assert outcome.state == "failed"
    assert outcome.projection_profile is None
    assert search.uploads == []  # nothing was written at all
    assert search.manifests == []


def test_the_authoritative_record_is_never_touched_by_the_projection():
    """The projection is a parallel artifact. The record it was taken from is not edited."""

    projection = _projection(rule_count=20, corpus="arabic")
    before = {key: dict(value) for key, value in projection["spans"].items()}

    _outcome, search, _client = _rebuild([projection])

    assert projection["spans"] == before
    for span_id, span in projection["spans"].items():
        assert span["text"] == before[span_id]["text"]
    # And nothing that was uploaded claims to be the record: the index holds
    # retrieval text and identifiers, never the payload.
    for document in search.documents:
        assert "spans" not in document
        assert "rules" not in document


def test_the_projection_never_logs_the_text_it_was_given(caplog):
    """A policy sentence in a log is a policy sentence outside the system.

    The renderer logs *that* a reply was rejected and *which* check rejected it.
    It never logs the value, on any path, including the failure path where the
    temptation is greatest.
    """

    secret = "A drangel exceeding 90 flunes is escalated under protocol ZX-7."
    projection = _projection(rule_count=20, corpus="invented")
    projection["spans"]["s0"] = {"text": secret}

    with caplog.at_level(logging.DEBUG):
        _outcome, _search, _client = _rebuild(
            [projection],
            client=echoing_projection_client(
                corrupt=lambda _key, text: "".join(c for c in text if not c.isdigit())
            )(),
        )

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert logged, "the failure was not reported at all"
    for fragment in ("drangel", "flunes", "ZX-7", secret):
        assert fragment not in logged


def test_a_batch_never_crosses_a_policy_boundary():
    """Terminology has to be consistent within the unit relevance is computed over.

    Two calls can legitimately choose two words for one term. Within a policy
    that is a ranking hazard, so a policy's own texts are rendered together and a
    second policy's are never mixed in.
    """

    first = _projection(rule_count=20, provision_key="first", corpus="veterinary")
    second = _projection(rule_count=20, provision_key="second", corpus="procurement")

    _outcome, _search, client = _rebuild([first, second])

    veterinary = {sentence.split()[1] for sentence in CORPORA["veterinary"]}
    procurement = {sentence.split()[1] for sentence in CORPORA["procurement"]}
    for batch in client.batches:
        blob = " ".join(batch.values())
        touches_first = any(word in blob for word in veterinary)
        touches_second = any(word in blob for word in procurement)
        assert not (touches_first and touches_second), "a batch spanned two policies"


def test_the_manifest_carries_nothing_a_query_could_rank():
    """It has no vector and no retrieval text, so it cannot surface as a policy."""

    _outcome, search, _client = _rebuild([_projection(rule_count=2)])
    manifest = search.final_manifest

    assert "body_vector" not in manifest
    assert manifest["retrieval_text"] == ""
    assert manifest["content_type"] == CONTENT_TYPE_MANIFEST
    assert manifest["id"] == policy_index_manifest_id(_KEY)


def test_a_rendering_failure_never_carries_the_service_reply_outward():
    """A build error is read by an operator, stored, and served by an endpoint.

    Whatever a model deployment puts in a 4xx body — which can quote back part of
    what it was sent — must not travel along that path. What travels is a fixed
    set of fields: the failure class this module chose, the HTTP status, any
    machine token the body yielded, and the size and position of the call. All of
    those are facts about *our request*; none of them can describe a document.
    """

    projection = _projection(rule_count=20, corpus="invented")
    secret = "A drangel exceeding 90 flunes is escalated under protocol ZX-7."
    projection["spans"]["s0"] = {"text": secret}

    class _Exploding:
        async def embed(self, texts):
            return [[0.0, 0.0, 1.0] for _ in texts]

        async def chat(self, messages, **_kwargs):
            raise RuntimeError(
                "Azure OpenAI chat call failed (400): {'error': {'message': "
                f"'the request contained {secret}'}}}}"
            )

    outcome, search, _client = _rebuild([projection], client=_Exploding())

    assert outcome.state == "failed"
    assert outcome.error

    # Nothing of the document, nothing of the reply, not even the exception type.
    for fragment in (
        "drangel",
        "flunes",
        "ZX-7",
        secret,
        "Azure OpenAI chat call failed",
        "RuntimeError",
        # The body's own shape: its quoted keys and its braces.
        "'error'",
        "'message'",
        "{",
        "}",
    ):
        assert fragment not in outcome.error

    # What an operator actually gets: a class, the status, and the shape of the
    # call that failed.
    assert f"class={english_projection.PROJECTION_SERVICE_ERROR}" in outcome.error
    assert "http=400" in outcome.error
    assert "batch=0" in outcome.error
    assert "items=" in outcome.error
    assert "chars=" in outcome.error
    assert search.uploads == []


def test_a_rejected_ready_manifest_is_not_reported_as_a_finished_build():
    """The last write is the one that changes what a query may do, and it is counted.

    A partially-rejected batch comes back as a success with per-document
    statuses. If the ready-manifest were written without checking that, a
    rebuild would report `built` and a current profile while the live index
    still said `incomplete` — a contradiction no repeat rebuild could resolve,
    because each one would report success again while every case kept refusing.
    """

    class _RejectsTheReadyManifest(RecordingSearch):
        async def upload_documents(self, index, documents):
            self.uploads.append(list(documents))
            return {
                "value": [
                    {
                        "key": doc["id"],
                        "status": doc.get("manifest_state") != MANIFEST_READY,
                    }
                    for doc in documents
                ]
            }

    outcome, search, _client = _rebuild(
        [_projection(rule_count=20)], search=_RejectsTheReadyManifest()
    )

    assert outcome.state == "failed"
    assert outcome.projection_profile is None
    assert outcome.manifest_state == MANIFEST_INCOMPLETE
    # It was attempted, and it was not accepted. Both facts are visible.
    assert MANIFEST_READY in [doc["manifest_state"] for doc in search.manifests]


def test_a_rejected_incomplete_manifest_is_not_reported_as_written():
    """`manifest_state` on the outcome says what is in the index, not what was sent."""

    class _RejectsEverything(RecordingSearch):
        async def upload_documents(self, index, documents):
            self.uploads.append(list(documents))
            return {"value": [{"key": doc["id"], "status": False} for doc in documents]}

    outcome, _search, _client = _rebuild(
        [_projection(rule_count=2)], search=_RejectsEverything()
    )

    assert outcome.state == "failed"
    assert outcome.manifest_state is None
    assert outcome.projection_profile is None


class SeededIndex(RecordingSearch):
    """An index that already holds a finished corpus and a `ready` manifest.

    The state a repair actually runs against. What matters about it is that it
    has something to lose: a rebuild that fails must leave every one of these
    documents where it found it, and must leave the manifest still saying the
    corpus may be read — because it still may.
    """

    def __init__(self, previous: list[dict], *, reject_incomplete=False, reject_ready=False):
        super().__init__(existing_ids=[doc["id"] for doc in previous])
        self.previous = {doc["id"]: dict(doc) for doc in previous}
        self.reject_incomplete = reject_incomplete
        self.reject_ready = reject_ready

    async def upload_documents(self, index, documents):
        self.uploads.append(list(documents))
        value = []
        for doc in documents:
            state = doc.get("manifest_state")
            rejected = (state == MANIFEST_INCOMPLETE and self.reject_incomplete) or (
                state == MANIFEST_READY and self.reject_ready
            )
            value.append(
                {"key": doc["id"], "status": not rejected, "statusCode": 503 if rejected else 201}
            )
            if not rejected:
                self.previous[doc["id"]] = dict(doc)
        return {"value": value}

    async def delete_documents(self, index, ids):
        self.deleted.append(list(ids))
        for doc_id in ids:
            self.previous.pop(doc_id, None)
        return {"value": []}


#: A version that is no longer the active one, so a rebuild at the current
#: version really does supersede everything the seed holds — which is what makes
#: the control case below able to prove the sweep still runs.
_SUPERSEDED_VERSION = "00000000-0000-4000-8000-000000000000"


def _seeded_corpus() -> list[dict]:
    """A finished previous build: its documents and its `ready` manifest.

    Built at a superseded version, because a repair runs against whatever the
    last build left and the interesting case is the one where that is not the
    same set the replacement will write.
    """

    outcome, search, _client = _rebuild(
        [_projection(rule_count=18, version_id=_SUPERSEDED_VERSION)], version_number=2
    )
    assert outcome.state == "built"
    documents: dict[str, dict] = {}
    for doc in search.documents:
        documents[doc["id"]] = dict(doc)
    return list(documents.values())


def test_a_rejected_incomplete_manifest_aborts_before_a_single_document_is_written():
    """The state worse than any failure, and the abort that stops it.

    Moving the manifest out of `ready` is what makes a project unmatchable, and
    it has to succeed *before* anything else is touched. If it is rejected and
    the rebuild carries on, the index ends up with a half-written corpus under a
    manifest that still says it may be read — and nothing downstream refuses
    that, because the manifest is the thing downstream asks.

    So: no content upload, no stale sweep, no delete. The previous corpus and the
    previous manifest are byte-for-byte what they were, and the outcome says
    plainly that nothing was built and no projection is claimed.
    """

    previous = _seeded_corpus()
    before = {doc["id"]: dict(doc) for doc in previous}
    search = SeededIndex(previous, reject_incomplete=True)

    outcome, _search, _client = _rebuild([_projection(rule_count=25)], search=search)

    # Nothing was written and nothing was removed.
    assert search.content_writes == [], "content was written after the abort"
    assert search.deleted == [], "the stale sweep ran after the abort"
    assert [doc["manifest_state"] for doc in search.manifests] == [MANIFEST_INCOMPLETE]

    # The index still holds exactly what it held, including a manifest that
    # still says the previous corpus may be read — because it still may.
    assert search.previous == before
    ready = [
        doc
        for doc in search.previous.values()
        if doc["content_type"] == CONTENT_TYPE_MANIFEST
    ]
    assert [doc["manifest_state"] for doc in ready] == [MANIFEST_READY]
    assert [doc["projection_profile"] for doc in ready] == [ENGLISH_PROJECTION_PROFILE]

    # And the outcome is truthful: failed, nothing claimed.
    assert outcome.state == "failed"
    assert outcome.projection_profile is None
    assert outcome.manifest_state is None
    assert outcome.document_count == 0
    assert outcome.error


def test_the_abort_holds_when_the_incomplete_manifest_is_rejected_on_every_attempt():
    """Not a race that resolves itself: a service refusing throughout still aborts."""

    previous = _seeded_corpus()
    before = {doc["id"]: dict(doc) for doc in previous}

    for _attempt in range(3):
        search = SeededIndex(previous, reject_incomplete=True)
        outcome, _search, _client = _rebuild([_projection(rule_count=25)], search=search)
        assert outcome.state == "failed"
        assert outcome.manifest_state is None
        assert search.content_writes == []
        assert search.deleted == []
        assert search.previous == before


def test_the_control_case_still_builds_and_sweeps_when_every_write_is_accepted():
    """The abort is not a rebuild that stopped working.

    The same seeded index, the same replacement corpus, nothing rejected: the
    content is written, the previous version's documents are swept, and the
    manifest ends `ready`. Without this the two tests above would pass against a
    rebuild that never did anything.
    """

    previous = _seeded_corpus()
    search = SeededIndex(previous)

    outcome, _search, _client = _rebuild([_projection(rule_count=25)], search=search)

    assert outcome.state == "built"
    assert outcome.projection_profile == ENGLISH_PROJECTION_PROFILE
    assert outcome.manifest_state == MANIFEST_READY
    assert outcome.rule_document_count == 25
    assert search.content_writes, "the control case wrote nothing"
    assert search.deleted, "the control case swept nothing, so the seed was not superseded"
    assert [doc["manifest_state"] for doc in search.manifests] == [
        MANIFEST_INCOMPLETE,
        MANIFEST_READY,
    ]


def test_a_partial_content_upload_deletes_nothing():
    """A short corpus must not also be a corpus missing its predecessor.

    The completeness check runs before the sweep, so a rebuild that could not
    write everything leaves the previous version's documents alone. They are
    unreachable — the manifest is `incomplete` — and the next successful rebuild
    removes them. Deleting them here would turn one recoverable failure into a
    smaller index.
    """

    previous = _seeded_corpus()

    class _RejectsOneRule(SeededIndex):
        async def upload_documents(self, index, documents):
            self.uploads.append(list(documents))
            value = []
            for position, doc in enumerate(documents):
                ok = not (doc["content_type"] == CONTENT_TYPE_RULE and position == 3)
                value.append(
                    {"key": doc["id"], "status": ok, "statusCode": 201 if ok else 429}
                )
            return {"value": value}

    search = _RejectsOneRule(previous)
    outcome, _search, _client = _rebuild([_projection(rule_count=25)], search=search)

    assert outcome.state == "failed"
    assert outcome.manifest_state == MANIFEST_INCOMPLETE
    assert outcome.projection_profile is None
    assert search.deleted == [], "a partial upload swept the previous corpus"
    assert MANIFEST_READY not in [doc["manifest_state"] for doc in search.manifests]


@pytest.mark.parametrize(
    "entry,accepted",
    [
        ({"key": "k", "status": True}, True),
        ({"key": "k", "status": True, "statusCode": 200}, True),
        ({"key": "k", "status": True, "statusCode": 201}, True),
        ({"key": "k", "status": False}, False),
        ({"key": "k", "status": False, "statusCode": 429}, False),
        ({"key": "k", "status": False, "statusCode": 503}, False),
        # The two fields disagreeing is exactly the case worth reading both for.
        ({"key": "k", "status": True, "statusCode": 429}, False),
        ({"key": "k", "status": True, "statusCode": 503}, False),
        ({"key": "k"}, True),
        ("not a mapping", False),
    ],
)
def test_every_per_document_response_shape_is_read(entry, accepted: bool):
    """A 207 carries a boolean and an HTTP code per document, and both can refuse.

    Reading only one of them would let a throttled or unavailable document be
    counted as written, which is a corpus reported complete while it is short.
    """

    assert _document_was_accepted(entry) is accepted


# ── which documents a reply actually acknowledges ────────────────────


_SUBMITTED = {"a", "b", "c"}


@pytest.mark.parametrize(
    "response,expected,why",
    [
        (None, set(), "no reply at all"),
        ({}, set(), "a reply with no value"),
        ({"value": None}, set(), "a value that is not a list"),
        ({"value": "ok"}, set(), "a value that is a string"),
        ({"value": []}, set(), "an empty value"),
        ({"value": [{"key": "z", "status": True}]}, set(), "a key we did not send"),
        (
            {"value": [{"key": "a", "status": True}, {"key": "a", "status": True}]},
            {"a"},
            "the same key twice is one document",
        ),
        ({"value": [{"status": True}]}, set(), "an entry naming no key"),
        ({"value": [{"key": 7, "status": True}]}, set(), "a key that is not a string"),
        ({"value": ["nonsense", 3, None]}, set(), "entries that are not mappings"),
        (
            {"value": [{"key": "a", "status": True}, {"key": "z", "status": True}]},
            {"a"},
            "one of ours and one that is not",
        ),
        (
            {
                "value": [
                    {"key": "c", "status": True},
                    {"key": "a", "status": True},
                    {"key": "b", "status": True},
                ]
            },
            {"a", "b", "c"},
            "order is the service's business, not ours",
        ),
        (
            {
                "value": [
                    {"key": "a", "status": True},
                    {"key": "b", "status": False, "statusCode": 429},
                    {"key": "c", "status": True},
                ]
            },
            {"a", "c"},
            "a throttled document did not land",
        ),
    ],
)
def test_a_reply_acknowledges_only_the_documents_it_names(response, expected, why: str):
    """Silence is not acknowledgement, and a count is not an acknowledgement either.

    Everything the rebuild guarantees rests on "every expected document landed".
    A count can be reached by the wrong documents — a repeated entry, an entry
    from another request, an entry naming nothing — so what is compared is a set
    of keys against the set that was sent.
    """

    assert _acknowledged_keys(response, _SUBMITTED) == expected, why


def test_a_real_azure_reply_shape_is_read_as_written():
    """The shape the service actually returns, field for field."""

    response = {
        "@odata.context": "https://example.search.windows.net/indexes('ix')/$metadata#Collection(...)",
        "value": [
            {"key": "a", "status": True, "errorMessage": None, "statusCode": 200},
            {"key": "b", "status": True, "errorMessage": None, "statusCode": 201},
            {
                "key": "c",
                "status": False,
                "errorMessage": "The request is throttled.",
                "statusCode": 429,
            },
        ],
    }

    assert _acknowledged_keys(response, _SUBMITTED) == {"a", "b"}


def test_an_unreadable_reply_fails_the_rebuild_rather_than_passing_it():
    """The invariant, end to end: a service that said nothing stamps nothing.

    This is the inversion that mattered. Counting an unreadable reply as a
    batch-sized success would let a rebuild mark a corpus ready on the strength
    of a reply that acknowledged no document at all — and the manifest is written
    through the same counter, so it would be marked ready too.
    """

    class _SaysNothing(RecordingSearch):
        async def upload_documents(self, index, documents):
            self.uploads.append(list(documents))
            return {"value": []}

    outcome, search, _client = _rebuild(
        [_projection(rule_count=20)], search=_SaysNothing()
    )

    assert outcome.state == "failed"
    assert outcome.projection_profile is None
    assert outcome.manifest_state is None
    # It aborted at the first write, so nothing else was attempted.
    assert search.content_writes == []
    assert search.deleted == []


def test_a_reply_that_acknowledges_a_key_it_was_not_sent_does_not_count():
    """A count reached by the wrong documents is not completeness.

    The service is made to answer every upload with one accepted entry naming a
    document from somewhere else. The arithmetic would pass a naive counter — one
    entry per document sent — and the rebuild must still refuse.
    """

    class _NamesSomethingElse(RecordingSearch):
        async def upload_documents(self, index, documents):
            self.uploads.append(list(documents))
            return {
                "value": [
                    {"key": f"not-ours-{position}", "status": True, "statusCode": 201}
                    for position, _doc in enumerate(documents)
                ]
            }

    outcome, search, _client = _rebuild(
        [_projection(rule_count=20)], search=_NamesSomethingElse()
    )

    assert outcome.state == "failed"
    assert outcome.manifest_state is None
    assert search.content_writes == []
    assert search.deleted == []


def test_a_reply_that_repeats_one_acknowledgement_does_not_cover_for_a_missing_one():
    """Two entries, one document. The other one still never landed."""

    projection = _projection(rule_count=20)
    probe, seen, _c = _rebuild([projection])
    content = [d["id"] for d in seen.documents if d["content_type"] != CONTENT_TYPE_MANIFEST]
    assert probe.state == "built"

    class _RepeatsTheFirst(RecordingSearch):
        async def upload_documents(self, index, documents):
            self.uploads.append(list(documents))
            first = documents[0]["id"]
            return {
                "value": [
                    {"key": first, "status": True, "statusCode": 201} for _doc in documents
                ]
            }

    outcome, search, _client = _rebuild([projection], search=_RepeatsTheFirst())

    # The manifest is a batch of one, so it lands; the content batch repeats one
    # key and is therefore one document short of what it claims.
    assert outcome.state == "failed"
    assert outcome.manifest_state == MANIFEST_INCOMPLETE
    assert outcome.projection_profile is None
    assert search.deleted == []
    assert len(content) > 1


def test_a_projection_never_asks_a_deployment_for_more_than_it_accepts():
    """The completion budget is a ceiling, not a function of the input.

    A budget larger than a deployment allows is a `400`; a budget the reply
    exhausts is truncated JSON, which the client refuses outright. Both end the
    rendering, so the way to carry more text is more calls — never a larger ask.
    """

    assert english_projection.PROJECTION_COMPLETION_TOKENS <= 4096
    for source_chars in (1, 500, 6_000, 12_000, 200_000):
        assert (
            english_projection._token_budget(source_chars)
            <= english_projection.PROJECTION_COMPLETION_TOKENS
        )
    # And the batch bounds are set from the ceiling rather than left to chance:
    # one full call's source has to be small enough that its rendering fits.
    assert english_projection.PROJECTION_BATCH_CHARS <= english_projection.PROJECTION_ITEM_CHARS


def test_the_requested_ceiling_is_what_reaches_the_deployment():
    """Asserted on the call, not on the constant."""

    asked: list[int] = []

    class _Recording:
        async def embed(self, texts):
            return [[0.0, 0.0, 1.0] for _ in texts]

        async def chat(self, messages, **kwargs):
            asked.append(kwargs["max_tokens"])
            payload = contained_payload(messages[-1]["content"])
            return json.dumps(payload, ensure_ascii=False)

    outcome, _search, _client = _rebuild(
        [_projection(rule_count=30, corpus="procurement")], client=_Recording()
    )

    assert outcome.state == "built"
    assert asked, "no rendering call was made"
    assert max(asked) <= english_projection.PROJECTION_COMPLETION_TOKENS


def _words(text: str) -> list[str]:
    """The non-whitespace tokens of a text, in order.

    The unit the projection's splitting actually preserves. Comparing two texts
    this way asserts *whitespace-normalised equivalence*: the same words in the
    same order, however they were spaced. Byte-exact concatenation is not what
    the splitter offers and asserting it would pin a promise the module does not
    make — see `split_for_rendering`.
    """

    return text.split()


def test_a_text_too_long_for_one_call_is_split_at_whitespace_and_never_mid_token():
    """A rule is rendered whole. What is split is the *call*, not the rule.

    The cut falls on whitespace the text already contains, so no number and no
    identifier — each an unbroken run of non-space characters — can be divided by
    it, and each piece stays checkable against its own source.
    """

    text = " ".join(f"clause {index} states 4{index} units" for index in range(1200))
    assert len(text) > english_projection.PROJECTION_ITEM_CHARS

    parts = english_projection.split_for_rendering(text)

    assert len(parts) > 1
    # Whitespace-normalised equivalence: every word, in order, once. The pieces
    # do **not** concatenate byte-for-byte — the whitespace a cut fell on is
    # consumed by the cut.
    assert [word for part in parts for word in _words(part)] == _words(text)
    assert all(part == part.strip() for part in parts)
    assert all(
        len(part) <= english_projection.PROJECTION_ITEM_CHARS for part in parts
    )
    # Every number survives the split intact — none is cut in half.
    assert english_projection._numbers(" ".join(parts)) == english_projection._numbers(text)


def test_the_split_normalises_whitespace_at_a_cut_and_nothing_else():
    """The documented cost, pinned so it stays the documented one — and no larger.

    Two claims, and the second is the one that keeps the first from being read as
    "the projection reflows the text":

      * the pieces do **not** concatenate byte-for-byte, because the whitespace a
        cut lands on is consumed by the cut; and
      * every piece is a byte-exact **substring** of the source, so whitespace
        inside a piece — a blank line, a run of spaces — survives untouched.

    Nothing is rewritten; the text is only sliced. Stating it this way is what
    stops a later reader building on an exactness the splitter never had, and it
    costs nothing: retrieval text is tokenised before it is matched, and no
    citation resolves to a projection.
    """

    filler = " ".join(f"term{index} 8{index} units" for index in range(1500))
    text = f"{filler}\n\nsecond  paragraph   with 42 spaced   words\n{filler}"

    parts = english_projection.split_for_rendering(text)
    assert len(parts) > 1

    # Nothing is rewritten: each piece is lifted verbatim out of the source.
    for part in parts:
        assert part in text

    rejoined = "\n".join(parts)
    # Equivalent word-for-word, and every quantity and code intact...
    assert _words(rejoined) == _words(text)
    assert english_projection._numbers(rejoined) == english_projection._numbers(text)
    assert english_projection._identifiers(rejoined) == english_projection._identifiers(text)
    # ...and deliberately not byte-for-byte, which is the mismatch this pins.
    assert rejoined != text
    # The difference is only at the cuts: the source's own runs of spaces are
    # still there, inside the pieces that carry them.
    assert "spaced   words" in rejoined


def test_a_run_with_no_whitespace_is_carried_whole_rather_than_cut():
    """Cutting inside an unbroken run would divide a quantity and corrupt it.

    A slightly over-large call is the honest answer to a pathological input; a
    silently halved number is not.
    """

    solid = "9" * (english_projection.PROJECTION_ITEM_CHARS + 2_000)
    assert english_projection.split_for_rendering(solid) == [solid]


def test_a_long_policy_is_rendered_in_several_calls_and_reassembled_in_order():
    """Multi-batch reconstruction: every key back, whole, and in its own order.

    The stub returns each value with its own marker appended, so a piece that
    came back under the wrong key, in the wrong order, or not at all is visible
    in the reassembled text rather than hidden by it.

    Compared word-for-word rather than byte-for-byte, because the reassembly
    normalises whitespace at each cut — see `split_for_rendering`.
    """

    long_rule = " ".join(f"row {index} allows 3{index} units" for index in range(900))
    short_rule = "A short clause allowing 7 units."
    items = [("policy", long_rule), ("rule-0", short_rule), ("rule-1", long_rule)]
    calls: list[dict] = []

    class _Marking:
        async def chat(self, messages, **kwargs):
            payload = contained_payload(messages[-1]["content"])
            calls.append(payload)
            return json.dumps(
                {key: f"{value} <<{len(calls)}>>" for key, value in payload.items()},
                ensure_ascii=False,
            )

    rendered = _run(
        english_projection.project_texts_to_english(
            items, settings=_settings(), openai_client=_Marking()
        )
    )

    assert len(calls) > 1, "the fixture did not exercise more than one call"
    assert set(rendered) == {"policy", "rule-0", "rule-1"}

    for key, source in items:
        stripped = re.sub(r" <<\d+>>", "", rendered[key])
        assert _words(stripped) == _words(source), f"{key} did not reassemble to its source"

    # The short item was never split; the long ones were.
    assert "<<" in rendered["rule-0"]
    assert rendered["rule-0"].count("<<") == 1
    assert rendered["policy"].count("<<") > 1


def test_a_piece_that_does_not_come_back_fails_the_whole_text():
    """A partly rendered passage is not a rendering, and is not stamped as one."""

    long_rule = " ".join(f"row {index} allows 3{index} units" for index in range(900))

    class _DropsAPiece:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, **kwargs):
            self.calls += 1
            payload = contained_payload(messages[-1]["content"])
            if self.calls > 1:
                # A reply missing one of the keys it was given.
                payload = dict(list(payload.items())[1:]) or {"t0": ""}
            return json.dumps(payload, ensure_ascii=False)

    with pytest.raises(english_projection.EnglishProjectionError):
        _run(
            english_projection.project_texts_to_english(
                [("policy", long_rule)], settings=_settings(), openai_client=_DropsAPiece()
            )
        )


def test_the_batch_bounds_carry_a_whole_rule_without_cutting_it():
    """A rule at the index's own per-rule ceiling is still rendered as one rule.

    It may take more than one call — that is what splitting the call is for — but
    it is never shortened, and what comes back is every word of it in order.
    """

    from policy_platform.infrastructure.search.policy_index import _MAX_RULE_TEXT_CHARS

    rule = " ".join(f"term{index} 5{index} units" for index in range(2000))[
        :_MAX_RULE_TEXT_CHARS
    ]
    parts = english_projection.split_for_rendering(rule)

    assert [word for part in parts for word in _words(part)] == _words(rule)
    assert english_projection._numbers("\n".join(parts)) == english_projection._numbers(rule)
    assert english_projection._identifiers("\n".join(parts)) == english_projection._identifiers(
        rule
    )


# ── budget failures: classified, then answered by sending less ───────


_TRUNCATED_REPLY = (
    "Azure OpenAI returned truncated JSON: the response hit the "
    "max_completion_tokens budget (4096) mid-object "
    "(completion_tokens=4096, content_chars=9182). Retry with a larger "
    "max_tokens value or a smaller input batch."
)
_EMPTY_BUDGET_REPLY = (
    "Azure OpenAI returned empty content: the reasoning model consumed the "
    "entire max_completion_tokens budget (4096) on hidden reasoning "
    "(reasoning_tokens=4096) before producing visible output. Retry with a "
    "larger max_tokens value."
)
_CONTENT_FILTER_REPLY = (
    'Azure OpenAI chat call failed (400): {"error": {"code": "content_filter", '
    '"message": "The response was filtered because of the prompt: a clause about '
    'berthing tariffs at quay 14", "innererror": {"code": "ResponsibleAIPolicyViolation", '
    '"content_filter_result": {"violence": {"filtered": true, "severity": "medium"}, '
    '"hate": {"filtered": false, "severity": "safe"}}}}}'
)


@pytest.mark.parametrize(
    "message,kind,http,code,category",
    [
        (_TRUNCATED_REPLY, english_projection.PROJECTION_TRUNCATED, None, None, None),
        (_EMPTY_BUDGET_REPLY, english_projection.PROJECTION_EMPTY_BUDGET, None, None, None),
        (
            _CONTENT_FILTER_REPLY,
            english_projection.PROJECTION_SERVICE_ERROR,
            400,
            "content_filter",
            "violence",
        ),
        (
            'Azure OpenAI chat call failed (429): {"error": {"code": "rate_limit_exceeded"}}',
            english_projection.PROJECTION_SERVICE_ERROR,
            429,
            "rate_limit_exceeded",
            None,
        ),
        (
            "Azure OpenAI chat call failed (401): not json at all, just prose",
            english_projection.PROJECTION_SERVICE_ERROR,
            401,
            None,
            None,
        ),
        # The shape that matters most in practice: a content-filter refusal whose
        # body the client cut at 500 characters, so it never parses. The code and
        # the category are still recoverable by field name — and the sentence
        # between them is not.
        (
            'Azure OpenAI chat call failed (400): {"error": {"code": "content_filter", '
            '"message": "The response was filtered due to the prompt triggering our '
            "content management policy for a clause about berthing tariffs at quay 14 "
            "and the surrounding para",
            english_projection.PROJECTION_SERVICE_ERROR,
            400,
            "content_filter",
            None,
        ),
        (
            'Azure OpenAI chat call failed (400): {"error": {"message": "filtered", '
            '"innererror": {"content_filter_result": {"self_harm": {"filtered": true, '
            '"severity": "medium"}, "hate": {"filtered": false, "sever',
            english_projection.PROJECTION_SERVICE_ERROR,
            400,
            None,
            "self_harm",
        ),
        ("something else entirely", english_projection.PROJECTION_SERVICE_ERROR, None, None, None),
    ],
)
def test_a_service_failure_is_classified_without_repeating_what_it_said(
    message: str, kind: str, http, code, category
):
    """The class, the status and any machine token — and nothing else.

    The content-filter case is the sharp one: its body quotes the request back,
    including the document's own subject. The category comes through because it
    is a machine token; the sentence beside it does not, because it is a
    sentence.
    """

    failure = english_projection.classify_projection_failure(
        RuntimeError(message), items=4, chars=2_400, ordinal=2
    )

    assert failure.kind == kind
    assert failure.http_status == http
    assert failure.service_code == code
    assert failure.content_filter_category == category

    rendered = str(failure)
    assert "batch=2" in rendered and "items=4" in rendered and "chars=2400" in rendered
    # Not one word of the body's prose.
    for fragment in ("berthing", "tariffs", "quay", "The response was filtered", "message"):
        assert fragment not in rendered


def test_a_timeout_is_told_apart_from_a_refusal():
    """Retrying is the transport's business and it already did; size is not the cause."""

    failure = english_projection.classify_projection_failure(
        TimeoutError("read timed out"), items=1, chars=900, ordinal=0
    )
    assert failure.kind == english_projection.PROJECTION_TIMEOUT
    assert failure.is_over_budget is False


def test_only_a_budget_failure_is_answered_by_sending_less():
    assert english_projection.ProjectionFailure(
        kind=english_projection.PROJECTION_TRUNCATED, items=1, chars=1, ordinal=0
    ).is_over_budget
    assert english_projection.ProjectionFailure(
        kind=english_projection.PROJECTION_EMPTY_BUDGET, items=1, chars=1, ordinal=0
    ).is_over_budget
    for kind in (
        english_projection.PROJECTION_TIMEOUT,
        english_projection.PROJECTION_SERVICE_ERROR,
        english_projection.PROJECTION_UNREADABLE,
        english_projection.PROJECTION_UNFAITHFUL,
    ):
        assert not english_projection.ProjectionFailure(
            kind=kind, items=1, chars=1, ordinal=0
        ).is_over_budget


class _RefusesLargeBatches:
    """A service that refuses any call carrying more than `limit` items.

    The behaviour a real deployment showed: a batch that is too much comes back
    as truncated JSON rather than as an error the transport raises. Everything
    small enough is rendered faithfully.
    """

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.calls: list[int] = []
        self.refusals = 0

    async def embed(self, texts):
        return [[0.0, 0.0, 1.0] for _ in texts]

    async def chat(self, messages, **_kwargs):
        payload = contained_payload(messages[-1]["content"])
        self.calls.append(len(payload))
        if len(payload) > self.limit:
            self.refusals += 1
            raise RuntimeError(_TRUNCATED_REPLY)
        return json.dumps(payload, ensure_ascii=False)


def test_a_batch_refused_for_budget_is_split_rather_than_repeated():
    """The same call again is asking and hoping. A smaller call is a different question.

    Six items, a service that takes at most two. The batch is halved, and halved
    again, until every piece is rendered — and no call is ever made twice with
    the same contents.
    """

    items = [(f"k{index}", f"clause {index} allows 4{index} units.") for index in range(6)]
    client = _RefusesLargeBatches(limit=2)

    rendered = _run(
        english_projection.project_texts_to_english(
            items, settings=_settings(), openai_client=client
        )
    )

    assert set(rendered) == {key for key, _text in items}
    for key, source in items:
        assert rendered[key] == source
    assert client.refusals >= 1, "the fixture never exercised a refusal"
    # Every call is strictly smaller than the one it replaced, and the successful
    # ones are inside what the service takes.
    assert max(client.calls) == 6
    assert all(size <= client.limit for size in client.calls if size <= client.limit)
    assert min(client.calls) >= 1


def test_the_split_is_deterministic_in_order_and_in_keys():
    """The same corpus divides the same way, however many times it is divided."""

    items = [(f"k{index}", f"row {index} permits 7{index} units.") for index in range(6)]

    runs = []
    for _attempt in range(3):
        client = _RefusesLargeBatches(limit=2)
        rendered = _run(
            english_projection.project_texts_to_english(
                items, settings=_settings(), openai_client=client
            )
        )
        runs.append((list(rendered), client.calls))

    assert all(run == runs[0] for run in runs)
    # And the keys come back in the order they were given, not the order they
    # happened to be rendered in.
    assert runs[0][0] == [key for key, _text in items]


def test_a_single_piece_that_is_still_refused_is_a_refusal_and_not_a_loop():
    """There is nothing smaller to send, so the honest answer is no answer.

    The failure names the class and the size of the call. It does not name the
    text, and it does not retry forever looking for a size that does not exist.
    """

    client = _RefusesLargeBatches(limit=0)
    items = [("only", "A single short clause allowing 5 units.")]

    with pytest.raises(english_projection.EnglishProjectionError) as raised:
        _run(
            english_projection.project_texts_to_english(
                items, settings=_settings(), openai_client=client
            )
        )

    message = str(raised.value)
    assert english_projection.PROJECTION_TRUNCATED in message
    assert "items=1" in message
    assert "nothing smaller to send" in message
    assert "clause" not in message and "units" not in message
    # One call per attempt at that size, and no unbounded retry.
    assert len(client.calls) <= 2


def test_a_non_budget_refusal_is_not_answered_by_splitting():
    """Splitting is the answer to "too large", not to "no".

    A service refusing on other grounds is refused back after the existing
    retry — the batch is not divided in the hope that a smaller version is
    somehow allowed.
    """

    calls: list[int] = []

    class _AlwaysRefuses:
        async def embed(self, texts):
            return [[0.0, 0.0, 1.0] for _ in texts]

        async def chat(self, messages, **_kwargs):
            calls.append(len(contained_payload(messages[-1]["content"])))
            raise RuntimeError(
                'Azure OpenAI chat call failed (403): {"error": {"code": "access_denied"}}'
            )

    items = [(f"k{index}", f"clause {index}.") for index in range(6)]

    with pytest.raises(english_projection.EnglishProjectionError) as raised:
        _run(
            english_projection.project_texts_to_english(
                items, settings=_settings(), openai_client=_AlwaysRefuses()
            )
        )

    assert "code=access_denied" in str(raised.value)
    assert "http=403" in str(raised.value)
    # The existing two attempts at the original size, and no halving beyond them.
    assert calls == [6, 6]


def test_search_being_unconfigured_is_a_skip_and_not_a_claimed_projection():
    """A build that never ran claims nothing — not a profile, not a manifest."""

    outcome = _run(
        rebuild_project_policy_index(
            policy_set_key=_KEY,
            version_number=1,
            projections=[_projection(rule_count=2)],
            settings=_settings(search_enabled=False),
        )
    )
    assert outcome.state == "skipped"
    assert outcome.projection_profile is None
    assert outcome.manifest_state is None
