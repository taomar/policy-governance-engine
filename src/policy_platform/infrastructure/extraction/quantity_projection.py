"""Compile a quantity the sentence states into a condition the engine can run.

`condition_from_stated_bound` already compiles one shape: a bound expressed as
a proportion of another quantity -- "shall not exceed 10% of the basic salary".
That shape is real but rare. The shape policy documents actually use is an
absolute quantity with a unit: "more than 15 minutes", "up to 60 calendar
days", "at least 12 months". Measured across an extracted handbook, every
threshold captured was of the second shape and none of the first, so the
proportional compiler returned None on every record and the deterministic route
came out empty while the quantities sat in the records, correctly extracted.

This module reads that second shape. It compiles a comparison between the
quantity the sentence measures and the literal value the document stated.

WHAT THE COMPARISON IS ABOUT

A compiled condition asserts two things: that the document stated a test, and
what the test is *about*. The second is as easy to get wrong as the first and
harder to notice. Naming the compared fact after the sentence's grammatical
subject reads "part-time employees <= 24" out of a sentence that capped weekly
hours -- an assertion about a headcount that the document never made, attached
to a rule that now looks computable and will be computed.

So the operand is what the number counts, never whom the rule governs. The
subject is kept as the measured thing's qualifier, because two limits sharing a
unit are different limits and an operand named for the unit alone would collapse
them into one fact that answers both. Where the document never says what the
number counts, nothing is compiled: a bare magnitude cannot be bound to a case.

WHAT IT REFUSES, AND WHY THAT IS THE IMPORTANT HALF

A compiled comparison asserts that the document stated a test. Producing one
where the document stated only a magnitude would manufacture a rule -- and a
manufactured rule is worse than an absent one, because it looks computable and
will be computed. So the reader refuses unless the comparison is *stated*:

  "more than 15 minutes"    -> compiles; the document supplied the relation
  "one (1) day"             -> refused; a duration, not a test
  "45 hours per week"       -> refused; states what is, not a limit on it
  "(2 to 6) days"           -> refused; a band, not a bound
  "50%"                     -> refused; a proportion of nothing stated

Each refusal is returned as a code rather than silence, because a rule that
carries a quantity and no condition is exactly the case a reviewer must be able
to see. Silence there is what made this route invisible.

GENERALITY

No unit, currency, date format or vocabulary from any particular document
appears here. Units are read from the document's own words and carried
verbatim; they are never normalised against a table, because mapping "calendar
days" onto some canonical unit asserts an equivalence the document did not
state. The comparison vocabulary is ordinary English comparatives, and the
compound negated forms are matched before the bare ones so that "no more than"
cannot be read as "more than".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from policy_platform.contracts.conditions import (
    ConditionNode,
    ConditionOperator,
    FactComparisonCondition,
)
from policy_platform.contracts.formulation import CanonicalPolicyRule
from policy_platform.contracts.policy import RequiredFact
from policy_platform.infrastructure.extraction.policy_facts import (
    _slugify,
    parse_proportion,
)


class QuantityRefusal(str, Enum):
    """Why a stated quantity did not become a condition.

    Every member is a statement about what the source supplied, never a verdict
    on the record. An AI Ready rule is stated in words and settled by
    someone reading them; that is a route, not a defect, and these codes are
    read by a reviewer who needs to know which route this record took and why.
    """

    #: Two bounds where a test needs one: "30 to 90 days". The document gave a
    #: band and left the choice inside it to whoever applies the rule, so there
    #: is no single comparison to compile.
    RANGE = "quantity_states_a_range"
    #: A magnitude with no relation attached: "45 hours per week", "3 doses".
    #: The document says what the quantity *is*, not what must be true of it.
    #: Supplying a relation would be inventing the test.
    NO_COMPARISON = "quantity_states_no_comparison"
    #: A quantity this reader could not resolve to a number -- spelled out in
    #: words, or written in a form it does not parse. A platform limit rather
    #: than anything missing from the source.
    NOT_A_NUMBER = "quantity_not_read_as_number"
    #: A proportion with nothing to take it of: "50%". The base is what the
    #: percentage applies to, and without it there is no second operand.
    NO_BASE = "proportion_has_no_stated_base"
    #: A number with no statement of what it counts: "at least 12". The relation
    #: is there and the value is there, but nothing says twelve of what, so there
    #: is no quantity for a case to supply and no operand to compare.
    NO_UNIT = "quantity_states_nothing_counted"


#: Comparison vocabulary, most specific first. Order is load-bearing: "no more
#: than" and "not less than" must match before "more than" and "less than", or a
#: cap would compile as a floor and a rule would be inverted rather than merely
#: missing. Each entry is a plain English comparative, not a document's phrasing.
_COMPARISONS: tuple[tuple[re.Pattern[str], ConditionOperator], ...] = (
    (
        re.compile(
            r"\b(?:no|not)\s+(?:more|greater|longer|later)\s+than\b"
            r"|\bnot\s+exceed(?:ing)?\b|\bat\s+most\b|\bup\s+to\b"
            r"|\bmaximum\s+of\b|\bor\s+less\b|\bwithin\b",
            re.IGNORECASE,
        ),
        ConditionOperator.LESS_THAN_OR_EQUAL,
    ),
    (
        re.compile(
            r"\b(?:no|not)\s+(?:less|fewer|shorter|earlier)\s+than\b"
            r"|\bat\s+least\b|\bminimum\s+of\b|\bor\s+more\b",
            re.IGNORECASE,
        ),
        ConditionOperator.GREATER_THAN_OR_EQUAL,
    ),
    (
        re.compile(
            r"\b(?:more|greater|longer)\s+than\b|\bexceed(?:s|ing)?\b"
            r"|\bover\b|\babove\b|\bbeyond\b",
            re.IGNORECASE,
        ),
        ConditionOperator.GREATER_THAN,
    ),
    (
        re.compile(
            r"\b(?:less|fewer|shorter)\s+than\b|\bunder\b|\bbelow\b",
            re.IGNORECASE,
        ),
        ConditionOperator.LESS_THAN,
    ),
)

#: A number as documents write one, including grouped thousands ("100 000",
#: "5,000") and decimals. Grouping is matched first so "100 000" reads as one
#: value rather than two, which is the difference between a quantity and an
#: apparent range.
_NUMBER_RE = re.compile(r"\d{1,3}(?:[ ,]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")

#: Digits joined by a colon are a clock time or a ratio, not a magnitude. Read
#: as two numbers they would look like a range, which would report the wrong
#: reason for refusing; this names the real one.
_COLON_PAIR_RE = re.compile(r"\d\s*:\s*\d")

#: Trailing parenthetical after a value: "two hours (only)", "(15) fifteen".
_BRACKETED_RE = re.compile(r"[(\[][^)\]]*[)\]]")


def _numbers_in(phrase: str) -> list[float]:
    """Distinct numeric values the phrase states, in order of appearance.

    Distinct rather than every occurrence, because documents routinely write a
    figure twice for legal clarity -- "fifteen (15) days" -- and reading that as
    two values would refuse a perfectly well-stated bound as a range.
    """

    values: list[float] = []
    for token in _NUMBER_RE.findall(phrase):
        try:
            value = float(token.replace(",", "").replace(" ", ""))
        except ValueError:  # pragma: no cover - regex admits only numerals
            continue
        if value not in values:
            values.append(value)
    return values


#: A comparative that trails the number rather than preceding it ("30 days or
#: less"). It states the comparison, so it is read as one -- but it is not part
#: of what the number counts, and leaving it in produced a unit of "minutes or
#: less". A unit is a noun; a consumer matching on it would never find that.
_TRAILING_COMPARATIVE_RE = re.compile(
    r"\b(?:or\s+(?:less|fewer|more|greater|longer|shorter))\b.*$",
    re.IGNORECASE,
)


def _unit_from(phrase: str, value_text: str) -> str:
    """The document's own words for what the number counts.

    Taken verbatim from the text following the numeral and never mapped onto a
    canonical vocabulary: "calendar days" and "working days" are different
    things, and a table that flattened them would silently change what a rule
    means.

    A trailing comparative is dropped, because it states the comparison rather
    than the thing counted and the comparison is already carried by the
    operator. Nothing else is removed: qualifiers like "per week" or "within a
    contract year" stay, since they say what the count is taken over and a unit
    without them means something different.
    """

    tail = phrase.split(value_text, 1)[-1] if value_text in phrase else ""
    tail = _BRACKETED_RE.sub(" ", tail)
    tail = _TRAILING_COMPARATIVE_RE.sub(" ", tail)
    words = [w for w in re.split(r"[^\w%]+", tail) if w]
    return " ".join(words).strip()


def _measured_quantity_name(subject: str, counted: str) -> str:
    """Name the quantity the comparison is about.

    `counted` is the document's own words for what the number counts; `subject`
    is what the sentence says the count belongs to. The name carries both, with
    the counted thing last so the operand always ends in the dimension a case
    engine must supply.

    Both parts earn their place. Without `counted` the operand is a population
    and the comparison is nonsense. Without `subject` every limit measured in
    the same unit collapses onto one fact -- a notice period and a leave
    allowance both become `days`, and a case supplying one answers both.

    Where the subject already ends in the counted words the repetition is
    dropped, so a sentence that names its own measurement does not produce
    `review-period-months-months`.
    """

    subject_slug = _slugify(subject)
    counted_slug = _slugify(counted)
    if not counted_slug:
        return ""
    if not subject_slug:
        return counted_slug
    if subject_slug == counted_slug or subject_slug.endswith(f"-{counted_slug}"):
        return subject_slug
    return f"{subject_slug}-{counted_slug}"


@dataclass(frozen=True)
class QuantityProjection:
    """The outcome of one attempt to compile a stated quantity.

    Carries either a condition or a refusal, never both and never neither, so a
    caller cannot read a projection as successful by forgetting to check.
    `quantity_text` is the document's own wording, kept so a reviewer sees what
    was read rather than a description of it -- the same reason
    `ConditionProvenance.unsupported_expression` keeps the agent's own output.
    """

    quantity_text: str
    condition: ConditionNode | None = None
    facts: tuple[RequiredFact, ...] = ()
    refusal: QuantityRefusal | None = None

    @property
    def compiled(self) -> bool:
        return self.condition is not None


def stated_comparison(*sources: str | None) -> ConditionOperator | None:
    """The comparison the document stated, read from the first source carrying one.

    Sources are tried in order so a caller controls precedence. Nothing is
    inferred: a phrase with no comparative returns None, which is what stops a
    magnitude from being promoted into a limit.

    Position is load-bearing, and reading it wrong inverts rules rather than
    losing them. "more than fifteen (15) consecutive days within a contract
    year" contains two comparatives: "more than", which governs the fifteen,
    and "within", which governs the contract year and says nothing about the
    quantity at all. Matching anywhere in the phrase let the second win and
    compiled a termination threshold of *more than* fifteen days as *at most*
    fifteen -- a rule that then fires on precisely the people it should
    exempt, while looking perfectly computable.

    So the comparative is read from the text that precedes the number, and
    where several do, the one ending nearest it wins: that is the one attached
    to the quantity. Ties on the ending position are broken by length, which
    is what keeps "not more than" from being read as the "more than" inside
    it. Where nothing precedes the number, the text after it is read, because
    "30 days or less" states its comparison on the right.
    """

    for source in sources:
        text = (source or "").strip()
        if not text:
            continue

        number = _NUMBER_RE.search(text)
        boundary = number.start() if number else len(text)

        before: list[tuple[int, int, ConditionOperator]] = []
        after: list[tuple[int, int, ConditionOperator]] = []
        for pattern, operator in _COMPARISONS:
            for match in pattern.finditer(text):
                if match.end() <= boundary:
                    before.append((match.end(), len(match.group(0)), operator))
                elif match.start() >= boundary:
                    after.append((-match.start(), len(match.group(0)), operator))

        # Nearest to the number wins; longer match breaks a tie at the same
        # position, so the compound negated form is preferred over the bare
        # comparative nested inside it.
        candidates = before or after
        if candidates:
            return max(candidates)[2]
    return None


def project_stated_quantity(
    rule: CanonicalPolicyRule | None,
) -> QuantityProjection | None:
    """Compile `rule`'s stated quantity, or say why it did not compile.

    Returns None when the rule states no quantity at all. That is different
    from a refusal: a rule with no threshold has nothing to project and no
    reviewer question to answer, whereas a rule carrying a quantity that did
    not compile is exactly the case the gate exists to surface.
    """

    if rule is None:
        return None

    threshold = (rule.threshold or "").strip()
    if not threshold:
        return None

    subject = (rule.subject or "").strip()
    if not subject:
        # Nothing to name the fact after. `assess` already reports an empty
        # subject as malformed, so the record is flagged; adding a second
        # quantity code here would report the same defect twice.
        return None

    # A proportion is the other compiler's shape when it names a base, and an
    # incomplete statement when it does not. Either way it is not this one's.
    if parse_proportion(threshold) is not None:
        return None
    if "%" in threshold:
        return QuantityProjection(
            quantity_text=threshold, refusal=QuantityRefusal.NO_BASE
        )

    if _COLON_PAIR_RE.search(threshold):
        return QuantityProjection(
            quantity_text=threshold, refusal=QuantityRefusal.NOT_A_NUMBER
        )

    values = _numbers_in(threshold)
    if not values:
        return QuantityProjection(
            quantity_text=threshold, refusal=QuantityRefusal.NOT_A_NUMBER
        )
    if len(values) > 1:
        return QuantityProjection(
            quantity_text=threshold, refusal=QuantityRefusal.RANGE
        )

    # The threshold phrase is consulted before the predicate because a
    # comparative sitting next to the number qualifies that number, whereas one
    # in the predicate may govern something else the sentence also says.
    operator = stated_comparison(threshold)
    if operator is None:
        # The threshold states a magnitude but no comparison. The predicate may
        # still supply one -- but only where it has no number of its own to
        # govern. stated_comparison binds a comparative to the number nearest
        # it, so where the predicate carries a number the comparison there is
        # attached to that number; lifting it onto the threshold's magnitude
        # would assert a limit the sentence states about something else (a bare
        # count beside "no later than 30 days" is a cap on the days, not the
        # count). A number-bearing predicate therefore governs itself, and the
        # threshold is left with no stated comparison rather than a borrowed one.
        predicate = (rule.predicate or "").strip()
        if not _NUMBER_RE.search(predicate):
            operator = stated_comparison(predicate)
    if operator is None:
        return QuantityProjection(
            quantity_text=threshold, refusal=QuantityRefusal.NO_COMPARISON
        )

    value = values[0]
    value_text = _NUMBER_RE.search(threshold)

    # What the number counts, in the document's own words. The threshold phrase
    # is read in preference to the model's `unit` field because it keeps the
    # qualifier that says what the count is taken over -- "hours per week" is a
    # different quantity from "hours", and an operand that dropped "per week"
    # would invite a case to supply a total.
    counted = _unit_from(threshold, value_text.group(0) if value_text else "")
    unit = counted or (rule.unit or "").strip()
    if not unit:
        return QuantityProjection(
            quantity_text=threshold, refusal=QuantityRefusal.NO_UNIT
        )

    fact_name = _measured_quantity_name(subject, unit)
    if not fact_name:
        return QuantityProjection(
            quantity_text=threshold, refusal=QuantityRefusal.NO_UNIT
        )

    return QuantityProjection(
        quantity_text=threshold,
        condition=FactComparisonCondition(
            fact=fact_name, operator=operator, value=value
        ),
        facts=(RequiredFact(name=fact_name, data_type="number", unit=unit),),
    )
