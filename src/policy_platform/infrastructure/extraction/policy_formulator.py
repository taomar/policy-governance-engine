"""The policy formulator agent: policy prose in, canonical + DMN JSON out.

This module is deliberately a *separate agent* from clause extraction rather
than another prompt inside `ai_extraction`. Scanning and formulating are
different jobs with different failure modes:

- **Scanning** (`ai_document_ingest` / `Clause` rows) decides *where a policy
  statement starts and stops* in a document. It is document-shaped: pages,
  headings, numbering.
- **Formulating** (this module) decides *what a policy statement means* as
  structured data. It is standards-shaped: OMG DMN 1.5, FEEL, and the
  canonical subject/predicate/object decomposition.

Keeping them apart means the formulator can be run over text from any source —
a scanned document, a pasted paragraph, a regression fixture — and can be
re-run and re-versioned without re-scanning documents. It also keeps the
extremely long specification prompt out of the extraction path's context when
extraction is doing something else.

The agent's system prompt is the specification shipped verbatim at
`prompts/policy_formulator_v1.md`. It is loaded from disk rather than inlined
so the governing standard stays reviewable as a document and so a prompt
revision is a visible file change rather than a diff buried in Python.

**Known, deliberate deviation from the specification.** Spec Section 104 asks
for two separately-labelled top-level blocks (`CANONICAL_JSON` then
`DMN_JSON`). Azure OpenAI's JSON mode — which the platform relies on to avoid
prose-wrapped, unparseable replies — guarantees exactly one JSON *object* per
response. The two are reconciled by asking for a single envelope with those
two labels as keys. This is a transport framing change only: both documents
are returned in full, unmodified, in the spec's own field order. The parser
below also accepts the spec's literal two-block form, so a future non-JSON-mode
transport needs no prompt change.
"""
from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any

from pydantic import ValidationError

from policy_platform.contracts.formulation import (
    CanonicalPolicy,
    DmnProjection,
    PolicyFormulation,
)
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.prompt_assets import load_prompt
from policy_platform.infrastructure.settings import Settings

logger = logging.getLogger(__name__)

#: Bump whenever the prompt asset or the transport addendum changes, so
#: `RuleLineage.prompt_version` distinguishes rules formulated under different
#: revisions of the standard. Recorded on every rule this agent contributes to.
FORMULATOR_PROMPT_VERSION = "dmn-formulator-v1"

#: Spec Section 3 mandates medium reasoning effort. It is set here rather than
#: left to callers because it is part of the standard, not a tuning knob.
FORMULATOR_REASONING_EFFORT = "medium"

_PROMPT_NAME = "policy_formulator_v1.md"

_TRANSPORT_ADDENDUM = """

---

# TRANSPORT ADDENDUM (application-supplied)

This deployment consumes your output programmatically through a JSON-mode API
that accepts exactly one JSON object per response. Section 104's two labelled
blocks are therefore carried as two keys of one object.

Return exactly one JSON object, and nothing else:

{
  "CANONICAL_JSON": { "canonical_policies": [ ... ] },
  "DMN_JSON": { "dmn_projection": { "standard": "OMG DMN 1.5", "expression_language": "FEEL", "representation": "DMN-compatible JSON IR", "decisions": [ ... ] } }
}

This changes framing only. Every other requirement stands unchanged: the
contents, the field order of Sections 93 and 94, the omission of absent
properties (Section 22), the closed vocabularies, the refusal to invent facts,
and the final silent validation of Section 105.

No prose. No markdown fences. No commentary before or after the object.
"""


@lru_cache(maxsize=1)
def load_formulator_prompt() -> str:
    """Return the specification prompt plus the transport addendum.

    Cached because the asset is ~3000 lines and is otherwise re-read on every
    formulation call.
    """

    return load_prompt(_PROMPT_NAME) + _TRANSPORT_ADDENDUM


class PolicyFormulationError(RuntimeError):
    """The agent's reply could not be read as a valid formulation.

    Raised instead of returning a partial result: a formulation that silently
    dropped half its canonical policies would be worse than a visible failure,
    because downstream review has no way to notice the absence.
    """


def _strip_code_fence(text: str) -> str:
    """Remove a wrapping ```json fence if the model emitted one anyway."""

    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    fenced = re.match(r"^```(?:json)?\s*\n(.*?)\n?```\s*$", stripped, re.DOTALL)
    return fenced.group(1).strip() if fenced else stripped


def _extract_labelled_blocks(text: str) -> dict[str, Any] | None:
    """Parse the spec's literal Section 104 two-block form, if that's what arrived.

    Kept so the agent still works if JSON mode is ever turned off (or a future
    model ignores the transport addendum and follows Section 104 to the
    letter). Returns None when the text isn't in that shape, so the caller can
    fall through to ordinary JSON parsing.
    """

    blocks = re.findall(
        r"(CANONICAL_JSON|DMN_JSON)\s*```(?:json)?\s*\n(.*?)\n?```",
        text,
        re.DOTALL,
    )
    if not blocks:
        return None
    merged: dict[str, Any] = {}
    for label, body in blocks:
        try:
            merged[label] = json.loads(body)
        except json.JSONDecodeError:
            return None
    return merged or None


def parse_formulation(raw: str) -> PolicyFormulation:
    """Turn one agent reply into a validated `PolicyFormulation`.

    Accepts, in order of preference:

    1. the transport envelope `{"CANONICAL_JSON": ..., "DMN_JSON": ...}`;
    2. a flat object already carrying `canonical_policies` / `dmn_projection`
       (some models "helpfully" merge the two documents);
    3. the spec's literal Section 104 two-fenced-block form.

    Tolerating all three is not sloppiness — it is the difference between a
    recoverable formatting drift and a hard failure that loses an entire
    document's worth of extraction work.
    """

    text = _strip_code_fence(raw)
    if not text:
        raise PolicyFormulationError("formulator agent returned an empty response")

    payload: Any
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        payload = _extract_labelled_blocks(raw)
        if payload is None:
            raise PolicyFormulationError(
                f"formulator agent returned unparseable output: {exc}"
            ) from exc

    if not isinstance(payload, dict):
        raise PolicyFormulationError(
            f"formulator agent returned a {type(payload).__name__}, expected a JSON object"
        )

    canonical = payload.get("CANONICAL_JSON")
    dmn = payload.get("DMN_JSON")
    if canonical is None and dmn is None:
        # Flat form: the two documents were merged into one object.
        canonical, dmn = payload, payload

    merged = {
        "canonical_policies": (canonical or {}).get("canonical_policies", []),
        "dmn_projection": (dmn or {}).get("dmn_projection", {}),
    }

    try:
        return PolicyFormulation.model_validate(merged)
    except ValidationError as exc:
        return _salvage_valid_policies(merged, exc)


def _salvage_valid_policies(
    merged: dict[str, Any], batch_error: ValidationError
) -> PolicyFormulation:
    """Keep the canonical policies that validate when a sibling one does not.

    Whole-batch validation makes the failure boundary the batch while the unit
    of value is the single policy. One policy arriving in a shape the contract
    does not anticipate then discards every correctly-formed policy beside it —
    observed in production as a 30-policy window lost because three entries
    wrapped `ambiguity` in an object. Nothing about a shape variance in one
    policy is evidence that the others are wrong.

    This is also why the field coercions in `contracts.formulation` each justify
    themselves with "discarding the whole formulation would lose real extraction
    work": they were carrying the weight of the wrong failure boundary. With
    recovery here, an unanticipated shape costs one policy instead of thirty,
    and each coercion only has to protect its own entry.

    Raises if nothing survives, because a batch where every policy is malformed
    is a genuine agent failure and must not be reported as an empty success.
    """

    raw_policies = merged.get("canonical_policies")
    if not isinstance(raw_policies, list) or not raw_policies:
        raise PolicyFormulationError(
            f"formulator agent output failed contract validation: {batch_error}"
        )

    kept: list[CanonicalPolicy] = []
    dropped: list[tuple[int, str]] = []
    # Old position -> new position. `DmnDecision.source_rule_indexes` are
    # positional into `canonical_policies` (Section 86), so compacting the list
    # without remapping would silently re-point every later decision at the
    # wrong rule — a quieter and worse failure than the one being fixed.
    index_map: dict[int, int] = {}

    for position, entry in enumerate(raw_policies):
        try:
            kept.append(CanonicalPolicy.model_validate(entry))
        except ValidationError as item_error:
            dropped.append((position, _first_error_summary(item_error)))
        else:
            index_map[position] = len(kept) - 1

    if not kept:
        raise PolicyFormulationError(
            f"formulator agent output failed contract validation: {batch_error}"
        )

    projection = _remap_projection(merged.get("dmn_projection"), index_map)

    logger.warning(
        "formulator: kept %d of %d canonical policies; dropped %s",
        len(kept),
        len(raw_policies),
        ", ".join(f"#{position} ({reason})" for position, reason in dropped),
    )

    return PolicyFormulation(canonical_policies=kept, dmn_projection=projection)


def _first_error_summary(error: ValidationError) -> str:
    """One short reason, so a drop is diagnosable without dumping a full trace."""

    errors = error.errors()
    if not errors:
        return "invalid"
    first = errors[0]
    location = ".".join(str(part) for part in first.get("loc", ())) or "?"
    return f"{location}: {first.get('msg', 'invalid')}"


def _remap_projection(raw: Any, index_map: dict[int, int]) -> DmnProjection:
    """Re-point surviving decisions at the compacted canonical list.

    A decision whose source rules were all dropped is dropped too: Section 86
    makes `source_rule_indexes` the link that keeps a projection traceable back
    to the canonical record, and a decision that can no longer name where it
    came from is not something a reviewer should be shown as evidence.

    A projection that fails validation for any *other* reason still raises. Its
    validity has nothing to do with whether a sibling policy was malformed, so
    recovering from a bad policy must not quietly widen what counts as an
    acceptable projection — an unknown `dmn_mapping_status` means something
    broke (Section 45) and has to stay loud whichever path reaches it.
    """

    if not isinstance(raw, dict):
        return DmnProjection()

    remapped_decisions = []
    for decision in raw.get("decisions") or []:
        if not isinstance(decision, dict):
            continue
        source_indexes = [
            index_map[old]
            for old in decision.get("source_rule_indexes") or []
            if isinstance(old, int) and old in index_map
        ]
        if not source_indexes:
            continue
        remapped_decisions.append({**decision, "source_rule_indexes": source_indexes})

    try:
        return DmnProjection.model_validate({**raw, "decisions": remapped_decisions})
    except ValidationError as exc:
        raise PolicyFormulationError(
            f"formulator agent output failed contract validation: {exc}"
        ) from exc


def check_trusted_config(config: dict[str, Any]) -> list[str]:
    """Return human-readable warnings for a config that cannot reach the agent.

    A trusted config that is wrong-shaped fails *silently*: the agent still runs,
    still returns well-formed output, and still reports `FACT_MODEL_REQUIRED` —
    identical to having supplied nothing. The caller's only signal is the absence
    of an improvement they were expecting, which is not a signal at all.

    Two shapes were observed producing exactly that. A key outside Section 83's
    list (`temporal_model` was tried, reasonably enough, and does not exist) is
    passed through to the model as noise and, worse, made the corresponding
    requirement code *more* frequent. And an entry keyed by the FEEL path rather
    than by the source term — `{"worker.ageYears": {...}}` instead of
    `{"age of the worker": {"feel_expression": "worker.ageYears", ...}}` — gives
    the agent a destination with no way to recognise the wording that maps onto
    it, which is the half that matters.

    Returned rather than only logged so the API can hand these back to whoever
    is authoring the config, at the moment they save it. A log line is the right
    channel for a batch job and the wrong one for a person editing a fact model:
    they will never see it, and the failure it describes is invisible by
    construction. Both callers share this one implementation so the rules cannot
    drift apart.
    """

    warnings: list[str] = []

    unknown = sorted(set(config) - PolicyFormulatorAgent._SECTION_83_KEYS)
    if unknown:
        warnings.append(
            f"Ignoring unknown key(s) {', '.join(unknown)}; Section 83 defines only "
            f"{', '.join(sorted(PolicyFormulatorAgent._SECTION_83_KEYS))}. Unknown keys "
            "reach the agent as noise and do not enrich anything."
        )

    for model_key, mapping_key in PolicyFormulatorAgent._EXPECTED_MAPPING_KEY.items():
        entries = config.get(model_key)
        if not isinstance(entries, dict):
            continue
        malformed = sorted(
            term
            for term, spec in entries.items()
            if not isinstance(spec, dict) or mapping_key not in spec
        )
        if malformed:
            warnings.append(
                f"{model_key}: entr(ies) {', '.join(malformed)} have no '{mapping_key}'. "
                "Section 84 keys each entry by the SOURCE TERM as it appears in the "
                "policy text, with the FEEL target inside — e.g. {'age of the worker': "
                f"{{'{mapping_key}': 'worker.ageYears', 'type': 'number'}}}}. Keying by "
                "the FEEL path instead leaves the agent unable to map wording onto it, "
                "and it will still report the enrichment as missing."
            )

    return warnings


def _warn_on_unusable_trusted_config(config: dict[str, Any]) -> None:
    """Log the warnings from `check_trusted_config`.

    Warnings rather than errors: Section 83 is the spec's list, not the model's,
    and a future spec revision adding a key should not stop an extraction. Being
    wrong here costs a log line; refusing to run costs a job.
    """

    for warning in check_trusted_config(config):
        logger.warning("trusted_config: %s", warning)


class PolicyFormulatorAgent:
    """Formulates policy text into canonical + DMN JSON.
    Stateless apart from its client and trusted configuration, so a single
    instance can be reused across a whole extraction run.

    `trusted_config` is the specification's Section 83 configuration
    (`fact_model`, `output_model`, `value_normalization`, …). It is the *only*
    sanctioned source of technical detail that is not present in the source
    text: without a fact model the agent must not invent FEEL fact paths, and
    must instead return `enrichment_required` with `FACT_MODEL_REQUIRED`. An
    empty config is therefore a valid and honest operating mode — it yields
    faithful canonical records and candidly non-executable DMN projections,
    rather than confident-looking fabrications.
    """

    #: Section 83's key set, verbatim. A key outside it is not "extra context"
    #: the agent can use — it is silently ignored, so the caller believes they
    #: supplied enrichment that never reached the model.
    _SECTION_83_KEYS = frozenset(
        {
            "fact_model",
            "output_model",
            "type_model",
            "value_normalization",
            "term_dictionary",
            "decision_precedence",
            "hit_policy",
            "definitions",
            "numeric_normalization",
            "currency",
            "unit_conversions",
        }
    )

    #: The key each mapping model uses to name its FEEL target (Section 84).
    _EXPECTED_MAPPING_KEY = {"fact_model": "feel_expression", "output_model": "feel_name"}

    def __init__(
        self,
        client: AzureOpenAIClient,
        settings: Settings,
        *,
        trusted_config: dict[str, Any] | None = None,
    ) -> None:
        self._client = client
        self._settings = settings
        self._trusted_config = trusted_config or {}
        _warn_on_unusable_trusted_config(self._trusted_config)

    def _build_user_message(self, source_text: str) -> str:
        config_block = (
            json.dumps(self._trusted_config, indent=2)
            if self._trusted_config
            else "{}\n\nNo trusted configuration is supplied. Per Sections 42-44 and 83 you may not\n"
            "invent fact paths, output variable names, data types, value normalizations,\n"
            "currencies, units, precedence or hit-policy semantics. Where execution would\n"
            "require any of these, return the appropriate non-executable mapping status\n"
            "with the corresponding requirement codes."
        )
        return (
            "TRUSTED APPLICATION CONFIGURATION:\n"
            f"{config_block}\n\n"
            "SOURCE POLICY TEXT:\n"
            f"{source_text}"
        )

    async def formulate(self, source_text: str) -> PolicyFormulation:
        """Formulate one block of policy text. Raises `PolicyFormulationError`.

        The token budget and timeout are sized for a reasoning deployment:
        `gpt-5.6-sol` spends part of the budget on a hidden reasoning pass
        before emitting any visible content, and this prompt is ~3000 lines of
        specification, so an undersized budget returns empty content rather
        than a short answer (see `AzureOpenAIClient.chat`).
        """

        if not source_text.strip():
            raise PolicyFormulationError("cannot formulate empty source text")

        raw = await self._client.chat(
            [
                {"role": "system", "content": load_formulator_prompt()},
                {"role": "user", "content": self._build_user_message(source_text)},
            ],
            deployment=self._settings.azure_openai_deployment,
            json_mode=True,
            # Sized against observed density: a 1,525-char batch of a definitions
            # section produced 13 canonical policies + 13 DMN decisions. Dense
            # legal text scales roughly linearly, so a 4,000-char batch can emit
            # ~35 records across both blocks. 32k leaves room for that plus the
            # hidden reasoning pass; the client now raises on truncated JSON
            # rather than letting a half-object reach the parser.
            max_tokens=32000,
            timeout=420.0,
            reasoning_effort=FORMULATOR_REASONING_EFFORT,
        )
        formulation = parse_formulation(raw)
        logger.info(
            "formulated %d canonical policies / %d DMN decisions from %d chars",
            len(formulation.canonical_policies),
            len(formulation.dmn_projection.decisions),
            len(source_text),
        )
        return formulation
