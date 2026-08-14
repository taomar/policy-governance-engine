"""Conjoined verbs over one object are one rule, and over several are several.

One sentence — "…it is essential for the staff members to read, understand, and
comply with the policies" — arrived as three records differing only in predicate.
A judge reading that sentence makes ONE decision: did the staff member read,
understand and comply. Three records create three decisions where the document
made one, and a reviewer approves the same provision three times.

The discriminator is structural and needs no vocabulary: conjoined verbs over one
object are one rule; conjoined verbs over different objects are several. Both
directions matter equally, so the central fixture here is the one real passage
that carries both shapes at once. A change that collapsed its five duties would
look like an improvement in every count this platform reports.
"""

from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    CanonicalPolicyRule,
    PolicyFormulation,
)
from policy_platform.infrastructure.extraction.formulation_mapping import (
    _conjoined_predicate,
    _normalised_subject,
    compound_predicate_merges,
    formulation_to_candidate_rules,
)

#: The provision the owner reported, quoted from the GMU staff handbook.
STAFF = (
    "In order to ensure a safe and productive work environment, it is essential "
    "for the staff members to read, understand, and comply with the policies, as "
    "well as all applicable laws and regulations."
)

#: The control. Five verbs over five objects, then three verbs over one object,
#: in one passage. Nothing else in the corpus catches a change that gets one
#: direction right and the other wrong.
SUPERVISOR = (
    "The employee's supervisor will discuss the work rules, show the work area, "
    "introduce key people, review the probationary report, and make known the "
    "safety regulations. The supervisor will introduce, orient and integrate the "
    "new employee to his/her new work situation."
)


def _policy(source: str, **fields) -> CanonicalPolicy:
    return CanonicalPolicy(
        source_text=source,
        rule=CanonicalPolicyRule(rule_type="obligation", **fields),
    )


def _staff_records() -> list[CanonicalPolicy]:
    return [
        _policy(STAFF, subject="the staff members", modality="must", predicate=verb,
                object="the policies, as well as all applicable laws and regulations")
        for verb in ("read", "understand", "comply with")
    ]


def _supervisor_records() -> list[CanonicalPolicy]:
    duties = [
        ("discuss", "the work rules"),
        ("show", "the work area"),
        ("introduce", "key people"),
        ("review", "the probationary report"),
        ("make known", "the safety regulations"),
    ]
    records = [
        _policy(SUPERVISOR, subject="The employee's supervisor", modality="must",
                predicate=verb, object=thing)
        for verb, thing in duties
    ]
    records += [
        _policy(SUPERVISOR, subject="the supervisor", modality="must", predicate=verb,
                object="the new employee to his/her new work situation")
        for verb in ("introduce", "orient", "integrate")
    ]
    return records


class TestTheReportedProvision:
    def test_three_records_become_one(self):
        """The defect itself: one sentence, one decision, one record."""

        merged, absorbed = compound_predicate_merges(_staff_records())

        assert len(merged) == 1
        assert len(absorbed) == 2

    def test_the_predicate_is_the_document_s_own_words(self):
        """Including the source's comma and coordinator. Nothing is composed."""

        merged, _ = compound_predicate_merges(_staff_records())

        assert list(merged.values()) == ["read, understand, and comply with"]

    def test_the_wording_is_a_literal_slice_of_the_sentence(self):
        """The strongest statement of the verbatim rule that can be asserted."""

        merged, _ = compound_predicate_merges(_staff_records())

        assert next(iter(merged.values())) in STAFF


class TestTheControlPassage:
    """Both directions, in one passage, so neither can be won by losing the other."""

    def test_five_duties_over_five_objects_stay_five(self):
        """Merging these would destroy five obligations the document states."""

        merged, absorbed = compound_predicate_merges(_supervisor_records())

        kept = [index for index in range(5) if index not in absorbed]
        assert kept == [0, 1, 2, 3, 4]
        assert not any(index in merged for index in range(1, 5))

    def test_three_verbs_over_one_object_become_one(self):
        """And the same pass still finds the shape it is here for."""

        merged, absorbed = compound_predicate_merges(_supervisor_records())

        assert absorbed == {6, 7}
        assert merged == {5: "introduce, orient and integrate"}

    def test_the_passage_goes_from_eight_records_to_six(self):
        records = _supervisor_records()

        _, absorbed = compound_predicate_merges(records)

        assert len(records) - len(absorbed) == 6

    def test_two_spellings_of_one_party_are_not_pooled(self):
        """Load-bearing, and it looks like a miss.

        A normaliser that merged "the employee's supervisor" with "the
        supervisor" would pool all eight records of this passage into one group.
        That group varies in object, so it would be refused — and the compound
        predicate sitting inside it would never be found. Normalising harder
        would trade a naming fix for the shape this module exists to detect.
        """

        assert _normalised_subject("The employee's supervisor") == "employee supervisor"
        assert _normalised_subject("the supervisor") == "supervisor"


class TestWhatIsRefused:
    def test_a_varying_selector_means_several_cases_not_one_rule(self):
        """A ladder: the same act under different conditions is several rules."""

        rungs = [
            _policy("A device is repaired or replaced.", subject="the device",
                    modality="must", predicate="be repaired", object="the device",
                    condition="if under warranty"),
            _policy("A device is repaired or replaced.", subject="the device",
                    modality="must", predicate="be replaced", object="the device",
                    condition="if beyond economic repair"),
        ]

        assert compound_predicate_merges(rungs) == ({}, set())

    def test_a_second_varying_field_would_cost_the_document_its_words(self):
        """Measured, and it is why the shipped rule is stricter than proposed.

        "misuse any equipment" and "use any equipment without authorization" are
        two records whose constraint differs. One conjoined predicate can carry
        only one constraint, so merging must either drop "without authorization"
        or apply it to "misuse" as well. Discarding what the document wrote is
        the same defect as inventing what it did not.
        """

        pair = [
            _policy("Employees may not use or misuse any equipment of the University.",
                    subject="employees", modality="must not", predicate="use",
                    object="any equipment", constraint="without authorization"),
            _policy("Employees may not use or misuse any equipment of the University.",
                    subject="employees", modality="must not", predicate="misuse",
                    object="any equipment"),
        ]

        assert compound_predicate_merges(pair) == ({}, set())

    def test_conjoined_verbs_over_different_objects_are_still_two_duties(self):
        """The hardest case for the rule, and the one the control cannot reach.

        On the supervisor passage the five duties are saved by the verbatim
        check alone: its verbs are separated by their own objects rather than by
        a coordinator, so no conjoined run exists to find. Here the source really
        does write "read and sign", and only the objects tell the two duties
        apart. Reading the policy and signing the agreement are two decisions.
        """

        pair = [
            _policy("Employees must read and sign the policy and the agreement.",
                    subject="employees", modality="must", predicate="read",
                    object="the policy"),
            _policy("Employees must read and sign the policy and the agreement.",
                    subject="employees", modality="must", predicate="sign",
                    object="the agreement"),
        ]

        assert compound_predicate_merges(pair) == ({}, set())

    def test_verbs_the_source_never_conjoined_are_left_alone(self):
        """Both verbs are in the sentence; the document did not write them as a list."""

        apart = [
            _policy("Staff must read the policies. Separately, staff must comply with the policies.",
                    subject="staff", modality="must", predicate="read", object="the policies"),
            _policy("Staff must read the policies. Separately, staff must comply with the policies.",
                    subject="staff", modality="must", predicate="comply with", object="the policies"),
        ]

        assert compound_predicate_merges(apart) == ({}, set())

    def test_an_empty_object_cannot_witness_one_object(self):
        """Punching in and punching out are two duties, not one compound duty."""

        clock = [
            _policy("Employees punch in and punch out.", subject="employees",
                    modality="must", predicate="punch in"),
            _policy("Employees punch in and punch out.", subject="employees",
                    modality="must", predicate="punch out"),
        ]

        assert compound_predicate_merges(clock) == ({}, set())

    def test_the_same_predicate_twice_is_a_duplicate_and_a_different_question(self):
        twice = [
            _policy("The supervisor will introduce the new employee.", subject="the supervisor",
                    modality="must", predicate="introduce", object="the new employee"),
            _policy("The supervisor will introduce the new employee.", subject="the supervisor",
                    modality="must", predicate="introduce", object="the new employee"),
        ]

        assert compound_predicate_merges(twice) == ({}, set())

    def test_a_head_word_is_not_enough_to_match_a_verb(self):
        """"comply with" is looked for whole.

        An earlier attempt keyed on the last word of each predicate and rejected
        the owner's own example, because the head of "comply with" is "with".
        """

        assert _conjoined_predicate(["read", "comply with"], "staff read and comply with the rules") == (
            "read and comply with"
        )


class TestTheRecordsThatComeOut:
    """Through the mapper itself, because that is where the fix has to bite."""

    @staticmethod
    def _rules(policies):
        return formulation_to_candidate_rules(
            PolicyFormulation(canonical_policies=policies),
            policy_set_id="test-set",
            extraction_run_id="test-run",
            deployment_name="test",
            prompt_version="test",
            parser_version="test",
        )

    def test_the_reported_sentence_yields_one_record_carrying_all_three_verbs(self):
        rules, _ = self._rules(_staff_records())

        assert len(rules) == 1
        assert rules[0].formulation.canonical.rule.predicate == "read, understand, and comply with"

    def test_the_folded_records_are_not_counted_as_declined_passages(self):
        """They are not skipped: their words survive in the conjoined predicate.

        Recording them as skips would tell a reviewer the extraction declined two
        passages of a document it in fact carried in full.
        """

        _, skipped = self._rules(_staff_records())

        assert skipped == []

    def test_the_control_passage_still_yields_six_records(self):
        rules, _ = self._rules(_supervisor_records())

        predicates = sorted(
            (rule.formulation.canonical.rule.predicate or "") for rule in rules
        )
        assert len(rules) == 6
        assert "introduce, orient and integrate" in predicates
        assert "make known" in predicates
