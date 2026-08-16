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

WHY THE INTENT IS READ FROM THE QUESTION AND NOTHING ELSE

The intent is a property of what is being asked, not of the policy it is asked
against or the words any one document happens to use. So `classify_case_intent`
is given the case and *only* the case, and a model decides it. It is never a
list of trigger phrases: a vocabulary of "how many" / "can I" / "am I" is a
property of one language, and this corpus is bilingual. A phrase list would
classify English and be blind to the Arabic clause that asks the same thing.

WHAT THIS DOES NOT DO

It does not decide anything. A determination is still the deterministic engine's
or the judge's to make, one rule at a time, through the paths that already exist
and are already audited. This module classifies, and — for an informational
request only — gathers and states what the policy holds. The words it composes
are its own and are marked as its own by the caller; it cites the rules its
answer rests on by id, and the reader's surface resolves each id to that rule's
name and its verbatim source sentence, so the document's own words reach the
reader unrewritten, untranslated, and untrimmed.
"""
from __future__ import annotations

import json
import logging

from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.projection.policy_case_payload import to_compact
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

PROMPT_VERSION = "ai-case-intent-v3"

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

_CLASSIFY_SYSTEM_PROMPT = """You sort one question a reviewer has put to a governance policy into exactly \
one of two kinds. Read only the question. Do not assume anything about the policy it was put to.

- "informational": the reviewer is asking what the policy provides, states, or allows on some \
subject — a limit, an entitlement, a definition, a procedure. They want the material the policy holds, \
stated back to them. The thing they ask about is what they want the policy to tell them: it is the \
answer they are seeking, not a fact they have supplied. Naming their own role or standing — that they \
hold some position or belong to some group — to point at the part of the policy they mean is \
orientation, not a case. It says which subject they are asking about; it does not hand over the facts a \
determination would weigh.
- "decision": the reviewer has supplied the specific facts a determination turns on — a quantity, a \
date, an event, a state of affairs they have described — and wants to know how the policy comes out on \
those facts: whether something is permitted, required, in breach, or within a limit for the situation \
they gave. What marks this kind is that the facts the governing rule would weigh are already present in \
the question, offered as inputs to be applied.

The reliable test is what the reviewer has done with the quantity or fact at issue. If that quantity is \
what they are asking the policy to state — the output they want back — the question is informational, \
even when they mention their own situation to place it. If they have already stated it and want the \
policy applied to it, the question is a decision.

Judge by what the question is doing, not by any particular word in it. The same question can be phrased \
as a request, a command, or a statement, and can be written in any language; none of that changes which \
of the two kinds it is.

Return ONLY a JSON object:
- "intent": "informational" or "decision".
- "reasoning": one or two sentences, in plain English, saying what the question is doing and therefore \
which kind it is."""

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


async def _chat_json(system_prompt: str, user_content: str, *, reasoning_effort: str) -> dict:
    """One JSON-mode model call with the same resilience the sibling scenario
    paths use: retry once on a bad parse, and drop `reasoning_effort` if the
    deployment rejects it rather than failing the whole feature."""

    settings = get_settings()
    if not settings.ai_enabled:
        raise RuntimeError("Azure OpenAI is not configured")

    ai_client = AzureOpenAIClient(settings)
    effort_to_send: str | None = _normalise_effort(reasoning_effort)
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
                deployment=settings.azure_openai_deployment,
                json_mode=True,
                max_tokens=4000,
                timeout=180.0,
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
                    deployment=settings.azure_openai_deployment,
                    json_mode=True,
                    max_tokens=4000,
                    timeout=180.0,
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


async def classify_case_intent(scenario: str, *, reasoning_effort: str = "medium") -> dict:
    """Sort the case into `informational` or `decision`, reading only the case.

    Returns ``{"intent": str, "reasoning": str}``. The model is handed the
    question and nothing else — not the policy, not its rules, not the corpus —
    because the intent is a property of the question. That is also what keeps
    this domain-neutral: there is no vocabulary to key on, so there is nothing
    to translate and nothing tuned to one document.
    """

    parsed = await _chat_json(
        _CLASSIFY_SYSTEM_PROMPT,
        f"Question: {scenario}",
        reasoning_effort=reasoning_effort,
    )
    intent = str(parsed.get("intent") or "").strip().lower()
    if intent not in _INTENTS:
        # An unreadable verdict is treated as a determination, the conservative
        # fallback: it routes the case to the deciders that already exist and
        # are audited, rather than to a composed answer this module would author.
        intent = DECISION
    return {"intent": intent, "reasoning": str(parsed.get("reasoning") or "")}


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

    # Cite by id only. The reader's surface resolves each id to its display name
    # and its verbatim source sentence, so nothing this app authored crosses the
    # wire as if it were the document's, and every cited id was checked against
    # the payload above.
    citations = [{"rule_id": rid} for rid in cited_ids]
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

    classification = await classify_case_intent(scenario, reasoning_effort=effort)
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
