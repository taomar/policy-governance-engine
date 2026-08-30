"""Reading part of a policy, and saying so — rule-level retrieval for a large one.

WHY A POLICY IS SOMETIMES TOO BIG TO BE ONE THING

A provision with a dozen rules is a *provision*: a reader holds it in mind at
once, every rule of it bears on the same subject, and putting the whole of it in
front of a model is both affordable and correct.

Past some size a "policy" stops being that and becomes a **table**. The measured
case is `Table of Violations and Penalties`, provision key
`e8326a491c60c8914b7932dd0f2607eb`, pages 21–27: seventy-four routing and
require-action rules, one per violation, enumerating cases that have nothing to
do with one another. A question touches at most a handful of its rows. Sending
all seventy-four costs 188,000 characters, and in company with anything else it
exhausted the one-gather budget outright — a question about annual leave got no
answer because a penalties table was large.

Skipping such a policy wholesale (the earlier repair) is honest but blunt: a
question that genuinely asks about one violation then gets nothing from the one
document that answers it. So a large policy is **sliced**: the rules that bear on
the question are selected, their necessary context is pulled in behind them, and
the receipt says plainly how many of the policy's rules were read.

THE THRESHOLD, AND WHY IT IS THE SELECTION BUDGET TOO

`LARGE_POLICY_RULE_THRESHOLD` is 15. It is not a measurement of any corpus and
is not tuned to one: it is the point at which a provision stops reading as a
single governing statement and starts reading as a schedule of independent rows.
Below it, the whole policy goes to the gather exactly as it always has, byte for
byte — no selection runs, so nothing about the ordinary case changes.

`SELECTED_RULE_BUDGET` is the same number on purpose. A sliced policy is then
never larger, in rules, than a policy that passes through whole, so the two paths
cannot produce records of different orders of magnitude and there is one number
to reason about rather than two that can drift apart.

THE BUDGET IS A CEILING ON THE RECORD, NOT ON ONE STEP OF BUILDING IT

Decision `991d819b-fb37-4b4d-bb02-b928d4633d4f` reported
`selected_rule_budget=15` and put **35** rules of the seventy-four-row penalties
policy in front of the gather: fifteen scenario matches plus twenty rules pulled
in as explicit context. Each step was individually within something — the
selection took fifteen, and every context rule fit the *character* budget — but
nothing measured the total, so the one number the reviewer was shown was not the
number that held.

So the budget is enforced where it is claimed: on the rules that reach a gather.
Context fills only the slots the primary selection left unused, and when the
selection has taken all fifteen, context adds nothing. It is the weaker claim of
the two — a context rule is included because a selected rule points at it, not
because it bears on the question — so it is the one that yields. Nothing is
dropped in silence: every context rule that could not be admitted, whether for
want of a slot or of characters, is named in `context_rules_omitted`, and a
reader can see exactly which links were not followed.

A COPY OF A RULE IS NOT A SECOND RULE

The same accounting failure has a second form, one level down. A published
version measured 280 rules against 229 distinct source texts — 34 groups of
duplicates covering 85 rules, with one lateness row appearing four times. A
selection of twenty-five ids there stood for seven distinct rows: eighteen of the
twenty-five slots, seventy-two per cent, said something the record already said,
and the rule that actually decided the case ranked just outside what was left.

Duplicate rules cost twice over, and the second cost is easy to miss. They take
slots, which is the visible half. They also distort the ranking: the weighting is
an inverse document frequency computed over this policy's own rules, so a row
repeated four times has its distinguishing terms discounted four times over and
sinks beneath rows that are merely wordy — the repetition actively buries the
thing it repeats. Both are repaired by collapsing before scoring rather than
after.

Equivalence here is the same one the duplicate-policy pass uses, applied per rule
(`rule_semantic_fingerprints`): everything the rule governs, with identity and
provenance removed and its links resolved to what they point at. Never source
text or title alone — two rows quoting one sentence under different effects,
conditions, authority, scope or effective windows are two rules and both stay
candidates. The representative is the earliest occurrence in document order,
which needs no tie-break because the copies are identical in everything compared.

WHY THE SELECTION IS LEXICAL AND NOT A SECOND MODEL CALL

A model call to choose rules would add latency and cost to every large policy,
would not be reproducible, and would put a second, unaudited judgement between
the reviewer's question and the record. This selects with a bounded function of
the scenario and the policy's own words, so the same question against the same
version always selects the same rules — which is what makes a receipt that names
`selected_rule_ids` worth anything.

The weighting is an inverse document frequency computed **over this policy's own
rules**, not against a wordlist. That matters twice. It is the reason boilerplate
ranks nothing: in a seventy-four-row penalties table the words every row shares —
the authority, the measure, the schedule — appear in every rule, so their weight
clamps to zero and only the terms that distinguish one row from another can
score. And it is the reason nothing here is tuned to a language: the corpus is
bilingual, the discounting is derived from the document in front of it, and no
list of English stop-words (or Arabic ones) is carried anywhere in this file.

WHAT IT REFUSES TO DO

  * **It never truncates a rule.** A rule is selected whole or not at all. Half a
    rule presented as a rule is the fabrication this whole area guards against.
  * **It never claims the policy was read whole.** Every sliced record is
    reported with `total_rules`, `selected_rules` and the ids, so a receipt says
    "74 rules · 8 selected for this case" rather than implying seventy-four were
    weighed.
  * **It never silently under-keeps.** When no rule scores against the question,
    the policy is *not* dropped — the first rules in document order are taken and
    the method says `document_order`, so a lexical miss costs context rather than
    the policy. Over-keeping is the safe error here: the gather re-checks bearing
    and cites only rules that speak to the question, so a retained rule that does
    not bear costs a little context, while under-keeping drops something that
    does.
"""
from __future__ import annotations

import math
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any, Final

from policy_platform.infrastructure.projection.policy_case_payload import to_compact
from policy_platform.infrastructure.projection.policy_semantic_identity import (
    rule_semantic_fingerprints,
)
from policy_platform.infrastructure.projection.text_canonical import canonical_tokens

#: Above this many rules a policy is treated as a table of independent rows
#: rather than one governing statement, and its rules are retrieved individually.
#: See the module docstring for why this number and not a measured one.
LARGE_POLICY_RULE_THRESHOLD: Final[int] = 15

#: How many rules of a large policy may be selected for one case. Deliberately
#: equal to the threshold: a sliced policy is then never larger, in rules, than
#: one that passes through whole.
SELECTED_RULE_BUDGET: Final[int] = 15

#: The characters one policy's record may occupy after slicing. The same ceiling
#: a whole policy is measured against, so a slice can never be admitted where a
#: whole policy of the same size would be refused.
SLICE_BUDGET_CHARS: Final[int] = 200_000

#: How the rules in a record were chosen. Named so a receipt can say which, and
#: so a reader never has to infer it from the counts.
METHOD_WHOLE_POLICY: Final[str] = "whole_policy"
METHOD_RELEVANCE: Final[str] = "scenario_relevance_v2"
#: Lexical over the **English projection**, with the quantity rank, and no
#: contribution from the rule index. Distinct from `scenario_relevance_v2`
#: because that one ranks a policy by its own stored words in the language it was
#: written in, and this one ranks a rendered projection against a rendered
#: question — the same algorithm over a different corpus is a different claim
#: about what was compared.
METHOD_RELEVANCE_V3: Final[str] = "scenario_relevance_v3"
#: Reciprocal-rank fusion of the lexical rank, the rule index's own rank and the
#: quantity-compatibility rank. Emitted whenever the rule index took part,
#: including when it ranked nothing here — "it was asked and had nothing to say"
#: is a different fact from "it was not asked".
METHOD_HYBRID_RULE: Final[str] = "hybrid_rule_v1"
METHOD_DOCUMENT_ORDER: Final[str] = "document_order"

#: Whether the rule index took part in this selection, and how.
#:
#: `unavailable` is the honest default and covers every path that never consults
#: it: a reviewer who named one policy, a project whose index holds no rule
#: documents, a caller that did not pass any. `degraded` is the narrow case the
#: disclosure exists for — rule documents under the expected profile *are*
#: present, and the vector query against them failed in a way the caller could
#: report; the selection then falls back to lexical and quantity over the English
#: projection and says so.
RULE_INDEX_UNAVAILABLE: Final[str] = "unavailable"
RULE_INDEX_MATCHED: Final[str] = "matched"
RULE_INDEX_DEGRADED: Final[str] = "degraded"

#: The reciprocal-rank-fusion constant. 60 is the value the technique was
#: published with and the one Azure AI Search itself uses to combine its keyword
#: and vector rankings, so the two layers of fusion in this pipeline are damped
#: the same way. What it buys is that a rank-0 hit cannot dominate: the
#: difference between rank 0 and rank 1 is small, so a rule has to place well in
#: more than one ranking to rise, which is the whole point of fusing them.
RRF_K: Final[int] = 60

#: Words of one character are dropped before scoring. This is not a stop-word
#: list — it carries no language's vocabulary — it is a floor below which a token
#: cannot distinguish one rule from another in any script.
_MIN_TOKEN_CHARS: Final[int] = 2

#: A number, then up to a few characters, then a second number, then a word: the
#: shape of a stated interval. Recognised by walking characters and asking
#: Unicode what each one is — never by a pattern, because a pattern is a claim
#: about what a word or a digit looks like and that claim is wrong in most of the
#: scripts this corpus can be in. The bounds below are distances, not vocabulary.
#:
#: How far past a number the word naming its unit may sit.
_MAX_UNIT_GAP_CHARS: Final[int] = 4
#: How far apart the two bounds of an interval may sit.
_MAX_RANGE_GAP_CHARS: Final[int] = 12
#: How many words may sit between them — one, for whatever the text writes
#: between a low and a high bound. Which word is never asked, so this carries no
#: language's vocabulary. The cost is named rather than hidden: a sentence
#: writing two unrelated quantities close together ("3 units, 5 hours") also
#: reads as an interval. That can only ever *offer* a rule to a gather that then
#: finds it does not bear, which the gather already checks, and it is the
#: documented safe direction for every ranking in this file.
_MAX_RANGE_GAP_WORDS: Final[int] = 1

#: The shortest unit token two spellings must share before they are allowed to
#: match on a common prefix. Below this a prefix relation says nothing: `m` is a
#: prefix of most words.
_MIN_UNIT_PREFIX_CHARS: Final[int] = 3
#: How much longer one spelling of a unit may be than another and still be taken
#: for the same unit. A generic string relation over two tokens, not a rule about
#: any language's morphology: it carries no suffix list and no vocabulary, and it
#: is applied identically to every token in every script.
_MAX_UNIT_SUFFIX_CHARS: Final[int] = 2


def _tokens(text: str) -> list[str]:
    """Case-folded word tokens, in any script the text happens to be in.

    Delegated to the shared canonicaliser rather than done here, because the
    version that lived here was a ``\\w+`` scan and case fold, and that is not the
    same question as "are these the same word" in most of the scripts this text
    can be in. A combining mark is not a word character, so the scan did not merely
    fail to match a marked spelling against an unmarked one — it *split the word*
    at every mark. Arabic carrying tashkeel came apart into four fragments, and
    Devanagari came apart at the vowel signs, producing tokens that matched
    nothing at all.

    WHICH SIDE THIS IS

    This reads *stored* text: the authoritative record's own sentences and its
    structured terms, which are held verbatim in whatever language the document
    was written in and are never rewritten. That is why it has to be correct in
    every script, and why it stays so even though the query side is settling on
    one language.

    It is emphatically **not** a place to reconcile two languages. It matches the
    text it is given against the text it is given; it does not translate, does not
    bridge a query in one language to a record in another, and must not be asked
    to. What is indexed and what is queried are decided upstream, by the stage that
    owns that boundary — not here, and not by widening this function.

    Sharing the canonicaliser with the fact-key path also means retrieval and
    identity can no longer answer that question differently, which they did.

    Nothing else about the tokens changed: still no stemming, no stop words and no
    language list, still a plain floor on token length, and still a pure function
    of its input, so scoring stays deterministic.
    """

    return canonical_tokens(text, min_chars=_MIN_TOKEN_CHARS)


def _fact_text(facts: dict, ref: object) -> str:
    entry = facts.get(str(ref)) if isinstance(facts, dict) else None
    if not isinstance(entry, dict):
        return ""
    return " ".join(
        str(entry.get(key) or "") for key in ("name", "source_phrase", "data_type")
    )


def rule_text(rule: dict, *, spans: dict, facts: dict) -> str:
    """Everything about one rule that a question could match, as one string.

    The largest and most important part is the document's own verbatim sentence,
    reached by following the rule's ``evidence_refs`` into ``spans`` — the same
    resolution a citation performs. A rule's generated *name* is deliberately not
    here and is not in the record at all (constraint 8); what is matched is the
    document's words and the policy's own structured terms.
    """

    parts: list[str] = []

    for ref in rule.get("evidence_refs") or []:
        span = spans.get(str(ref)) if isinstance(spans, dict) else None
        if isinstance(span, dict) and span.get("text"):
            parts.append(str(span["text"]))

    effect = rule.get("effect") or {}
    if isinstance(effect, dict):
        parts.append(str(effect.get("action") or ""))
        parts.append(str(effect.get("type") or ""))
    parts.append(str(rule.get("rule_type") or ""))
    parts.append(str(rule.get("modality") or ""))

    for required in rule.get("required_facts") or []:
        if isinstance(required, dict):
            parts.append(
                " ".join(
                    str(required.get(key) or "")
                    for key in ("name", "phrase", "unit", "role", "data_type")
                )
            )

    attributes = rule.get("attributes") or {}
    if isinstance(attributes, dict):
        for group in ("applies", "outcome"):
            for attribute in attributes.get(group) or []:
                if not isinstance(attribute, dict):
                    continue
                parts.append(str(attribute.get("attribute") or ""))
                if attribute.get("text"):
                    parts.append(str(attribute["text"]))
                if attribute.get("fact_ref"):
                    parts.append(_fact_text(facts, attribute["fact_ref"]))

    for fact in rule.get("facts") or []:
        if isinstance(fact, dict):
            parts.append(_fact_text(facts, fact.get("ref")))
            parts.append(" ".join(str(role) for role in fact.get("roles") or []))

    for exception in rule.get("exceptions") or []:
        if isinstance(exception, dict):
            parts.append(str(exception.get("description") or ""))
            parts.append(str(exception.get("limit_unit") or ""))

    for advice in rule.get("advice") or []:
        if isinstance(advice, dict):
            parts.append(str(advice.get("text") or ""))

    parts.extend(str(tag) for tag in rule.get("tags") or [])

    scope = rule.get("scope")
    if isinstance(scope, dict):
        for values in scope.values():
            parts.extend(str(value) for value in values or [])

    return " ".join(part for part in parts if part)


def score_rules(
    payload: dict,
    scenario: str,
    *,
    rule_projections: Mapping[str, str] | None = None,
) -> list[float]:
    """One relevance score per rule, in the payload's own rule order.

    The weight of a query term is an inverse document frequency taken over *this
    policy's* rules, clamped at zero. A term every rule carries therefore scores
    nothing, which is what makes a table of near-identical rows separable at all:
    what distinguishes row 41 from row 42 is the handful of words only it uses.

    Deterministic by construction — no randomness, no model, no ordering that
    depends on anything but the payload and the question.

    ONE LANGUAGE ON BOTH SIDES

    ``rule_projections`` is the English projection of each rule, when the caller
    has one. The question reaching this function has already been reduced to the
    processing language, so scoring it against a rule's stored words is a
    cross-language comparison whenever the document was not written in that
    language — and a cross-language comparison scores near zero regardless of how
    well the rule bears on the question. Given projections, this scores the
    rendered question against the rendered rule and the two sides match.

    A rule the caller has no projection for scores **zero**, and is not scored
    against its stored text as a consolation. Falling back would reintroduce the
    cross-language match this exists to remove, and a zero here is not a
    dismissal: the rule can still be ranked by the rule index and by the quantity
    rank, both of which the caller fuses with this one.

    Without ``rule_projections`` nothing changes at all: every rule is scored
    against its own stored words exactly as before, which is what the
    single-policy scope and every existing caller get.
    """

    rules = payload.get("rules") or []
    spans = payload.get("spans") or {}
    facts = payload.get("facts") or {}
    if not rules:
        return []

    if rule_projections is None:
        texts = [rule_text(rule, spans=spans, facts=facts) for rule in rules]
    else:
        texts = [str(rule_projections.get(str(rule.get("rule_id")), "")) for rule in rules]

    per_rule = [set(_tokens(text)) for text in texts]
    total = len(rules)

    document_frequency: dict[str, int] = {}
    for tokens in per_rule:
        for token in tokens:
            document_frequency[token] = document_frequency.get(token, 0) + 1

    query = set(_tokens(scenario))
    if not query:
        return [0.0] * total

    weights = {
        token: max(0.0, math.log(total / (1 + document_frequency.get(token, 0))))
        for token in query
    }

    return [
        round(sum(weights[token] for token in query & tokens), 6) for tokens in per_rule
    ]


# ── quantities: a scalar, a range, and whether one is inside the other ──


def _atoms(text: str) -> list[tuple[bool, str, int, int]]:
    """Split text into number atoms and word atoms, by Unicode category alone.

    Returns ``(is_number, value, start, end)``. There are exactly two kinds and
    the flag is the whole of that distinction — no tag, no name, nothing a reader
    of this function could mistake for a category it might one day extend by
    adding a word. Everything else — punctuation, spaces, brackets, dashes — is a
    separator and is not returned, but the offsets are kept so a caller can ask
    how far apart two atoms sit.

    No pattern is used, deliberately. A character is a digit if Unicode says so,
    a letter if Unicode says so, and part of the letter before it if it is a
    combining mark — which is what stops a marked spelling coming apart into
    fragments, and is the same reading the shared canonicaliser performs.
    """

    found: list[tuple[bool, str, int, int]] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char.isdigit():
            start = index
            digits: list[str] = []
            while index < length and (
                text[index].isdigit()
                or (
                    text[index] in ".,"
                    and index + 1 < length
                    and text[index + 1].isdigit()
                    and digits
                )
            ):
                if text[index].isdigit():
                    try:
                        digits.append(str(unicodedata.decimal(text[index])))
                    except (TypeError, ValueError):  # pragma: no cover - non-decimal digit
                        digits.append(text[index])
                else:
                    digits.append(".")
                index += 1
            found.append((True, "".join(digits), start, index))
            continue
        if char.isalpha():
            start = index
            while index < length and (
                text[index].isalpha() or unicodedata.category(text[index]).startswith("M")
            ):
                index += 1
            found.append((False, text[start:index], start, index))
            continue
        index += 1
    return found


def _numeric_value(raw: str) -> float | None:
    """One number atom as a value, or None when it is not one.

    A run carrying more than one separator (a date, a clause reference) is not a
    quantity and is refused rather than guessed at.
    """

    try:
        return float(raw)
    except ValueError:
        return None


def _unit_key(token: str) -> str:
    """A unit token, canonicalised the same way every other token here is."""

    canonical = canonical_tokens(token, min_chars=1)
    return canonical[0] if canonical else ""


def units_match(left: str, right: str) -> bool:
    """Whether two unit tokens name the same unit.

    Equality first. Then one generic string relation, and only one: a token that
    is a prefix of the other, where both are at least
    :data:`_MIN_UNIT_PREFIX_CHARS` long and they differ by at most
    :data:`_MAX_UNIT_SUFFIX_CHARS` characters.

    That relation carries no vocabulary, no suffix list and no language: it is a
    statement about two strings, applied identically to every token in every
    script. What it buys is that a question stating one of something and a rule
    stating several of the same thing are not treated as stating different
    things. What it deliberately does **not** buy is any relation between two
    tokens that merely start alike but are far apart in length — which is why the
    difference is bounded rather than open.

    It is a **retrieval** relation. Nothing here decides an outcome; the worst a
    false match can do is offer a rule to a gather that then finds it does not
    bear, which the gather already checks.
    """

    if not left or not right:
        return False
    if left == right:
        return True
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    if len(shorter) < _MIN_UNIT_PREFIX_CHARS:
        return False
    if len(longer) - len(shorter) > _MAX_UNIT_SUFFIX_CHARS:
        return False
    return longer.startswith(shorter)


def quantity_scalars(text: str) -> list[tuple[float, str]]:
    """Every ``(value, unit)`` the text states, in the order it states them.

    A number's unit is the next word atom, provided it sits within
    :data:`_MAX_UNIT_GAP_CHARS` of it and no other number intervenes. A number
    with no word near it states a quantity of nothing nameable and is skipped —
    matching two bare numbers would match a clause reference against a duration.
    """

    atoms = _atoms(text)
    found: list[tuple[float, str]] = []
    for position, (is_number, raw, _start, end) in enumerate(atoms):
        if not is_number:
            continue
        value = _numeric_value(raw)
        if value is None:
            continue
        if position + 1 >= len(atoms):
            continue
        next_is_number, next_raw, next_start, _next_end = atoms[position + 1]
        if next_is_number or next_start - end > _MAX_UNIT_GAP_CHARS:
            continue
        unit = _unit_key(next_raw)
        if unit:
            found.append((value, unit))
    return found


def quantity_ranges(text: str) -> list[tuple[float, float, str]]:
    """Every closed interval the text states, as ``(low, high, unit)``.

    Recognised by distance, not by vocabulary: two numbers within
    :data:`_MAX_RANGE_GAP_CHARS` of one another with at most
    :data:`_MAX_RANGE_GAP_WORDS` words between them, and the unit taken from the
    word following the *second* number — which is where a stated interval puts
    it. The bounds are ordered, so a text writing the larger one first still
    yields an interval rather than an empty one.
    """

    atoms = _atoms(text)
    found: list[tuple[float, float, str]] = []
    for position, (is_number, raw, _start, end) in enumerate(atoms):
        if not is_number:
            continue
        low = _numeric_value(raw)
        if low is None:
            continue
        words_between = 0
        cursor = position + 1
        while cursor < len(atoms):
            next_is_number, next_raw, next_start, next_end = atoms[cursor]
            if next_start - end > _MAX_RANGE_GAP_CHARS:
                break
            if not next_is_number:
                words_between += 1
                if words_between > _MAX_RANGE_GAP_WORDS:
                    break
                cursor += 1
                continue
            high = _numeric_value(next_raw)
            if high is None:
                break
            if cursor + 1 < len(atoms):
                unit_is_number, unit_raw, unit_start, _unit_end = atoms[cursor + 1]
                if not unit_is_number and unit_start - next_end <= _MAX_UNIT_GAP_CHARS:
                    unit = _unit_key(unit_raw)
                    if unit:
                        found.append((min(low, high), max(low, high), unit))
            break
    return found


def quantity_compatible(scenario_scalars: Sequence[tuple[float, str]], text: str) -> bool:
    """Whether a quantity the question states is admitted by a quantity this text states.

    Two ways, and both require the units to match:

      * the question's value falls inside an interval the text states — a case
        of three days against a schedule row covering two to six days; or
      * the question's value equals a value the text states outright.

    A question stating a quantity in one unit and a text stating one in another
    is **not** compatible, and gets nothing. That is the whole of the check: no
    conversion, no ordering assumption about which side of a stated bound is
    permitted, and no reading of what the text *means* by its number. Deciding
    that is the gather's, over the rule's own words; this only decides whether
    the rule is worth putting in front of it.
    """

    if not scenario_scalars:
        return False
    ranges = quantity_ranges(text)
    scalars = quantity_scalars(text)
    for value, unit in scenario_scalars:
        for low, high, range_unit in ranges:
            if units_match(unit, range_unit) and low <= value <= high:
                return True
        for other, other_unit in scalars:
            if units_match(unit, other_unit) and other == value:
                return True
    return False


# ── fusion: several rankings, one deterministic order ─────────────────


def reciprocal_rank_scores(ranks: Mapping[int, int]) -> dict[int, float]:
    """Turn one ranking into its reciprocal-rank contribution.

    ``1 / (K + rank)`` per member, zero-based ranks. Members absent from the
    ranking contribute nothing rather than a penalty: a ranking that did not
    place a rule has said nothing about it, and a penalty would make silence
    count against a rule another ranking placed first.
    """

    return {index: 1.0 / (RRF_K + rank) for index, rank in ranks.items()}


def dense_ranks(order: Sequence[int]) -> dict[int, int]:
    """Positions in a sequence, as zero-based ranks."""

    return {index: rank for rank, index in enumerate(order)}


def fuse_rankings(rankings: Sequence[Mapping[int, int]]) -> dict[int, float]:
    """Reciprocal-rank fusion over several rankings of the same candidates.

    Deterministic given the same inputs, which is what makes a receipt naming
    `selected_rule_ids` worth anything: the same question against the same
    version and the same index always fuses to the same order. Ties are not
    resolved here — the caller breaks them on document order, which is a total
    order the record already carries.
    """

    fused: dict[int, float] = {}
    for ranking in rankings:
        for index, contribution in reciprocal_rank_scores(ranking).items():
            fused[index] = fused.get(index, 0.0) + contribution
    return fused


def _referenced_ids(rules: list[dict]) -> tuple[set[str], set[str]]:
    """The span and fact ids this set of rules actually points at."""

    span_ids: set[str] = set()
    fact_ids: set[str] = set()

    for rule in rules:
        for ref in rule.get("evidence_refs") or []:
            span_ids.add(str(ref))
        for fact in rule.get("facts") or []:
            if isinstance(fact, dict) and fact.get("ref"):
                fact_ids.add(str(fact["ref"]))
        attributes = rule.get("attributes") or {}
        if isinstance(attributes, dict):
            for group in ("applies", "outcome"):
                for attribute in attributes.get(group) or []:
                    if isinstance(attribute, dict) and attribute.get("fact_ref"):
                        fact_ids.add(str(attribute["fact_ref"]))

    return span_ids, fact_ids


def build_slice(payload: dict, rules: list[dict]) -> dict:
    """A record holding exactly these rules, with only what they reference.

    The `spans` and `facts` dictionaries are rebuilt to the ids the kept rules
    point at. That is where a slice's saving actually comes from — a rule is
    small, its verbatim source sentence is not — and it is also what keeps the
    record *closed*: a span nothing points at would be text in front of the model
    that no citation could ever resolve to.

    The envelope is carried unchanged. It is the policy's identity and the values
    every rule of it shares; editing it to describe a subset would make the slice
    claim to be a different policy.
    """

    span_ids, fact_ids = _referenced_ids(rules)
    source_spans = payload.get("spans") or {}
    source_facts = payload.get("facts") or {}

    sliced = dict(payload)
    sliced["rules"] = list(rules)
    sliced["spans"] = {k: v for k, v in source_spans.items() if str(k) in span_ids}
    sliced["facts"] = {k: v for k, v in source_facts.items() if str(k) in fact_ids}
    return sliced


def _record_chars(policy: dict, payload: dict) -> int:
    """The transport size of one policy record, as the gather will see it."""

    return len(to_compact({"policies": [{"policy": policy, "record": payload}]}))


def _context_ids(rule: dict) -> list[str]:
    """The rules this one explicitly leans on, in a stable order.

    Only references the record itself carries: `related_rule_ids` (the drafter's
    own "read these together"), and `supersedes_rule_ids` (what this rule
    displaces — a reader shown the override without the rule it overrides is
    being shown half a change). An override marker with no ids names nothing and
    pulls in nothing, which is correct: it is a property of the rule, not a link.

    Exceptions are *inline* on the rule, so a selected rule always carries its own
    carve-outs and there is nothing to close over for them.
    """

    ids: list[str] = []
    for key in ("supersedes_rule_ids", "related_rule_ids"):
        for value in rule.get(key) or []:
            text = str(value)
            if text and text not in ids:
                ids.append(text)
    return ids


def evidence_group_keys(payload: dict) -> list[object]:
    """Which source passage each rule rests on, aligned to ``payload["rules"]``.

    The verbatim text of the rule's grounding spans, in evidence order — content,
    never a span id or a clause number, so two rules cut from one sentence group
    together whatever the extraction called them.

    A rule with no readable grounding text is its own group, keyed by position.
    Grouping rules on the absence of evidence would put every unplaceable rule in
    one bucket and let the first of them crowd out the rest, which is the failure
    this exists to prevent, inverted.
    """

    spans = payload.get("spans") or {}
    keys: list[object] = []
    for index, rule in enumerate(payload.get("rules") or []):
        refs = (rule.get("evidence_refs") or []) if isinstance(rule, dict) else []
        texts = tuple(
            (spans.get(ref) or {}).get("text") for ref in refs
        )
        keys.append(texts if any(t for t in texts) else ("\u0000unplaceable", index))
    return keys


def _diverse_by_evidence(
    candidates: list[int], group_of: list[object], scores: dict[int, float]
) -> list[int]:
    """Order positively-matching rules so distinct source passages come first.

    Retained because it is the ordering the pre-fusion selection was built on and
    is still exactly right when there is one ranking: with a single relevance
    score and no budget pressure, offering the best rule of each passage first
    costs nothing. :func:`order_with_evidence_quota` is what the budgeted path
    now uses, and it is this ordering with the starvation removed — see there for
    why an unbounded "firsts then rest" was the wrong shape once a policy could
    have more distinct passages than slots.

    ONE SENTENCE, SEVERAL RULES

    A paragraph often states more than one thing, and extraction emits one rule
    per obligation — so four genuinely different rules can rest on one sentence.
    They are four rules and must never be collapsed: one may permit where another
    forbids. But reading all four before reading any *other* matching passage
    spends four slots on one row of the document.

    So the highest-scoring rule of each distinct passage is taken first, passages
    ordered by their best rule; only then are the second and later rules of those
    passages considered, in ordinary score order. Every candidate here already
    scored positively against the question, so nothing that does not bear on it
    can displace something that does — the pass reorders matches among
    themselves and never admits a non-match.

    Ties break on document order at both stages, so one question against one
    version always produces one selection.
    """

    best: dict[object, int] = {}
    for index in candidates:
        key = group_of[index]
        if key not in best or (-scores[index], index) < (-scores[best[key]], best[key]):
            best[key] = index

    firsts = sorted(best.values(), key=lambda i: (-scores[i], i))
    chosen = set(firsts)
    rest = sorted((i for i in candidates if i not in chosen), key=lambda i: (-scores[i], i))
    return firsts + rest


def evidence_diversity_quota(rule_budget: int) -> int:
    """How many slots passage diversity may claim before relevance takes over.

    Half the budget, rounded up. Named as a function of the budget rather than as
    a number so the two cannot drift, and expressed as a *reserve* rather than a
    filter because of what the filter did.

    WHAT THE UNBOUNDED VERSION COST

    :func:`_diverse_by_evidence` offers the best rule of **every** distinct
    passage before it offers any passage's second rule. In a schedule with more
    distinct passages than slots — which is what a schedule is — the budget is
    exhausted inside the firsts, and the second rule of a passage is unreachable
    however well it scores. A paragraph stating two obligations then contributes
    at most one of them to any case, and which one is decided by score alone
    among rules that may not even be about the same thing.

    That is a starvation, not a diversity policy. Reserving half the budget keeps
    what diversity was for — one strong passage cannot take every slot — while
    leaving the rest to be filled on merit, so a second strongly relevant rule
    from a passage already covered is reachable whenever it outranks the first
    rules of weaker passages.
    """

    return max(1, -(-rule_budget // 2))


def order_with_evidence_quota(
    candidates: Sequence[int],
    group_of: Sequence[object],
    *,
    quota: int,
    budget: int,
) -> list[int]:
    """Offer candidates so passage diversity is guaranteed but never total.

    ``candidates`` arrive already ordered by fused relevance, ties broken on
    document order by the caller, so this pass is purely about *which* of them
    the budget reaches:

    1. **The reserve.** Walking the fused order, the first candidate of each
       passage not yet represented is taken, until ``quota`` of them have been.
       This is what stops one heavily-matching paragraph consuming the record.
    2. **The remainder, on merit.** Everything still unselected is offered in
       fused order regardless of passage. A second rule of a passage already
       covered competes here on exactly the same terms as the first rule of a
       passage not yet covered — and wins when it ranks higher, which is what the
       unbounded version made impossible.

    Both passes preserve the fused order, so the result is a deterministic
    function of the fusion and the document's own order. The full ordering is
    returned rather than the first ``budget`` of it: the caller applies the
    budget, and callers that measure characters need to see what came next.
    """

    seen: set[object] = set()
    reserved: list[int] = []
    for index in candidates:
        if len(reserved) >= min(quota, budget):
            break
        key = group_of[index] if index < len(group_of) else index
        if key in seen:
            continue
        seen.add(key)
        reserved.append(index)

    taken = set(reserved)
    remainder = [index for index in candidates if index not in taken]
    return reserved + remainder


def distinct_rule_representatives(
    payload: dict, *, governing_extras: dict | None = None
) -> tuple[list[int], dict[int, list[int]]]:
    """Which rules of this policy are the same rule, said more than once.

    Returns the representative indices in **document order**, and a map from each
    representative to the indices of its copies.

    The representative is the earliest occurrence, which is deterministic and
    needs no tie-break: document order is a total order the record already
    carries, so the same policy always yields the same representatives and the
    same receipt. Nothing is scored or preferred between copies — they are
    identical in everything the equivalence compares, so there is nothing to
    prefer.

    A rule whose semantics cannot be computed is its own representative and is
    never collapsed. Matching on absence would set a rule aside on the strength
    of what was not recorded about it.
    """

    fingerprints = rule_semantic_fingerprints(payload, governing_extras=governing_extras)
    first_by_fingerprint: dict[str, int] = {}
    copies: dict[int, list[int]] = {}
    representatives: list[int] = []

    for index, fingerprint in enumerate(fingerprints):
        if fingerprint is None:
            representatives.append(index)
            continue
        seen = first_by_fingerprint.get(fingerprint)
        if seen is None:
            first_by_fingerprint[fingerprint] = index
            representatives.append(index)
        else:
            copies.setdefault(seen, []).append(index)

    return representatives, copies


def select_rules_for_scenario(
    payload: dict,
    *,
    policy: dict,
    scenario: str,
    threshold: int = LARGE_POLICY_RULE_THRESHOLD,
    rule_budget: int = SELECTED_RULE_BUDGET,
    budget_chars: int = SLICE_BUDGET_CHARS,
    governing_extras: dict | None = None,
    rule_hits: Mapping[str, int] | None = None,
    rule_projections: Mapping[str, str] | None = None,
    rule_index_state: str = RULE_INDEX_UNAVAILABLE,
) -> tuple[dict, dict]:
    """The record to put in front of the gather, and what was done to get it.

    Returns ``(payload, selection)``. For a policy at or under ``threshold`` the
    payload returned is the **same object** that was passed in and `selection`
    records `whole_policy` — the ordinary case is not merely equivalent, it is
    untouched.

    For a larger policy:

    1. Rules that govern identically to an earlier rule of the same policy are
       collapsed into it first, so a copy can neither take a slot nor distort the
       weighting. Everything after this runs on the representatives.
    2. The survivors are ranked **three ways**, and the three are fused:

       * **lexical** — the inverse-document-frequency score over this policy's
         own rules, against the English projection of each rule when the caller
         has one (:func:`score_rules`);
       * **the rule index** — the rank Azure AI Search gave this rule's own
         document for this question, passed in as ``rule_hits``. This is what
         makes a row past the policy document's retrieval-text ceiling reachable
         at all;
       * **quantity compatibility** — rules stating a quantity that admits a
         quantity the question states (:func:`quantity_compatible`). A question
         about three of something and a schedule row covering two to six of the
         same thing match on their numbers even when they share few words.

       Fusion is reciprocal rank (:func:`fuse_rankings`) and ties break on
       document order, so the same question against the same version and index
       always selects the same rules. A ranking that placed a rule contributes;
       one that did not is silent rather than negative.
    3. Only rules some ranking placed are taken, up to ``rule_budget``, offered
       through the evidence-diversity **quota** (:func:`order_with_evidence_quota`)
       — passage diversity is guaranteed for half the budget and the rest is
       filled on fused rank, so a second strongly relevant rule from a passage
       already covered is reachable.
    4. If nothing places, the first ``rule_budget`` rules in document order are
       taken instead and the method says so. The policy is never dropped for a
       lexical miss.
    5. The selected slice is measured. **If it alone exceeds ``budget_chars`` it
       is returned as it is**, marked oversize, and no context is added — the
       honest refusal downstream is the right answer, and trimming to fit would
       be the one thing this must not do. The context it did not follow is still
       named, so `context_rules_omitted` means the same thing on every path.
    6. Otherwise each selected rule's explicit context is offered, in rank order,
       and admitted only while there is **both a free rule slot and room in
       characters**. Context fills the slots the selection left unused; it never
       extends ``rule_budget``. One that cannot be admitted, for either reason, is
       named in `context_rules_omitted` rather than dropped in silence, and later,
       smaller context rules are still tried.

    The invariant this guarantees, and the reason step 6 is written that way:
    ``selected_rules == len(selected_rule_ids) <= rule_budget`` on every path, so
    the number a receipt reports as the budget is the number that actually
    bounded the record a gather read.

    ``rule_hits``, ``rule_projections`` and ``rule_index_state`` are all optional and
    all default to "the rule index was not consulted". Left alone, this function
    behaves exactly as it did: one lexical ranking over the policy's own stored
    words, `scenario_relevance_v2`, and the same selection. That is what the
    single-policy scope gets, and it is why naming a policy still works when the
    project index does not.
    """

    rules = list(payload.get("rules") or [])
    total = len(rules)

    if total <= threshold:
        return payload, {
            "total_rules": total,
            "selected_rules": total,
            "selected_rule_ids": [str(rule.get("rule_id")) for rule in rules],
            "rules_discarded": 0,
            "method": METHOD_WHOLE_POLICY,
            "sliced": False,
            "context_rules_added": 0,
            "context_rules_omitted": [],
            "chars": _record_chars(policy, payload),
            "budget_chars": budget_chars,
            "oversize": False,
            "duplicate_rules_collapsed": 0,
            "represented_rule_ids": [],
        }

    # A policy can hold the same rule several times, and a copy is not a second
    # rule. Collapsed *before* scoring, for two reasons: a copy must not take a
    # second selection slot, and the relevance weighting is an inverse document
    # frequency over this policy's own rules — so a row repeated four times has
    # its distinguishing terms discounted four times over and sinks beneath rows
    # that are merely wordy. Scoring the distinct rules repairs both at once.
    representatives, copies = distinct_rule_representatives(
        payload, governing_extras=governing_extras
    )
    representative_of = {index: index for index in representatives}
    for representative, duplicated in copies.items():
        for index in duplicated:
            representative_of[index] = representative

    distinct_payload = build_slice(payload, [rules[i] for i in representatives])
    distinct_scores = score_rules(distinct_payload, scenario, rule_projections=rule_projections)
    scores = {index: distinct_scores[k] for k, index in enumerate(representatives)}

    # ── ranking one: lexical, over whichever corpus the caller supplied ──
    # Only rules that actually scored are ranked. A zero-scoring rule has no
    # lexical evidence, and giving it a reciprocal-rank contribution would let
    # document order enter the fusion dressed as relevance.
    lexical_order = [
        index
        for index in sorted(representatives, key=lambda i: (-scores[i], i))
        if scores[index] > 0
    ]
    lexical_ranks = dense_ranks(lexical_order)

    # ── ranking two: the rule index's own ranking of these rules ─────────
    # A hit naming a rule that was collapsed into another is credited to the
    # representative that stands for it, at the best rank any of the group
    # achieved: the record holds that rule, under that id.
    index_ranks: dict[int, int] = {}
    if rule_hits:
        by_rule_id = {
            str(rule.get("rule_id")): position
            for position, rule in enumerate(rules)
            if rule.get("rule_id")
        }
        for rule_id, rank in rule_hits.items():
            position = by_rule_id.get(str(rule_id))
            if position is None:
                continue
            target = representative_of.get(position, position)
            if target not in index_ranks or rank < index_ranks[target]:
                index_ranks[target] = int(rank)
        index_ranks = dense_ranks(
            [index for index, _ in sorted(index_ranks.items(), key=lambda kv: (kv[1], kv[0]))]
        )

    # ── ranking three: quantities the question and the rule share ────────
    scenario_scalars = quantity_scalars(scenario)
    spans = payload.get("spans") or {}
    facts = payload.get("facts") or {}
    quantity_order: list[int] = []
    if scenario_scalars:
        for index in representatives:
            rule_id = str(rules[index].get("rule_id"))
            text = (
                rule_projections.get(rule_id)
                if rule_projections is not None and rule_id in rule_projections
                else rule_text(rules[index], spans=spans, facts=facts)
            )
            if quantity_compatible(scenario_scalars, _structured_quantity_text(rules[index], text)):
                quantity_order.append(index)
    quantity_ranks = dense_ranks(quantity_order)

    fused = fuse_rankings([lexical_ranks, index_ranks, quantity_ranks])
    ordered = sorted(fused, key=lambda i: (-fused[i], i))

    if ordered:
        chosen = order_with_evidence_quota(
            ordered,
            evidence_group_keys(payload),
            quota=evidence_diversity_quota(rule_budget),
            budget=rule_budget,
        )[:rule_budget]
        method = _selection_method(rule_index_state)
    else:
        # No ranking placed anything. Document order is the honest fallback and
        # is left exactly as it was: with nothing scoring, there is no evidence
        # that one ordering serves the reader better than the document's own.
        chosen = representatives[:rule_budget]
        method = METHOD_DOCUMENT_ORDER

    by_id = {str(rule.get("rule_id")): index for index, rule in enumerate(rules) if rule.get("rule_id")}
    selected_indices = list(chosen)
    selected_ids = [str(rules[i].get("rule_id")) for i in selected_indices]

    retrieval_counters = {
        "rule_index_state": rule_index_state,
        "rule_index_hits": len(index_ranks),
        "lexical_candidates": len(lexical_ranks),
        "quantity_candidates": len(quantity_ranks),
        "fused_candidates": len(fused),
        "evidence_diversity_quota": evidence_diversity_quota(rule_budget),
        "rules_without_projection": (
            sum(1 for index in representatives if str(rules[index].get("rule_id")) not in rule_projections)
            if rule_projections is not None
            else 0
        ),
    }

    def _represented(indices: list[int]) -> list[str]:
        """Ids not read, that did not need to be: exact copies of ones that were.

        `rules_discarded` counts every rule the record does not hold, which is
        the truth but reads as "unknown content". These are the part of it a
        reader can stop worrying about — each says exactly what a selected rule
        says — so naming them makes the receipt more informative without
        claiming any of them was read.
        """

        out: list[str] = []
        for index in sorted(indices):
            for duplicate in copies.get(index, []):
                rule_id = rules[duplicate].get("rule_id")
                if rule_id is not None:
                    out.append(str(rule_id))
        return out

    # The context the selection would like, in the order the selected rules were
    # chosen, so which context survives a tight budget is as reproducible as the
    # selection itself. Computed before the oversize check so that every return
    # path can say which links it did not follow. A link naming a copy is
    # followed to that copy's representative: the rule it names *is* in the
    # record, under the id that stands for it.
    wanted: list[int] = []
    for index in selected_indices:
        for rule_id in _context_ids(rules[index]):
            target = by_id.get(rule_id)
            if target is None:
                continue
            target = representative_of.get(target, target)
            if target not in selected_indices and target not in wanted:
                wanted.append(target)

    primary = build_slice(payload, [rules[i] for i in selected_indices])
    primary_chars = _record_chars(policy, primary)

    if primary_chars > budget_chars:
        # The rules that bear on the question do not themselves fit. There is no
        # smaller truth: dropping some of them would answer from part of the
        # relevant slice while presenting as the slice, so the record is returned
        # as it is and refused downstream, whole.
        return primary, {
            "total_rules": total,
            "selected_rules": len(selected_ids),
            "selected_rule_ids": selected_ids,
            "rules_discarded": total - len(selected_ids),
            "method": method,
            "sliced": True,
            "context_rules_added": 0,
            "context_rules_omitted": [str(rules[i].get("rule_id")) for i in wanted],
            "chars": primary_chars,
            "budget_chars": budget_chars,
            "oversize": True,
            "duplicate_rules_collapsed": total - len(representatives),
            "represented_rule_ids": _represented(selected_indices),
            **retrieval_counters,
        }

    kept = list(selected_indices)
    omitted: list[str] = []
    current = primary
    for target in wanted:
        # A free slot first, and only then room in characters. Context is the
        # weaker claim — it is here because a selected rule points at it, not
        # because it bears on the question — so when the selection has taken the
        # whole budget, context takes none of it.
        if len(kept) >= rule_budget:
            omitted.append(str(rules[target].get("rule_id")))
            continue
        trial_indices = sorted(kept + [target])
        trial = build_slice(payload, [rules[i] for i in trial_indices])
        if _record_chars(policy, trial) <= budget_chars:
            kept = trial_indices
            current = trial
        else:
            omitted.append(str(rules[target].get("rule_id")))

    added = [i for i in kept if i not in selected_indices]
    kept_ids = [str(rules[i].get("rule_id")) for i in sorted(kept)]

    # The claim the receipt makes about itself, checked here rather than trusted:
    # the budget bounds the record a gather reads, not one step of building it.
    assert len(kept_ids) <= rule_budget, (
        f"slice put {len(kept_ids)} rules before a gather against a budget of {rule_budget}"
    )

    return current, {
        "total_rules": total,
        "selected_rules": len(kept_ids),
        "selected_rule_ids": kept_ids,
        "rules_discarded": total - len(kept_ids),
        "method": method,
        "sliced": True,
        "context_rules_added": len(added),
        "context_rules_omitted": omitted,
        "chars": _record_chars(policy, current),
        "budget_chars": budget_chars,
        "oversize": False,
        "duplicate_rules_collapsed": total - len(representatives),
        "represented_rule_ids": _represented(kept),
        **retrieval_counters,
    }


def _selection_method(rule_index_state: str) -> str:
    """Which algorithm produced a selection, named rather than described.

    Three claims, and they are different sizes:

      * ``hybrid_rule_v1`` — the rule index took part. The selection fused its
        ranking with the lexical and quantity ones, so a rule the policy
        document's own text could never have surfaced was reachable.
      * ``scenario_relevance_v3`` — rule documents for this policy exist under
        the expected projection, and the query against them failed in a way the
        caller could see and report. The selection is lexical and quantity over
        the English projection, which is a real selection over the right corpus,
        made without one of its rankings.
      * ``scenario_relevance_v2`` — the rule index was not consulted at all. The
        selection ranked the policy's own stored words, which is what this has
        always meant and what a receipt written before the rule index existed
        also means.

    Emitting the wrong one of these would be claiming a ranking that did not run,
    which is the same class of untruth as claiming a rule was read.
    """

    if rule_index_state == RULE_INDEX_MATCHED:
        return METHOD_HYBRID_RULE
    if rule_index_state == RULE_INDEX_DEGRADED:
        return METHOD_RELEVANCE_V3
    return METHOD_RELEVANCE


def _structured_quantity_text(rule: dict, text: str) -> str:
    """The rule's text, plus the quantities it states in structured form.

    A carve-out's `limit_value` and `limit_unit` are a stated quantity that the
    prose around them may not repeat, and a required fact's `unit` names the unit
    a rule measures in even when the threshold itself sits in a sentence. Both
    are already in the record, so the quantity rank reads them from there rather
    than hoping the projection re-stated them — which is what "use the structure
    where there is structure" means here.

    Appended to the text rather than replacing it: an interval stated in a
    sentence is still the most common way a threshold appears, and the pattern
    that recognises it needs the sentence.
    """

    parts = [text]
    for exception in rule.get("exceptions") or []:
        if not isinstance(exception, dict):
            continue
        value = exception.get("limit_value")
        unit = exception.get("limit_unit")
        if value is not None and unit:
            parts.append(f"{value} {unit}")
    for required in rule.get("required_facts") or []:
        if isinstance(required, dict) and required.get("unit"):
            parts.append(str(required["unit"]))
    return " ".join(part for part in parts if part)
