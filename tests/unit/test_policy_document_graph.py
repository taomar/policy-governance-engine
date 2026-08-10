"""Tests for the ``PolicyDocumentGraphV1`` candidate template.

Three properties matter more than field-by-field coverage:

* **tolerance** — one malformed candidate must not destroy the valid ones,
  because dense extraction uses prompt-schema output and partial results are
  expected rather than exceptional;
* **domain neutrality** — a schema tuned to the sample documents would score
  well on them and fail on the next one;
* **identity discipline** — graph identity is bookkeeping and must never look
  like canonical policy identity.
"""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from policy_platform.contracts.policy_document_graph import (
    CANDIDATE_MODELS,
    TEMPLATE_VERSION,
    ApprovalCandidate,
    ConditionCandidate,
    DefinitionCandidate,
    ExceptionCandidate,
    PolicyDocumentGraphV1,
    PolicyUnitCandidate,
    edge_labels,
    validate_candidates,
)


class TestTolerance:
    def test_one_malformed_candidate_does_not_discard_the_others(self) -> None:
        """The failure mode that would turn a small model error into total loss."""

        payloads = [
            {"term": "Eligible Employee", "meaning": "Employed 12 months."},
            {"meaning": "Missing its required term."},
            {"term": "Immediate Family", "meaning": "Spouse, child, parent."},
        ]
        valid, diagnostics = validate_candidates(DefinitionCandidate, payloads)

        assert [c.term for c in valid] == ["Eligible Employee", "Immediate Family"]
        assert len(diagnostics) == 1
        assert "DefinitionCandidate[1]" in diagnostics[0]

    def test_rejections_are_reported_not_swallowed(self) -> None:
        _, diagnostics = validate_candidates(DefinitionCandidate, [{}])
        assert diagnostics and "term" in diagnostics[0]

    def test_non_object_entries_are_rejected_individually(self) -> None:
        valid, diagnostics = validate_candidates(
            DefinitionCandidate, [{"term": "A"}, "not an object", None]
        )
        assert len(valid) == 1
        assert len(diagnostics) == 2

    def test_every_field_except_identity_is_optional(self) -> None:
        """A partially-formed candidate is still useful; a rejected one is not."""

        unit = PolicyUnitCandidate.model_validate({"unit_key": "2.1"})
        assert unit.modality is None
        assert unit.conditions == []
        assert unit.exceptions == []

    def test_unknown_fields_do_not_reject_a_candidate(self) -> None:
        unit = PolicyUnitCandidate.model_validate(
            {"unit_key": "2.1", "some_field_a_model_invented": "x"}
        )
        assert unit.unit_key == "2.1"


class TestIdentityDiscipline:
    @pytest.mark.parametrize("model", CANDIDATE_MODELS)
    def test_every_entity_declares_scalar_identity_fields(self, model: type[BaseModel]) -> None:
        """Docling Graph merges on these, so they must exist and be scalar."""

        config = model.model_config
        assert config.get("is_entity") is True
        id_fields = config.get("graph_id_fields", [])
        assert id_fields, f"{model.__name__} declares no graph_id_fields"
        for name in id_fields:
            assert name in model.model_fields

    def test_identity_keys_are_document_derived_not_generated(self) -> None:
        """The unit key is a printed label or a canonical reference, never a name."""

        description = PolicyUnitCandidate.model_fields["unit_key"].description or ""
        assert "canonical element reference" in description
        assert "Never a generated name" in description

    def test_document_identity_is_not_inferred_from_a_filename(self) -> None:
        """A filename stem looks authoritative while being an artifact of saving."""

        graph = PolicyDocumentGraphV1()
        assert graph.document_reference is None
        assert graph.document_title is None

    def test_template_version_is_recorded_by_default(self) -> None:
        assert PolicyDocumentGraphV1().template_version == TEMPLATE_VERSION


class TestRelationshipFamilies:
    def test_policy_unit_declares_the_required_edge_families(self) -> None:
        labels = set(edge_labels(PolicyUnitCandidate).values())
        assert {
            "APPLIES_TO",
            "CONDITION_OF",
            "EXCEPTION_TO",
            "APPROVAL_FOR",
            "REFERENCES",
            "FOOTNOTE_QUALIFIES",
            "TABLE_CONTEXT_FOR",
        } <= labels

    def test_root_declares_definition_and_containment_edges(self) -> None:
        labels = set(edge_labels(PolicyDocumentGraphV1).values())
        assert "DEFINES" in labels
        assert "CONTAINS" in labels

    def test_edge_metadata_uses_the_documented_convention(self) -> None:
        """Edges are read from json_schema_extra['edge_label'] by the extractor."""

        extra = PolicyUnitCandidate.model_fields["conditions"].json_schema_extra
        assert isinstance(extra, dict)
        assert extra["edge_label"] == "CONDITION_OF"

    def test_list_edges_default_to_empty_not_none(self) -> None:
        """An absent relationship is an absence, not a validation failure."""

        unit = PolicyUnitCandidate(unit_key="1")
        assert unit.conditions == []
        assert unit.approvals == []

    def test_single_edges_default_to_none(self) -> None:
        assert PolicyUnitCandidate(unit_key="1").scope is None


class TestAttachment:
    def test_supporting_material_hangs_off_the_unit_it_governs(self) -> None:
        """A detached exception is misleading, not merely less useful.

        A reader cannot tell which rule an unattached exception modifies.
        """

        unit = PolicyUnitCandidate.model_validate(
            {
                "unit_key": "2.1",
                "conditions": [{"condition_key": "12 months service"}],
                "exceptions": [{"exception_key": "probation"}],
                "approvals": [{"approval_key": "manager sign-off"}],
            }
        )
        assert isinstance(unit.conditions[0], ConditionCandidate)
        assert isinstance(unit.exceptions[0], ExceptionCandidate)
        assert isinstance(unit.approvals[0], ApprovalCandidate)

    def test_duplicates_are_observations_not_merges(self) -> None:
        """Two clauses differing only by a negation are different rules."""

        unit = PolicyUnitCandidate(unit_key="2.1", possible_duplicate_of=["3.4"])
        assert unit.possible_duplicate_of == ["3.4"]
        description = PolicyUnitCandidate.model_fields["possible_duplicate_of"].description or ""
        assert "never a merge" in description


class TestUncertainty:
    def test_unstated_boundary_inclusivity_stays_unset(self) -> None:
        """Guessing turns 'more than 5' into 'at least 5'."""

        condition = ConditionCandidate(condition_key="service length")
        assert condition.boundary_inclusive is None

    def test_unstated_modality_stays_unset(self) -> None:
        assert PolicyUnitCandidate(unit_key="1").modality is None

    @pytest.mark.parametrize("model", CANDIDATE_MODELS)
    def test_candidates_can_record_why_they_may_be_wrong(
        self, model: type[BaseModel]
    ) -> None:
        if model is PolicyDocumentGraphV1:
            pytest.skip("the root is not a candidate")
        assert "uncertainty" in model.model_fields
        assert "anchors" in model.model_fields


class TestEvidenceDiscipline:
    def test_candidates_anchor_by_reference_not_by_quoted_text(self) -> None:
        """A model that never emits evidence text cannot fabricate it."""

        description = DefinitionCandidate.model_fields["anchors"].description or ""
        assert "never evidence text" in description

    def test_quote_hint_is_documented_as_advisory_only(self) -> None:
        description = DefinitionCandidate.model_fields["quote_hint"].description or ""
        assert "never used as evidence" in description


class TestDomainNeutrality:
    #: Subject matter drawn from the sample documents. A schema mentioning any
    #: of these would be tuned to the fixtures rather than to policy documents.
    FORBIDDEN = (
        "leave",
        "maternity",
        "pregnancy",
        "hardware",
        "laptop",
        "incident",
        "severity",
        "security",
        "expense",
        "travel",
        "employee_id",
    )

    @pytest.mark.parametrize("model", CANDIDATE_MODELS)
    def test_no_field_name_encodes_a_subject_domain(self, model: type[BaseModel]) -> None:
        for name in model.model_fields:
            lowered = name.lower()
            for term in self.FORBIDDEN:
                assert term not in lowered, f"{model.__name__}.{name} is domain-specific"

    def test_schema_serializes_for_the_extractor(self) -> None:
        """The template's value is its JSON schema; it must render."""

        schema = PolicyDocumentGraphV1.model_json_schema()
        assert "properties" in schema
        assert "policy_units" in schema["properties"]


def _catalog_available() -> bool:
    try:
        import docling_graph.core.extractors.contracts.dense.catalog  # noqa: F401
    except ImportError:
        return False
    return True


requires_docling_graph = pytest.mark.skipif(
    not _catalog_available(), reason="optional 'graph' extra (docling-graph) is not installed"
)


class TestDoclingGraphCompatibility:
    """Validate the template against the extractor that will actually consume it.

    Asserting our own metadata only proves the template is self-consistent. These
    tests run Docling Graph's real catalog builder, so a schema the extractor
    cannot walk fails here rather than during a live extraction run.
    """

    @requires_docling_graph
    def test_extractor_discovers_every_candidate_path(self) -> None:
        from docling_graph.core.extractors.contracts.dense.catalog import build_node_catalog

        catalog = build_node_catalog(PolicyDocumentGraphV1)
        paths = {node.path for node in catalog.nodes}

        assert {
            "",
            "definitions[]",
            "policy_units[]",
            "policy_units[].scope",
            "policy_units[].conditions[]",
            "policy_units[].exceptions[]",
            "policy_units[].approvals[]",
            "policy_units[].references[]",
            "policy_units[].footnotes[]",
            "policy_units[].tables[]",
            "process_steps[]",
        } <= paths

    @requires_docling_graph
    def test_extractor_reads_the_declared_identity_fields(self) -> None:
        """Docling Graph merges duplicates on these; a missing one merges wrongly."""

        from docling_graph.core.extractors.contracts.dense.catalog import build_node_catalog

        catalog = build_node_catalog(PolicyDocumentGraphV1)
        id_fields = {node.path: node.id_fields for node in catalog.nodes}

        assert id_fields["policy_units[]"] == ["unit_key"]
        assert id_fields["definitions[]"] == ["term"]
        assert all(fields for fields in id_fields.values())

    @requires_docling_graph
    def test_every_candidate_path_is_an_entity_not_an_embedded_component(self) -> None:
        """Components are embedded as dictionaries and get no node of their own.

        An exception embedded in its parent cannot be reviewed, linked, or given
        its own evidence span.
        """

        from docling_graph.core.extractors.contracts.dense.catalog import build_node_catalog

        catalog = build_node_catalog(PolicyDocumentGraphV1)
        assert all(node.kind == "entity" for node in catalog.nodes)

    @requires_docling_graph
    def test_supporting_material_is_filled_before_the_unit_it_governs(self) -> None:
        """Dense extraction fills bottom-up, so attachment depends on this order."""

        from docling_graph.core.extractors.contracts.dense.catalog import (
            bottom_up_path_order,
            build_node_catalog,
        )

        order = bottom_up_path_order(build_node_catalog(PolicyDocumentGraphV1))
        position = {path: index for index, path in enumerate(order)}

        for child in (
            "policy_units[].conditions[]",
            "policy_units[].exceptions[]",
            "policy_units[].approvals[]",
        ):
            assert position[child] < position["policy_units[]"]
        assert position["policy_units[]"] < position[""]
