"""A short generated handle for what each rule under one heading is for.

WHAT THIS IS, AND THE ONE THING IT IS NOT

A policy card lists the rules drawn from one passage. Sibling rules come from
the same few sentences, so several of them open with the same words and differ
only deep in the clause; beside each is an identifier that is a hash. Nothing on
the card lets a reviewer say "that one" without reading all of them in full,
every time the card is drawn.

This writes a line or two per rule saying what that rule is *for*. It is a
handle for finding and telling apart, and it is never a reading: anyone deciding
anything about a rule reads the rule. The interface says so in its own words and
marks the line as this app's, because a generated phrase sitting above verbatim
evidence is read as evidence unless it is visibly not.

WHY THE NAME IS STORED OUTSIDE THE RULE

A rule's record is evidence about a document. This is our commentary on that
record. Inside `payload_json` it would leave in every export and in every
published version, and a reader downstream would find words in a policy record
that no document stated and no extraction produced. So it goes to
`candidate_rule_names`, keyed by the rule, and no read path of a rule can reach
it. `rule_name_lookup` is the only way to get one, and it can only be asked for
by name.

WHY THE MODEL IS SHOWN THE RECORD AND NEVER THE DOCUMENT'S SENTENCE

`policy_explainer` established this and it applies here with more force. Rules of
one passage are decomposed from the same sentence, so a name generated from that
sentence is the *same name* for every one of them — which is precisely the
failure this feature exists to remove. What differs between siblings is only in
the records. Showing the sentence as well would also hide extraction defects: a
model holding both silently reconciles them, and a reviewer checking whether the
decomposition is faithful would be handed a name written from the source rather
than from what we made of it.

So `facts_for_rule` is imported rather than re-derived — one definition of what a
rule's record is, and the field that carries the document's characters is the one
field it does not send.

WHY A WHOLE POLICY IS NAMED IN ONE REQUEST

Two reasons that are one reason. What distinguishes a rule from its siblings is
only visible when they are seen together, so a request naming one rule at a time
cannot be asked to distinguish. And a request per rule costs a multiple of a
request per policy for exactly the same words.

Identical records are named once and the name is stored for each of them. A
document read twice produces two rules with the same record, and asking twice
would buy a second copy of the same answer — and then, under the distinctness
rule below, refuse it for repeating the first.

DISTINCTNESS IS ENFORCED, NOT REQUESTED

A name that reads the same as its sibling's has failed at the only thing it is
for. The prompt asks for distinct phrases; this module then checks, and a repeat
is refused with a code rather than stored. Records that are identical may share
a name, because they are the same rule seen twice and giving them different
handles would be inventing a difference the records do not have.

THE PHRASE IS NOT ALLOWED TO BE THE RULE AGAIN

Two structural bounds, both language-neutral. A name may not appear inside the
record material it names — a handle that is a span of the record is a quotation
with the quotation marks removed. And it must be shorter than that material,
because a handle no shorter than the thing it stands for saves the reader
nothing. Neither bound consults a vocabulary and neither knows what any document
is about.

NOTHING HERE IS ABOUT EITHER DECISION ROUTE

The prompt does not mention how a rule's test is decided, and a reply that
reaches for that vocabulary is refused. A handle is for finding a rule; how the
rule is decided is a property of the rule and is shown where the rule is shown.
"""

from __future__ import annotations

import hashlib
import json
import logging
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import (
    CandidateRule,
    CandidateRuleName,
    DocumentProvision,
)
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.assistants.policy_explainer import (
    RuleFacts,
    facts_for_rule,
)
from policy_platform.infrastructure.assistants.policy_explainer import (
    _names_a_route as names_a_route,
)

# Imported rather than restated. "Which writing system is this" and "is this mark
# punctuation or part of a word" are subtle, were arrived at against a bilingual
# corpus, and a second copy of either would drift from the first without anything
# failing. The leading underscores say they are internal to the label module;
# taking them here is the narrower fault of the two.
from policy_platform.infrastructure.assistants.provision_topic_label import (
    MAX_LABEL_CHARS as _ONE_LINE_CHARS,
)
from policy_platform.infrastructure.assistants.provision_topic_label import (
    _FORBIDDEN_PUNCTUATION as FORBIDDEN_PUNCTUATION,
)
from policy_platform.infrastructure.assistants.provision_topic_label import (
    _marks_between_words as marks_between_words,
)
from policy_platform.infrastructure.assistants.provision_topic_label import (
    _QUOTE_MARKS as QUOTE_MARKS,
)
from policy_platform.infrastructure.assistants.provision_topic_label import (
    _scripts as scripts_of,
)
from policy_platform.infrastructure.assistants.provision_topic_label import (
    _strip_enclosing_quotes as strip_enclosing_quotes,
)
from policy_platform.infrastructure.assistants.provision_topic_label import (
    _WORD_MARKS as WORD_MARKS,
)
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

#: Which instruction produced a stored name. Bumped whenever the prompt changes
#: in a way that would produce different names, so a name written under an older
#: one is recognisable instead of assumed to satisfy today's rule.
PROMPT_VERSION = "rule-name-v1"

#: Why a rule has no name. Codes and never sentences: the words a reader sees
#: belong beside the reader, where they can be written for them.
UNAVAILABLE_NO_RECORD = "no_record_to_name"
UNAVAILABLE_MODEL_FAILED = "model_call_failed"
UNAVAILABLE_REPLY_UNUSABLE = "reply_not_a_purpose"
UNAVAILABLE_DECLINED = "reply_declined_to_name"
UNAVAILABLE_NAMED_A_ROUTE = "reply_named_a_decision_route"
UNAVAILABLE_RESTATES_RECORD = "reply_restates_the_record"
UNAVAILABLE_NOT_DISTINCT = "name_repeats_a_sibling"
UNAVAILABLE_UNANSWERED = "reply_left_this_unnamed"

#: The reply that declines rather than guesses, for one rule inside a batch.
#: A word for the reason the subject label gives: an empty string cannot be told
#: apart from a call that returned nothing.
DECLINE_REPLY = "NONE"

#: The shape of the phrase: one line, or two.
#:
#: `_ONE_LINE_CHARS` is the subject label's ceiling — the width at which a
#: generated line stops being scannable — and this allows two of them. The word
#: count is the same shape counted the other way: a phrase somebody writes
#: without needing punctuation runs to about seven words, and two of those is
#: fourteen. Both are properties of a line of text, not of any document. Nothing
#: pads a name up to either; a name that says it in five words is right at five.
MAX_NAME_CHARS = 2 * _ONE_LINE_CHARS
MAX_NAME_WORDS = 14

#: How much record material one request may carry. A budget and not a
#: measurement: a policy larger than this is named in several requests, each
#: seeing whole records, and distinctness is enforced across all of them.
MAX_RECORD_CHARS = 8000

#: A second ask, covering only the records the first ask left unusable. A record
#: already named is not asked about again, and a record the model explicitly
#: declined is not either — that is an answer, not a miss. Measured on the live
#: corpus, most of what comes back unusable is a phrase written in a language the
#: heading does not use, which the same request asked again does not repeat.
ASK_ATTEMPTS = 2

#: The punctuation a handle may not hold. The subject label's set, less the list
#: separators.
#:
#: The label names one subject, so a comma in it is a sign the model wrote two.
#: A handle is not under that restraint: a rule may govern several things at once
#: and the shortest honest handle for it joins them with a comma. Everything that
#: ends or joins a sentence stays out, because a handle is a phrase and a reader
#: must not read it as the rule.
#:
#: Which characters those are is asked of Unicode rather than listed here, so a
#: script whose comma this app has not met yet is treated like every other one.
NAME_PUNCTUATION = frozenset(
    mark
    for mark in FORBIDDEN_PUNCTUATION
    if "COMMA" not in (unicodedata.name(mark, "") or "")
)

#: What a handle may hold between two of the things it names, and nowhere else.
_LIST_SEPARATORS = frozenset(FORBIDDEN_PUNCTUATION) - NAME_PUNCTUATION


@dataclass(frozen=True)
class NamingSource:
    """Exactly what one request shows the model, and a digest of it.

    The heading is included for the reason `policy_explainer` gives: it is the
    document's own name for what follows, and it is the only thing here that
    orients a model seeing one fragment of a document. It is also what decides
    the language of the reply.
    """

    #: The governing headings, outermost first, verbatim. The document's.
    heading_path: tuple[str, ...]
    #: The records to be named, in document order. Their `stated_text` — the
    #: document's own characters — is deliberately not part of `request_body`.
    rules: tuple[RuleFacts, ...]

    @property
    def request_body(self) -> str:
        """The user message: the heading, and the records, numbered.

        Numbered because the reply has to say which name belongs to which rule
        and a rule's identifier is a hash the model has no use for. The ordinal
        is positional and local to this request, so nothing about it can leak
        into a name.
        """

        return json.dumps(
            {
                "heading_stated_by_the_document": list(self.heading_path),
                "extracted_rules": [
                    {"ordinal": index + 1, **rule.for_model}
                    for index, rule in enumerate(self.rules)
                ],
            },
            ensure_ascii=False,
            indent=2,
        )

    @property
    def scripts(self) -> set[str]:
        """The writing systems the *document's* words here are written in.

        Deliberately narrower than `record_material`. A record carries one field
        this app wrote rather than the document — the effect, which is a term of
        our own contract and is therefore always in one script. Counting it
        would put that script into the permitted set for every document in every
        language, and a name in it would then pass the language check on a page
        that has no other word in it. Measured against the live corpus: with the
        effect counted, a reply in the wrong script was accepted for every
        Arabic record here.
        """

        material = "\n".join(
            [*self.heading_path, *(language_material(rule) for rule in self.rules)]
        )
        return scripts_of(material)

    @property
    def is_empty(self) -> bool:
        return not self.rules


def language_material(rule: RuleFacts) -> str:
    """The part of a record whose words came from the document."""

    parts = [rule.title, *rule.stated.values()]
    return " ".join(part.strip() for part in parts if part and part.strip())


def record_material(rule: RuleFacts) -> str:
    """One rule's record as plain words: what a name would stand in for.

    The title, the populated fields and the effect — the same material the model
    is shown, flattened. Not the document's sentence, which is not shown and
    which a name is not measured against: a name saves a reader picking one rule
    out of several, and what they would otherwise read to do that is the record.
    """

    parts = [rule.title, *rule.stated.values(), rule.effect]
    return " ".join(part.strip() for part in parts if part and part.strip())


def _normalised(text: str) -> str:
    """Case-folded and single-spaced, for comparing two phrases as phrases.

    Comparison only. Nothing normalised here is ever stored or shown.
    """

    return " ".join((text or "").split()).casefold()


def digest_of(rule: RuleFacts) -> str:
    """A key for one record, so the same record is not named twice.

    Over what the model would be shown, so two rules that would produce the same
    request share a key. A document read twice produces exactly this.
    """

    body = json.dumps(rule.for_model, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(f"{PROMPT_VERSION}\n{body}".encode("utf-8")).hexdigest()


def build_source(
    heading_path: Sequence[str],
    rules: Sequence[RuleFacts],
) -> NamingSource:
    """One request's input: the heading chain, and the records to name."""

    return NamingSource(
        heading_path=tuple(part for part in (h.strip() for h in heading_path) if part),
        rules=tuple(rules),
    )


def chunk_rules(
    rules: Sequence[RuleFacts], *, max_chars: int = MAX_RECORD_CHARS
) -> list[list[RuleFacts]]:
    """Split records into request-sized groups, never splitting a record.

    Half a record is a different record, and a model asked to name one would be
    naming something the extraction did not produce. A single record larger than
    the budget still goes on its own rather than being cut.
    """

    groups: list[list[RuleFacts]] = []
    current: list[RuleFacts] = []
    spent = 0
    for rule in rules:
        cost = len(json.dumps(rule.for_model, ensure_ascii=False))
        if current and spent + cost > max_chars:
            groups.append(current)
            current = []
            spent = 0
        current.append(rule)
        spent += cost
    if current:
        groups.append(current)
    return groups


# The instruction. Ordered as `policy_explainer` orders its own: what you are
# given, what to write, how to write it, and last the rule that would be worst to
# lose — which is the language rule, for the reason the generated subject label
# measured and wrote down.
#
# It names no subject, no category and no vocabulary, so it reads the same for a
# document about anything. It says nothing about how a rule's test is decided,
# because a handle is for finding a rule and that is a property of the rule
# itself, shown where the rule is shown.
_SYSTEM_PROMPT = """You are given a heading a document wrote, and the records \
this app extracted from the passage under that heading. Each record is one rule \
as this app decomposed it.

For each record, write a short phrase naming what that rule is for: its purpose, \
its subject, or the occasion and the people it governs — the thing a reader \
would look it up by. Do not restate what the rule says. The phrase stands beside \
the rule, never in place of it.

These records were drawn from one passage and several of them are alike. What \
tells them apart is often who the rule is about, or when it applies, or which \
step of a process it covers. Say that, in words. Each phrase must be one no \
reader could mistake for another phrase in the same reply.

One line, or two where two are needed to tell a record from its neighbours. At \
most fourteen words, and fewer wherever fewer is enough. Do not lengthen a \
phrase to fill the room.

Do not give any figure, amount or date, and do not give what the rule requires \
or what follows from it: a reader must go to the rule for those. Do not copy any \
run of words from the record. Do not end with a full stop. Do not add quotation \
marks.

If a record holds nothing you can name this way, give the single word NONE for \
that record.

Reply with a JSON object with one key, "names", holding one entry for every \
record you were given: the record's ordinal written as a string, and the phrase.

Write every phrase in the same language and the same script as the heading you \
were given. Never write a phrase in a language the heading does not use, even \
where you have found a shorter or a more general way to say it."""


def validate_name(
    reply: str, *, rule: RuleFacts, source_scripts: set[str]
) -> tuple[str | None, str | None]:
    """The usable name in one reply, or the code saying why there is none.

    Returns `(name, None)` or `(None, code)`. Never both and never neither.

    Every check is about shape, or about codepoints the material itself uses.
    None consults a vocabulary, a subject list or anything a particular document
    contains, so this behaves the same on the next document as on the last.
    """

    text = strip_enclosing_quotes(" ".join((reply or "").split()))
    # A separator at either end joins this phrase to nothing, so it is dropped
    # rather than refused: the phrase itself is still the phrase.
    text = text.strip("".join(_LIST_SEPARATORS)).strip()
    if not text:
        return None, UNAVAILABLE_REPLY_UNUSABLE

    # Asked, and answered. Kept apart from an unusable reply because the two say
    # different things about the record and only one of them is worth re-asking.
    if text.casefold() == DECLINE_REPLY.casefold():
        return None, UNAVAILABLE_DECLINED

    if any(char in QUOTE_MARKS for char in text):
        return None, UNAVAILABLE_REPLY_UNUSABLE
    if marks_between_words(text, WORD_MARKS, allow_at_edge=True):
        return None, UNAVAILABLE_REPLY_UNUSABLE
    if marks_between_words(text, NAME_PUNCTUATION):
        return None, UNAVAILABLE_REPLY_UNUSABLE
    # A number in a handle is a term of the rule, and a term of the rule belongs
    # in the rule where a reviewer checks it against the source.
    if any(char.isdigit() for char in text):
        return None, UNAVAILABLE_REPLY_UNUSABLE
    if len(text) > MAX_NAME_CHARS:
        return None, UNAVAILABLE_REPLY_UNUSABLE
    if len(text.split()) > MAX_NAME_WORDS:
        return None, UNAVAILABLE_REPLY_UNUSABLE

    reply_scripts = scripts_of(text)
    if not reply_scripts:
        return None, UNAVAILABLE_REPLY_UNUSABLE
    if not reply_scripts.issubset(source_scripts):
        return None, UNAVAILABLE_REPLY_UNUSABLE

    if names_a_route(text):
        return None, UNAVAILABLE_NAMED_A_ROUTE

    material = record_material(rule)
    normalised = _normalised(text)
    if normalised and _normalised(material).find(normalised) >= 0:
        return None, UNAVAILABLE_RESTATES_RECORD
    if len(text) >= len(material.strip()):
        return None, UNAVAILABLE_RESTATES_RECORD

    return text, None


@dataclass(frozen=True)
class NameAttempt:
    """What one generation produced for one rule, with its provenance.

    Carries the refusal as well as the name, because "asked, and nothing usable
    came back" is a different fact from "nobody has asked", and only the second
    is worth spending a model call on again.
    """

    name: str | None
    unavailable_code: str | None
    model_deployment: str | None
    prompt_version: str
    source_digest: str

    @property
    def named(self) -> bool:
        return self.name is not None


def _replies_by_ordinal(reply: str) -> dict[int, str]:
    """The phrases in one reply, by the ordinal they were asked for.

    Tolerant about the envelope and strict about nothing else: a reply that is
    not an object, or holds no usable entries, comes back empty and the caller
    treats every rule in the batch as unanswered.
    """

    try:
        parsed = json.loads(reply or "")
    except (TypeError, ValueError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    names = parsed.get("names")
    if not isinstance(names, dict):
        # A model that answered with the mapping directly rather than under the
        # key it was asked for. The entries are what matter.
        names = parsed
    out: dict[int, str] = {}
    for key, value in names.items():
        try:
            ordinal = int(str(key).strip())
        except (TypeError, ValueError):
            continue
        if isinstance(value, str):
            out[ordinal] = value
    return out


async def generate_names(
    source: NamingSource,
    *,
    client: AzureOpenAIClient | None = None,
    taken: set[str] | None = None,
    settled_scripts: set[str] | None = None,
) -> list[NameAttempt]:
    """Name every record in one request, in the order they were given.

    `taken` carries the names already accepted elsewhere in the same policy, so
    a policy split across several requests still cannot end up with two rules
    wearing the same handle. It is read and added to; nothing about it reaches
    the model, which is shown records and a heading and nothing else.

    `settled_scripts` carries the writing systems the earlier requests of the
    same policy actually wrote in. A bilingual passage permits either, and each
    request would otherwise choose for itself — which on the live corpus put two
    languages of handle on one card. Narrowing to what the policy has already
    used makes that choice once. It only ever narrows, and never to nothing.

    A failure is an outcome and not an exception: the card renders without
    names, so every failing path returns attempts carrying a code.
    """

    settings = get_settings()
    deployment = settings.azure_openai_fast_deployment
    already = taken if taken is not None else set()

    if source.is_empty:
        return []

    def failed(code: str, *, model: str | None) -> list[NameAttempt]:
        return [
            NameAttempt(
                name=None,
                unavailable_code=code,
                model_deployment=model,
                prompt_version=PROMPT_VERSION,
                source_digest=digest_of(rule),
            )
            for rule in source.rules
        ]

    if all(not language_material(rule) for rule in source.rules):
        return failed(UNAVAILABLE_NO_RECORD, model=None)

    replies: dict[int, str] = {}
    source_scripts = source.scripts
    if settled_scripts:
        narrowed = source_scripts & settled_scripts
        if narrowed:
            source_scripts = narrowed
    # The name accepted for each ordinal, and for the rest the code saying why
    # there is none yet. Kept apart so a second ask only has to cover what the
    # first left, and so a record already named is never asked about again.
    usable: dict[int, str] = {}
    codes: dict[int, str] = {}
    answered: set[int] = set()
    try:
        ask = client or AzureOpenAIClient(settings)
        for attempt_number in range(ASK_ATTEMPTS):
            raw = await ask.chat(
                [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": source.request_body},
                ],
                deployment=deployment,
                json_mode=True,
                # Room for one phrase per record plus the envelope. Generous
                # because a phrase in a script that tokenises finely costs
                # several times what the same phrase costs in another, and a
                # budget that fits one language and not another would be this
                # module preferring a language.
                max_tokens=min(6000, 400 + 120 * len(source.rules)),
                timeout=90.0,
            )
            replies = _replies_by_ordinal(raw)
            for index, rule in enumerate(source.rules):
                ordinal = index + 1
                if ordinal in usable or ordinal in answered:
                    continue
                reply = replies.get(ordinal)
                if reply is None:
                    codes[ordinal] = UNAVAILABLE_UNANSWERED
                    continue
                name, code = validate_name(
                    reply, rule=rule, source_scripts=source_scripts
                )
                if name is not None:
                    usable[ordinal] = name
                    codes.pop(ordinal, None)
                    continue
                codes[ordinal] = code or UNAVAILABLE_REPLY_UNUSABLE
                if code == UNAVAILABLE_DECLINED:
                    # The model was asked and said there was nothing to name.
                    # That is an answer, and asking the same question again
                    # would be this module disagreeing with it.
                    answered.add(ordinal)

            outstanding = [
                index + 1
                for index in range(len(source.rules))
                if index + 1 not in usable and index + 1 not in answered
            ]
            if not outstanding:
                break
            if attempt_number + 1 < ASK_ATTEMPTS:
                # Measured on the live corpus: most of what comes back unusable
                # is a reply written in a language the heading does not use, and
                # that is sampling noise rather than a property of the record —
                # the same request asked again is usually answered properly.
                logger.info(
                    "rule name reply unusable for %d of %d records, asking again "
                    "(attempt %d of %d)",
                    len(outstanding),
                    len(source.rules),
                    attempt_number + 2,
                    ASK_ATTEMPTS,
                )
    except Exception as exc:  # noqa: BLE001 - a card without names is a card
        logger.warning("rule name generation failed: %s", exc)
        return failed(UNAVAILABLE_MODEL_FAILED, model=deployment)

    attempts: list[NameAttempt] = []
    for index, rule in enumerate(source.rules):
        ordinal = index + 1
        name = usable.get(ordinal)
        code = None if name is not None else codes.get(ordinal, UNAVAILABLE_UNANSWERED)
        if name is not None:
            key = _normalised(name)
            if key in already:
                # A handle that reads the same as a sibling's cannot do the one
                # thing a handle is for. Refused rather than made unique by this
                # module, which would mean composing words of its own.
                name, code = None, UNAVAILABLE_NOT_DISTINCT
            else:
                already.add(key)
                if settled_scripts is not None:
                    settled_scripts.update(scripts_of(name))
        attempts.append(
            NameAttempt(
                name=name,
                unavailable_code=code,
                model_deployment=deployment,
                prompt_version=PROMPT_VERSION,
                source_digest=digest_of(rule),
            )
        )
    return attempts


async def store_attempt(
    session: AsyncSession, candidate_rule_id: uuid.UUID, attempt: NameAttempt
) -> CandidateRuleName:
    """Write what one attempt produced, replacing any earlier attempt.

    Replaced and not appended, for the reason the unique constraint states: a
    rule wears one handle, and a second row would make "which one" a question
    the reader has to answer.
    """

    row = (
        await session.execute(
            select(CandidateRuleName).where(
                CandidateRuleName.candidate_rule_id == candidate_rule_id
            )
        )
    ).scalar_one_or_none()

    if row is None:
        row = CandidateRuleName(candidate_rule_id=candidate_rule_id)
        session.add(row)

    row.name_text = attempt.name
    row.unavailable_code = attempt.unavailable_code
    row.model_deployment = attempt.model_deployment
    row.prompt_version = attempt.prompt_version
    row.source_digest = attempt.source_digest
    row.generated_at = datetime.now(UTC)
    await session.flush()
    return row


async def name_rules(
    session: AsyncSession,
    *,
    policy_set_id: uuid.UUID,
    limit: int,
    regenerate: bool = False,
) -> dict:
    """Name the rules of every policy in a set, one policy at a time.

    `limit` counts policies rather than rules, because a policy is the unit that
    can be named: its rules are named together or not at all, since what tells
    them apart is only visible when they are seen side by side.

    Rules the extraction has since superseded are left alone. A handle is for
    finding a rule in a queue, and those are not in one.

    Reports counts rather than raising. A run that names sixty policies and not
    the other ten has done sixty policies' worth of good, and an exception would
    throw that away.
    """

    settings = get_settings()
    if not settings.ai_enabled:
        raise RuntimeError("Azure OpenAI is not configured on this server")

    provisions = (
        (
            await session.execute(
                select(DocumentProvision)
                .where(DocumentProvision.policy_set_id == policy_set_id)
                .order_by(DocumentProvision.first_sequence)
            )
        )
        .scalars()
        .all()
    )

    client = AzureOpenAIClient(settings)
    policies = 0
    attempted = 0
    named = 0
    unavailable = 0
    not_distinct = 0
    skipped_no_rules = 0
    results: list[dict] = []

    for provision in provisions:
        if policies >= limit:
            break

        rules = (
            (
                await session.execute(
                    select(CandidateRule)
                    .where(
                        CandidateRule.provision_id == provision.id,
                        CandidateRule.superseded_at.is_(None),
                    )
                    .order_by(CandidateRule.created_at, CandidateRule.id)
                )
            )
            .scalars()
            .all()
        )
        if not rules:
            skipped_no_rules += 1
            continue

        stored = (
            (
                await session.execute(
                    select(CandidateRuleName).where(
                        CandidateRuleName.candidate_rule_id.in_(
                            [rule.id for rule in rules]
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        existing = {row.candidate_rule_id for row in stored}
        pending = [rule for rule in rules if regenerate or rule.id not in existing]
        if not pending:
            continue

        # One record may belong to several rules — a document read twice
        # produces exactly that — and it is named once. Order is preserved so
        # the model still sees the policy as the document states it.
        facts_by_rule = {rule.id: facts_for_rule(rule.payload_json or {}) for rule in pending}
        first_for_digest: dict[str, uuid.UUID] = {}
        distinct: list[RuleFacts] = []
        for rule in pending:
            key = digest_of(facts_by_rule[rule.id])
            if key not in first_for_digest:
                first_for_digest[key] = rule.id
                distinct.append(facts_by_rule[rule.id])

        policies += 1
        # A run that names only what an extraction has just added still has to
        # tell those rules from the siblings named before it. The handles this
        # policy already carries are taken, and the writing system they are in
        # is the one it settled on — otherwise the second run repeats a name, or
        # answers in the other language, and the card carries both.
        keeping = {
            row.candidate_rule_id for row in stored
        } - {rule.id for rule in pending}
        carried = [
            row.name_text
            for row in stored
            if row.candidate_rule_id in keeping and row.name_text
        ]
        taken: set[str] = {_normalised(text) for text in carried}
        # One policy, one language of handle, even when the passage is bilingual
        # and large enough to need several requests.
        settled: set[str] = set()
        for text in carried:
            settled |= scripts_of(text)
        attempt_by_digest: dict[str, NameAttempt] = {}
        for group in chunk_rules(distinct):
            source = build_source(list(provision.heading_path_json or []), group)
            for attempt in await generate_names(
                source, client=client, taken=taken, settled_scripts=settled
            ):
                attempt_by_digest[attempt.source_digest] = attempt

        for rule in pending:
            attempt = attempt_by_digest.get(digest_of(facts_by_rule[rule.id]))
            if attempt is None:
                continue
            await store_attempt(session, rule.id, attempt)
            attempted += 1
            if attempt.named:
                named += 1
            else:
                unavailable += 1
                if attempt.unavailable_code == UNAVAILABLE_NOT_DISTINCT:
                    not_distinct += 1
            results.append(
                {
                    "provision_key": provision.provision_key,
                    "rule_id": (rule.payload_json or {}).get("rule_id"),
                    "name": attempt.name,
                    "unavailable_code": attempt.unavailable_code,
                }
            )

    return {
        "policies_in_set": len(provisions),
        "policies_named": policies,
        "attempted": attempted,
        "named": named,
        "unavailable": unavailable,
        "duplicates_within_a_policy": not_distinct,
        "skipped_with_no_rules": skipped_no_rules,
        "prompt_version": PROMPT_VERSION,
        "results": results,
    }
