"""Explaining, in plain words, what one policy's extracted record says.

A reviewer opening a policy card sees a heading the document wrote and a list of
rules this system decomposed out of it. Between those two things sits work the
reviewer has to do in their head: read six structured records and reconstruct
what the passage actually requires. This module does that reconstruction and
hands it back as a few sentences.

WHAT THE MODEL IS SHOWN, AND THE ONE THING IT IS NOT

It is shown the **extracted record** — each rule's title and the core fields the
extraction populated. It is **not** shown the document's verbatim source text,
and that omission is the whole design rather than a budget saving.

The reviewer's question is not "what does this passage say"; they can read the
passage. It is "is our decomposition faithful to it". An explanation written
from the source text answers the first question and quietly forecloses the
second: shown both the record and the words it came from, a model reconciles
them, and an extraction that dropped a condition or mistook a threshold reads
back as correct because the model repaired it from the source on the way past.
The reviewer is then reassured by a sentence that was never evidence about the
thing they were checking.

Shown the record alone, the model can only say what the record says. Set beside
the verbatim source — which the popup keeps in front of the reader, and which is
the reason `explain_provision` returns `stated_text` it never sent anywhere —
agreement and disagreement both become visible. So the explanation is a
back-translation, and its value to a reviewer is highest exactly when it is
wrong, because a wrong explanation of a record is a correct report of a bad
record.

This also settles "it explains, it does not add" by construction rather than by
instruction. A model that was never shown the document cannot import a fact from
it, whatever the prompt does or does not say. The prompt asks anyway, because
the model can still invent, but the source of the largest and least detectable
class of addition has been removed rather than forbidden.

WHY THE ROUTES ARE NOT MENTIONED

Whether a rule's test is computable or is stated in words is a property of the
sentence the document wrote. It is not a property this explanation has any
occasion to raise, and a model given the vocabulary will reach for it — the
generated-label work already found a prompt's later lines dominating its earlier
ones badly enough to change the *language* of a reply. So the routes are absent
from the prompt, and `_names_a_route` rejects a reply that names one anyway.
Absent from the question and refused in the answer is two independent defences,
which is what the subject warrants: the framing guards in this repository scan
source files, and no guard in it can see a sentence a model wrote at runtime.

CACHING, AND WHY STALENESS CANNOT ARISE HERE

Generated on demand, and kept against a digest of the exact record explained. A
record that has since been edited digests differently, so a cached explanation
of it is never found and never served — the reviewer cannot read a description
of a record that no longer exists, rather than being warned they might be. The
entry carries `generated_at` so the popup can say when the words were made.

Deliberately in memory and not a table. The label needed persistence because a
card renders it unasked on every policy in the queue; an explanation is asked
for one policy at a time by someone waiting for it, and a table would cost a
migration to a schema other work is actively landing on. `source_digest` is
stored on the entry in the same shape `ProvisionTopicLabel` stores it, so
promoting this to a table later is a move, not a redesign.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import CandidateRule, DocumentProvision
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

#: Which instruction produced an explanation. Bumped whenever the prompt
#: changes, so words written under a superseded instruction are recognisable
#: rather than assumed to satisfy today's rule.
PROMPT_VERSION = "policy-explain-v1"

#: Why there is no explanation, when an attempt produced none.
#:
#: Codes and never sentences, for the reason `provision_topic_label` gives: a
#: stored sentence cannot be re-worded for the reader, and cannot be told apart
#: later from something a document stated.
UNAVAILABLE_NO_RECORD = "no_record_to_explain"
UNAVAILABLE_MODEL_FAILED = "model_call_failed"
UNAVAILABLE_REPLY_UNUSABLE = "reply_unusable"
UNAVAILABLE_DECLINED = "reply_declined_to_explain"
UNAVAILABLE_NAMED_A_ROUTE = "reply_named_a_decision_route"
UNAVAILABLE_NOT_SHORTER = "reply_no_shorter_than_the_source"
UNAVAILABLE_NOTHING_TO_ASSEMBLE = "record_states_a_single_rule"

#: How many rules a record must hold before an explanation is offered at all.
#:
#: NOT A TUNED THRESHOLD, AND NOT TAKEN FROM ANY CORPUS. It is the boundary
#: between assembling and not assembling, which is structural.
#:
#: What this feature does is reassemble a decomposition. A policy holding six
#: records makes a reader reconstruct one arrangement out of six fragments, and
#: doing that for them is worth a model call. A policy holding one record has
#: nothing to reassemble: the explanation can only be that single statement
#: said again, and it is said again *beside the statement itself*, in prose that
#: is ours, in a card whose whole purpose is to let someone check our words
#: against the document's.
#:
#: Measured before this was added, and the measurement is why it exists. Three
#: single-rule policies produced, in each case, the source sentence with two or
#: three words exchanged — one differed from the document only in replacing
#: "considering" with "because". A reader glancing at that sees the evidence
#: twice and has no way to know which copy is authoritative, which is the exact
#: harm the whole card is built to prevent. A near-copy of evidence is worse
#: than no explanation, so below this the button reports that there is nothing
#: to assemble rather than spending a call to produce a paraphrase.
MIN_RULES_TO_ASSEMBLE = 2

#: What the model may answer instead of explaining. Offered so that "this record
#: does not support an explanation" has a way to be said; without it the only
#: available move is to write something, and a model with no way to decline
#: invents rather than declining.
DECLINE_REPLY = "NONE"

#: How much of a policy's record the model reads. A budget, so that a section
#: running to dozens of rules costs one bounded request rather than an unbounded
#: one. Truncation is by whole rules and never mid-rule: half a record is a
#: different record, and the model would be describing something the extraction
#: does not hold.
MAX_RECORD_CHARS = 6000

#: One re-ask on an unusable reply, matching `provision_topic_label`. A decline
#: is not re-asked — see the loop in `generate_explanation`.
ASK_ATTEMPTS = 2

#: How many explanations are kept. A bound rather than a policy about age: the
#: entries are keyed by a digest of what they explain, so none of them can go
#: stale, and the only reason to drop one is that memory is finite.
CACHE_ENTRIES = 256

#: Core fields carrying what a rule actually decides, in reading order.
#:
#: An explicit sequence rather than whatever order a payload's keys happen to
#: take, so the same record always produces the same request and the same
#: request always produces the same cache key. Populated fields only ever appear
#: in this order; a field the extraction left empty appears not at all, because
#: telling the model a field is empty invites it to explain the emptiness.
#:
#: The list drives *sequence*, never *inclusion*: anything else the extraction
#: populated follows in a stable order, so a field added to the contract later
#: reaches the reader without this constant being edited. A display list used as
#: a filter is a way of hiding part of the record from the person checking it.
STATED_FIELDS: tuple[str, ...] = (
    "subject",
    "modality",
    "predicate",
    "object",
    "actor",
    "beneficiary",
    "trigger",
    "condition",
    "constraint",
    "threshold",
    "unit",
    "currency",
    "temporal_constraint",
    "frequency",
    "deadline",
    "location",
    "prerequisite",
    "exception",
    "sequence",
    "consequence",
    "remedy",
    "calculation",
)

#: Words naming how a record's test is decided.
#:
#: Held as word sequences and joined at use, for the reason
#: `apps/web/src/routeNotFault.test.ts` sets out at length: written adjacently,
#: two of these are character-for-character phrasings that
#: `tests/unit/test_no_readiness_framing.py` forbids in a string literal, and
#: that guard cannot tell a phrase quoted as data from one written as language.
#: Its rule is right and is why it catches real violations, so this file plants
#: no such string for it to find.
_ROUTE_WORDS: tuple[tuple[str, ...], ...] = (
    ("deterministic",),
    ("machine", "executable"),
    ("executable",),
    ("automatable",),
    ("ai", "ready"),
    ("documentation", "only"),
    ("manual", "review"),
)


def _route_pattern() -> re.Pattern[str]:
    """A matcher for route vocabulary, however a reply happens to spell it.

    Built at import from the atoms above so that the hyphenated, spaced and
    underscored spellings are all covered without any of them being written
    down. Word-bounded at both ends, so a longer word that merely contains one
    of these is not a match.
    """

    alternatives = [r"[-_ ]".join(words) for words in _ROUTE_WORDS]
    return re.compile(rf"\b(?:{'|'.join(alternatives)})\b", re.IGNORECASE)


_ROUTE_RE = _route_pattern()


def _names_a_route(text: str) -> bool:
    """Whether a reply reached for the vocabulary of decision routes.

    The prompt never mentions them, so any appearance is the model supplying a
    frame nobody asked for — and the frame it supplies unprompted is the one
    where a rule stated in words is the lesser rule. Refused rather than
    rewritten: an explanation is a whole piece of reasoning, and deleting a
    clause from it leaves the reasoning that produced the clause in place.
    """

    return bool(_ROUTE_RE.search(text))


@dataclass(frozen=True)
class RuleFacts:
    """What one rule's record states, and the words it was drawn from.

    `stated` and `stated_text` travel together and go to different places.
    `stated` is the decomposition and is what the model is shown; `stated_text`
    is the document's verbatim sentence, is returned to the reader, and is never
    sent anywhere. Keeping them on one object is what makes it possible for a
    caller to hand a reviewer both halves of the comparison at once.
    """

    rule_id: str
    title: str
    stated: "OrderedDict[str, str]" = field(default_factory=OrderedDict)
    effect: str = ""
    #: The document's own sentence. Never sent to the model — see the module
    #: docstring. Returned so the popup can put it beside the explanation.
    stated_text: str = ""

    @property
    def for_model(self) -> dict:
        """This rule as the model sees it: the record, and nothing else."""

        out: dict = {"title": self.title}
        if self.stated:
            out["states"] = dict(self.stated)
        if self.effect:
            out["effect"] = self.effect
        return out


@dataclass(frozen=True)
class ExplainSource:
    """Exactly what one explanation is generated from, and a digest of it.

    The digest covers what the model is shown and the instruction in force. Two
    requests that would produce the same answer therefore share a key, and any
    edit to the record — or to the prompt — produces a different one.
    """

    heading_path: tuple[str, ...]
    rules: tuple[RuleFacts, ...]
    #: How many rules the policy holds, including any the budget excluded.
    rule_count: int
    #: The language the reader asked the reading to come back in, as a BCP-47
    #: tag — or None for the model's own, which is the heading's. Pre-validated
    #: by `build_source`; part of the digest only when set, so a request that
    #: names no language keys exactly as it did before this field existed and
    #: shares every cache entry already written under that key.
    answer_language: str | None = None

    @property
    def covered_rule_count(self) -> int:
        return len(self.rules)

    @property
    def is_complete(self) -> bool:
        """Whether every rule of the policy reached the model."""

        return self.covered_rule_count == self.rule_count

    @property
    def request_body(self) -> str:
        """The user message: the heading chain, and the rules' records.

        The heading is included because it is the document's own name for what
        follows and is the only thing here that orients the model in a document
        it is otherwise seeing one fragment of. It is marked as the document's
        so that a model asked to describe "the record" does not narrate the
        heading as though the extraction had produced it.
        """

        return json.dumps(
            {
                "heading_stated_by_the_document": list(self.heading_path),
                "extracted_rules": [rule.for_model for rule in self.rules],
            },
            ensure_ascii=False,
            indent=2,
        )

    @property
    def digest(self) -> str:
        payload = f"{PROMPT_VERSION}\n{self.request_body}"
        # Appended only when a language was actually asked for. A None must leave
        # the payload — and so every cached key — byte-for-byte what it was
        # before this field existed; a distinct language earns a distinct key, so
        # one language's reading is never handed back in place of another's.
        if self.answer_language:
            payload = f"{payload}\n{self.answer_language}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @property
    def is_empty(self) -> bool:
        return not any(rule.stated or rule.effect or rule.title for rule in self.rules)

    @property
    def narrated_length(self) -> int:
        """The size of the material an explanation would be standing in for.

        The document's own sentences, deduplicated — not the decomposed fields.
        The referent matters and getting it wrong made this bound useless once
        already: measured against the decomposition, a single rule allows an
        explanation about as long as its own source sentence, which is precisely
        the paraphrase the bound exists to refuse. What an explanation saves a
        reader is *reading the source*, so the source is what it is measured
        against.

        Deduplicated because rules of one passage record overlapping spans — a
        four-rule passage often carries the same sentence four times — and
        counting it four times would quadruple the allowance for no extra
        content.
        """

        seen: list[str] = []
        for rule in self.rules:
            text = rule.stated_text.strip()
            if not text or any(text in other for other in seen):
                continue
            seen = [other for other in seen if other not in text]
            seen.append(text)
        return sum(len(text) for text in seen)


def _stated_fields(payload: dict) -> "OrderedDict[str, str]":
    """The populated core fields of one rule, in reading order.

    Ordered by `STATED_FIELDS` first and then by anything else the extraction
    populated, so the sequence is stable across calls and the inclusion is not
    limited by a list this module happens to know about.
    """

    formulation = (payload or {}).get("formulation") or {}
    canonical = formulation.get("canonical") or {}
    core = canonical.get("rule") or {}
    if not isinstance(core, dict):
        return OrderedDict()

    def usable(name: str) -> str:
        value = core.get(name)
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
        return ""

    stated: "OrderedDict[str, str]" = OrderedDict()
    remaining = sorted(key for key in core if key not in STATED_FIELDS)
    for name in (*STATED_FIELDS, *remaining):
        if name in {"rule_type", "source_origin"}:
            continue
        value = usable(name)
        if value:
            stated[name] = value
    return stated


def facts_for_rule(payload: dict) -> RuleFacts:
    """One rule's record, split into what the model reads and what it may not."""

    payload = payload or {}
    formulation = payload.get("formulation") or {}
    canonical = formulation.get("canonical") or {}
    effect = payload.get("effect") or {}
    action = effect.get("action") if isinstance(effect, dict) else None

    return RuleFacts(
        rule_id=str(payload.get("rule_id") or ""),
        title=(payload.get("title") or "").strip(),
        stated=_stated_fields(payload),
        effect=(action or "").strip() if isinstance(action, str) else "",
        stated_text=(canonical.get("source_text") or "").strip(),
    )


#: A BCP-47 language tag, matched with `fullmatch` so a trailing newline is a
#: rejection rather than a smuggled line break. The same expression the ask path
#: uses; a copy rather than a shared import because it is one line and the two
#: paths reach different models, so a change meant for one is not silently made
#: to both.
_LANGUAGE_TAG = re.compile(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8}){0,4}")


def _valid_language(tag: str | None) -> str | None:
    """A language tag only when it is well-formed, else None.

    A value that is not a tag is treated as no request at all — no directive is
    appended and the digest is left unchanged — so a malformed or hostile string
    can neither inject a line into the prompt nor split the cache off from the
    reading it should share.
    """

    if tag and _LANGUAGE_TAG.fullmatch(tag):
        return tag
    return None


def build_source(
    heading_path: Sequence[str],
    payloads: Sequence[dict],
    *,
    max_chars: int = MAX_RECORD_CHARS,
    answer_language: str | None = None,
) -> ExplainSource:
    """The input for one policy: its heading chain, and its rules' records.

    A rule holding nothing to explain is dropped rather than sent as an empty
    object, which would ask the model to account for a blank. The budget is
    spent on whole rules in document order, so an explanation that could not
    cover everything covers a prefix a reader can locate rather than an
    arbitrary selection they cannot.
    """

    facts = [facts_for_rule(payload) for payload in payloads]
    usable = [rule for rule in facts if rule.stated or rule.effect or rule.title]

    budget = max_chars
    within: list[RuleFacts] = []
    for rule in usable:
        cost = len(json.dumps(rule.for_model, ensure_ascii=False))
        if cost > budget:
            break
        within.append(rule)
        budget -= cost

    return ExplainSource(
        heading_path=tuple(part for part in (h.strip() for h in heading_path) if part),
        rules=tuple(within),
        rule_count=len(usable),
        answer_language=_valid_language(answer_language),
    )


# The instruction. Ordered deliberately: what you are given, what to write, how
# to write it, and last the constraint that matters most.
#
# Last because last is what a model weighs heaviest. The generated-label work
# established that here rather than in the abstract — its third prompt carried
# the language rule in the middle and produced replies in languages appearing
# nowhere in the corpus, and moving that same sentence to the end eliminated the
# drift entirely without another word changing. So the position at the bottom of
# this prompt is reserved for whichever rule would be worst to lose, and that is
# the rule against adding, because an addition here is an unsourced assertion
# sitting beside verbatim evidence and wearing the same authority.
_EXPLAIN_SYSTEM_PROMPT = """You help someone read a structured record that was \
extracted from a document.

You are given a heading the document wrote, and the rules that were extracted \
from the passage under it. Each rule has a title, the parts the extraction \
identified, and what it says follows.

Write a short plain-language explanation of what this record requires, in the \
language the heading is written in. Cover what it applies to, what it requires \
or permits, and any conditions, limits or exceptions the record states. Where \
several rules describe one arrangement, explain the arrangement rather than \
listing the rules one by one.

Write continuous prose. No headings, no bullet points, no markdown, no bold. Do \
not number the rules. Do not describe the record as a record or refer to \
"rules", "fields" or "the extraction" — write about what it requires, the way \
the document's own reader would need it. Be brief: shorter than the material \
you are given, always, and much shorter where it is long. Say less rather than \
padding.

Answer with exactly {decline} if the record does not hold enough to explain.

The single rule that overrides every other instruction above: say nothing that \
is not in the record you were given. Not a number, not a limit, not a deadline, \
not an obligation, not an exception, however obvious it seems or however \
incomplete the record looks without it. You are not being asked what this kind \
of document usually says. If the record is thin, your explanation is thin. If \
you cannot explain it without supplying something, answer {decline}.""".format(
    decline=DECLINE_REPLY
)


def _explain_language_directive(tag: str) -> str:
    """Ask for the explanation in one language, and move nothing else.

    Shorter than the ask path's twin because this reply carries no quotation to
    protect. The ask path returns the document's own sentences inside its JSON
    and must forbid their translation; this path returns continuous prose in the
    app's own voice, and the document's verbatim sentences are never shown to the
    model (see the module docstring) — they reach the reader from the record
    untouched. So the only thing to say is which language this app's reading is
    written in, named by the tag so the sentence reads the same for a language
    nobody has chosen yet.

    Appended last, after the rule against adding. That rule is written to sit
    last because last is weighed heaviest, and the same finding says a language
    instruction drifts unless it too is last. Both cannot be, so the language
    line restates the rule against adding inside itself rather than displacing
    it: the reading comes back in another language and is still only what the
    record holds, never more.
    """

    return (
        "\n\nLANGUAGE OF YOUR EXPLANATION.\n"
        "The reader has asked for this explanation in the language written as the "
        f'IETF BCP-47 tag "{tag}". Write the whole of it in that language, using '
        "that language's own script, whatever language the heading is written in. "
        "This replaces only the instruction to write in the heading's language. "
        "Everything else holds, the rule against adding above most of all: an "
        "explanation in another language is still only what the record states, "
        "never a word more."
    )


def validate_explanation(reply: str, source: ExplainSource) -> tuple[str | None, str | None]:
    """Whether a reply is usable as an explanation, and why not when it is not.

    Four ways to fail, each returning a code rather than a repaired string. An
    explanation is one piece of reasoning and editing it leaves the reasoning
    that produced the edited part standing; a reviewer is better served by
    nothing than by a sentence this system quietly rewrote.
    """

    text = (reply or "").strip()
    if not text:
        return None, UNAVAILABLE_REPLY_UNUSABLE
    if text.strip(" .").upper() == DECLINE_REPLY:
        return None, UNAVAILABLE_DECLINED
    if _names_a_route(text):
        return None, UNAVAILABLE_NAMED_A_ROUTE

    # An explanation earns its place by being shorter than the words it saves
    # the reader from reading. A bound taken from the shape of the thing rather
    # than from a measured distribution: at equal length it has stopped standing
    # in for the source and has become a second copy of it, competing with the
    # verbatim text for the reader's attention while carrying none of its
    # authority.
    if len(text) > source.narrated_length:
        return None, UNAVAILABLE_NOT_SHORTER

    return text, None


@dataclass(frozen=True)
class ExplainAttempt:
    """What one generation produced, with everything that produced it."""

    explanation: str | None
    unavailable_code: str | None
    model_deployment: str | None
    prompt_version: str
    source_digest: str
    source_rule_count: int
    covered_rule_count: int
    generated_at: datetime

    @property
    def explained(self) -> bool:
        return self.explanation is not None

    def as_dict(self) -> dict:
        return {
            "explanation": self.explanation,
            "unavailable_code": self.unavailable_code,
            "model_deployment": self.model_deployment,
            "prompt_version": self.prompt_version,
            "source_digest": self.source_digest,
            "source_rule_count": self.source_rule_count,
            "covered_rule_count": self.covered_rule_count,
            "generated_at": self.generated_at.isoformat(),
        }


def _attempt(
    source: ExplainSource,
    *,
    explanation: str | None,
    code: str | None,
    deployment: str | None,
) -> ExplainAttempt:
    return ExplainAttempt(
        explanation=explanation,
        unavailable_code=code,
        model_deployment=deployment,
        prompt_version=PROMPT_VERSION,
        source_digest=source.digest,
        source_rule_count=source.rule_count,
        covered_rule_count=source.covered_rule_count,
        generated_at=datetime.now(UTC),
    )


async def generate_explanation(
    source: ExplainSource, *, client: AzureOpenAIClient | None = None
) -> ExplainAttempt:
    """Ask the model to say what one policy's record requires.

    A failure is an outcome and not an exception. The card keeps its heading,
    its rules and their verbatim text whatever happens here, so every failure
    path returns an attempt carrying a code and the caller shows the record.
    """

    settings = get_settings()
    deployment = settings.azure_openai_fast_deployment

    if source.is_empty:
        return _attempt(
            source, explanation=None, code=UNAVAILABLE_NO_RECORD, deployment=None
        )

    # Refused before the call rather than after it. There is no reply that would
    # be usable here, so asking would spend a request to reject its answer — and
    # would put a paraphrase of the evidence one accepted patch away from the
    # reader's screen.
    if source.covered_rule_count < MIN_RULES_TO_ASSEMBLE:
        return _attempt(
            source,
            explanation=None,
            code=UNAVAILABLE_NOTHING_TO_ASSEMBLE,
            deployment=None,
        )

    explanation: str | None = None
    code: str | None = UNAVAILABLE_REPLY_UNUSABLE
    try:
        ask = client or AzureOpenAIClient(settings)
        # The base prompt writes in the heading's language and keeps the rule
        # against adding last. A reader can ask for another language instead;
        # only then is a directive appended, so the default request stays the
        # exact prompt it has always been. Re-checked here rather than trusted
        # from the field, so a source built by hand cannot carry an unvalidated
        # tag into the text.
        system_prompt = _EXPLAIN_SYSTEM_PROMPT
        if source.answer_language and _LANGUAGE_TAG.fullmatch(source.answer_language):
            system_prompt += _explain_language_directive(source.answer_language)
        for attempt_number in range(ASK_ATTEMPTS):
            reply = await ask.chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": source.request_body},
                ],
                deployment=deployment,
                max_tokens=700,
                timeout=90.0,
            )
            explanation, code = validate_explanation(reply, source)
            if explanation is not None:
                break
            # A decline is an answer. Re-asking is asking the same question of
            # the same record hoping for a different reply, which is how a
            # refusal stops meaning anything. Only an unusable reply is
            # re-asked, because that is the one that samples variance.
            if code == UNAVAILABLE_DECLINED:
                break
            if attempt_number + 1 < ASK_ATTEMPTS:
                logger.info(
                    "policy explanation reply was unusable (%s), asking again "
                    "(attempt %d of %d)",
                    code,
                    attempt_number + 2,
                    ASK_ATTEMPTS,
                )
    except Exception as exc:  # noqa: BLE001 - the record stands on its own
        logger.warning("policy explanation generation failed: %s", exc)
        return _attempt(
            source, explanation=None, code=UNAVAILABLE_MODEL_FAILED, deployment=deployment
        )

    return _attempt(source, explanation=explanation, code=code, deployment=deployment)


#: Explanations already generated, keyed by the digest of what they explain.
#:
#: Insertion-ordered and evicted from the front, so the bound is on count and
#: never on age — an entry cannot go stale, because a record that changed
#: digests differently and its old entry is simply never looked up again.
_CACHE: "OrderedDict[str, ExplainAttempt]" = OrderedDict()


def cached(digest: str) -> ExplainAttempt | None:
    attempt = _CACHE.get(digest)
    if attempt is not None:
        _CACHE.move_to_end(digest)
    return attempt


def remember(attempt: ExplainAttempt) -> None:
    """Keep an explanation against the record it explains.

    Only successful attempts are kept. A failure is cheap to repeat and may not
    repeat — a model call that timed out once will likely answer next time — so
    caching one would turn a transient failure into a permanent one for as long
    as the process lives, and the reviewer's button would stop working with no
    way for them to tell why.
    """

    if not attempt.explained:
        return
    _CACHE[attempt.source_digest] = attempt
    _CACHE.move_to_end(attempt.source_digest)
    while len(_CACHE) > CACHE_ENTRIES:
        _CACHE.popitem(last=False)


def _forget_all() -> None:
    """Empty the cache. For tests, which must not inherit each other's answers.

    Private because nothing the product runs empties this cache, and a public
    name would claim otherwise. Staleness is handled by the digest rather than
    by eviction: an edited record hashes differently and never finds the older
    reading, so there is no product moment at which forgetting is the answer.
    """

    _CACHE.clear()


async def explain_provision(
    session: AsyncSession,
    *,
    provision_id: uuid.UUID,
    use_ai: bool = True,
    regenerate: bool = False,
    answer_language: str | None = None,
    client: AzureOpenAIClient | None = None,
) -> dict:
    """What one policy's record states, deterministically, plus an explanation.

    The deterministic half is always returned and is the substance: every rule,
    its title, the parts the extraction identified, and the document's own
    sentence for each. That is what a reviewer checks, and it is complete
    whether or not a model was reachable, configured, or willing.

    Raises `ValueError` when the provision does not exist. A provision that
    simply holds no rules is not an error — a bilingual document writes headings
    with nothing under them — so that returns a populated result with an
    unavailable code rather than raising.

    `answer_language` is an optional BCP-47 tag for the language the reading
    should come back in. Omitted, the reading is written in the heading's own
    language and the request is unchanged from before this argument existed —
    same prompt, same digest, same cache entry. Given, only this app's reading
    takes that language: the document's own sentences are never shown to the
    model and are returned untouched, so no quotation is ever translated.
    """

    provision = await session.get(DocumentProvision, provision_id)
    if provision is None:
        raise ValueError(f"provision '{provision_id}' not found")

    payloads = [
        row.payload_json or {}
        for row in (
            await session.execute(
                select(CandidateRule)
                .where(CandidateRule.provision_id == provision_id)
                # Stable, and the same on every call. The order decides which
                # rules a budget keeps and therefore what the digest is, so an
                # unordered read would make the cache key depend on however the
                # database happened to return the rows.
                .order_by(CandidateRule.created_at, CandidateRule.id)
            )
        ).scalars()
    ]

    heading_path = [str(part) for part in (provision.heading_path_json or [])]
    source = build_source(heading_path, payloads, answer_language=answer_language)

    result: dict = {
        "provision_id": str(provision_id),
        "heading_path": heading_path,
        "rule_count": len(payloads),
        # What the model was shown, so the popup can say so, and what it was
        # not: `stated_text` is the document's and travels to the reader only.
        "rules": [
            {
                "rule_id": rule.rule_id,
                "title": rule.title,
                "states": dict(rule.stated),
                "effect": rule.effect,
                "stated_text": rule.stated_text,
            }
            for rule in source.rules
        ],
        "covers_every_rule": source.is_complete,
        "explanation": None,
        "unavailable_code": None,
        "generated_at": None,
        "model_deployment": None,
        "prompt_version": PROMPT_VERSION,
        "source_digest": source.digest,
    }

    settings = get_settings()
    if not use_ai or not settings.ai_enabled:
        # Not an attempt and not a refusal: nobody asked a model anything. The
        # deterministic record above is the whole answer, and `unavailable_code`
        # stays null so a reader can tell this from a generation that failed.
        return result

    attempt = None if regenerate else cached(source.digest)
    reused = attempt is not None
    if attempt is None:
        attempt = await generate_explanation(source, client=client)
        remember(attempt)

    result["explanation"] = attempt.explanation
    result["unavailable_code"] = attempt.unavailable_code
    result["generated_at"] = attempt.generated_at.isoformat()
    result["model_deployment"] = attempt.model_deployment
    result["prompt_version"] = attempt.prompt_version
    result["generated_earlier"] = reused
    return result
