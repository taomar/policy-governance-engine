"""Deciding what a case *is* before deciding how to answer it.

WHY THIS EXISTS

A reviewer puts a case to a policy for one of two reasons, and the two are not
the same question.

  - They may be asking what the policy *provides* — "how many hours may a
    part-timer work?" — and want the material the policy holds on that subject,
    gathered and stated back to them. This module calls that an *informational*
    request. The number they are asking for is an answer the record already
    carries; a rule that names it holds the reply, not a blank to be filled.
  - They may be stating the facts of a specific situation and asking for a
    determination — "someone works thirty hours a week; are they within the
    cap?" — and want the rule that those facts land on, applied to them. This
    module calls that a *decision* request. Here a rule that names a quantity
    the case did not state is right to ask for it: the determination turns on
    the value.

The defect that made this module necessary: an informational request was run as
a determination against every rule at once. The one rule that *stated the
answer* was reported as unsettled, because as a determination it needed the very
quantity the reviewer was asking about as its output. The answer was in the
record the whole time, demanded as an input.

WHY THE INTENT IS READ FROM THE QUESTION AGAINST WHAT THE RULES TEST

The two kinds divide on one thing: whether the question *supplies* a fact the
rules test or *asks after* one. "How many hours may a part-timer work?" asks
after the very quantity the cap rule tests; "a part-timer works thirty hours,
are they within the cap?" supplies it. They name the same category and differ
only there. So `classify_case_intent` is given the question *together with the
facts and quantities the policy's rules test* — drawn from the same lean record
the gather grounds on — and a model decides which the question does with them. It
is never a list of trigger phrases: a vocabulary of "how many" / "can I" / "am I"
is a property of one language, and this corpus is bilingual. The facts it is
shown are the policy's own, in the document's own words; the cut keys on the
*structure* of the question against them, not on any word this code carries, so
it survives Arabic and is tuned to no document.

WHY THE CLASSIFICATION IS DETERMINISTIC

A reviewer who asks the same question twice must get the same kind of answer, or
the feature cannot be trusted. The reasoning deployment cannot promise that — it
rejects `temperature=0` outright and does not honour `seed` (see
`AzureOpenAIClient.chat`). So the classifier runs on the fast deployment at
`temperature=0`, the one determinism control that deployment honours and the same
lever the Ask-AI chat uses to stop its wording drifting between runs. Classifying
is a sort, not a synthesis: it does not need the reasoning budget, and a stable
answer matters more here than a deeper one.

WHAT THIS DOES NOT DO

It does not decide anything. A determination is still the deterministic engine's
or the judge's to make, one rule at a time, through the paths that already exist
and are already audited. This module classifies, and — for an informational
request only — gathers and states what the policy holds. The words it composes
are its own and are marked as its own by the caller; it cites the rules its
answer rests on by id, and carries with each citation that rule's *verbatim
source sentence* — resolved here by following the rule's ``evidence_refs`` into
the payload's ``spans`` — so the document's own words reach the reader
unrewritten, untranslated, and untrimmed. Only the display *name* is left for the
reader's surface to resolve from the id, because a generated name is this app's
and must not cross the wire dressed as the document's (constraint 8).
"""
from __future__ import annotations

import json
import logging

from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.projection.policy_case_payload import to_compact
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

PROMPT_VERSION = "ai-case-intent-v4"

VALID_REASONING_EFFORTS = ("low", "medium", "high")

#: A conservative ceiling on the characters of the lean policy payload shown to
#: the model in one gather — the compact ``grounding_projection_v1`` transport,
#: the same bytes the JSON tab renders. Set well under the deployment's context
#: window so a whole policy fits alongside the system prompt and the reply.
#:
#: When a policy's payload exceeds it the gather is refused, never trimmed.
#: Dropping some rules to fit would let an answer be composed from part of a
#: policy while presenting as the whole policy's answer — the one narrowing a
#: reviewer cannot see, because nothing on screen would say a rule went unread.
#: So the ceiling is reported and the honest outcome is an unanswered one over
#: the full rule count, not a quiet answer over a subset.
_MAX_RECORD_CHARS = 200_000

#: The two intents a case can carry. Named, not numbered: the reviewer named
#: these two, and a determination and a request for what the record holds are a
#: real boundary rather than a taxonomy invented for completeness.
INFORMATIONAL = "informational"
DECISION = "decision"
_INTENTS = (INFORMATIONAL, DECISION)

#: The states an informational answer can be in. Four, and kept apart on
#: purpose: a policy that holds nothing on the subject, a policy that holds
#: something and it was gathered, a model that would not compose an answer, and
#: a request that never completed are four different replies to a reviewer, and
#: collapsing any pair of them reports one situation as another.
ANSWERED = "answered"
NO_RULE_BEARS = "no_rule_bears"
DECLINED = "declined"
#: The fourth state: a case read as informational whose answer did not get
#: gathered. `answer_informational` never *returns* this — it raises, so that
#: "the policy holds nothing on this" can never be produced by a request that
#: did not actually run. Its caller `answer_policy_case`, which by then knows the
#: intent was informational, catches that failure and materialises it as this
#: status. That keeps it apart from the other three, and stops a known
#: informational request from silently falling through to a determination, which
#: would answer a different question than the one that was asked.
FAILED = "failed"

#: The states a citation's source sentence can be in, kept apart for the same
#: reason the answer's four states are (constraint 5): an empty quote must never
#: stand in for the document's words, and a reader is told which case it is.
#: The projection stores each sentence once in ``spans`` and points every rule at
#: the spans it was drawn from through ``evidence_refs``; the quote is resolved by
#: following that reference, and these name the four ways that resolution can land.
SOURCE_QUOTED = "quoted"  # the rule's verbatim sentence was found and is carried
SOURCE_NO_CITATION = "no_citation"  # the rule points at no clause (empty ``evidence_refs``)
SOURCE_UNRESOLVED = "unresolved"  # it points at a clause, but no span carried the sentence
SOURCE_NOT_STORED = "not_stored"  # the span is present but its text was never stored (empty)

_CLASSIFY_SYSTEM_PROMPT = """You sort one question a reviewer has put to a governance policy into exactly \
one of two kinds. You are given the question and, below it, the facts and quantities the policy's rules \
test — the things a rule is measured against. Decide which kind the question is by what it does with \
those tested facts, not by any word it happens to use.

One thing separates the two kinds: whether the question SUPPLIES a tested fact or ASKS AFTER one.

- "informational": the reviewer is asking the policy to state a fact or quantity it holds — a limit, an \
entitlement, a definition, a procedure. The value they name is the subject they want told, the answer \
they are seeking; they have not supplied it. Naming their own role, status, or category — the position \
they hold or the group they belong to — only points at which part of the policy they mean. It is not \
one of the tested facts, and it does not turn a request into a case.

- "decision": the reviewer has SUPPLIED one of the tested facts as true of their own situation — a \
number, a date, an event, a state of affairs — and wants to know how the policy comes out on it: \
whether something is permitted, required, in breach, or within a limit. What marks this kind is that a \
fact the governing rule tests is already present in the question, offered as an input to be applied.

The reliable test is what the reviewer has done with the tested fact at issue. Two questions can name \
the same category and differ only here: one asks what value the policy sets for that category — asking \
after the quantity the rule tests — while the other states that value as already true of the reviewer's \
own case, supplying it. The first is informational; the second is a decision.

If a question does both — supplies one tested fact and asks after another — it is a "decision". The \
determination it calls for will name the rules it rests on and state what they hold, so the part it \
asks after is answered there rather than dropped.

Judge by what the question is doing, not by any particular word in it. The same question can be phrased \
as a request, a command, or a statement, and can be written in any language; none of that changes which \
of the two kinds it is.

Return ONLY a JSON object:
- "intent": "informational" or "decision".
- "reasoning": one or two sentences, in plain English, naming the tested fact at issue and saying \
whether the question supplied it or asked after it, and therefore which kind it is."""

_INFORMATIONAL_SYSTEM_PROMPT = """A reviewer has asked what a governance policy provides on some \
subject. You are given the reviewer's question and one policy as a lean JSON record, \
`grounding_projection_v1`. Read the answer from that record and nothing else.

The record has four parts:
- `envelope`: the policy's identity and the values every rule shares — its ids, the authority behind \
it, its effective dates, and the document's heading path.
- `spans`: the exact sentences from the source document, each stored once under an id, in the \
document's own words and uncut. A rule points at the sentences it was drawn from by id.
- `facts`: the terms and quantities the rules are measured against, each stored once under an id, \
with the unit it is counted in.
- `rules`: the policy's rules. Each carries a `rule_id`, a `rule_type` and an `evaluation_mode` of \
either deterministic or ai_ready, an `effect`, the attributes and facts it turns on (referenced by \
id), its `required_facts`, and `evidence_refs` — the ids of the `spans` it was drawn from.

This is the whole set you may draw on: answer only from this record, and cite only `rule_id`s that \
appear in `rules`.

A rule bears on the question when what it holds speaks to the subject the reviewer asked about — for \
example, a rule whose source sentence states a weekly hours cap bears on a question about how many \
hours someone may work, whether or not the reviewer supplied any hours. The quantity a reviewer asks \
after is usually in the rule's source sentence — follow its `evidence_refs` into `spans` — and may \
also be carried in its `facts` or `required_facts`; read them and report the limit the rule already \
holds rather than asking the reviewer to supply it.

Judge by what each rule holds, not by any particular word in it, and answer in the language the \
reviewer asked in; the record is bilingual and which subject a question is about is not a property of \
the language it is written in.

Return ONLY a JSON object:
- "bears": true if at least one rule speaks to the subject of the question, false if none does.
- "answer": your plain-language answer to the question, drawn only from the rules that bear on it. \
Empty string if none bears. Write it in the language the reviewer asked in. This is your own wording; \
do not present it as a direct quotation of the document.
- "cited_rule_ids": the `rule_id`s of the rules your answer draws on. Every rule you relied on, no \
rule you did not, and only ids that appear in `rules`. Empty array if none bears.
- "declined": true only if you cannot compose an answer from the record for a reason other than no \
rule bearing on it — for example the question is unintelligible. Normally false.
- "note": optional one-sentence caveat, e.g. that the record is partial or points elsewhere. Empty \
string if you have nothing to add."""


def _normalise_effort(reasoning_effort: str) -> str:
    return reasoning_effort if reasoning_effort in VALID_REASONING_EFFORTS else "medium"


def _grounding(
    *,
    rules_available: int,
    citations_requested: int,
    cited_ids: list[str],
    fabricated: list[str],
    oversize: bool,
) -> dict:
    """What the gather grounded on, reported rather than merely performed.

    The rules shown are the closed set an answer may draw on. This records how
    large that set was, how many citations the model asked for, how many named a
    rule actually in it, and — the check with teeth — which named none and were
    refused as fabrications. ``oversize`` is true when the policy's records were
    too large to show in one pass and no answer was composed.

    A grounding check that is only ever performed, never seen to refuse anything,
    is the "validator that could not fail" this repository documents. Reporting
    the refused ids here, alongside the coverage the explainer path already
    reports, means the check is observable: a reader — and a test — can watch it
    reject a citation to a rule that was never in front of it.
    """

    return {
        "prompt_version": PROMPT_VERSION,
        "rules_available": rules_available,
        "citations_requested": citations_requested,
        "rules_cited": len(cited_ids),
        "fabricated_citations": fabricated,
        "oversize": oversize,
    }


async def _chat_json(
    system_prompt: str,
    user_content: str,
    *,
    reasoning_effort: str | None = None,
    deployment: str | None = None,
    temperature: float | None = None,
) -> dict:
    """One JSON-mode model call with the same resilience the sibling scenario
    paths use: retry once on a bad parse, and drop `reasoning_effort` if the
    deployment rejects it rather than failing the whole feature.

    Two shapes of call share this body and are never mixed. The gather runs on
    the reasoning deployment with a `reasoning_effort` and no temperature — depth
    for a synthesis. The classifier runs on the fast deployment with
    `temperature=0` and no reasoning_effort — the one determinism control that
    deployment honours (the reasoning deployment rejects `temperature` and does
    not honour `seed`; see `AzureOpenAIClient.chat`). A temperature call therefore
    sends no reasoning_effort, and the reasoning-effort fallback below never fires
    for it.
    """

    settings = get_settings()
    if not settings.ai_enabled:
        raise RuntimeError("Azure OpenAI is not configured")

    ai_client = AzureOpenAIClient(settings)
    target_deployment = deployment or settings.azure_openai_deployment
    #: A deterministic (temperature) call carries no reasoning_effort; only the
    #: reasoning-deployment gather does.
    effort_to_send: str | None = (
        None if temperature is not None else _normalise_effort(reasoning_effort or "medium")
    )
    last_error: str | None = None

    for attempt in range(2):
        prompt = user_content
        if last_error:
            prompt += f"\n\nYour previous response was invalid: {last_error}\nPlease correct it and retry."
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        try:
            raw = await ai_client.chat(
                messages,
                deployment=target_deployment,
                json_mode=True,
                max_tokens=4000,
                timeout=180.0,
                temperature=temperature,
                reasoning_effort=effort_to_send,
            )
        except Exception as exc:  # noqa: BLE001
            if effort_to_send is not None:
                logger.warning(
                    "chat call with reasoning_effort=%s failed (%s); retrying without it",
                    effort_to_send,
                    exc,
                )
                effort_to_send = None
                raw = await ai_client.chat(
                    messages,
                    deployment=target_deployment,
                    json_mode=True,
                    max_tokens=4000,
                    timeout=180.0,
                    temperature=temperature,
                )
            else:
                raise
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("expected a JSON object")
            return parsed
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            logger.warning("case-intent call attempt %s failed to parse: %s", attempt, exc)

    raise RuntimeError(f"AI case-intent call did not produce a valid response after retry: {last_error}")


def _tested_quantities(payload: dict) -> list[str]:
    """The facts and quantities the policy's rules test, as short strings.

    This is the anchor the cut turns on: a determination *supplies* one of these
    as a fact of the case, an informational request *asks after* one. Each is the
    policy's own data — a rule's ``required_facts`` first (the named quantities it
    is measured against, with the unit it is counted in), then the terms the rules
    speak about from ``facts``, in the document's own words. Nothing here is a
    vocabulary this code carries: it is read from the record, it is bilingual, and
    it is tuned to no document, so the cut keys on the *structure* of the question
    against these — supplied or asked — never on a phrase.
    """

    out: list[str] = []
    seen: set[str] = set()

    def _add(label: str) -> None:
        label = " ".join(label.split())
        if label and label not in seen:
            seen.add(label)
            out.append(label)

    for rule in payload.get("rules") or []:
        for required in (rule or {}).get("required_facts") or []:
            if not isinstance(required, dict):
                continue
            name = str(required.get("name") or required.get("phrase") or "").strip()
            if not name:
                continue
            details = ", ".join(
                part
                for part in (
                    str(required.get("data_type") or "").strip(),
                    f"in {str(required.get('unit')).strip()}" if required.get("unit") else "",
                )
                if part
            )
            _add(f"{name} ({details})" if details else name)

    facts = payload.get("facts") or {}
    if isinstance(facts, dict):
        for fact in facts.values():
            if not isinstance(fact, dict):
                continue
            _add(str(fact.get("source_phrase") or fact.get("name") or "").strip())

    return out[:80]


async def classify_case_intent(
    scenario: str, *, tested_quantities: list[str] | None = None
) -> dict:
    """Sort the case into `informational` or `decision`.

    Returns ``{"intent": str, "reasoning": str}``. The model is handed the
    question together with ``tested_quantities`` — the facts and quantities the
    policy's rules test, from :func:`_tested_quantities` — and decides the one
    thing that separates the two kinds: whether the question *supplies* one of
    those facts or *asks after* it. Anchoring on the record rather than a
    vocabulary is what keeps this domain-neutral and lets it survive the corpus's
    Arabic; passing no quantities (the direct-call shape) leaves the model the
    question alone, and it sorts on the same supplied-vs-asked structure.

    The call runs on the fast deployment at ``temperature=0`` — the only
    determinism control that deployment honours — so the same question classifies
    the same way on every run. Where no fast deployment is configured it degrades
    to the reasoning deployment, which cannot promise that stability; the feature
    keeps working, but the guarantee is the fast deployment's to give.
    """

    settings = get_settings()
    lines = tested_quantities or []
    tested_block = (
        "\n".join(f"- {item}" for item in lines)
        if lines
        else "- (none supplied: sort on the question alone)"
    )
    user_content = (
        f"Question: {scenario}\n\n"
        "The facts and quantities the policy's rules test — a determination "
        "supplies one of these as a fact of the case, an informational request "
        "asks the policy to state one:\n"
        f"{tested_block}"
    )

    fast_deployment = settings.azure_openai_fast_deployment
    if fast_deployment:
        parsed = await _chat_json(
            _CLASSIFY_SYSTEM_PROMPT,
            user_content,
            deployment=fast_deployment,
            temperature=0.0,
        )
    else:
        logger.warning(
            "no fast deployment configured; classifying on the reasoning deployment, "
            "which does not guarantee run-to-run stability",
        )
        parsed = await _chat_json(_CLASSIFY_SYSTEM_PROMPT, user_content, reasoning_effort="low")

    intent = str(parsed.get("intent") or "").strip().lower()
    if intent not in _INTENTS:
        # An unreadable verdict is treated as a determination, the conservative
        # fallback: it routes the case to the deciders that already exist and
        # are audited, rather than to a composed answer this module would author.
        intent = DECISION
    return {"intent": intent, "reasoning": str(parsed.get("reasoning") or "")}


def _rules_by_id(rules: list[dict]) -> dict[str, dict]:
    """Index the payload's rules by their string id, first occurrence winning.

    The citation resolver needs each cited rule's ``evidence_refs``; the model
    cites by id, so the rules are indexed by the same id here rather than scanned
    per citation.
    """

    by_id: dict[str, dict] = {}
    for rule in rules:
        rid = rule.get("rule_id")
        if rid is not None and str(rid) not in by_id:
            by_id[str(rid)] = rule
    return by_id


def _citation_source(rule: dict | None, spans: dict) -> dict:
    """Follow a cited rule's ``evidence_refs`` into ``spans`` and return the
    verbatim sentence it rests on — or the reason there is none.

    The lean ``grounding_projection_v1`` payload stores every source sentence once
    in ``spans`` and has each rule point at the spans it was drawn from by id,
    attaching the rule's own quoted sentence to its first evidence reference
    (see ``policy_case_payload._evidence_refs``). A citation names a rule; to show
    the reader the words that rule rests on, that reference has to be followed.
    It is followed here — once, server-side, over the closed payload the answer
    was grounded on — never shipped to the client to redo, which would mean
    carrying the whole span dictionary to the browser and re-implementing the join
    there (§4.2). The text is returned exactly as the span holds it, uncut and
    untranslated (constraint 4); ``page`` and ``section`` ride along when the span
    recorded them, so a reader can find the sentence in the document.

    Four outcomes are kept apart (constraint 5), each naming which case it is so a
    blank never stands in for the document's words:

      - ``quoted`` — a span carried the sentence; ``text`` (and any ``page`` /
        ``section``) is returned.
      - ``no_citation`` — the rule points at no clause at all.
      - ``unresolved`` — it points at a clause, but no referenced span carried the
        sentence (the reference resolved to nothing here).
      - ``not_stored`` — a referenced span is present but its text was never stored
        (empty), the app's "source text was not stored with its rules" case.

    A generated rule name is never read or returned here (constraint 8): the only
    words carried are the document's own verbatim sentence, and the reader's
    surface still resolves the display name from the id.
    """

    refs = (rule or {}).get("evidence_refs") or []
    if not refs:
        return {"state": SOURCE_NO_CITATION}

    for ref in refs:
        span = spans.get(ref)
        if span is None or "text" not in span:
            # Either the reference resolved to nothing, or it is a supporting
            # clause carrying identity but no quoted sentence — keep looking for
            # the span that holds the rule's words.
            continue
        text = span.get("text")
        if not text:
            # The span is present but its sentence was never stored. Distinct from
            # a missing span, and never emitted as an empty-string quote.
            return {"state": SOURCE_NOT_STORED}
        source: dict = {"state": SOURCE_QUOTED, "text": text}
        page = span.get("page")
        if page is not None:
            source["page"] = page
        section = span.get("section")
        if section is not None:
            source["section"] = section
        return source

    # References were named, but none resolved to a span carrying the sentence —
    # not the same as citing no clause at all, so it is its own state.
    return {"state": SOURCE_UNRESOLVED}


def _citations(cited_ids: list[str], rules_by_id: dict[str, dict], spans: dict) -> list[dict]:
    """Build the citations the answer rests on: each cited id, with the verbatim
    source sentence resolved from the payload's spans.

    Every id here has already been checked against the closed payload, so each
    names a real rule; this attaches to it the document's own words that rule
    rests on, resolved server-side (never a name this app authored — constraint 8).
    """

    return [
        {"rule_id": rid, "source": _citation_source(rules_by_id.get(rid), spans)}
        for rid in cited_ids
    ]


async def answer_informational(
    payload: dict, *, scenario: str, reasoning_effort: str = "medium"
) -> dict:
    """Gather and state what the policy provides on the subject of the question.

    ``payload`` is the lean ``grounding_projection_v1`` record for one policy —
    the same projection the JSON tab renders — built by
    :func:`case_payload_for_provision` and handed in whole. It is the *closed
    set* an answer may draw on: one gather over the record rather than one call
    per rule, so the model can relate the rules to each other and to the
    question.

    Returns one of three content shapes, each also carrying a ``grounding``
    report, kept distinct so a reviewer is never shown one situation dressed as
    another:

      - answered:      ``{"status": "answered", "answer", "citations", "note", "grounding"}``
      - no rule bears: ``{"status": "no_rule_bears", "answer": "", "citations": [], "note", "grounding"}``
      - declined:      ``{"status": "declined", "answer": "", "citations": [], "note", "grounding"}``

    A failed request is the fourth state and is *not* returned here: it is raised
    as ``RuntimeError`` from the model call, so that "no rule bears on this"
    cannot be produced by a request that never actually ran.

    Two mechanical checks keep the answer grounded in the payload rather than
    merely instructed to be:

      - Every id the model cites must name a rule in ``payload["rules"]``. One
        that does not is a fabrication; it is dropped from the citations and
        reported in ``grounding.fabricated_citations`` so the refusal is visible,
        and if nothing valid is left the answer cannot be ``answered``.
      - If the payload is too large to show in one pass the gather is refused, not
        trimmed — an answer over some of a policy, presented as the policy's, is a
        narrowing a reviewer could not detect.

    Citations are ``rule_id``s only. A generated rule name is never sent to the
    model and never returned from here; the reader's surface resolves each id to
    that rule's display name and its verbatim source sentence at render time, so
    no name this app authored is mistaken for the document's, and the document's
    words reach the reader exactly.
    """

    rules = payload.get("rules") or []
    available_ids = {str(rule.get("rule_id")) for rule in rules if rule.get("rule_id")}

    transport = to_compact(payload)
    if len(transport) > _MAX_RECORD_CHARS:
        # The whole policy payload does not fit one grounded gather. Refuse rather
        # than trim: an answer composed from part of a policy and presented as the
        # policy's answer is the hiding a reviewer cannot see. Reported as its own
        # grounding fact, over the full rule count, and no model call is made.
        return {
            "status": DECLINED,
            "answer": "",
            "citations": [],
            "note": (
                "This policy's record is larger than can be read in one grounded pass, so no single "
                "answer was composed from it. The rules are listed below to read directly."
            ),
            "grounding": _grounding(
                rules_available=len(rules),
                citations_requested=0,
                cited_ids=[],
                fabricated=[],
                oversize=True,
            ),
        }

    user_content = f"Question: {scenario}\n\nPolicy record (grounding_projection_v1 JSON):\n{transport}"

    parsed = await _chat_json(
        _INFORMATIONAL_SYSTEM_PROMPT,
        user_content,
        reasoning_effort=reasoning_effort,
    )

    note = str(parsed.get("note") or "")

    raw_ids = parsed.get("cited_rule_ids") or []
    if not isinstance(raw_ids, list):
        raw_ids = []
    # Split what the model asked to cite into ids that name a rule in the payload
    # and ids that do not, keeping first-seen order and dropping repeats. A
    # citation to a rule not in the closed set is a fabrication: it is not a
    # citation, and — rather than vanish in silence — it is reported below so the
    # check that refused it can be seen to have refused something.
    requested = list(dict.fromkeys(str(rid) for rid in raw_ids))
    cited_ids = [rid for rid in requested if rid in available_ids]
    fabricated = [rid for rid in requested if rid not in available_ids]

    grounding = _grounding(
        rules_available=len(rules),
        citations_requested=len(requested),
        cited_ids=cited_ids,
        fabricated=fabricated,
        oversize=False,
    )

    if parsed.get("declined"):
        return {"status": DECLINED, "answer": "", "citations": [], "note": note, "grounding": grounding}

    bears = bool(parsed.get("bears"))
    answer = str(parsed.get("answer") or "").strip()

    if not bears or not cited_ids:
        # Nothing valid in this policy speaks to the subject — either the model
        # said so, or every id it offered named no rule here and nothing is left
        # to rest an answer on. Not a refusal and not a failure: it is an answer,
        # and a true one; the reviewer's question may be answerable, only not from
        # here. A fabricated-only citation cannot become an answer, and the
        # grounding records what was refused.
        return {"status": NO_RULE_BEARS, "answer": "", "citations": [], "note": note, "grounding": grounding}

    if not answer:
        # Rules bear on it but the model composed no answer. That is the model
        # standing back, kept separate from the record holding nothing.
        return {"status": DECLINED, "answer": "", "citations": [], "note": note, "grounding": grounding}

    # Cite by id, and carry the document's own verbatim source sentence for each —
    # resolved server-side here by following the rule's ``evidence_refs`` into the
    # payload's ``spans`` (constraint 4: exactly as stored, uncut and untranslated).
    # No name this app authored crosses the wire (constraint 8): the reader's
    # surface still resolves each id to its display name. Every id was checked
    # against the payload above, and a rule whose sentence is missing, unstored or
    # unreferenced is told apart rather than shown as an empty quote (constraint 5).
    spans = payload.get("spans") or {}
    citations = _citations(cited_ids, _rules_by_id(rules), spans)
    return {"status": ANSWERED, "answer": answer, "citations": citations, "note": note, "grounding": grounding}


async def answer_policy_case(
    payload: dict, *, scenario: str, reasoning_effort: str = "medium"
) -> dict:
    """Classify the case, and — for an informational request only — gather the
    answer the policy holds.

    ``payload`` is the lean ``grounding_projection_v1`` record for one policy,
    built by :func:`case_payload_for_provision`. Returns
    ``{"intent", "classification_reasoning", "informational", "reasoning_effort"}``.
    ``informational`` is populated only when the intent is informational; for a
    determination it is ``None`` and the caller runs the per-rule deciders it
    already has, unchanged. This module never runs those deciders itself, so
    there is one implementation of a determination and this is not a second.

    Two kinds of failure are kept apart, because they are not the same fact. A
    classification that does not complete leaves the intent *unknown*: there is
    no honest answer to compose, so it is raised for the endpoint to turn into a
    503 the product degrades on — never guessed into one intent or the other. A
    gather that does not complete on a case already read as informational leaves
    the intent *known*: that is the fourth informational state, reported as
    ``{"status": "failed"}`` rather than raised, so the reader is told the answer
    for their question did not come back rather than being handed a determination
    of a different question.
    """

    effort = _normalise_effort(reasoning_effort)

    classification = await classify_case_intent(
        scenario, tested_quantities=_tested_quantities(payload)
    )
    intent = classification["intent"]

    informational = None
    if intent == INFORMATIONAL:
        try:
            informational = await answer_informational(
                payload, scenario=scenario, reasoning_effort=effort
            )
        except RuntimeError:
            # The intent is known; only the gather failed. Report it as the
            # fourth state rather than letting it propagate, which would fail
            # the whole request and drop the product onto the determination
            # path — answering a question the reviewer did not ask. The
            # grounding still names how many rules were in scope, so a failed
            # gather is not mistaken for one over an empty policy.
            rules = payload.get("rules") or []
            informational = {
                "status": FAILED,
                "answer": "",
                "citations": [],
                "note": "",
                "grounding": _grounding(
                    rules_available=len(rules),
                    citations_requested=0,
                    cited_ids=[],
                    fabricated=[],
                    oversize=False,
                ),
            }

    return {
        "intent": intent,
        "classification_reasoning": classification["reasoning"],
        "informational": informational,
        "reasoning_effort": effort,
    }
