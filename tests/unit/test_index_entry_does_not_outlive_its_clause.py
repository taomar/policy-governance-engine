"""An index entry must not outlive what it points at.

The search index is keyed by `{document_version_id}_{clause_id}`. Re-extracting
a version replaces its clause rows with new identifiers, so the previous run's
keys stop pointing at anything. These tests hold the rule that writing the
index reconciles it: after a write, no entry under that version survives
without a clause behind it.

Everything here runs against a fake search client. The rule is about which keys
are removed, and that does not need a search service to state or to check.
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from policy_platform.infrastructure.search.indexing import clause_search_document_id
from policy_platform.infrastructure.search.reconciliation import (
    IndexReconciliation,
    live_keys_for_version,
    orphaned_keys,
    reconcile_version_index,
)


class FakeSearchClient:
    """Records what it was asked to look at and delete.

    Deliberately not a mock: the assertions are about the keys that survive, so
    the fake holds a real set of documents and applies the deletions to it.
    """

    def __init__(self, documents: dict[str, str]):
        # key -> document_version it belongs to
        self.documents = dict(documents)
        self.filters_seen: list[str] = []
        self.delete_calls: list[list[str]] = []
        self.uploads: list[str] = []

    async def upload_documents(self, index: str, documents: list[dict]) -> dict:
        for doc in documents:
            self.uploads.append(doc["id"])
            self.documents[doc["id"]] = doc["document_version"]
        return {"value": []}

    async def find_ids_by_filter(self, index: str, *, filter_expr: str) -> list[str]:
        self.filters_seen.append(filter_expr)
        version = filter_expr.split("'")[1]
        return sorted(key for key, owner in self.documents.items() if owner == version)

    async def delete_documents(self, index: str, ids: list[str]) -> dict:
        self.delete_calls.append(list(ids))
        for key in ids:
            self.documents.pop(key, None)
        return {"value": []}


def _run(coro):
    return asyncio.run(coro)


def test_an_entry_whose_clause_is_gone_is_removed():
    """The defect: re-extraction replaces clause rows, leaving the old keys behind."""

    version = str(uuid4())
    surviving_clause = str(uuid4())
    departed_clause = str(uuid4())

    surviving_key = clause_search_document_id(version, surviving_clause)
    orphan_key = clause_search_document_id(version, departed_clause)

    client = FakeSearchClient({surviving_key: version, orphan_key: version})

    outcome = _run(
        reconcile_version_index(
            client,
            "policy-authoring",
            document_version_id=version,
            clause_ids=[surviving_clause],
        )
    )

    assert outcome.examined == 2, (
        "the sweep must read the entries it is judging; "
        f"expected to examine 2 entries, examined {outcome.examined}"
    )
    assert outcome.removed == (orphan_key,), (
        "expected exactly the entry with no clause behind it to be removed; "
        f"removed {outcome.removed}"
    )
    assert surviving_key in client.documents, "the live clause's entry must survive"
    assert orphan_key not in client.documents, (
        "an index entry outlived the clause it points at"
    )


def test_a_version_whose_entries_all_still_have_clauses_is_left_alone():
    """No deletion call at all when there is nothing to reconcile."""

    version = str(uuid4())
    clauses = [str(uuid4()) for _ in range(3)]
    documents = {clause_search_document_id(version, c): version for c in clauses}
    client = FakeSearchClient(documents)

    outcome = _run(
        reconcile_version_index(
            client,
            "policy-authoring",
            document_version_id=version,
            clause_ids=clauses,
        )
    )

    assert outcome.examined == 3, (
        f"expected to examine 3 entries, examined {outcome.examined}"
    )
    assert outcome.removed == ()
    assert client.delete_calls == [], "nothing to remove, so nothing should be deleted"
    assert len(client.documents) == 3


def test_another_version_is_not_touched():
    """The sweep is scoped to one version and must not reach across."""

    ours = str(uuid4())
    theirs = str(uuid4())
    our_clause = str(uuid4())
    their_clause = str(uuid4())

    our_orphan = clause_search_document_id(ours, str(uuid4()))
    their_key = clause_search_document_id(theirs, their_clause)

    client = FakeSearchClient(
        {
            clause_search_document_id(ours, our_clause): ours,
            our_orphan: ours,
            their_key: theirs,
        }
    )

    outcome = _run(
        reconcile_version_index(
            client,
            "policy-authoring",
            document_version_id=ours,
            clause_ids=[our_clause],
        )
    )

    assert outcome.removed == (our_orphan,)
    assert their_key in client.documents, (
        "a sweep of one version removed an entry belonging to another"
    )
    assert client.filters_seen == [f"document_version eq '{ours}'"], (
        f"expected the query to be scoped to one version, got {client.filters_seen}"
    )


def test_an_empty_index_is_reported_as_empty_not_as_clean():
    """A sweep that read nothing must say so rather than report success.

    `examined` exists precisely so absence of evidence and evidence of absence
    do not render identically.
    """

    version = str(uuid4())
    client = FakeSearchClient({})

    outcome = _run(
        reconcile_version_index(
            client,
            "policy-authoring",
            document_version_id=version,
            clause_ids=[str(uuid4())],
        )
    )

    assert outcome.examined == 0
    assert outcome.removed == ()
    assert isinstance(outcome, IndexReconciliation)


def test_the_rule_itself_sees_a_difference():
    """Guard the comparison, not just the plumbing around it."""

    assert orphaned_keys(["a", "b"], ["a"]) == ("b",)
    assert orphaned_keys(["a"], ["a", "b"]) == ()
    assert orphaned_keys([], ["a"]) == ()
    assert orphaned_keys(["b", "a"], []) == ("a", "b"), "result should be ordered"


def test_the_keys_the_store_entitles_a_version_to_match_the_writer():
    """The sweep and the writer must derive keys the same way.

    If these drift, the sweep deletes live entries or spares stale ones, and
    both failures are silent.
    """

    version = str(uuid4())
    clause = uuid4()  # deliberately not a string: the writer stringifies too

    assert live_keys_for_version(version, [clause]) == (
        clause_search_document_id(version, str(clause)),
    )


def test_the_writer_reconciles_after_it_writes(monkeypatch):
    """The wiring, not just the capability, and asserted by behaviour.

    A reconciler nothing calls is the defect this repository has found
    repeatedly. An earlier version of this test asserted that the writer's
    source mentioned the reconciler; that passed with the call removed, because
    the import line still carried the name. So this drives the real write path
    and asserts the sweep actually happened.
    """

    from types import SimpleNamespace

    from policy_platform.infrastructure.search import indexing

    version = str(uuid4())
    live_clause = uuid4()
    live_key = clause_search_document_id(version, str(live_clause))
    orphan_key = clause_search_document_id(version, str(uuid4()))

    client = FakeSearchClient({orphan_key: version})

    settings = SimpleNamespace(
        ai_enabled=True,
        search_enabled=True,
        azure_search_authoring_index="policy-authoring",
        azure_openai_embedding_deployment="embed",
        azure_openai_embedding_dimensions=3,
    )

    class FakeOpenAI:
        def __init__(self, _settings):
            pass

        async def embed(self, texts):
            return [[0.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr(indexing, "get_settings", lambda: settings)
    monkeypatch.setattr(indexing, "AzureOpenAIClient", FakeOpenAI)
    monkeypatch.setattr(indexing, "AzureSearchClient", lambda _s: client)

    clause = SimpleNamespace(id=live_clause, text="a clause", clause_ref="1", section="S")

    indexed = _run(
        indexing.index_clauses_best_effort(
            document_title="T",
            document_id=str(uuid4()),
            document_version_id=version,
            version_number=1,
            content_hash="h",
            clauses=[clause],
        )
    )

    assert indexed == 1, f"expected the writer to index 1 clause, it reported {indexed}"
    assert client.uploads == [live_key], (
        f"expected the live clause to be written, wrote {client.uploads}"
    )
    assert client.filters_seen == [f"document_version eq '{version}'"], (
        "the writer did not reconcile the index after writing it; "
        f"queries made: {client.filters_seen}"
    )
    assert orphan_key not in client.documents, (
        "an entry from a superseded run of this same version survived the write"
    )
    assert live_key in client.documents, "the clause just written must remain"


@pytest.mark.parametrize("orphan_count", [1, 5, 40])
def test_every_orphan_is_removed_whatever_the_volume(orphan_count):
    """Scale is not a special case; the rule is a set difference."""

    version = str(uuid4())
    live_clause = str(uuid4())
    documents = {clause_search_document_id(version, live_clause): version}
    orphans = set()
    for _ in range(orphan_count):
        key = clause_search_document_id(version, str(uuid4()))
        documents[key] = version
        orphans.add(key)

    client = FakeSearchClient(documents)
    outcome = _run(
        reconcile_version_index(
            client,
            "policy-authoring",
            document_version_id=version,
            clause_ids=[live_clause],
        )
    )

    assert outcome.examined == orphan_count + 1
    assert set(outcome.removed) == orphans, (
        f"expected {orphan_count} orphans removed, removed {outcome.removed_count}"
    )
    assert set(client.documents) == {clause_search_document_id(version, live_clause)}
