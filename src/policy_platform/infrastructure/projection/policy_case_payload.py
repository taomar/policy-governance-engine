"""Flavour 2 — the lean, model-facing projection of one policy.

The JSON tab renders two flavours of the same policy:

* **Flavour 1** is the full canonical record — every field, every notation, the
  whole provenance apparatus. It is the record of what was extracted and it is
  what a reviewer audits. `policyCards.ts` / `policyExport.ts` own it and it is
  unchanged.
* **Flavour 2** (this module) is a lean projection chosen for a model to read.
  It is the input the case-testing mechanism sends to an LLM. It keeps the
  operative meaning of every rule and removes only *structural duplication* —
  the same words repeated in another notation, or once per rule when they could
  be stored once and referenced.

The objective is not to minify. It is to separate four kinds of thing that the
full record interleaves and repeats: the values shared by every rule, the
source evidence, the repeated facts and terms, and the rules themselves. Each
is stored once; the rules reference the rest by stable id.

Why one module, server-side
----------------------------
The case-testing mechanism builds this payload server-side and the JSON tab
shows the same thing client-side. If the projection were written twice — once
in Python and once in TypeScript — the two would drift, and a model would then
be tested against a payload no reviewer ever saw. So the projection lives here,
once, and the tab fetches it from the API rather than rebuilding it.

The representation, chosen on measured evidence (677 live rules)
---------------------------------------------------------------
Every rule carries several restatements of itself: the canonical
subject/predicate/object formulation, a DMN block, and an XACML view. Only one
can be the carrier, and the measurement is decisive:

* the **canonical formulation** exists on **677/677 = 100 %** of live rules, on
  both the AI-ready and the deterministic route, and it retains the document's
  verbatim source phrase — the thing grounding rests on;
* the **DMN block** never contains a decision table: across the whole corpus
  **2063 / 2063** `dmn_decisions` entries carry `decision_table = null`. It is a
  semantic summary mislabelled DMN, so it is not repeated inline — it collapses
  to a `dmn_status`;
* an **executable XACML projection** compiles only for the deterministic
  minority (**7/677 ≈ 1 %**) and is derived on read, never stored, so it is not
  carried here at all (it belongs to the execution slice).

The canonical formulation is the carrier, and it is also the shape the app's own
display contract already uses — attribute name, the document's words verbatim,
and the identifier a case supplies a value for — so the model reads the policy
the same way the reviewer sees it.

The four sections of ``grounding_projection_v1``
------------------------------------------------
* **envelope** — the identity and the values every rule shares (schema, policy
  and policy-version ids, provision id/key, document-version id, the common
  authority and effective dates, and the document's heading path, verbatim). A
  rule carries one of these only when its value *differs* from the envelope.
* **spans** — each source passage stored once, keyed by an immutable content id,
  with the exact original text (uncut), the clause and search-document ids, the
  source hash, page, section and offsets. Rules point at spans by id instead of
  copying the sentence into `description`, `canonical.source_text`, a quotation
  and an evidence block four times over.
* **facts** — each repeated fact/term stored once, keyed by ``(name, phrase)``
  so a normalised id that two documents' words share never collapses two
  verbatim phrases into one. Rules reference facts by id; attributes that *are*
  a fact reference it too, which is how the phrase the user saw twice — once in
  `attributes[].text`, once in `facts[].source_phrase` — is now stored once and
  pointed at twice.
* **rules** — the compact canonical rules: stable id and revision, type and
  modality, the effect, the attributes (referencing facts), the fact usages with
  their roles, the required facts, the exceptions and advice verbatim, the
  grounding span refs, and the DMN status. Nothing that only restates the rule
  in another notation, and nothing that only records how the extraction ran.

Re-derived, never read back
---------------------------
`attributes` and `facts` are recomputed here from `formulation.canonical` with
the very functions the API's read path uses (`published_facts`,
`attributes_for`), never read from the stored copy in `payload_json`, which can
be stale. This mirrors `candidate_rules._with_decision_readiness` exactly, so
the lean payload can never disagree with the served record about the same rule.

What identity is kept, and the one trade-off
--------------------------------------------
The identity set is explicit: **rule id, policy id, and the search / AI document
id are enough.** Run history is dropped. The one clause-level id kept is the
span's `search_document_id` (`{document_version_id}_{clause_id}`) — the Azure AI
Search key the AI route already grounds against. What is *dropped* with it is the
sub-clause character span (`start_offset`/`end_offset` are preserved on the span
when present, but no finer offset is invented): an answer can be traced to a
**clause** (and its search document) but not to a character range the document
never recorded. The verbatim span text is preserved uncut, so the phrase remains
findable by string search.

Absent, empty, and default are not collapsed together (constraint 5)
--------------------------------------------------------------------
A scalar that carries a distinction keeps its explicit ``None`` (a fact's
`data_type` of ``None`` says the phrase never named a kind). A list whose
emptiness is *meaningful* is emitted even when empty — `required_facts` on an
AI-ready rule is ``[]`` because the rule's test is words, not named quantities,
and omitting it would let a reader infer the field was never computed. A list or
scalar whose empty value is merely the schema's default and carries no
distinction (an empty `scope`, an absent exception) is omitted, because there its
presence would only be noise.

Contract with the case-intent agent
------------------------------------
`case_payload_for_provision(session, provision_id)` is the entry point the
case-testing mechanism calls directly (no HTTP hop). It is the spec's
``for_grounding`` view. The whole persistence stack is async, so it is an
``async def`` taking an ``AsyncSession`` and returning ``dict | None`` (``None``
for an unknown provision, so the caller can 404); the name, path and parameters
are exactly as agreed. `build_case_payload` is a pure, session-free core so the
shape can be tested without a database.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.contracts.policy import (
    CANONICAL_SCHEMA_VERSION,
    CanonicalRule,
    PolicyAttribute,
    PolicyFact,
    attributes_for,
    evaluation_mode_for,
)
from policy_platform.domain.models import CandidateRule, DocumentProvision
from policy_platform.infrastructure.extraction.policy_facts import published_facts
from policy_platform.infrastructure.search.indexing import clause_search_document_id

#: Names and versions the projected shape so a consumer can tell it apart from
#: the full record and pin the structure it parsed.
PROJECTION = "grounding_projection_v1"
REPRESENTATION = "canonical"


def _plain(value: object) -> object:
    """A JSON-native scalar for an enum member, unchanged for anything else."""

    return value.value if isinstance(value, Enum) else value


def _digest(*parts: str) -> str:
    """A short, deterministic content id — stable across runs, never positional.

    Used to key spans by their content so a reference is a stable id and never a
    fragile array index (constraint 8), and so the same passage seen twice keys
    to one entry.
    """

    joined = "\u0000".join(parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


# --- the derived core of one rule -------------------------------------------


class _Derived:
    """One rule's re-derived facts, attributes and source text, computed once.

    `attributes` and `facts` come from `formulation.canonical` through the same
    read-path functions the served record uses, so the lean payload can never
    disagree with it. A hand-authored rule has no formulation to derive from, so
    its own stored `attributes`/`fact_model` stand and its source text is empty.
    """

    __slots__ = ("rule", "canonical", "facts", "attributes", "source_text")

    def __init__(self, rule: CanonicalRule) -> None:
        self.rule = rule
        canonical = None
        if rule.formulation is not None and rule.formulation.canonical is not None:
            canonical = rule.formulation.canonical
        self.canonical = canonical
        if canonical is not None:
            self.facts = published_facts(canonical.rule, rule.required_facts)
            self.attributes = attributes_for(canonical.rule, self.facts)
            self.source_text = canonical.source_text
        else:
            self.facts = list(rule.fact_model)
            self.attributes = rule.attributes
            self.source_text = ""


# --- the fact / term dictionary ---------------------------------------------


def _assign_fact_ids(derived: list[_Derived]) -> dict[tuple[str, str], str]:
    """A stable id per ``(name, source_phrase)`` across the whole policy.

    Keyed by the pair, not the name alone, because a normalised `name` can be
    shared by two different verbatim phrases (``staff`` and ``employees`` both
    normalise to one id). Merging them would drop one document's actual words
    (constraint 4). The id stays the readable `name` when that name owns a single
    phrase, and is disambiguated by a content suffix only when it does not — so
    the common case reads naturally and the rare collision stays lossless.
    """

    phrases_by_name: dict[str, set[str]] = defaultdict(set)
    for item in derived:
        for fact in item.facts:
            phrases_by_name[fact.name].add(fact.source_phrase)

    ids: dict[tuple[str, str], str] = {}
    for item in derived:
        for fact in item.facts:
            key = (fact.name, fact.source_phrase)
            if key in ids:
                continue
            if len(phrases_by_name[fact.name]) == 1:
                ids[key] = fact.name
            else:
                ids[key] = f"{fact.name}#{_digest(fact.source_phrase)[:6]}"
    return ids


def _register_fact(facts: dict, fact_id: str, fact: PolicyFact) -> None:
    """Record a fact once in the shared dictionary.

    `source_phrase` is verbatim and uncut (constraint 4). `data_type` keeps its
    explicit ``None`` (the phrase named no kind), a distinction an omitted key
    would erase (constraint 5). `roles` are a property of how a rule *uses* the
    fact, so they live on the rule's reference, not here.
    """

    if fact_id in facts:
        return
    facts[fact_id] = {
        "name": fact.name,
        "source_phrase": fact.source_phrase,
        "data_type": fact.data_type,
    }


# --- the source-span dictionary ---------------------------------------------


def _span_ref(spans: dict, document_version_id: str, clause_id, text: str | None) -> str:
    """Ensure the passage is in the span dictionary and return its id.

    Keyed by document, clause and the verbatim text together, so two rules that
    quote the same sentence of the same clause share one span (the text is stored
    once) while the same words genuinely grounded in two clauses stay two spans.
    `text` is stored uncut (constraint 4). A supporting clause reference that
    carries no quoted text (``text is None``) is recorded with the clause
    identity and no `text` key, so a reader can tell "quoted here" from "also
    supported here".
    """

    clause = clause_id or ""
    span_id = _digest(document_version_id or "", clause, "" if text is None else f"\u0001{text}")
    if span_id not in spans:
        entry: dict = {"document_version_id": document_version_id}
        if text is not None:
            entry["text"] = text
        if clause_id:
            entry["clause_id"] = clause_id
            entry["search_document_id"] = clause_search_document_id(document_version_id, clause_id)
        spans[span_id] = entry
    return span_id


def _evidence_refs(spans: dict, derived: _Derived) -> list[str]:
    """The span ids a rule is grounded in, its quoted sentence stored once.

    The rule's own sentence (`source_text`) is attached to its first evidence
    reference — the clause it was quoted from. Any further evidence references
    are supporting clauses, recorded by identity without re-attaching the text,
    so no verbatim string is copied more than once.
    """

    refs: list[str] = []
    rule = derived.rule
    for index, ref in enumerate(rule.evidence):
        text = derived.source_text if index == 0 else None
        refs.append(_span_ref(spans, ref.document_version_id, ref.clause_id, text))
    _enrich_spans(spans, refs, rule)
    return refs


def _enrich_spans(spans: dict, refs: list[str], rule: CanonicalRule) -> None:
    """Fold each evidence reference's hash, page, section and offsets onto its span.

    These are a property of the clause, not the rule, so they are preserved on
    the span (constraints 3 and 4) rather than repeated on every rule that cites
    it. Explicit ``None`` offsets are kept — the document recorded no character
    range, which is not the same as a range of zero.
    """

    for ref, span_id in zip(rule.evidence, refs):
        entry = spans.get(span_id)
        if entry is None or "source_hash" in entry:
            continue
        entry["source_hash"] = ref.source_hash
        entry["page"] = ref.page
        entry["section"] = ref.section
        entry["start_offset"] = ref.start_offset
        entry["end_offset"] = ref.end_offset


# --- the compact rule -------------------------------------------------------


def _attribute_payload(attribute: PolicyAttribute, fact_ids: dict[tuple[str, str], str]) -> dict:
    """One attribute, its verbatim phrase referenced through the fact dictionary.

    When the attribute names a fact, the phrase is already in the fact
    dictionary, so the attribute points at it by id rather than copying the
    words — this is where `attributes[].text` and `facts[].source_phrase`, the
    same phrase the user saw twice, become one stored string pointed at twice. A
    predicate or literal that names no fact keeps its `text` verbatim and uncut
    (constraint 4), because there is nothing in the dictionary to point at.
    `data_type` keeps its explicit ``None`` (constraint 5).
    """

    payload: dict = {"attribute": attribute.attribute}
    key = (attribute.fact, attribute.text)
    if attribute.fact is not None and key in fact_ids:
        payload["fact_ref"] = fact_ids[key]
    else:
        payload["text"] = attribute.text
    payload["data_type"] = attribute.data_type
    return payload


def _required_facts(rule: CanonicalRule) -> list[dict]:
    """The rule's required facts, merged with any decision-readiness attributes.

    Emitted even when empty: ``[]`` on an AI-ready rule means the rule's test is
    words, not named quantities, and dropping it would erase that from a reader
    (constraint 5). `decision_readiness.required_attributes` — present only on
    the deterministic route — is merged in as one typed structure so a consumer
    reads a single required-fact list, never two.
    """

    seen: set[str] = set()
    out: list[dict] = []
    for fact in rule.required_facts:
        seen.add(fact.name)
        entry = {"name": fact.name, "data_type": fact.data_type, "required": fact.required}
        if fact.unit:
            entry["unit"] = fact.unit
        out.append(entry)
    readiness = rule.decision_readiness
    if readiness is not None:
        for attribute in readiness.required_attributes:
            if attribute.phrase in seen:
                continue
            seen.add(attribute.phrase)
            out.append({"phrase": attribute.phrase, "role": attribute.role, "required": True})
    return out


def _dmn_status(rule: CanonicalRule) -> object:
    """The DMN mapping status, collapsed from the block that never held a table.

    The block's `decision_table` is ``null`` on every rule in the corpus and its
    `semantic_projection` only restates the canonical, so neither is carried.
    What remains is the status — whether the rule *could* map — and that is a
    real, per-rule signal. One status is a string; the rare rule with two DMN
    decisions yields the sorted set.
    """

    formulation = rule.formulation
    if formulation is None or not formulation.dmn_decisions:
        return "not_applicable"
    statuses = sorted({_plain(d.dmn_mapping_status) for d in formulation.dmn_decisions})
    return statuses[0] if len(statuses) == 1 else statuses


def _dmn_missing(rule: CanonicalRule) -> list[str]:
    """Structured reasons a rule could not map to DMN, if any were recorded."""

    formulation = rule.formulation
    if formulation is None:
        return []
    reasons: list[str] = []
    for decision in formulation.dmn_decisions:
        for code in getattr(decision, "requirements", []) or []:
            value = _plain(code)
            if value not in reasons:
                reasons.append(value)
    return reasons


def _exceptions(rule: CanonicalRule) -> list[dict]:
    """Operative carve-outs, kept verbatim with their explicit limits."""

    return [
        {
            "exception_id": exc.exception_id,
            "description": exc.description,
            "limit_value": exc.limit_value,
            "limit_unit": exc.limit_unit,
        }
        for exc in rule.exceptions
    ]


def _advice(rule: CanonicalRule) -> list[dict]:
    """Non-blocking guidance, kept verbatim when present."""

    return [{"advice_id": item.advice_id, "text": item.text} for item in rule.advice]


def _scope_payload(rule: CanonicalRule) -> dict | None:
    """The rule's scope, only when it actually narrows anything.

    An empty scope is the schema default (the rule applies generally) and carries
    no distinction, so it is omitted rather than emitted as four empty lists.
    """

    scope = rule.scope
    narrowing = {
        "jurisdictions": list(scope.jurisdictions),
        "organizational_units": list(scope.organizational_units),
        "personas": list(scope.personas),
        "processes": list(scope.processes),
    }
    if not any(narrowing.values()):
        return None
    return {key: value for key, value in narrowing.items() if value}


def project_rule(
    derived: _Derived,
    spans: dict,
    facts: dict,
    fact_ids: dict[tuple[str, str], str],
    envelope: dict,
) -> dict:
    """Project one rule to its compact, reference-carrying shape."""

    rule = derived.rule

    for fact in derived.facts:
        _register_fact(facts, fact_ids[(fact.name, fact.source_phrase)], fact)

    payload: dict = {
        # Identity only — never a name (constraint 8). The UI resolves the
        # display name from a separate table at render time.
        "rule_id": rule.rule_id,
        "rule_revision": rule.rule_revision,
        "rule_type": _plain(rule.rule_type),
        # Derived from the condition, so it can never disagree with the tree.
        "evaluation_mode": _plain(evaluation_mode_for(rule)),
        "ambiguity_status": _plain(rule.ambiguity_status),
        "effect": {"type": _plain(rule.effect.type), "action": rule.effect.action},
        "attributes": {
            "applies": [_attribute_payload(a, fact_ids) for a in derived.attributes.applies],
            "outcome": [_attribute_payload(a, fact_ids) for a in derived.attributes.outcome],
        },
        "facts": [
            {"ref": fact_ids[(f.name, f.source_phrase)], "roles": list(f.roles)}
            for f in derived.facts
        ],
        "required_facts": _required_facts(rule),
        "evidence_refs": _evidence_refs(spans, derived),
        "dmn_status": _dmn_status(rule),
    }

    if derived.canonical is not None and derived.canonical.rule is not None:
        modality = derived.canonical.rule.modality
        if modality:
            payload["modality"] = modality

    missing = _dmn_missing(rule)
    if missing:
        payload["dmn_missing"] = missing

    # Structural facts about the rule — emitted only when they hold, never as a
    # constant default.
    if rule.is_explicit_override:
        payload["is_explicit_override"] = True
    if rule.supersedes_rule_ids:
        payload["supersedes_rule_ids"] = list(rule.supersedes_rule_ids)
    if rule.related_rule_ids:
        payload["related_rule_ids"] = list(rule.related_rule_ids)
    if rule.tags:
        payload["tags"] = list(rule.tags)

    scope = _scope_payload(rule)
    if scope is not None:
        payload["scope"] = scope

    # An envelope value only reappears on a rule that departs from it.
    authority = {
        "level": rule.authority.level,
        "owner": rule.authority.owner,
        "rank": rule.authority.rank,
    }
    if authority != envelope.get("authority"):
        payload["authority"] = authority
    if str(rule.effective_from) != envelope.get("effective_from"):
        payload["effective_from"] = str(rule.effective_from)
    effective_to = None if rule.effective_to is None else str(rule.effective_to)
    if "effective_to" in envelope and effective_to != envelope.get("effective_to"):
        payload["effective_to"] = effective_to

    exceptions = _exceptions(rule)
    if exceptions:
        payload["exceptions"] = exceptions
    advice = _advice(rule)
    if advice:
        payload["advice"] = advice

    return payload


# --- the envelope and the whole payload -------------------------------------


def _common(values: list) -> object:
    """The one value shared by every rule, or ``None`` when they disagree."""

    if not values:
        return None
    first = values[0]
    return first if all(value == first for value in values) else None


def _build_envelope(
    *,
    policy_set_id: str,
    provision_id: str,
    provision_key: str,
    heading_path: list[str],
    rules: list[CanonicalRule],
) -> dict:
    """The identity and the values every rule shares, stored once."""

    envelope: dict = {
        "schema_version": rules[0].schema_version if rules else CANONICAL_SCHEMA_VERSION,
        "policy_set_id": policy_set_id,
        "provision_id": provision_id,
        "provision_key": provision_key,
        # Copied verbatim from the document; the only prose the envelope holds.
        "heading_path": list(heading_path or []),
    }

    policy_version_id = _common([r.policy_version_id for r in rules])
    if policy_version_id is not None:
        envelope["policy_version_id"] = policy_version_id

    document_version_id = _common(
        [r.evidence[0].document_version_id for r in rules if r.evidence]
    )
    if document_version_id is not None:
        envelope["document_version_id"] = document_version_id

    authority = _common(
        [
            {"level": r.authority.level, "owner": r.authority.owner, "rank": r.authority.rank}
            for r in rules
        ]
    )
    if authority is not None:
        envelope["authority"] = authority

    effective_from = _common([str(r.effective_from) for r in rules])
    if effective_from is not None:
        envelope["effective_from"] = effective_from

    effective_to = _common([None if r.effective_to is None else str(r.effective_to) for r in rules])
    if rules and all(r.effective_to == rules[0].effective_to for r in rules):
        envelope["effective_to"] = effective_to

    return envelope


def build_case_payload(
    *,
    policy_set_id: str,
    provision_id: str,
    provision_key: str,
    heading_path: list[str],
    rules: list[CanonicalRule],
) -> dict:
    """Assemble ``grounding_projection_v1`` for one policy.

    A *policy* with its rules nested (constraint 2), not a bag of rules. Pure and
    session-free so the projected shape can be tested without a database.
    """

    derived = [_Derived(rule) for rule in rules]
    fact_ids = _assign_fact_ids(derived)
    envelope = _build_envelope(
        policy_set_id=policy_set_id,
        provision_id=provision_id,
        provision_key=provision_key,
        heading_path=heading_path,
        rules=rules,
    )

    spans: dict = {}
    facts: dict = {}
    projected = [project_rule(item, spans, facts, fact_ids, envelope) for item in derived]

    return {
        "projection": PROJECTION,
        "representation": REPRESENTATION,
        "envelope": envelope,
        "spans": spans,
        "facts": facts,
        "rules": projected,
    }


def to_pretty(payload: dict) -> str:
    """The diagnostic serialization — indented, for a human reading the tab.

    Non-ASCII is never escaped, so Arabic source text stays legible (constraint
    9). This form is for inspection; it is never the source of truth.
    """

    return json.dumps(payload, ensure_ascii=False, indent=2)


def to_compact(payload: dict) -> str:
    """The transport serialization — no indentation, for a model or the API.

    Generated deterministically from the same governed dict as `to_pretty`, so
    the compact bytes can never drift from what a reviewer inspects. Non-ASCII is
    preserved, not escaped (constraint 9).
    """

    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


async def case_payload_for_provision(session: AsyncSession, provision_id) -> dict | None:
    """The grounding payload for one provision's current (non-superseded) rules.

    Returns ``None`` when the provision id is unknown, so a caller can answer a
    404 without this module importing anything web-facing. Rules are loaded in
    the same order the review surface uses (`created_at`), filtered to the
    current set (`superseded_at IS NULL`), exactly as every other read means.
    """

    pid = provision_id if isinstance(provision_id, uuid.UUID) else uuid.UUID(str(provision_id))

    provision = await session.get(DocumentProvision, pid)
    if provision is None:
        return None

    stmt = (
        select(CandidateRule)
        .where(CandidateRule.provision_id == pid)
        .where(CandidateRule.superseded_at.is_(None))
        .order_by(CandidateRule.created_at)
    )
    result = await session.execute(stmt)
    candidates = list(result.scalars().all())

    rules = [CanonicalRule.model_validate(candidate.payload_json) for candidate in candidates]

    return build_case_payload(
        policy_set_id=str(provision.policy_set_id),
        provision_id=str(provision.id),
        provision_key=provision.provision_key,
        heading_path=provision.heading_path_json,
        rules=rules,
    )
