from policy_platform.infrastructure.search.indexing import clause_search_document_id


def test_clause_search_document_id_matches_index_key_contract():
    # Pinned deliberately: the web client derives this same key in
    # apps/web/src/ruleIdentity.ts to show Search provenance on rule JSON, and
    # cannot import this function. Changing the format here silently breaks
    # that derivation, so treat this assertion as a cross-language contract
    # rather than a restatement of the implementation.
    assert (
        clause_search_document_id("document-version-id", "clause-id")
        == "document-version-id_clause-id"
    )
