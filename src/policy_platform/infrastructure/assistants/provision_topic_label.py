"""A short generated name for the subject a policy is about.

WHY THIS EXISTS

A policy card is titled by the heading the document wrote over it, quoted whole.
That is the right title — it is the document's own answer to "what is this" and
it is the only string on the card a reviewer can cite. But a heading is written
for somebody already reading the document in order, and a queue is not read in
order. A reviewer scanning seventy cards meets headings that number a section
without naming it, headings that repeat the word above them, and headings that
are a clause of the sentence beneath. Those tell the scanner nothing.

So a second string is offered beside the heading: two or three words naming the
subject the passage is about. It is generated, it is ours, and it is an aid to
finding the card. It is never the card's name.

WHAT SEPARATES A LABEL FROM EVIDENCE

A label NAMES A SUBJECT. It never STATES WHAT THE POLICY SAYS. The difference is
the whole safety argument: a phrase naming a subject cannot be read as a claim
about the document, while a sentence sitting beside verbatim evidence will be
read as more evidence — and it would be an assertion nobody sourced.

That distinction cannot be enforced by vocabulary, because vocabulary is
domain-specific and this reads whatever a customer uploads. It is enforced by
SHAPE, which is a property of every language:

* a subject name is a few words; a statement needs more,
* a statement carries quantities, and a subject name carries no digits at all,
* a statement ends, and terminal punctuation is where it ends,
* a statement joins clauses, and clause punctuation is where it joins them,
* an identifier is not language at all, so a token glued together by an
  underscore is not a name a reader would write.

Each rejection is structural and none of them mentions a topic, a sector or a
word from any document. The prompt carries the rest of the instruction, and the
validator is what the system actually relies on: a prompt is a request and a
validator is a guarantee.

WHY THE SCRIPT OF THE REPLY IS CHECKED AGAINST THE SOURCE

The corpus is bilingual and a label has to be readable by the person reading the
passage, so it is written in the language of the passage. Language is not
observable from characters, but the writing system is: Unicode names every
letter after the script it belongs to, so the set of scripts a text uses can be
read straight out of the character database. Requiring the reply's scripts to be
a subset of the source's catches a reply written in a writing system the passage
does not use, without this file naming a single language.

Direction class was the first attempt and was not enough — it separates only
left-to-right from right-to-left, and a reply in an unrelated left-to-right
script passed against a left-to-right source. That was observed against the live
corpus, not imagined, and is why the check reads scripts instead.

WHAT THIS MODULE MAY NOT DO

It may not hold a label. Nothing here is a list of subjects, a taxonomy, a
category or an example — a fallback string would be this system naming a
document's subject out of its own vocabulary, which is the failure the whole
product exists to avoid. `test_the_generator_holds_no_label.py` asserts that
structurally: the value stored as a label is never a literal from this file.

It may not compose a sentence. The reply is stored exactly as the model returned
it, minus an enclosing pair of quote marks, and a reply that needs more repair
than that is refused rather than repaired.
"""

from __future__ import annotations

import hashlib
import logging
import unicodedata
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import (
    CandidateRule,
    DocumentProvision,
    ProvisionTopicLabel,
)
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

#: Which instruction produced a stored label. Bumped whenever the prompt or the
#: validator changes, so a label generated under an older rule is recognisable
#: as such rather than being assumed to satisfy the current one.
PROMPT_VERSION = "topic-label-v4"

#: Why no label is stored, when an attempt was made and produced none.
#:
#: Codes rather than sentences, for the reason `eb5068b` gives: a composed
#: sentence in a stored column is a message that cannot be re-worded, cannot be
#: translated and cannot be told apart from something a document said. The
#: reader-facing wording lives in the interface, next to the reader.
UNAVAILABLE_NO_SOURCE = "no_source_text"
UNAVAILABLE_MODEL_FAILED = "model_call_failed"
UNAVAILABLE_REPLY_UNUSABLE = "reply_not_a_subject_name"
#: The model was asked and answered that this passage has no subject it can
#: name. Distinct from the code above: that one says a reply arrived and did not
#: hold a name, this one says a reply arrived and said there is none to hold.
UNAVAILABLE_DECLINED = "reply_declined_to_name"

#: The most words a subject name may have.
#:
#: A ceiling on shape, not a measurement of any corpus. Four words is enough for
#: a noun phrase with an article and a qualifier in the languages this has been
#: read in, and far too few for a sentence that states a condition and an
#: outcome. Raising it weakens the only structural guarantee that a label cannot
#: be a statement, so it is raised only with that trade made deliberately.
MAX_LABEL_WORDS = 4

#: A ceiling on characters as well, because "words" is a weak measure in a
#: script that does not separate them the way spaces do. Same reasoning: shape,
#: not observation.
MAX_LABEL_CHARS = 60

#: Punctuation a subject name does not contain.
#:
#: Terminal marks end a statement; clause marks join one; an underscore glues an
#: identifier together and no writer uses it inside a name. Listed as
#: codepoints rather than by script so the rule holds for text this has never
#: seen: `\u061F` is one script's question mark, `\u060C` and `\u061B` its comma
#: and semicolon, `\u3002` and `\uFF0C` another's full stop and comma.
_FORBIDDEN_PUNCTUATION = frozenset(
    ".!?;:,_\u061F\u060C\u061B\u3002\uFF0C\uFF1B\uFF1A\uFF01\uFF1F\u2026\u00B7|"
)

#: Quote characters that are never part of a word.
#:
#: No orthography writes a doubled or angled quotation mark inside or at the
#: edge of a word, so one of these left in a reply is quoting something. A pair
#: enclosing the whole reply is removed first, because a model wrapping its
#: answer in quotes is a formatting habit rather than a claim about the
#: document. Anything after that is refused: a label carrying a quotation mark
#: presents itself as somebody's exact words, and it is not.
_QUOTE_MARKS = "\"\u2018\u201C\u201D\u00AB\u00BB\u2039\u203A\u0060"

#: Marks that may belong to a word.
#:
#: An apostrophe joins letters in an elision and trails a letter in a possessive,
#: in more languages than could be listed here. Positionally it is
#: indistinguishable from a closing single quote, so it is admitted when it
#: touches a letter and refused when it floats. Admitting it is the side to err
#: on: a passage was refused a label for containing the same apostrophe its own
#: heading contains, which is the check being hostile to how a language writes.
_WORD_MARKS = "'\u2019\u02BC"

#: What `_strip_enclosing_quotes` removes when it wraps the whole reply.
_QUOTES = _QUOTE_MARKS + _WORD_MARKS

#: How many times the model is asked before a reply that is not a subject name
#: is recorded as the outcome.
#:
#: A reply is a sample, not a verdict. Asked twice about eleven passages whose
#: first reply had been refused, this model produced a usable subject name for
#: six of them on the second ask -- the same passage, the same words, the same
#: prompt. So a single refused reply was recording model variance as a property
#: of the passage, and a reviewer lost a label to it permanently.
#:
#: Two, not more: the point is to sample past variance, not to keep asking until
#: something gets through, which is how a validator stops meaning anything. And
#: only a reply that fails validation is re-asked -- a call that raises is not,
#: because a refusal by the service is a decision about the text and repeating
#: it only spends the quota again.
ASK_ATTEMPTS = 2#: How much of the passage the model reads. A budget, so one enormous section
#: cannot cost a run; the subject of a passage is stated at its start, so the
#: opening is what is kept.
MAX_SOURCE_CHARS = 4000

#: What the model is asked. The heading is sent with the text because a heading
#: is part of what the document said about its own subject, and because it
#: settles the language question below.
#:
#: WHICH LANGUAGE, WHEN A PASSAGE USES MORE THAN ONE. Some passages are written
#: twice over, in two languages, and "the language of the text" then has no
#: single answer. The rule chosen here is the language of the heading, and the
#: reason is where the label is rendered: immediately above the heading, in the
#: same block, meant to be taken in with it at a glance. A label in one script
#: sitting on top of a heading in another is not one line explaining the next --
#: it is two reading tasks where the reader had one, which is the opposite of
#: what the label is for. The heading is itself part of the text sent, so this
#: stays inside "the language of the source" rather than importing a preference
#: from outside it.
#:
#: The instruction names no language and no script, and would read the same way
#: for any pair of them.
#:
#: WHAT THE TEXT IS ABOUT VERSUS WHAT IT MENTIONS. Measured against the corpus,
#: every wrong label failed the same way: it named something the passage
#: mentioned instead of what the passage was about. A welcome message that tells
#: the reader where to take their questions came back named after the office it
#: pointed at; two different introductory passages both came back named after the
#: document they introduce. Both are things present in the text. Neither is what
#: the text is about, and a wrong subject sitting above verbatim evidence is
#: worse than no subject at all.
#:
#: Two instructions answer it, and both are about the shape of the answer rather
#: than its content, so neither carries a subject, a category or a vocabulary:
#:
#: One, an entity appearing in the text is not thereby its subject. This is the
#: distinction itself, stated plainly.
#:
#: Two, the answer must be narrower than the document. A passage is part of a
#: document; naming it after the whole cannot separate it from any other part,
#: and a name that fits every passage identifies none of them. This is what makes
#: the same label arriving twice a fault rather than a coincidence.
#:
#: Refusing is offered as an answer, in both cases, because for some passages
#: there is no honest short answer and the design would rather have nothing than
#: have something plausible. A refusal is recorded as a refusal and can be told
#: apart afterwards from never having asked.
_SYSTEM_PROMPT = """You are given a heading and some text taken from a document, \
exactly as the document wrote them.

Reply with a short noun phrase naming the subject that text is about. At most \
four words.

Name what the text is about, not something the text mentions. A person, an \
office, a role or a document named in the text is not its subject unless the \
text is about that thing.

The text is one part of a longer document. Name what sets this part apart from \
the rest of it. Do not reply with the name or the purpose of the document as a \
whole, because that would fit every other part equally.

If the text has no subject you can name this way, reply with the single word \
NONE.

Name the subject only. Do not say what the text requires, allows or forbids. Do \
not include any number, amount, date, condition or outcome. Do not copy a \
sentence. Do not end with a full stop. Do not add quotation marks.

Write your reply in the same language and the same script as the text you were \
given. If that text is written in more than one language, use the language of \
the heading. Never write your reply in a language the text does not use, even \
where you have found a shorter or a more general way to say it.

Reply with the noun phrase and nothing else."""

#: The reply that declines rather than guesses.
#:
#: A word, not a punctuation mark or an empty reply, because an empty reply is
#: indistinguishable from a call that returned nothing and a mark is
#: indistinguishable from a formatting slip. Compared case-insensitively and
#: only against the whole reply, so a passage genuinely about this word -- it is
#: an ordinary word in one of the languages this reads -- is not silently
#: discarded when it appears inside a longer name.
DECLINE_REPLY = "NONE"


@dataclass(frozen=True)
class LabelSource:
    """Exactly what the model is shown, and a digest of it.

    The digest is provenance: it says which words produced a stored label, so a
    label generated from an earlier reading of a document is recognisable
    afterwards rather than assumed to describe the current one.
    """

    #: The governing headings, outermost first, verbatim. Copied, never joined.
    heading_path: tuple[str, ...]
    #: The passage texts, verbatim, in the order the document states them.
    texts: tuple[str, ...]
    #: How many rules those texts came from.
    rule_count: int

    @property
    def combined(self) -> str:
        """The source as one string, for digesting and for the request body.

        Newline-separated, which is a separator this system chose — that is why
        it is confined to a request and a digest, and why nothing built here is
        ever shown to a reader or stored as the document's words.
        """

        return "\n".join([*self.heading_path, *self.texts]).strip()

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.combined.encode("utf-8")).hexdigest()

    @property
    def is_empty(self) -> bool:
        return not self.combined


def build_source(
    heading_path: Sequence[str],
    texts: Sequence[str],
    *,
    max_chars: int = MAX_SOURCE_CHARS,
) -> LabelSource:
    """The input for one provision: its headings and the words stated under it.

    Duplicates collapse and a text wholly inside a longer one is dropped, for
    the reason `passageQuotations` gives on the reading side: rules of one
    passage record overlapping source texts, and sending the overlap costs
    budget while telling the model nothing new.

    Truncation is by whole texts and never mid-text. Half a sentence is a
    different sentence, and the model would be naming the subject of something
    the document did not write.
    """

    kept: list[str] = []
    for raw in texts:
        text = (raw or "").strip()
        if not text or any(text in other for other in kept):
            continue
        kept = [other for other in kept if other not in text]
        kept.append(text)

    budget = max_chars
    within: list[str] = []
    for text in kept:
        if len(text) > budget:
            break
        within.append(text)
        budget -= len(text)

    return LabelSource(
        heading_path=tuple(part for part in (h.strip() for h in heading_path) if part),
        texts=tuple(within),
        rule_count=len(texts),
    )


def _scripts(text: str) -> set[str]:
    """The writing systems `text` is written in, from Unicode character data.

    Unicode names every letter after the script it belongs to — the name of a
    letter begins with the script that letter is from. Taking that first token
    per letter therefore yields the set of scripts present, straight out of the
    character database, with nothing in this file naming a script or a language.

    Direction class was tried first and is not sufficient. It distinguishes only
    left-to-right from right-to-left, so a reply in one left-to-right script
    passes against a source written in a different left-to-right script — which
    was observed against the live corpus and is exactly the failure this check
    exists to catch.

    Only letters are consulted. Digits, spaces and punctuation are shared across
    scripts and carry no evidence about which one wrote the text.
    """

    found: set[str] = set()
    for char in text:
        if not char.isalpha():
            continue
        name = unicodedata.name(char, "")
        if name:
            found.add(name.split()[0])
    return found


def _strip_enclosing_quotes(text: str) -> str:
    """Remove one symmetric pair of quote marks around the whole reply."""

    if len(text) >= 2 and text[0] in _QUOTES and text[-1] in _QUOTES:
        return text[1:-1].strip()
    return text


def _marks_between_words(text: str, marks, *, allow_at_edge: bool = False) -> bool:
    """Whether any of `marks` appears where it separates runs rather than joins them.

    A mark with a letter on both sides is part of a word: the apostrophe in an
    elision, the hyphen in a compound. A mark anywhere else is doing the work of
    punctuation -- ending a clause, ending a sentence, opening a quotation --
    because sentence machinery is always followed by a space or by the end of
    the text, never by a letter.

    `allow_at_edge` widens that to a mark touching a letter on either side, for
    marks that trail a word as well as join one.

    The distinction is positional, so it holds for text in scripts this has
    never read. The alternative -- listing which marks are letters in which
    language -- would be one language's spelling rules written into a check that
    every language has to pass.
    """

    for index, char in enumerate(text):
        if char not in marks:
            continue
        before = text[index - 1].isalpha() if index > 0 else False
        after = text[index + 1].isalpha() if index + 1 < len(text) else False
        joined = (before or after) if allow_at_edge else (before and after)
        if not joined:
            return True
    return False


def validate_label(reply: str, source: LabelSource) -> tuple[str | None, str | None]:
    """The usable label in a reply, or the code saying why there is none.

    Returns `(label, None)` or `(None, code)`. Never both, and never neither.

    Every check is a statement about shape or about the codepoints the source
    itself uses. None of them consults a vocabulary, a subject list or anything
    a particular document contains, so this behaves the same on the next
    document as on the last one.
    """

    text = _strip_enclosing_quotes(" ".join((reply or "").split()))
    if not text:
        return None, UNAVAILABLE_REPLY_UNUSABLE

    # Asked for, and therefore an answer rather than a malformed reply. Recorded
    # under its own code so that "there is no subject here I can name" is not
    # filed with "the reply came back unusable" -- they say different things
    # about the passage, and only one of them is worth asking again about.
    if text.casefold() == DECLINE_REPLY.casefold():
        return None, UNAVAILABLE_DECLINED

    if any(char in _QUOTE_MARKS for char in text):
        return None, UNAVAILABLE_REPLY_UNUSABLE
    if _marks_between_words(text, _WORD_MARKS, allow_at_edge=True):
        return None, UNAVAILABLE_REPLY_UNUSABLE
    if _marks_between_words(text, _FORBIDDEN_PUNCTUATION):
        return None, UNAVAILABLE_REPLY_UNUSABLE
    if any(char.isdigit() for char in text):
        return None, UNAVAILABLE_REPLY_UNUSABLE
    if len(text) > MAX_LABEL_CHARS:
        return None, UNAVAILABLE_REPLY_UNUSABLE
    if len(text.split()) > MAX_LABEL_WORDS:
        return None, UNAVAILABLE_REPLY_UNUSABLE

    reply_scripts = _scripts(text)
    if not reply_scripts:
        return None, UNAVAILABLE_REPLY_UNUSABLE
    if not reply_scripts.issubset(_scripts(source.combined)):
        return None, UNAVAILABLE_REPLY_UNUSABLE

    return text, None


@dataclass(frozen=True)
class LabelAttempt:
    """What one generation produced, with everything that produced it.

    Carries the refusal as well as the label, because "we tried and got nothing
    usable" is a different fact from "nobody has tried", and a reader is owed
    the difference.
    """

    label: str | None
    unavailable_code: str | None
    model_deployment: str | None
    prompt_version: str
    source_digest: str
    source_rule_count: int

    @property
    def named(self) -> bool:
        return self.label is not None


async def generate_label(
    source: LabelSource, *, client: AzureOpenAIClient | None = None
) -> LabelAttempt:
    """Ask the model to name the subject of one provision's words.

    A failure is an outcome, not an exception: the card still has the document's
    heading and has to say the label is unavailable rather than show nothing. So
    every failure path returns an attempt carrying a code.
    """

    settings = get_settings()
    deployment = settings.azure_openai_deployment

    if source.is_empty:
        return LabelAttempt(
            label=None,
            unavailable_code=UNAVAILABLE_NO_SOURCE,
            model_deployment=None,
            prompt_version=PROMPT_VERSION,
            source_digest=source.digest,
            source_rule_count=source.rule_count,
        )

    try:
        ask = client or AzureOpenAIClient(settings)
        for attempt_number in range(ASK_ATTEMPTS):
            reply = await ask.chat(
                [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": source.combined},
                ],
                deployment=deployment,
                max_tokens=4000,
                timeout=120.0,
            )
            label, code = validate_label(reply, source)
            if label is not None:
                break
            # A decline is an answer. Asking again would be asking the same
            # question of the same text hoping for a different reply, which is
            # how a refusal stops meaning anything. Only an unusable reply is
            # re-asked, because that is the one that samples variance.
            if code == UNAVAILABLE_DECLINED:
                break
            if attempt_number + 1 < ASK_ATTEMPTS:
                logger.info(
                    "topic label reply was not a subject name, asking again "
                    "(attempt %d of %d)",
                    attempt_number + 2,
                    ASK_ATTEMPTS,
                )
    except Exception as exc:  # noqa: BLE001 - the heading stands on its own
        logger.warning("topic label generation failed: %s", exc)
        return LabelAttempt(
            label=None,
            unavailable_code=UNAVAILABLE_MODEL_FAILED,
            model_deployment=deployment,
            prompt_version=PROMPT_VERSION,
            source_digest=source.digest,
            source_rule_count=source.rule_count,
        )

    return LabelAttempt(
        label=label,
        unavailable_code=code,
        model_deployment=deployment,
        prompt_version=PROMPT_VERSION,
        source_digest=source.digest,
        source_rule_count=source.rule_count,
    )


def source_for_provision(
    heading_path: Sequence[str], payloads: Sequence[dict]
) -> LabelSource:
    """The words of one provision, as its rules recorded them.

    A provision composes no text, so there is nothing on it to read but the
    heading chain. The words are on the rules, each with its span, and this
    takes each rule's verbatim source text — the same field the reading side
    quotes on the card. Falling back to the rule's description keeps a rule
    whose formulation recorded no span from contributing nothing.
    """

    texts: list[str] = []
    for payload in payloads:
        formulation = (payload or {}).get("formulation") or {}
        canonical = formulation.get("canonical") or {}
        text = (canonical.get("source_text") or "").strip()
        if not text:
            text = ((payload or {}).get("description") or "").strip()
        if text:
            texts.append(text)
    return build_source(heading_path, texts)


async def store_attempt(
    session: AsyncSession, provision_id: uuid.UUID, attempt: LabelAttempt
) -> ProvisionTopicLabel:
    """Write what one attempt produced, replacing any earlier attempt.

    Replaced rather than appended for the reason the unique constraint states:
    a card shows one label, and a second row would make "which one" a question
    a reader has to answer. The previous attempt is not history worth keeping —
    it describes the same words under an instruction that is no longer in force,
    and `prompt_version` on the surviving row already says which one is.
    """

    row = (
        await session.execute(
            select(ProvisionTopicLabel).where(
                ProvisionTopicLabel.provision_id == provision_id
            )
        )
    ).scalar_one_or_none()

    if row is None:
        row = ProvisionTopicLabel(provision_id=provision_id)
        session.add(row)

    row.label_text = attempt.label
    row.unavailable_code = attempt.unavailable_code
    row.model_deployment = attempt.model_deployment
    row.prompt_version = attempt.prompt_version
    row.source_digest = attempt.source_digest
    row.source_rule_count = attempt.source_rule_count
    row.generated_at = datetime.now(UTC)
    await session.flush()
    return row


async def label_provisions(
    session: AsyncSession,
    *,
    policy_set_id: uuid.UUID,
    limit: int,
    regenerate: bool = False,
) -> dict:
    """Name the subject of every provision of a policy set that has rules.

    Provisions with no rules are skipped rather than attempted. Such a provision
    is a heading the document states with nothing under it — a bilingual
    document produces one for every heading it writes twice — and it has no
    words for anything to be about.

    Already-attempted provisions are skipped unless `regenerate`, so running
    this twice costs one model call per provision rather than two, and a
    reviewer watching the queue fill sees it fill once.

    Reports counts rather than raising: a run that could name sixty provisions
    and not the other ten has done sixty provisions' worth of good, and losing
    that to an exception would be the "fewer records than they started with"
    failure in a new place.
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
    existing = {
        row.provision_id
        for row in (
            await session.execute(
                select(ProvisionTopicLabel).where(
                    ProvisionTopicLabel.provision_id.in_(
                        [provision.id for provision in provisions]
                    )
                )
            )
        ).scalars()
    } if provisions else set()

    client = AzureOpenAIClient(settings)
    named = 0
    unavailable = 0
    skipped_no_rules = 0
    attempted: list[dict] = []

    for provision in provisions:
        if len(attempted) >= limit:
            break
        if not regenerate and provision.id in existing:
            continue

        payloads = [
            row.payload_json or {}
            for row in (
                await session.execute(
                    select(CandidateRule).where(
                        CandidateRule.provision_id == provision.id
                    )
                )
            ).scalars()
        ]
        if not payloads:
            skipped_no_rules += 1
            continue

        source = source_for_provision(
            list(provision.heading_path_json or []), payloads
        )
        attempt = await generate_label(source, client=client)
        await store_attempt(session, provision.id, attempt)
        if attempt.named:
            named += 1
        else:
            unavailable += 1
        attempted.append(
            {
                "provision_key": provision.provision_key,
                "heading_path": list(provision.heading_path_json or []),
                "label": attempt.label,
                "unavailable_code": attempt.unavailable_code,
            }
        )

    return {
        "provisions": len(provisions),
        "attempted": len(attempted),
        "named": named,
        "unavailable": unavailable,
        "skipped_with_no_rules": skipped_no_rules,
        "prompt_version": PROMPT_VERSION,
        "results": attempted,
    }
