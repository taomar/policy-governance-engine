"""A rule points at its policy; it never carries a second copy of one.

WHY THIS FILE EXISTS

The grouping — which rules form a policy, under which heading chain — is
computed once, by extraction, and persisted. Everything downstream is supposed
to read that one answer. The failure this guards against is subtle and has
already happened once in this repository under a different name: a second path
to the same fact, which agrees with the first on the day it is written and is
free to disagree on any day after.

The flat candidate list and the policy list are two views of one population. It
is legitimate for a candidate to say *which* policy states it. It is not
legitimate for it to say *what that policy is* — the heading chain, the sibling
rules, the passage boundary — because then a client holding both lists has two
answers to one question, and nothing makes them agree once a filter, a
superseded row or a stale cache separates them.

An identity cannot disagree with the thing it identifies. It can only fail to
resolve, and a failure to resolve is visible. That is the whole argument for the
shape asserted here.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from policy_platform.api.schemas import CandidateRuleResponse
from policy_platform.infrastructure.assembly.policy_assembly import (
    AssembledPolicy,
    ProvisionGrouping,
    assemble,
)

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCHEMAS = _ROOT / "src" / "policy_platform" / "api" / "schemas.py"

#: Names that would mean the flat list had started composing a policy rather
#: than pointing at one. Deliberately about structure, not about any document:
#: none of these is a word from a corpus, they are the parts of the grouping.
_COMPOSITION = ("heading", "passage", "rules", "rule_count", "provision_key", "trail")


class TestTheFlatListPointsAndDoesNotCompose:
    def test_a_candidate_carries_the_provision_identity(self):
        """Without this, a client must rebuild the grouping to use it.

        Rebuilding it client-side is the defect: a second opinion on membership,
        free to disagree with the persisted one exactly where it matters.
        """

        assert "provision_id" in CandidateRuleResponse.model_fields

    def test_the_identity_is_optional_because_not_every_rule_has_one(self):
        """A rule extracted before provisions existed still has to be reviewable.

        Required here would make the whole queue unserialisable the moment one
        such row is returned — trading a missing label for a missing queue.
        """

        field = CandidateRuleResponse.model_fields["provision_id"]
        assert not field.is_required()
        assert field.default is None

    @pytest.mark.parametrize("part", _COMPOSITION)
    def test_a_candidate_carries_no_part_of_the_grouping_itself(self, part: str):
        """The composition is served once, by the policy list, or it is not one
        answer.
        """

        for name in CandidateRuleResponse.model_fields:
            if name == "rule":
                continue
            assert part not in name, (
                f"`{name}` puts a second copy of the grouping on the flat list; "
                "send the identity and let the policy list compose"
            )

    def test_the_identity_costs_no_extra_lookup(self):
        """A field that costs a query per row is a field that gets removed.

        `provision_id` is read straight off the row being serialised. This
        asserts the serializer reaches for the column and nothing else — no
        session, no repository, no await — so 692 rules cost 692 attribute
        reads and zero round trips.
        """

        tree = ast.parse(_SCHEMAS.read_text(encoding="utf-8"))
        del tree  # parsed only to prove the file is well-formed for the reader

        source = (
            _ROOT / "src" / "policy_platform" / "api" / "routers" / "candidate_rules.py"
        ).read_text(encoding="utf-8")
        serializer = source.split("def _to_response(")[1].split("\ndef ")[0]
        assert "provision_id=str(candidate.provision_id)" in serializer
        assert "await" not in serializer
        assert "session" not in serializer


class TestThePolicyIsWhatTheReferenceResolvesTo:
    def test_a_persisted_policy_states_which_provision_it_is(self):
        """Otherwise the reference the flat list sends points at nothing the
        client can see, and the client is back to matching headings.
        """

        assert "provision_id" in AssembledPolicy.__dataclass_fields__

    def test_a_fallback_policy_claims_no_provision(self):
        """A read-time grouping is not a persisted one and must not borrow its
        identity. Null here is the honest answer and `persisted` already says
        so; a fabricated id would make an inferred boundary indistinguishable
        from a stored one.
        """

        from tests.unit.test_policy_assembly import _rule  # noqa: PLC0415

        policies = assemble([_rule("R1", "p4-E000012", section="S")])
        assert policies[0].persisted is False
        assert policies[0].provision_id is None

    def test_the_identity_and_the_persisted_flag_never_disagree(self):
        """Two fields describing one fact must not be able to contradict.

        `persisted` is what a reviewer reads; `provision_id` is what a client
        joins on. If one could be set without the other, a policy could claim a
        stored boundary while pointing at nothing, or point at a row while
        reporting itself inferred.
        """

        from tests.unit.test_policy_assembly import _rule  # noqa: PLC0415

        grouping = ProvisionGrouping(
            key="a-key", provision_id="an-id", heading_path=("A heading",)
        )
        rules = [_rule("R1", "p4-E000012", section="S")]
        for provisions in ({}, {"R1": grouping}):
            for policy in assemble(rules, provisions=provisions):
                assert policy.persisted is (policy.provision_id is not None)
