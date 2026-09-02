"""Stage 1 agent: strict verbatim policy-passage extraction.

Runs *before* the policy formulator. Its only job is to decide which spans of a
document are policy-bearing and to copy them out character-for-character. It
never writes policy text.

Why this stage exists
---------------------
Feeding raw document text straight to the formulator made the formulator do two
incompatible jobs at once: decide *what is a rule* and decide *what that rule
means as structured data*. With no instruction to reject anything, it dutifully
converted every sentence it saw — table-of-contents lines, translation
conventions, publication clauses, and legislative amendment instructions like
"Paragraph (3) of Article (38) ... shall be deleted" — into obligations. Those
records are structurally valid and semantically worthless.

Stage 1 pushes that judgement to a boundary where it can be *checked*. Because
its output must be a contiguous substring of the source, a fabricated passage is
detectable by string containment rather than by human re-reading. The agent is
told to self-validate (specification Section 26), but `verify_verbatim` below
re-checks every passage in code: an LLM's promise about its own output is not
evidence, and this is the one property of the pipeline that can be proven
cheaply.

The system prompt is the specification shipped verbatim at
`prompts/passage_extractor_v1.md`, loaded from disk so a prompt revision is a
visible file change rather than a diff buried in Python.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from functools import lru_cache

from pydantic import ValidationError

from policy_platform.contracts.passage import PassageExtraction, PassageSource, PolicyPassage
from policy_platform.infrastructure.ai.openai_client import (
    EXTRACTION_SEED,
    AzureOpenAIClient,
    AzureOpenAITransientError,
)
from policy_platform.infrastructure.prompt_assets import load_prompt
from policy_platform.infrastructure.settings import Settings

logger = logging.getLogger(__name__)

#: Bump whenever the prompt asset or the transport addendum changes.
PASSAGE_PROMPT_VERSION = "verbatim-passage-extractor-v1"

#: The specification header mandates medium reasoning effort. Set here rather
#: than left to callers because it is part of the standard, not a tuning knob.
PASSAGE_REASONING_EFFORT = "medium"

_PROMPT_NAME = "passage_extractor_v1.md"

_TRANSPORT_ADDENDUM = """

---

# TRANSPORT ADDENDUM (application-supplied)

## How the source is supplied

The source document is supplied to you as a sequence of clause blocks. Each
block begins with a marker line of the form:

    [clause_ref=<identifier>]

followed by the clause's source text.

**The marker line is NOT part of the source document.** It is an application
addressing label. Therefore:

- NEVER copy a `[clause_ref=...]` marker into the `text` field.
- NEVER treat a marker as a sentence, heading or policy statement.
- The source text of a clause is everything after its marker line, up to the
  next marker line.

## Reporting the location

For every passage you return, set `source.clause_ref` to the identifier of the
clause the passage was copied from, exactly as supplied.

If a passage necessarily spans two or more consecutive clause blocks, set
`source.clause_ref` to the identifier of the FIRST clause in that span, and set
`source.end_clause_ref` to the identifier of the LAST clause in that span.

`source.clause_ref` is required. A passage returned without it cannot be traced
back to the document and will be discarded.

**The span reference is the most important field you produce.** The application
holds the authoritative source text and copies passages out of it using your
span. Your `text` value is a cross-check, not the product. A passage with an
accurate span and imperfectly transcribed text is recoverable; a passage with
perfect text and no span is not.

## Verification performed by the application

Every passage you return is mechanically re-checked: the application asserts
that your `text` value occurs inside the supplied source text. A passage whose
text does not occur is NOT silently dropped — the application replaces it with
the text it copies itself from your span reference. So an inaccurate
transcription costs precision, while an inaccurate span costs the passage.

This check ignores differences in whitespace only. It does not tolerate a
single changed, added or removed word.

## Output

Return exactly one JSON object, and nothing else, in the Section 24 shape:

{
  "document_id": "...",
  "document_name": "...",
  "policy_passages": [
    {
      "passage_id": "P000001",
      "classification": "POLICY",
      "text": "EXACT SOURCE TEXT ONLY",
      "source": {
        "clause_ref": "...",
        "end_clause_ref": null,
        "page": null, "section": null, "article": null, "paragraph": null
      }
    }
  ]
}

If the supplied source contains no policy-bearing text at all, return the same
object with an empty `policy_passages` array. An empty result is a valid and
correct answer; inventing a passage to avoid returning nothing is not.

No prose. No markdown fences. No commentary before or after the object.
"""


@lru_cache(maxsize=1)
def load_passage_prompt() -> str:
    """Return the specification prompt plus the transport addendum."""

    return load_prompt(_PROMPT_NAME) + _TRANSPORT_ADDENDUM


class PassageExtractionError(RuntimeError):
    """The agent's reply could not be read as a valid passage extraction."""


def _strip_code_fence(text: str) -> str:
    """Remove a wrapping ```json fence if the model emitted one anyway."""

    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    fenced = re.match(r"^```(?:json)?\s*\n(.*?)\n?```\s*$", stripped, re.DOTALL)
    return fenced.group(1).strip() if fenced else stripped


def parse_passages(raw: str) -> PassageExtraction:
    """Turn one agent reply into a validated `PassageExtraction`."""

    text = _strip_code_fence(raw)
    if not text:
        raise PassageExtractionError("passage extractor returned an empty response")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PassageExtractionError(
            f"passage extractor returned unparseable output: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise PassageExtractionError(
            f"passage extractor returned a {type(payload).__name__}, expected a JSON object"
        )

    try:
        return PassageExtraction.model_validate(payload)
    except ValidationError as exc:
        raise PassageExtractionError(
            f"passage extractor output failed contract validation: {exc}"
        ) from exc


#: Characters that PDF extraction and typography routinely vary without any
#: change in wording: curly vs straight quotes, the several dash widths, and
#: the soft hyphen used to break words across lines. Folding these is not a
#: relaxation of the verbatim rule — the *words* must still match exactly — it
#: prevents a correctly-copied passage being rejected because the ingestion
#: layer and the model rendered the same character differently.
_CHAR_FOLD = {
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
    "\u2014": "-", "\u2015": "-", "\u2212": "-",
    "\u00a0": " ", "\u202f": " ", "\u2007": " ", "\u2009": " ",
    "\u00ad": "", "\ufeff": "", "\u200b": "",
}


def _normalize(text: str) -> str:
    """Collapse formatting-only variation so wording can be compared.

    Whitespace is collapsed because PDF ingestion inserts line breaks at
    arbitrary points (specification Section 17 explicitly anticipates this),
    and a passage split across two lines is still the same passage. Word
    identity is preserved: nothing here can make two different words compare
    equal.
    """

    folded = unicodedata.normalize("NFKC", text)
    folded = "".join(_CHAR_FOLD.get(ch, ch) for ch in folded)
    return re.sub(r"\s+", " ", folded).strip().casefold()


#: Lines the application writes into what Stage 1 reads, which are not document
#: text. `ai_extraction._render_batch` prefixes every clause with an addressing
#: label, its section name, and — for a table row — its column names, so the
#: model can tell one clause from the next and read a row in context.
#:
#: `_render_passages` already strips them before Stage 2, in its own words
#: because they are "non-policy strings to misread as content". Stage 1 sees
#: them, and sometimes copies one into a passage.
#:
#: The shapes are anchored to the start of a line and mirror exactly what
#: `_render_batch` emits. They are not a guess about what a document might
#: contain: `(section:` appears in 0 of 362 parsed clauses of the corpus this
#: was found on, because the string exists only in what this application
#: renders.
_APPLICATION_SCAFFOLDING = (
    re.compile(r"^\s*\[clause_ref=[^\]]*\]\s*", re.IGNORECASE),
    re.compile(r"^\s*\(section:[^)]*\)\s*", re.IGNORECASE),
    re.compile(r"^\s*\(columns?:[^)]*\)\s*", re.IGNORECASE),
)


def strip_application_scaffolding(passage_text: str) -> str:
    """Remove the application's own labels from the front of a passage.

    A passage is the product's promise that these words are in the customer's
    document. `verify_verbatim` proves it by containment — against the *rendered
    batch*, which is the document plus the labels this application added. So a
    passage that copied a label was verified against the copy of the label
    sitting in the very text it was checked against, and passed.

    The result reaches a reviewer as the sentence the policy states, travels
    into the record's `source_text`, is quoted as evidence, and on the AI Ready
    route is what a judge reads to decide a case. Sixteen records in one
    extraction of a staff handbook began with "(section: Table of Violations and
    Penalties)", which that handbook does not say anywhere.

    It is also, measurably, most of Stage 1's run-to-run variance. Comparing two
    extractions of the same file: 42 spans differed, 38 of them by exactly this
    prefix — the model copying the label on one run and not the other. The
    re-segmentation proposal held for a user decision was aimed at boundary
    variance; this is what that variance mostly was.

    Only leading labels are removed, and only whole ones. A passage is a
    contiguous span, so a label the model copied can only be at its front; a
    parenthesis mid-sentence is the document's own and is left alone.
    """

    text = passage_text or ""
    changed = True
    while changed:
        changed = False
        for pattern in _APPLICATION_SCAFFOLDING:
            stripped = pattern.sub("", text, count=1)
            if stripped != text:
                text = stripped
                changed = True
    return text.strip()


def verify_verbatim(passage_text: str, source_text: str) -> bool:
    """True when `passage_text` really occurs inside `source_text`.

    This is the guarantee that makes Stage 1 trustworthy. The agent is
    instructed to self-validate, but self-reporting is not evidence: the whole
    point of a verbatim stage is that its output is *checkable*, so it is
    checked here rather than assumed.

    Note what `source_text` is at the call site: the rendered batch, which is
    the document *plus* this application's addressing labels. Containment
    against it cannot distinguish a span of the document from a span of the
    scaffolding, which is why `strip_application_scaffolding` runs before this
    rather than inside it — the labels have to be gone before the question is
    asked, not forgiven while answering it.
    """

    if not passage_text.strip():
        return False
    if passage_text in source_text:
        return True
    return _normalize(passage_text) in _normalize(source_text)


def clean_clause_ref(ref: str | None) -> str | None:
    """Recover the bare identifier from a decorated one.

    Agents routinely echo an addressing label back with helpful adornment —
    surrounding brackets, a `clause_ref=` prefix, a trailing section name. None
    of that changes which clause is meant, so discarding a passage over it
    would be throwing away a correct answer on a formatting technicality. Only
    the leading token is kept, because that is the identifier; anything after
    the first space is commentary.
    """

    if ref is None:
        return None
    cleaned = ref.strip().strip("[]").strip()
    if cleaned.lower().startswith("clause_ref="):
        cleaned = cleaned[len("clause_ref=") :].strip()
    cleaned = cleaned.split()[0] if cleaned.split() else ""
    return cleaned or None


def _span_indices(
    source: PassageSource, clause_texts: dict[str, str], clause_order: list[str]
) -> tuple[int, int] | None:
    """Resolve a passage's source span to a `(start_idx, end_idx)` pair into `clause_order`.

    Shared by `resolve_span` (which needs the span's text) and
    `span_clause_refs` (which needs the span's identifiers), so the text
    Stage 2 reads and the identifiers evidence later points at can never fall
    out of sync — both are computed from exactly the same index resolution.

    Returns None when the span cannot be resolved: an unknown identifier, or
    an empty span. An unresolvable span is a real failure and must not be
    papered over with a best guess, because the guess would silently
    attribute one clause block's text to another clause's location.
    """

    start_ref = clean_clause_ref(source.clause_ref)
    if not start_ref or start_ref not in clause_texts:
        return None

    end_ref = clean_clause_ref(source.end_clause_ref) or start_ref
    if end_ref not in clause_texts:
        # A hallucinated end is recoverable — the start is known and is where
        # the passage begins — so degrade to the single starting clause rather
        # than losing the passage entirely.
        end_ref = start_ref

    try:
        start_idx = clause_order.index(start_ref)
        end_idx = clause_order.index(end_ref)
    except ValueError:
        return None

    if end_idx < start_idx:
        start_idx, end_idx = end_idx, start_idx
    return start_idx, end_idx


def resolve_span(
    source: PassageSource,
    clause_texts: dict[str, str],
    clause_order: list[str],
) -> str | None:
    """Copy the text a span reference points at, out of the application's own store.

    This is the step the architecture specification ends on: the agent returns
    *where* the policy is, and the application — which holds the authoritative
    canonical text — produces the characters. It is a stronger guarantee than
    verifying the agent's transcription after the fact. Verification makes a
    fabricated word *detectable*; copying makes it *impossible*, because no
    model-authored character ever reaches the output.

    Returns None when the span cannot be resolved (see `_span_indices`).
    """

    indices = _span_indices(source, clause_texts, clause_order)
    if indices is None:
        return None
    start_idx, end_idx = indices

    parts = [clause_texts[ref] for ref in clause_order[start_idx : end_idx + 1]]
    joined = "\n\n".join(part.strip() for part in parts if part.strip())
    return joined or None


def span_clause_refs(
    source: PassageSource,
    clause_texts: dict[str, str],
    clause_order: list[str],
) -> list[str] | None:
    """Return the ordered clause identifiers a passage's source span covers.

    This is `resolve_span`'s sibling for provenance rather than content: it
    answers "which clause(s) did this text actually come from?" instead of
    "what does that span say?". Extraction uses it to attach evidence to the
    *specific* clause(s) a passage was copied from, rather than to every
    clause anywhere near it in the batch — the same span/reference precision
    that document-interchange standards for normative text (e.g. Akoma
    Ntoso's element-level cross-references, LegalRuleML's many-to-many
    rule-to-provision linking) treat as a basic correctness requirement,
    regardless of what kind of source document (statute, HR handbook, IT
    policy, procurement manual, ...) the clauses came from.

    Returns None when the span cannot be resolved (see `_span_indices`).
    """

    indices = _span_indices(source, clause_texts, clause_order)
    if indices is None:
        return None
    start_idx, end_idx = indices
    return clause_order[start_idx : end_idx + 1]


class PassageExtractorAgent:
    """Identifies and copies policy-bearing passages. Stateless apart from its client."""

    def __init__(self, client: AzureOpenAIClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    async def extract(
        self,
        source_text: str,
        *,
        document_id: str = "",
        document_name: str = "",
        clause_texts: dict[str, str] | None = None,
        clause_order: list[str] | None = None,
    ) -> tuple[list[PolicyPassage], list[PolicyPassage]]:
        """Extract passages from one block of source text.

        Returns `(kept, rejected)`. `rejected` holds passages that could
        neither be verified against the source nor resolved from a span
        reference — they are returned rather than silently dropped so the caller
        can log and count them, because a rising fabrication rate is a signal
        about the model that must not disappear.

        When `clause_texts`/`clause_order` are supplied, a passage whose text
        fails verification is repaired by copying the span it points at, rather
        than discarded. That converts the common failure — a near-miss
        transcription of real policy text — from a lost rule into a slightly
        coarser but provably authentic one.

        Raises `PassageExtractionError` on an unusable reply.
        """

        if not source_text.strip():
            raise PassageExtractionError("cannot extract passages from empty source text")

        try:
            raw = await self._client.chat(
                [
                    {"role": "system", "content": load_passage_prompt()},
                    {
                        "role": "user",
                        "content": (
                            f"DOCUMENT_ID: {document_id or 'unknown'}\n"
                            f"DOCUMENT_NAME: {document_name or 'unknown'}\n\n"
                            "SOURCE DOCUMENT TEXT:\n"
                            f"{source_text}"
                        ),
                    },
                ],
                deployment=self._settings.azure_openai_deployment,
                json_mode=True,
                # Stage 1 copies rather than restructures, so its output is bounded
                # by the size of the input: at worst it returns the whole batch
                # plus per-passage metadata.
                #
                # RAISED FOR THE REASONING PASS, AND GENEROUS ON PURPOSE. This was
                # 16,000, set for a non-reasoning model; a reasoning deployment
                # spends part of the budget before emitting anything, and an
                # exhausted budget returns empty content rather than an error. Azure
                # meters TPM on prompt + `max_tokens` at request time, so a budget
                # this size can throttle a concurrent call — accepted, because a
                # passage lost to truncation is one no later stage can recover,
                # while a throttled call is retried with back-off by
                # `_post_with_retry`.
                max_tokens=64000,
                timeout=1200.0,
                reasoning_effort=PASSAGE_REASONING_EFFORT,
                # Measured as making no difference on this deployment; see
                # EXTRACTION_SEED. Sent so that the determinism controls this
                # call *can* set are all set and visible in one place.
                seed=EXTRACTION_SEED,
            )
        except AzureOpenAITransientError as exc:
            # Reported as this agent's own failure so the caller skips the batch
            # instead of losing the run. See the matching note in the formulator.
            raise PassageExtractionError(
                f"passage extractor was unreachable: {exc}"
            ) from exc

        extraction = parse_passages(raw)

        kept: list[PolicyPassage] = []
        rejected: list[PolicyPassage] = []
        repaired = 0
        for passage in extraction.policy_passages:
            # The application's own labels are not the customer's document.
            # Removed before verification, not after: `source_text` here is the
            # rendered batch, so a copied label would otherwise be verified
            # against itself. See `strip_application_scaffolding`.
            passage.text = strip_application_scaffolding(passage.text)
            if verify_verbatim(passage.text, source_text):
                kept.append(passage)
                continue

            recovered = (
                resolve_span(passage.source, clause_texts, clause_order)
                if clause_texts is not None and clause_order is not None
                else None
            )
            if recovered is None:
                rejected.append(passage)
                continue

            passage.text = recovered
            passage.text_origin = "application_copied"
            kept.append(passage)
            repaired += 1

        if rejected:
            logger.warning(
                "passage extractor: discarded %d of %d passages that are neither verbatim "
                "substrings of the source nor resolvable spans; first offender: %r",
                len(rejected),
                len(extraction.policy_passages),
                rejected[0].text[:200],
            )
        logger.info(
            "extracted %d policy passages (%d repaired from span refs, %d rejected) from %d chars",
            len(kept),
            repaired,
            len(rejected),
            len(source_text),
        )
        return kept, rejected
