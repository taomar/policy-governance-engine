"""Cross-rule correlation agent: contradiction, overlap, gap and duplicate detection.

Runs *after* extraction, over already-structured rules rather than raw text. It
answers the question a per-rule review cannot: given these rules together, which
pairs contradict, overlap, duplicate, supersede or specialize one another?

Division of labour
------------------
The application decides **which rules to compare**; the model decides **what the
relationship is**. That split is required by Section 86 of the specification
("do not compare every rule blindly... first group candidate rules") and is
forced by arithmetic: a 1,400-rule policy set has roughly a million pairs, so
exhaustive comparison is not merely slow, it is impossible within any budget.

Grouping is therefore deterministic and lives here, in code. It is built from
semantic signals the rules already carry — subject, effect action, decision
output, fact model, business domain — and is deliberately *generous*: a pair
that shares any strong signal is compared. Over-inclusion costs model calls;
under-inclusion silently loses real contradictions, and a missed contradiction
is invisible to the reviewer who would otherwise have caught it.

Section 86 also warns that "candidate grouping must not itself determine
contradiction". Grouping here never classifies anything. Two rules landing in
the same group means only that they are worth looking at together; two rules in
different groups are not asserted to be compatible, merely unexamined — which
is why `analyze_policy_set` reports its coverage rather than implying it was
exhaustive.
"""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError

from policy_platform.contracts.correlation import (
    CorrelationAnalysis,
    CorrelationFinding,
)
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.settings import Settings

logger = logging.getLogger(__name__)

#: Bump whenever the prompt asset or the transport addendum changes.
CORRELATION_PROMPT_VERSION = "contradiction-detector-v1"

#: The specification header mandates medium reasoning effort.
CORRELATION_REASONING_EFFORT = "medium"

_PROMPT_PATH = Path(__file__).parent / "prompts" / "contradiction_detector_v1.md"

#: Maximum rules handed to the model in one call. Every rule in a group is
#: compared against every other, so the model's work grows quadratically while
#: its attention does not. Twelve keeps one group's pairwise comparisons at 66 —
#: large enough to be worth a call, small enough that the model can hold all of
#: them at once rather than skimming.
_MAX_RULES_PER_GROUP = 12

#: A signal shared by more rules than this is not a signal, it is a category.
#: "every rule whose subject is 'employee'" describes an HR manual, not a set of
#: plausibly-conflicting rules, and comparing all of them would spend the entire
#: budget on the least informative comparisons. Such signals are dropped and the
#: rules are reached through their more specific signals instead.
_MAX_RULES_PER_SIGNAL = 60

#: Cap on model calls for one analysis. Lexical signals (below) are generous by
#: design, and an unbounded run over a large policy set would be neither
#: affordable nor finishable. Groups are emitted most-specific-first, so a cap
#: trims the vaguest comparisons rather than a random slice.
_MAX_GROUPS = 400

#: Shortest word treated as content. Below this, English is almost entirely
#: function words that appear in every rule and discriminate nothing.
_MIN_TERM_LENGTH = 4

#: Content terms taken from one rule's text. A long clause yields dozens of
#: words; using all of them makes a rule a member of dozens of signals and the
#: group count explodes. The cap is applied to the longest terms, which are the
#: domain nouns ("compensation", "probationary") rather than the connectives.
_MAX_TERMS_PER_RULE = 12

_WORD_RE = re.compile(r"[a-z0-9]+")

#: Words that carry no distinguishing meaning in a policy subject or action.
#: Without this, "the employee" and "an employee" produce different signals and
#: two rules about the same subject are never compared.
_STOPWORDS = frozenset(
    {
        "a", "an", "the", "of", "for", "to", "in", "on", "at", "by", "with",
        "and", "or", "any", "all", "each", "every", "such", "shall", "must",
        "may", "will", "be", "is", "are", "who", "that", "this", "these",
        # Added for lexical signals: these are frequent enough in regulatory
        # prose to appear in most rules, so they group rules that have nothing
        # in common and crowd out the terms that do discriminate.
        "from", "not", "have", "has", "been", "than", "then", "into", "upon",
        "which", "their", "there", "where", "when", "shall", "under", "other",
        "case", "cases", "accordance", "provisions", "provision", "article",
        "articles", "pursuant", "subject", "following", "above", "below",
        "unless", "otherwise", "including", "include", "includes", "without",
        "within", "during", "after", "before", "between", "both", "same",
        "said", "its", "his", "her", "they", "them", "shall", "should",
    }
)


_TRANSPORT_ADDENDUM = """

---

# TRANSPORT ADDENDUM (application-supplied)

## How the rules are supplied

You receive a JSON object with a `canonical_policies` array, in the Section 2
shape. The rules have been pre-grouped by the application as plausible
comparison candidates (Section 86). That grouping is NOT evidence of conflict:
it means only that these rules were worth examining together.

## Addressing

Refer to rules ONLY by their zero-based position in the supplied
`canonical_policies` array, via `policy_indexes` and `evidence[].policy_index`.

Never invent, guess or echo a rule identifier. The application resolves indexes
back to identifiers itself, so an index is sufficient and an identifier is not
checkable.

## Completeness

Analyse every pair in the supplied array. If a pair has no meaningful
relationship, you may omit it or classify it INDEPENDENT — but do not omit a
pair because you are unsure: classify it AMBIGUOUS_CONFLICT and list what
would settle it in `requirements`.

## Output

Return exactly one JSON object in the Section 79 shape, and nothing else:

{
  "policy_conflict_analysis": {
    "summary": { ... },
    "findings": [ ... ]
  }
}

No prose. No markdown fences. No commentary before or after the object.
"""


@lru_cache(maxsize=1)
def load_correlation_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8").rstrip() + _TRANSPORT_ADDENDUM


class CorrelationError(RuntimeError):
    """The agent's reply could not be read as a valid correlation analysis."""


def _tokens(value: str) -> list[str]:
    return [w for w in _WORD_RE.findall(value.lower()) if w not in _STOPWORDS]


def _normalize_phrase(value: str) -> str:
    """Reduce a phrase to a comparable key.

    Sorted rather than sequential because "approval of the manager" and
    "manager approval" name the same thing, and a signal that treats them as
    different would never bring the two rules together.
    """

    tokens = _tokens(value)
    return " ".join(sorted(set(tokens)))


def _content_terms(payload: dict) -> set[str]:
    """Distinctive words from the rule's own text.

    Bigrams are included alongside single words because "annual leave" and
    "sick leave" share a word that means little on its own; the pair is what
    identifies the subject. Single words are kept too, so a rule phrasing the
    same subject differently ("leave, annual") is still reachable.
    """

    parts = [
        str(payload.get("title") or ""),
        str((payload.get("effect") or {}).get("action") or ""),
        str(payload.get("statement") or ""),
    ]
    words = [w for part in parts for w in _tokens(part) if len(w) >= _MIN_TERM_LENGTH]
    if not words:
        return set()

    bigrams = {f"{a} {b}" for a, b in zip(words, words[1:]) if a != b}
    # Longest-first: domain nouns carry the subject, short residual words do not.
    ranked = sorted(set(words), key=lambda w: (-len(w), w))[:_MAX_TERMS_PER_RULE]
    return set(ranked) | set(sorted(bigrams)[:_MAX_TERMS_PER_RULE])


def rule_signals(payload: dict) -> set[str]:
    """Semantic dimensions on which a rule might collide with another.

    Each signal is namespaced by dimension so an action named "leave" cannot
    collide with a tag named "leave" — an accidental match wastes a comparison
    and, worse, makes the grouping look better-targeted than it is.
    """

    signals: set[str] = set()

    effect = payload.get("effect") or {}
    action = _normalize_phrase(str(effect.get("action") or ""))
    if action:
        signals.add(f"action:{action}")
        effect_type = str(effect.get("type") or "").lower()
        if effect_type:
            # Action alone groups "grant leave" with "deny leave", which is
            # exactly the pair most likely to contradict, so the un-typed signal
            # is kept as well as the typed one.
            signals.add(f"effect:{effect_type}:{action}")

    scope = payload.get("scope") or {}
    for persona in scope.get("personas") or []:
        normalized = _normalize_phrase(str(persona))
        if normalized:
            signals.add(f"subject:{normalized}")
    for unit in scope.get("organizational_units") or []:
        normalized = _normalize_phrase(str(unit))
        if normalized:
            signals.add(f"org:{normalized}")
    for process in scope.get("processes") or []:
        normalized = _normalize_phrase(str(process))
        if normalized:
            signals.add(f"process:{normalized}")

    # The fact model is the strongest available signal: two rules that read the
    # same facts are deciding on the same inputs, which is what makes an
    # inconsistent outcome possible in the first place.
    for fact in payload.get("required_facts") or []:
        name = str(fact.get("name") or "").strip().lower()
        if name:
            signals.add(f"fact:{name}")

    group_label = _normalize_phrase(str(payload.get("group_label") or ""))
    if group_label:
        signals.add(f"group:{group_label}")

    for tag in payload.get("tags") or []:
        normalized = _normalize_phrase(str(tag))
        if normalized:
            signals.add(f"tag:{normalized}")

    for aggregate in payload.get("aggregate_limits") or []:
        aggregate_id = str(aggregate.get("aggregate_id") or "").strip().lower()
        if aggregate_id:
            # Rules contributing to one combined cap interact by definition.
            signals.add(f"aggregate:{aggregate_id}")

    # Lexical fallback.
    #
    # Everything above assumes the rule carries structured semantic metadata.
    # Measured against real extracted corpora that assumption does not hold: of
    # 156 rules extracted from the Saudi Labour Law, none had tags, personas or
    # a fact model, and `effect.action` was a whole clause rather than a short
    # normalized phrase — so `_normalize_phrase` produced a unique key per rule
    # and nothing was ever grouped.
    #
    # That is a property of source documents, not of one extraction: prose
    # legislation states obligations in sentences and does not label them. A
    # grouping strategy that only works on richly-tagged rules is a grouping
    # strategy that does not work, so subject terms are also taken from the text
    # the rule always has. Individually these are weak signals; the frequency
    # filter in `group_rules_for_comparison` is what makes them useful, by
    # keeping only terms shared by a few rules and discarding both the unique
    # and the ubiquitous.
    for term in _content_terms(payload):
        signals.add(f"term:{term}")

    return signals


def groupable_rule_ids(
    rules: list[tuple[str, dict]],
    *,
    max_rules_per_signal: int = _MAX_RULES_PER_SIGNAL,
) -> set[str]:
    """Rules that share a usable comparison signal with at least one other rule.

    This answers "could this rule ever be compared?", which is a different
    question from "was it compared on this run?" — the latter also depends on
    the group budget. Keeping them apart matters because the two causes call for
    opposite responses from a reviewer: a rule that genuinely stands alone is
    nothing to act on, while a rule dropped by the budget means the analysis was
    truncated and re-running with a larger budget would cover more.

    Computed from the signal buckets directly rather than from the returned
    groups, so it is unaffected by the budget by construction.
    """

    by_signal: dict[str, list[str]] = defaultdict(list)
    for rule_id, payload in rules:
        for signal in rule_signals(payload):
            by_signal[signal].append(rule_id)

    groupable: set[str] = set()
    for members in by_signal.values():
        # A signal shared by only one rule compares against nothing; one shared
        # by more rules than the per-signal ceiling is too vague to be useful and
        # is skipped by the grouper, so neither makes a rule groupable.
        if 2 <= len(members) <= max_rules_per_signal:
            groupable.update(members)
    return groupable


def group_rules_for_comparison(
    rules: list[tuple[str, dict]],
    *,
    max_group_size: int = _MAX_RULES_PER_GROUP,
    max_rules_per_signal: int = _MAX_RULES_PER_SIGNAL,
    max_groups: int = _MAX_GROUPS,
) -> list[list[tuple[str, dict]]]:
    """Bucket rules into plausible comparison groups.

    `rules` is a list of `(rule_id, canonical payload)`. Returns groups of at
    least two rules; a rule sharing no signal with any other is not returned,
    because there is nothing to compare it against.

    Groups may overlap, and a pair may appear in more than one group. That is
    accepted rather than deduplicated: two rules sharing several signals are
    precisely the pairs most likely to conflict, and the caller suppresses
    duplicate *findings* afterwards, which is cheaper than reasoning about
    which single group a pair "belongs" to.
    """

    by_signal: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for rule_id, payload in rules:
        for signal in rule_signals(payload):
            by_signal[signal].append((rule_id, payload))

    groups: list[list[tuple[str, dict]]] = []
    seen_group_keys: set[frozenset[str]] = set()

    # Most specific first, then alphabetically. A signal shared by three rules
    # says far more about them than one shared by fifty, so when the group
    # budget runs out it should be the vaguest comparisons that are dropped.
    # The alphabetical tiebreak keeps this deterministic (Section 114): the same
    # policy set must produce the same groups, and so the same findings, on
    # every run.
    ordered = sorted(by_signal, key=lambda s: (len(by_signal[s]), s))

    for signal in ordered:
        if len(groups) >= max_groups:
            break
        members = by_signal[signal]
        if len(members) < 2 or len(members) > max_rules_per_signal:
            continue
        for start in range(0, len(members), max_group_size):
            chunk = members[start : start + max_group_size]
            if len(chunk) < 2:
                # A trailing chunk of one would silently drop that rule from
                # this signal entirely. Back the window up so the straggler is
                # compared against the rules it shares the signal with; the
                # resulting overlap costs one repeated pair, which the finding
                # deduplication absorbs.
                chunk = members[-min(max_group_size, len(members)) :]
                if len(chunk) < 2:
                    continue
            key = frozenset(rule_id for rule_id, _ in chunk)
            if key in seen_group_keys:
                continue
            seen_group_keys.add(key)
            groups.append(chunk)

    return groups


def _render_rule(payload: dict) -> dict:
    """Project a canonical rule into the Section 2 input shape.

    Only fields the specification names are sent. Section 90 forbids inventing a
    missing property, and the surest way to stop a model inventing one is not to
    show it a half-populated field it feels obliged to complete.
    """

    effect = payload.get("effect") or {}
    scope = payload.get("scope") or {}
    authority = payload.get("authority") or {}
    subject = ", ".join(str(p) for p in (scope.get("personas") or []))

    rule: dict = {
        "rule_type": payload.get("rule_type"),
        "subject": subject,
        "modality": effect.get("type"),
        "predicate": effect.get("action"),
    }
    if payload.get("condition"):
        rule["condition"] = payload["condition"]
    exceptions = payload.get("exceptions") or []
    if exceptions:
        rule["exception"] = [e.get("description") for e in exceptions if e.get("description")]

    record: dict = {
        "policy_id": payload.get("rule_id"),
        "rule": rule,
    }
    if payload.get("title"):
        record["title"] = payload["title"]
    if payload.get("description"):
        record["source_text"] = payload["description"]
    if payload.get("category"):
        record["domain"] = payload["category"]
    if payload.get("effective_from"):
        record["effective_date"] = payload["effective_from"]
    if payload.get("effective_to"):
        record["effective_to"] = payload["effective_to"]
    if authority.get("level"):
        record["authority_level"] = authority["level"]
    if authority.get("rank") is not None:
        record["authority_rank"] = authority["rank"]
    if payload.get("priority"):
        record["priority"] = payload["priority"]
    if payload.get("supersedes_rule_ids"):
        record["supersedes"] = payload["supersedes_rule_ids"]
    return record


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    fenced = re.match(r"^```(?:json)?\s*\n(.*?)\n?```\s*$", stripped, re.DOTALL)
    return fenced.group(1).strip() if fenced else stripped


def parse_analysis(raw: str) -> CorrelationAnalysis:
    """Turn one agent reply into a validated `CorrelationAnalysis`."""

    text = _strip_code_fence(raw)
    if not text:
        raise CorrelationError("correlation agent returned an empty response")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CorrelationError(f"correlation agent returned unparseable output: {exc}") from exc

    if not isinstance(payload, dict):
        raise CorrelationError(
            f"correlation agent returned a {type(payload).__name__}, expected a JSON object"
        )

    # The specification nests the result under `policy_conflict_analysis`, but a
    # model that returns the inner object directly has still answered correctly;
    # rejecting it would discard a good analysis over an envelope.
    body = payload.get("policy_conflict_analysis", payload)
    if not isinstance(body, dict):
        raise CorrelationError("correlation agent returned a malformed analysis envelope")

    try:
        return CorrelationAnalysis.model_validate(body)
    except ValidationError as exc:
        raise CorrelationError(f"correlation output failed contract validation: {exc}") from exc


def resolve_indexes(
    analysis: CorrelationAnalysis, rule_ids: list[str]
) -> tuple[list[CorrelationFinding], list[str]]:
    """Replace batch positions with rule identifiers.

    Returns `(resolved, problems)`. A finding whose index is out of range is
    dropped rather than clamped: an index the application cannot resolve is a
    statement about rules that were never sent, so there is nothing to attach it
    to and guessing would attribute a contradiction to an innocent rule.
    """

    resolved: list[CorrelationFinding] = []
    problems: list[str] = []

    for finding in analysis.findings:
        indexes = finding.policy_indexes or [e.policy_index for e in finding.evidence]
        if not indexes:
            problems.append(f"finding {finding.finding_id or '?'} referenced no rules")
            continue
        if any(i < 0 or i >= len(rule_ids) for i in indexes):
            problems.append(
                f"finding {finding.finding_id or '?'} referenced out-of-range index "
                f"{[i for i in indexes if i < 0 or i >= len(rule_ids)]}"
            )
            continue

        finding.rule_ids = [rule_ids[i] for i in indexes]
        for evidence in finding.evidence:
            if 0 <= evidence.policy_index < len(rule_ids):
                evidence.rule_id = rule_ids[evidence.policy_index]
        resolved.append(finding)

    return resolved, problems


def finding_key(finding: CorrelationFinding) -> tuple:
    """Identity of a finding, for suppressing repeats across overlapping groups.

    Rule ids are sorted because "A contradicts B" and "B contradicts A" are one
    finding, and the classification is included because the same pair can
    legitimately hold two different relationships worth reporting separately.
    """

    return (tuple(sorted(finding.rule_ids)), finding.classification)


class CorrelationAgent:
    """Analyses relationships between rules. Stateless apart from its client."""

    def __init__(self, client: AzureOpenAIClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    async def analyze_group(
        self, rules: list[tuple[str, dict]]
    ) -> tuple[list[CorrelationFinding], list[str]]:
        """Analyse one comparison group. Returns `(findings, problems)`."""

        if len(rules) < 2:
            raise CorrelationError("correlation analysis needs at least two rules")

        rule_ids = [rule_id for rule_id, _ in rules]
        payload = {"canonical_policies": [_render_rule(p) for _, p in rules]}

        raw = await self._client.chat(
            [
                {"role": "system", "content": load_correlation_prompt()},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
            ],
            deployment=self._settings.azure_openai_deployment,
            json_mode=True,
            max_tokens=16000,
            timeout=300.0,
            reasoning_effort=CORRELATION_REASONING_EFFORT,
        )

        analysis = parse_analysis(raw)
        findings, problems = resolve_indexes(analysis, rule_ids)
        if problems:
            logger.warning("correlation: %d unusable findings: %s", len(problems), problems[:3])
        return findings, problems
