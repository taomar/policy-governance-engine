"""Phase 1 measurement: every quality check and the route it presupposes.

This module is the recorded inventory, not a detector. It exists so the
analysis behind the route-awareness work survives independently of the fixes,
and so a test can hold the inventory to the suite it describes -- a code added
to a detector later, and not classified here, is caught rather than silently
uninventoried.

THE TWO ROUTES
--------------
A rule is decided by one of two routes, derived from its own shape by
``evaluation_mode_from`` (``contracts/policy.py``):

- ``Deterministic`` -- the engine computes a comparison. Exact verdict. A rule
  reaches this route only when its condition tree holds a comparison and it
  declares the facts that comparison reads.
- ``AI Ready`` -- a judge reads the rule against the case and returns a verdict
  with its confidence. Everything that is not Deterministic is this.

On the live set the judged route is the product, not the exception:
measured 2046 AI Ready against 17 Deterministic across the candidate corpus,
and the same shape (a handful of computed rules against a large judged
majority) holds per policy set. A check written as though every rule were a
computed decomposition is therefore describing the rare case and firing on the
common one.

HOW THIS WAS MEASURED
---------------------
Two stored quality runs were cross-tabulated, each finding joined to the route
of the rule it fired on (the route is derived, and the stored ``evaluation_mode``
was confirmed to equal the derived value for all 2063 candidate rules, so the
stored value was used for the join):

- Candidate run (398 rules, 130 findings, method 3-454a9e5e90d3). Every
  structural finding fell on AI Ready rules; the 17 Deterministic rules drew
  effectively no structural finding. ``decomposition_malformed`` fired 41
  times, all on AI Ready, none on Deterministic. ``not_decidable_as_written``
  fired 49 times, all on AI Ready -- correctly, because it is the AI Ready
  route's own question.
- Published run (9 rules, 8 findings, method 3-454a9e5e90d3) -- the run in the
  report the user is reading. ``decomposition_malformed`` fired once, at high
  severity, on an AI Ready rule. That is the finding whose wording this work
  corrects.

The cross-tabulation shows the corpus is overwhelmingly judged, so *every*
route-blind check fires on AI Ready simply because almost every rule is AI
Ready. Firing on AI Ready is therefore not by itself evidence of a false
positive: the question for each check is whether its *assertion* presupposes a
computed decomposition, not whether its findings happen to land on judged
rules.

WHAT WAS ALREADY RIGHT
----------------------
The subsystem is partly route-aware already, and those places are the pattern
the rest should follow rather than defects to remove:

- ``_runner_fitness_findings`` asks each route its own question:
  ``not_runnable_as_stored`` of a Deterministic record, ``not_decidable_as_written``
  of an AI Ready one. It replaced a single question asked of both populations
  that had reported most records defective for a check that could not apply to
  them.
- ``condition_not_compiled`` is deliberately not reported, because a condition
  stated in words and read by a judge is the ordinary AI Ready outcome, not a
  defect; the same fact is carried route-correctly by ``condition_provenance``.
  It is suppressed as a report, never counted as a silent pass.

THE CATEGORIES
--------------
Each check is classified by what it presupposes, following the task's scheme:

- ``ROUTE_NEUTRAL`` (a): asserts something true of a record on either route --
  a misquoted source, a dropped negation, a fabricated party, an unreadable
  slice. Correct as-is. Several of these matter *more* on AI Ready, where the
  judge sees only the record's own words.
- ``DETERMINISTIC_ONLY_FALSE_POSITIVE`` (b): asserts a property only a computed
  decomposition can have, so firing on an AI Ready rule is a false positive.
  None were found in the current suite: the one historical instance -- the
  single runner-fitness question asked of both routes -- had already been
  split into the route-specific pair below.
- ``WORDING_ASSUMES_A_ROUTE`` (c): a real defect on both routes, but its
  user-facing wording presupposes one route. ``decomposition_malformed`` is
  the one instance: a damaged decomposition is broken however a rule is
  decided, but its detail said the *logic derived from it* cannot be trusted,
  and on an AI Ready rule no logic is derived -- the judge reads the words.
  Fixed by rewording, never by suppressing: suppressing would leave 41 real
  defects unreported on the judged majority.
- ``ROUTE_SPECIFIC`` : correctly asks each route its own question. The
  runner-fitness pair. Not a defect; the model for the seam.
- ``MISSING_FOR_JUDGED`` (d): a failure mode a judged rule has that nothing
  checks. The judged route's own failure modes -- a rule whose words cannot be
  read against a case, a rule whose subject is unresolvable, a slice that
  cannot be read on its own -- are already covered by ``not_decidable_as_written``,
  ``decomposition_malformed`` (empty subject, dangling referent), and
  ``record_does_not_stand_alone``. The gap that remained was structural, not a
  missing detector: the routes a check speaks to were implicit, re-derived
  inside one detector and by omission in another, with no single place to
  declare them and no way to say a check is *not applicable* to a route rather
  than silent about it. That seam is what the fix adds.

The structured ``INVENTORY`` below carries the same classification in a form a
test can read.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RoutePresupposition(str, Enum):
    """The route a check's assertion assumes, independent of where it fires."""

    #: True of a record however it is decided.
    NONE = "none"
    #: Only a computed decomposition can have the asserted property.
    DETERMINISTIC = "deterministic"
    #: Only a judged record can have the asserted property.
    AI_READY = "ai_ready"


class Category(str, Enum):
    """The task's classification of each check."""

    ROUTE_NEUTRAL = "a"
    DETERMINISTIC_ONLY_FALSE_POSITIVE = "b"
    WORDING_ASSUMES_A_ROUTE = "c"
    MISSING_FOR_JUDGED = "d"
    #: Correctly asks each route its own question. Not a defect.
    ROUTE_SPECIFIC = "route_specific"
    #: Raised by the pass but deliberately not carried to the report.
    NOT_REPORTED = "not_reported"


@dataclass(frozen=True)
class CheckRecord:
    """One check, what it asserts, and the route that assertion presupposes."""

    code: str
    module: str
    asserts: str
    presupposes: RoutePresupposition
    category: Category
    note: str = ""


#: Every finding code the four quality modules can emit, with its route
#: presupposition and category. ``snake_case`` (a system-prompt placeholder),
#: ``review_coverage`` and ``review_backlog`` (run-level meta, not per-rule
#: assertions) are omitted; the AI review layer is judged, not a structural
#: check, and is out of this structural inventory.
INVENTORY: tuple[CheckRecord, ...] = (
    # -- ai_quality.py structural detectors -------------------------------
    CheckRecord(
        "duplicate_rule_id", "ai_quality", "no rule_id repeats within a version",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "ambiguity", "ai_quality", "the rule is not flagged blocking-ambiguous",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "expired_rule", "ai_quality", "an active rule has not already expired",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "orphan_exception_fact", "ai_quality",
        "an exception's referenced fact is declared",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
        "reads a fact name, but a dangling reference is a record-integrity "
        "defect on either route",
    ),
    CheckRecord(
        "conflicting_effect", "ai_quality",
        "no two rules of one type both allow and deny one action",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "definition_carries_effect", "ai_quality",
        "a definition rule carries no operative effect",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "degenerate_predicate", "ai_quality", "the predicate is not empty or degenerate",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "eligibility_polarity_inversion", "ai_quality",
        "an eligibility rule's polarity is not inverted",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "duplicate_extraction", "ai_quality", "one sentence was not extracted twice",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "contradictory_reading", "ai_quality",
        "one sentence was not read two contradictory ways",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "unstable_extraction", "ai_quality",
        "two runs read one sentence the same way",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "not_runnable_as_stored", "ai_quality",
        "a Deterministic record's condition names only facts it declares",
        RoutePresupposition.DETERMINISTIC, Category.ROUTE_SPECIFIC,
        "asked only of Deterministic records, by design",
    ),
    CheckRecord(
        "not_decidable_as_written", "ai_quality",
        "an AI Ready record answers a judge's questions from itself",
        RoutePresupposition.AI_READY, Category.ROUTE_SPECIFIC,
        "asked only of judged records, by design; it is the judged route's own "
        "question",
    ),
    CheckRecord(
        "record_does_not_stand_alone", "ai_quality",
        "the record can be read on its own",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
        "more pertinent to AI Ready, where the judge sees only the record",
    ),
    CheckRecord(
        "record_reference_is_opaque", "ai_quality",
        "a reference the record makes can be resolved",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "decision_split_across_records", "ai_quality",
        "a single decision is not split across records",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "qualifier_promoted_to_record", "ai_quality",
        "a qualifier was not promoted to a standalone record",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "invalid_candidate_payload", "ai_quality", "a candidate payload validates",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    # -- policy_faithfulness.py -------------------------------------------
    CheckRecord(
        "negation_dropped", "policy_faithfulness",
        "the record's effect keeps the sentence's negation",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "quantity_dropped", "policy_faithfulness",
        "a figure stated in the sentence is kept",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "source_condition_not_captured", "policy_faithfulness",
        "the record's condition carries what the sentence states",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "action_missing", "policy_faithfulness",
        "the record has the action the sentence requires",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "action_fragment", "policy_faithfulness",
        "the record's action is a whole instruction",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "duplicate_rule", "policy_faithfulness",
        "two records do not restate the same sentence",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "condition_not_compiled", "policy_faithfulness",
        "a stated condition compiles against a fact model",
        RoutePresupposition.DETERMINISTIC, Category.NOT_REPORTED,
        "the ordinary AI Ready outcome; not carried to the report, and reported "
        "route-correctly by condition_provenance -- suppressed as a report, "
        "never counted as a silent pass",
    ),
    # -- logic_faithfulness.py --------------------------------------------
    CheckRecord(
        "attribute_not_in_source", "logic_faithfulness",
        "each attribute value is quoted from the source",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "party_not_in_source", "logic_faithfulness",
        "each named party is quoted from the source",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "authority_from_negated_phrase", "logic_faithfulness",
        "authority is not drawn from a negated phrase",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "discretion_without_authority", "logic_faithfulness",
        "a discretionary decision names who exercises it",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
    CheckRecord(
        "decomposition_malformed", "logic_faithfulness",
        "the canonical decomposition is well-formed",
        RoutePresupposition.NONE, Category.WORDING_ASSUMES_A_ROUTE,
        "detection is route-neutral -- an empty subject or mis-split sentence "
        "is broken on either route -- but the detail presupposed logic derived "
        "from the record, which the judged route does not derive; corrected by "
        "rewording",
    ),
    CheckRecord(
        "polarity_lost_in_projection", "logic_faithfulness",
        "the effect keeps the sentence's polarity",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
        "the effect carries polarity on either route",
    ),
    CheckRecord(
        "polarity_doubled_in_projection", "logic_faithfulness",
        "the effect does not negate an already-negated action",
        RoutePresupposition.NONE, Category.ROUTE_NEUTRAL,
    ),
)
