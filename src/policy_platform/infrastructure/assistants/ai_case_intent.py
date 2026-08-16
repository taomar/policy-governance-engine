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
are its own and are marked as its own by the caller; the words it quotes are the
record's, attached here verbatim from the rule's stored source and never
rewritten, translated, or trimmed.
"""
from __future__ import annotations

import json
import logging

from policy_platform.contracts.policy import CanonicalRule
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

PROMPT_VERSION = "ai-case-intent-v1"

VALID_REASONING_EFFORTS = ("low", "medium", "high")

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
# The fourth state, a failed request, is not a value here: it is an exception
# the caller turns into its own reply, so that "the policy holds nothing on
# this" can never be produced by a request that did not actually run.

_CLASSIFY_SYSTEM_PROMPT = """You sort one question a reviewer has put to a governance policy into exactly \
one of two kinds. Read only the question. Do not assume anything about the policy it was put to.

- "informational": the reviewer is asking what the policy provides, states, or allows on some \
subject — a limit, an entitlement, a definition, a procedure. They want the material the policy \
holds, stated back to them. The subject of their question is something the policy would answer, \
not a fact about a particular person or event that they have supplied.
- "decision": the reviewer has described a specific situation — facts about a person, an amount, \
an event — and wants to know how the policy comes out on it: whether something is permitted, \
required, in breach, or within a limit for that situation.

Judge by what the question is doing, not by any particular word in it. The same question can be \
phrased as a request, a command, or a statement, and can be written in any language; none of that \
changes which of the two kinds it is.

Return ONLY a JSON object:
- "intent": "informational" or "decision".
- "reasoning": one or two sentences, in plain English, saying what the question is doing and \
therefore which kind it is."""

_INFORMATIONAL_SYSTEM_PROMPT = """A reviewer has asked what a governance policy provides on some \
subject. You are given the reviewer's question and the policy's rules, each with an id, a title, \
and the exact sentence from the source document it was drawn from. Your job is to gather the \
material that answers the question and state it plainly.

Use only what the rules say. Do not invent a limit, a number, or a condition that is not in the \
material you were given. A rule bears on the question when the sentence it carries speaks to the \
subject the reviewer asked about — for example, a rule stating a weekly hours cap bears on a \
question about how many hours someone may work, whether or not the reviewer supplied any hours.

Return ONLY a JSON object:
- "bears": true if at least one rule speaks to the subject of the question, false if none does.
- "answer": your plain-English answer to the question, drawn only from the rules that bear on it. \
Empty string if none bears. Write it in the language the reviewer asked in. This is your own \
wording; do not present it as a direct quotation of the document.
- "cited_rule_ids": the ids of the rules your answer draws on. Every rule you relied on, and no \
rule you did not. Empty array if none bears.
- "declined": true only if you cannot compose an answer from the material for a reason other than \
no rule bearing on it — for example the question is unintelligible. Normally false.
- "note": optional one-sentence caveat, e.g. that the material is partial or points elsewhere. \
Empty string if you have nothing to add."""


def _normalise_effort(reasoning_effort: str) -> str:
    return reasoning_effort if reasoning_effort in VALID_REASONING_EFFORTS else "medium"


def _verbatim_source(rule: CanonicalRule) -> str:
    """The record's own words for this rule, for quoting back unchanged.

    Preference order is by fidelity to the document. The formulation's
    `source_text` is the sentence the extraction was anchored to and is
    preserved verbatim; `description` is the rule's own statement of itself; the
    title is the last resort. Whichever is returned is the document's language,
    never this app's, so a caller must not translate or trim it.
    """

    formulation = rule.formulation
    if formulation is not None and formulation.canonical is not None:
        text = (formulation.canonical.source_text or "").strip()
        if text:
            return text
    description = (rule.description or "").strip()
    if description:
        return description
    return (rule.title or "").strip()


def _rule_digest(rule: CanonicalRule) -> dict:
    """What the model is shown about one rule when gathering an answer.

    The source sentence carries the subject and any quantity it names, so it is
    the load-bearing field. The required-fact names are included as the
    quantities the rule is *about*, which is exactly what an informational
    question tends to ask after — never as a demand, because nothing here is
    deciding anything.
    """

    return {
        "rule_id": rule.rule_id,
        "title": rule.title,
        "statement": _verbatim_source(rule),
        "concerns": [fact.name for fact in rule.required_facts],
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
    rules: list[CanonicalRule], *, scenario: str, reasoning_effort: str = "medium"
) -> dict:
    """Gather and state what the policy provides on the subject of the question.

    Returns one of four shapes, kept distinct so a reviewer is never shown one
    situation dressed as another:

      - answered:      ``{"status": "answered", "answer", "citations", "note"}``
      - no rule bears: ``{"status": "no_rule_bears", "answer": "", "citations": [], "note"}``
      - declined:      ``{"status": "declined", "answer": "", "citations": [], "note"}``

    A failed request is the fourth state and is *not* returned here: it is raised
    as ``RuntimeError`` from the model call, so that "no rule bears on this"
    cannot be produced by a request that never actually ran.

    ``answer`` is this module's own wording — the caller marks it as such. The
    ``citations`` carry each cited rule's source sentence verbatim, taken from
    the record here and not from the model, so the document's words reach the
    reader exactly as the document wrote them.
    """

    by_id = {rule.rule_id: rule for rule in rules}
    digests = [_rule_digest(rule) for rule in rules]
    user_content = (
        f"Question: {scenario}\n\n"
        f"Policy rules:\n{json.dumps(digests, ensure_ascii=False, indent=2)}"
    )

    parsed = await _chat_json(
        _INFORMATIONAL_SYSTEM_PROMPT,
        user_content,
        reasoning_effort=reasoning_effort,
    )

    note = str(parsed.get("note") or "")
    if parsed.get("declined"):
        return {"status": DECLINED, "answer": "", "citations": [], "note": note}

    bears = bool(parsed.get("bears"))
    raw_ids = parsed.get("cited_rule_ids") or []
    if not isinstance(raw_ids, list):
        raw_ids = []
    # Keep only ids that name a rule actually in this policy, in the order the
    # model gave them and without repeats. A citation to a rule not in front of
    # the reader is not a citation.
    seen: set[str] = set()
    cited_ids: list[str] = []
    for rid in raw_ids:
        rid = str(rid)
        if rid in by_id and rid not in seen:
            seen.add(rid)
            cited_ids.append(rid)

    answer = str(parsed.get("answer") or "").strip()

    if not bears or not cited_ids:
        # Nothing in this policy speaks to the subject. This is not a refusal and
        # not a failure — it is an answer, and a true one: the reviewer's
        # question may be answerable, only not from here.
        return {"status": NO_RULE_BEARS, "answer": "", "citations": [], "note": note}

    if not answer:
        # Rules bear on it but the model composed no answer. That is the model
        # standing back, kept separate from the record holding nothing.
        return {"status": DECLINED, "answer": "", "citations": [], "note": note}

    citations = [
        {
            "rule_id": rid,
            "title": by_id[rid].title,
            "quote": _verbatim_source(by_id[rid]),
        }
        for rid in cited_ids
    ]
    return {"status": ANSWERED, "answer": answer, "citations": citations, "note": note}


async def answer_policy_case(
    rule_payloads: list[dict], *, scenario: str, reasoning_effort: str = "medium"
) -> dict:
    """Classify the case, and — for an informational request only — gather the
    answer the policy holds.

    Returns ``{"intent", "classification_reasoning", "informational", "reasoning_effort"}``.
    ``informational`` is populated only when the intent is informational; for a
    determination it is ``None`` and the caller runs the per-rule deciders it
    already has, unchanged. This module never runs those deciders itself, so
    there is one implementation of a determination and this is not a second.
    """

    effort = _normalise_effort(reasoning_effort)

    # Validate the rule shapes up front, before any model call, so a malformed
    # payload fails as the caller's error (422) rather than mid-feature.
    rules = [CanonicalRule.model_validate(payload) for payload in rule_payloads]

    classification = await classify_case_intent(scenario, reasoning_effort=effort)
    intent = classification["intent"]

    informational = None
    if intent == INFORMATIONAL:
        informational = await answer_informational(
            rules, scenario=scenario, reasoning_effort=effort
        )

    return {
        "intent": intent,
        "classification_reasoning": classification["reasoning"],
        "informational": informational,
        "reasoning_effort": effort,
    }
