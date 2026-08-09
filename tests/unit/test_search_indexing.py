from policy_platform.infrastructure.search.indexing import clause_search_document_id


def test_clause_search_document_id_matches_index_key_contract():
    assert (
        clause_search_document_id("document-version-id", "clause-id")
        == "document-version-id_clause-id"
    )
