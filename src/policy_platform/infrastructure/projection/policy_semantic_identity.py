"""When two published policies are the same policy, said twice.

WHY THIS EXISTS

Receipt `76a5e936-7ea4-4cc3-828a-0fb099c2ee5b`, question "What do the policies say
about laptop replacement eligibility, and is my 26-month-old laptop eligible
now?". Retrieval's policy budget is five, and the five it retained were: two
copies of `2.1 Standard entitlement`, two copies of `4.2 Accidental damage`, and
`4.4 Lost/stolen`. `3.1 Standard refresh interval` — the provision that decides a
26-month-old laptop — ranked sixth and was discarded `outside_budget`. The
information track answered; the verdict came back `not_settled_by_rules`, because
the rule that settles it was never read.

Nothing ranked wrongly. The corpus held the same policy twice, under two
provisions carrying different ids and different keys because they were extracted
from two document versions, and retrieval spent two of five answer slots saying
the same thing twice. The budget is a budget of *distinct policies to read*, and
a copy is not a second policy.

WHAT IS COLLAPSED, AND WHAT IS NEVER COLLAPSED

Only an **exact** match of everything the policy governs. The fingerprint is
taken over the lean published record with identity and provenance removed and
nothing else removed:

  * removed — record ids, rule ids, policy/provision/document-version ids, the
    span dictionary's content-addressed keys and the evidence refs that name
    them, the clause and search-document locators, the source hash, the page,
    section and character offsets, the order the rules were emitted in, and the
    fields that only *re-derive* a parse of the rule's own sentence. Every one of
    these answers "which record is this, where did it come from, and how was it
    tokenised" — not "what does it require".
  * kept — the heading path verbatim, the effective window, the authority and
    priority the lean record omits, and for every rule: its type, evaluation
    mode, modality, ambiguity status, effect, stored required facts, scope,
    exceptions, advice, tags, override flag, DMN status, **the verbatim source
    sentence of every span it is grounded in**, and **its links to other rules,
    resolved to what they point at**.

Three of those removals were forced by the live corpus rather than chosen a
priori. All three look like content until you see why they are not, and each is
pinned by a test so that putting it back fails loudly:

  * **Rule order.** `2.1 Standard entitlement` is a table of role profiles. Two
    extractions of it enumerated the rows in different orders and were otherwise
    word for word identical. The rules a policy imposes are what it governs; the
    sequence an extractor emitted them in is provenance. So rules are compared as
    a canonical *multiset* — a policy stating a rule twice still differs from one
    stating it once.
  * **`related_rule_ids` / `supersedes_rule_ids`.** Of those same two
    extractions, one recorded six cross-references and the other recorded none.
    These are **not** dropped, and comparing how many there are would be worse
    than dropping them: two policies each superseding one rule, where the rules
    they displace govern differently, would fingerprint equal and a case could be
    answered from whichever copy ranked first. Instead each target is resolved to
    the target rule's **link-free identity** — what the link points at rather
    than what it is called — so a link survives a re-extraction that renumbers it
    while still discriminating on what it displaces. A target outside the policy
    cannot be resolved and keeps its raw id, which forgoes the collapse. That is
    the intended direction: a forgone collapse costs one budget slot, a wrong
    collapse costs a reviewer the policy that governed their case.
  * **The derived parse.** `attributes`, the rule's `facts` usages and the
    `decision_readiness` entries merged into `required_facts` are all recomputed
    from `formulation.canonical` on every projection. The last thing keeping the
    receipt's own pair apart was one of them labelling "appropriate to their role
    profile" a `constraint` where the other labelled "in scope" a `condition` —
    over a byte-identical sentence, effect, type and set of stored required
    facts. That is one sentence parsed twice, not two policies.

Dropping the parse is safe *because the sentence is not dropped with it*: every
span's text is compared verbatim, beside the effect, the rule type, the
evaluation mode, the modality, the stored required facts, the scope, the
exceptions and the effective window. A rule that governs differently says so in
one of those. A rule that governs identically cannot be told apart by how its
own sentence was tokenised.

The list of removals is a **denylist**, deliberately. An allowlist would silently
drop any governing field added to the projection later, and a governing field
missing from the fingerprint is how two materially different policies get
collapsed into one. Under a denylist a new field is governing until someone says
otherwise: the failure mode is a fingerprint that is too strict, which costs a
budget slot and never costs a reviewer an answer.

Measured against the live hw-policy corpus: 115 published policies fingerprint to
102 distinct ones, collapsing 13 copies. Every collapsing group shares one heading
*and* a byte-identical set of source sentences, and of the 57 pairs that share a
heading, none whose sentences differ is collapsed.

Two consequences worth stating, because they are the cases this must not get
wrong:

  * **Heading is never the test.** It is one component among all the others, so
    two provisions sharing `2.1 Standard entitlement` collapse only when every
    rule, sentence, date and carve-out also matches. The same corpus holds two
    `1.1 Who this applies to` provisions differing only in "twenty working days"
    versus "ten working days", and two `5.1 Warranty first` provisions with
    different effects — none of them collapses.
  * **Identical text under different authority is not a copy.** Effective dates
    and scope are governing, and authority and priority are carried in from
    beside the payload precisely because the lean record drops them. The same
    words issued for two jurisdictions, two organisational units, two effective
    windows or two owners fingerprint apart and are both read. Only provenance is
    erased, never the terms under which the words bind.

WHAT THIS MODULE DOES NOT DECIDE

It computes an equivalence key and nothing else. It never chooses a
representative, never discards, and never reports — the retrieval module owns
those, because the discard has to be disclosed in the same narrowing report as
every other discard. Keeping the fingerprint here, pure and session-free, is what
lets a test assert "these two payloads are the same policy" without a database,
a search index or a model.
"""
from __future__ import annotations

from typing import Any

from policy_platform.contracts.canonical import canonical_hash, canonical_json

#: Named on every fingerprint so a stored one can be told apart from a
#: fingerprint taken under a later definition of "the same policy".
POLICY_SEMANTIC_FINGERPRINT_VERSION = "policy_semantic_v1"

#: Keys that say *which record this is* and *where it came from*, at every depth.
#: Removing them is the whole of the normalisation; see the module docstring for
#: why this is a denylist and not an allowlist.
IDENTITY_KEYS = frozenset(
    {
        # record and rule identity
        "rule_id",
        "rule_revision",
        "exception_id",
        "advice_id",
        # policy, provision and version identity
        "policy_set_id",
        "provision_id",
        "provision_key",
        "policy_version_id",
        "document_version_id",
        # where in a document the words were found, and the tokens that name it
        "clause_id",
        "search_document_id",
        "source_hash",
        "page",
        "section",
        "start_offset",
        "end_offset",
    }
)

#: Fields that only *restate* the rule. `policy_case_payload` re-derives
#: `attributes` and the rule's `facts` usages from `formulation.canonical` on
#: every projection; they are a parse of the rule's own sentence into slots, not
#: something the document says. The live corpus shows why that matters: two
#: extractions of `2.1 Standard entitlement` carry a byte-identical source
#: sentence, a byte-identical effect and byte-identical required facts, and
#: differ only in whether the derivation labelled "appropriate to their role
#: profile" a `constraint` or "in scope" a `condition`. That is two parses of one
#: sentence, not two policies.
#:
#: Excluding them is safe precisely because the sentence itself is not excluded:
#: `evidence[].text` is compared verbatim, beside `effect`, `rule_type`,
#: `evaluation_mode`, `modality`, `required_facts`, `scope`, `exceptions`,
#: `advice` and the effective window. Any rule that governs differently says so
#: in one of those; a rule that governs identically cannot be told apart by how
#: its own sentence was tokenised.
DERIVED_RESTATEMENT_KEYS = frozenset({"attributes", "facts"})


#: Lists that name *other rules*. These are the one place where an id is not
#: merely provenance: "this rule supersedes that one" is a term of the rule, and
#: two rules each superseding one materially different target are two different
#: rules. Comparing the raw ids would refuse every cross-version duplicate;
#: comparing only how many there are — or dropping them — would let a policy
#: superseding X collapse into one superseding Y. Neither is acceptable, so the
#: targets are **resolved to the semantic identity of the rules they name** (see
#: :func:`_relationship_semantics`), which compares what a link points at rather
#: than what it is called.
RELATIONSHIP_KEYS: Final[tuple[str, ...]] = ("supersedes_rule_ids", "related_rule_ids")

#: The subset of :data:`RELATIONSHIP_KEYS` that changes what a rule *does*.
#: Superseding a rule displaces it — drop that and a policy replacing one rule
#: reads the same as one replacing another. Being marked "related" is the
#: drafter's reading aid: it says which rules are worth reading together, not
#: what any of them requires of anyone.
#:
#: The split exists for :func:`policy_normative_group_key`, which needs a
#: comparison that is coarser than identity but still normative. Equality — what
#: :func:`policy_semantic_fingerprint` computes, and the only thing that may ever
#: justify calling a policy a duplicate — uses all of them.
DECISIVE_RELATIONSHIP_KEYS: Final[tuple[str, ...]] = ("supersedes_rule_ids",)

#: Everything removed from a rule before its *base* identity is taken. The
#: relationship keys are removed here and added back resolved, which is also what
#: makes the resolution cycle-safe: a base identity never contains a link, so
#: resolving a link can never recurse into another resolution.
_RULE_DROPPED_KEYS = frozenset(RELATIONSHIP_KEYS) | DERIVED_RESTATEMENT_KEYS

#: Marks a link whose target is not among this policy's own rules, so it cannot
#: be resolved to anything. Its raw id is kept beside this marker rather than
#: discarded: an unresolvable link is exactly the case where nothing has been
#: proven, and the safe reading of "not proven identical" is "not identical".
UNRESOLVED_TARGET: Final[str] = "unresolved_rule_id"


def _strip_identity(value: Any) -> Any:
    """The same structure with every identity key removed, at every depth."""

    if isinstance(value, dict):
        return {
            key: _strip_identity(item)
            for key, item in value.items()
            if key not in IDENTITY_KEYS
        }
    if isinstance(value, list):
        return [_strip_identity(item) for item in value]
    return value


def _span_semantics(span: Any) -> Any:
    """One grounding passage as its words, with its locators removed.

    A span whose entry carries no `text` is a supporting clause reference: the
    rule is grounded there but no sentence was quoted from it. That distinction
    is kept (as an explicit ``None``) rather than dropped, because a rule
    supported by two clauses and one supported by one are not the same rule, and
    an omitted key would erase the difference.
    """

    if not isinstance(span, dict):
        return _strip_identity(span)
    return {"text": span.get("text"), **_strip_identity({k: v for k, v in span.items() if k != "text"})}


def _governing_required_facts(rule: dict) -> list:
    """The rule's *stored* required facts, without the derived readiness parse.

    `policy_case_payload._required_facts` merges two things into one list so a
    consumer reads one: the rule's own `required_facts` — a name, a data type and
    a unit, which the document's terms determine — and
    `decision_readiness.required_attributes`, which are re-derived from the same
    canonical parse `attributes` comes from and are emitted as a `phrase` and a
    `role`.

    Only the first is compared, and the shape tells them apart. The live corpus
    is again the reason: two extractions of one entitlement rule agree on the
    sentence, the effect and every stored required fact, and disagree only on
    whether "appropriate to their role profile" is a `constraint` or "in scope"
    is a `condition`. That is the parse differing, not the entitlement.
    """

    return [
        entry
        for entry in (rule.get("required_facts") or [])
        if not (isinstance(entry, dict) and "phrase" in entry and "name" not in entry)
    ]


def _per_rule_extras(governing_extras: dict | None, rules: list, index: int) -> dict | None:
    """The governing fields the lean record drops, for one rule.

    `governing_extras` carries `authority` and `priority` as lists aligned to the
    policy's rules (see
    :func:`~policy_platform.infrastructure.projection.published_case_payload.governing_extras_for_group`).
    They are governing — two otherwise identical rules issued under different
    authority are two rules — but the lean payload does not hold them, so they
    have to be supplied beside it.

    Alignment is checked rather than assumed: extras taken over a whole policy
    would silently mis-describe a *sliced* payload, and attributing one rule's
    authority to another is exactly the error this exists to prevent. When the
    lengths disagree, nothing is attributed and the comparison falls back to what
    the payload itself carries — a false negative, never a false match.
    """

    if not governing_extras:
        return None
    out: dict = {}
    for key, values in governing_extras.items():
        if isinstance(values, list) and len(values) == len(rules):
            out[key] = values[index]
    return out or None


def _unattributable_extras(governing_extras: dict | None, rules: list) -> dict | None:
    """Governing extras that could not be attached to any particular rule.

    A list aligned to the rules is attributed one entry per rule by
    :func:`_per_rule_extras`, and is therefore already inside each rule's own
    identity. Anything else — a mis-aligned list, a scalar, a key this module has
    never seen — has no per-rule meaning, so it is compared here instead of being
    dropped. That keeps the guard in `_per_rule_extras` honest: extras that do not
    line up still make two policies differ, they just do so as a whole rather than
    rule by rule.
    """

    if not governing_extras:
        return None
    unattributed = {
        key: value
        for key, value in governing_extras.items()
        if not (isinstance(value, list) and len(value) == len(rules))
    }
    return unattributed or None


def _base_identity_index(
    rules: list, spans: dict, governing_extras: dict | None = None
) -> dict[str, str]:
    """Each rule's link-free identity, keyed by the id other rules use to name it.

    Pass one of the two-pass resolution. Pass two resolves every link against
    this. Two passes rather than recursion is what makes the resolution total and
    cycle-safe — see :func:`_rule_base_semantics`.
    """

    index: dict[str, str] = {}
    for position, rule in enumerate(rules):
        if not isinstance(rule, dict):
            continue
        rule_id = rule.get("rule_id")
        if rule_id is None:
            continue
        index[str(rule_id)] = canonical_hash(
            _rule_base_semantics(
                rule, spans, _per_rule_extras(governing_extras, rules, position)
            )
        )
    return index


def rule_semantic_fingerprints(
    payload: dict, *, governing_extras: dict | None = None
) -> list[str | None]:
    """One semantic identity per rule, aligned to ``payload["rules"]``.

    The same equivalence the whole-policy fingerprint uses, applied one level
    down: everything the rule governs, with identity and provenance removed and
    its links resolved to what they point at. Two entries are equal exactly when
    the two rules bind identically — same condition, effect, type, mode, stored
    required facts, scope, exceptions, advice, effective window, verbatim source
    sentences, the authority and priority carried in through
    ``governing_extras``, and the same *semantics* behind every rule they
    supersede or relate to.

    ``None`` for anything that is not a rule object, so a caller can tell "not
    comparable" from "comparable and unique" and refuse to collapse the first.

    Exists because a policy can hold the same rule several times just as a corpus
    can hold the same policy several times, and the second costs exactly what the
    first did: a published version holds 280 rules with 229 distinct source
    texts, and a selection of twenty-five ids there represented seven distinct
    rows. The caller that owns the selection budget owns what to do about that;
    this only says which rules are the same rule.
    """

    spans = payload.get("spans") or {}
    rules = payload.get("rules") or []
    base_by_id = _base_identity_index(rules, spans, governing_extras)
    return [
        canonical_hash(
            _rule_semantics(
                rule, spans, base_by_id, _per_rule_extras(governing_extras, rules, position)
            )
        )
        if isinstance(rule, dict)
        else None
        for position, rule in enumerate(rules)
    ]


def _rule_base_semantics(
    rule: dict, spans: dict, per_rule_extras: dict | None = None
) -> dict:
    """One rule as what it governs, *without* its links to other rules.

    This is the identity a link resolves **to**, and it is deliberately
    link-free. That is the whole of the cycle safety: resolving a link yields a
    base identity, a base identity contains no links, so no resolution can ever
    trigger another. Two rules that supersede each other, a rule that supersedes
    itself, and a chain of a thousand rules all terminate in one pass.

    `evidence_refs` are span-dictionary keys, and those keys are digests of the
    document version — so two copies of one policy extracted from two document
    versions carry different refs for identical sentences. The refs are therefore
    replaced by the spans' own content, **in evidence order**, which is
    meaningful: the first reference is the clause the rule was quoted from and
    the rest are supporting clauses.
    """

    semantics = _strip_identity({k: v for k, v in rule.items() if k not in _RULE_DROPPED_KEYS})
    semantics.pop("evidence_refs", None)
    semantics["evidence"] = [
        _span_semantics(spans.get(ref)) for ref in (rule.get("evidence_refs") or [])
    ]
    if "required_facts" in semantics:
        semantics["required_facts"] = _strip_identity(_governing_required_facts(rule))
    semantics["governing_extras"] = _strip_identity(per_rule_extras) if per_rule_extras else None
    return semantics


def _relationship_semantics(
    rule: dict, base_by_id: dict[str, str], keys: tuple[str, ...] = RELATIONSHIP_KEYS
) -> dict:
    """What this rule's links point *at*, rather than what the targets are called.

    Each target id is replaced by the digest of the target rule's base identity.
    Two policies that each supersede one rule therefore compare equal only when
    the rules they supersede govern identically — which is the distinction that
    count-only comparison, and dropping the links altogether, both destroy.

    A target that is not one of this policy's own rules cannot be resolved to
    anything, so its raw id is kept under :data:`UNRESOLVED_TARGET`. That is a
    deliberate false negative: two copies of a policy whose links leave it will
    generally carry different ids for the same external rule and will not
    collapse. Forgoing a collapse costs one answer slot; a wrong collapse costs a
    reviewer the policy that governed their case, so the asymmetry is not close.

    `supersedes` and `related` are kept apart — displacing a rule and being read
    beside it are different claims — and each is sorted, because the order a
    drafter listed two links in is not a term.
    """

    resolved: dict[str, list] = {}
    for key in keys:
        targets = []
        for value in rule.get(key) or []:
            target_id = str(value)
            digest = base_by_id.get(target_id)
            targets.append(
                digest if digest is not None else {UNRESOLVED_TARGET: target_id}
            )
        resolved[key] = sorted(targets, key=canonical_json)
    return resolved


def _rule_semantics(
    rule: dict,
    spans: dict,
    base_by_id: dict[str, str],
    per_rule_extras: dict | None = None,
    relationship_keys: tuple[str, ...] = RELATIONSHIP_KEYS,
) -> dict:
    """One rule as what it governs, links included and resolved."""

    return {
        **_rule_base_semantics(rule, spans, per_rule_extras),
        **_relationship_semantics(rule, base_by_id, relationship_keys),
    }


def policy_semantic_core(
    payload: dict,
    *,
    governing_extras: dict | None = None,
    relationship_keys: tuple[str, ...] = RELATIONSHIP_KEYS,
) -> dict:
    """Everything the published policy governs, with identity and provenance gone.

    ``governing_extras`` carries the governing fields the lean payload
    deliberately does not hold — `authority` and `priority`, which the gather
    never reads (see
    :func:`~policy_platform.infrastructure.projection.published_case_payload.governing_extras_for_group`).
    They are compared here because two otherwise identical statements issued
    under different authority are two policies. When a caller has no extras to
    give, ``None`` is carried explicitly rather than omitted: "authority
    unrecorded" and "authority absent" must fingerprint the same way for every
    policy in one comparison, and they do, because the same caller supplies all
    of them or none of them.

    They are compared **once**, attached to the rule each entry describes, and
    never again as positional lists at this level. That is not a tidiness
    preference: the rules are compared as a sorted multiset precisely so that the
    order an extractor emitted them in cannot decide identity, and a parallel
    list of per-row authority carried beside them would put that order straight
    back in. Two policies stating the same rules in a different order, with
    authority varying between rows, would then have equal rules and unequal
    extras and would fail to match. Per-rule attribution is preserved and the
    ordering dependence is not.

    Returned rather than hashed directly so a test — and a reviewer asking why
    two policies did or did not collapse — can read exactly what was compared.
    """

    envelope = payload.get("envelope") or {}
    spans = payload.get("spans") or {}
    rules = payload.get("rules") or []

    # Pass one: each rule's link-free identity, keyed by the id other rules use
    # to name it. Pass two (below) resolves every link against this.
    base_by_id = _base_identity_index(rules, spans, governing_extras)

    return {
        "fingerprint_version": POLICY_SEMANTIC_FINGERPRINT_VERSION,
        "projection": payload.get("projection"),
        "representation": payload.get("representation"),
        # The heading is the document's own words and is compared like any other
        # content — one component of the fingerprint, never the test on its own.
        "envelope": _strip_identity(envelope),
        # The fact dictionary is re-derived from the same canonical the rule
        # attributes are, so it is a restatement for the same reason and is
        # compared through the rules' own sentences rather than on its own.
        #
        # The *set* of rules a policy imposes, as a canonical multiset. Order is
        # not compared, because it is the order an extractor happened to
        # enumerate the document in, not a term of the policy — the live corpus
        # holds one role-profile table extracted twice with its rows in two
        # different orders and otherwise word-for-word identical. A multiset, not
        # a set: a policy stating a rule twice is not the same as one stating it
        # once, and sorting by each rule's own canonical form keeps that while
        # making the comparison independent of arrangement.
        "rules": sorted(
            canonical_json(
                _rule_semantics(
                    rule,
                    spans,
                    base_by_id,
                    _per_rule_extras(governing_extras, rules, position),
                    relationship_keys,
                )
            )
            for position, rule in enumerate(rules)
            if isinstance(rule, dict)
        ),
        # Extras that *are* aligned to the rules are attributed one entry per
        # rule above, inside each rule's own identity — so they are absent here
        # deliberately. Emitting the aligned lists again at this level would
        # reintroduce the order dependence the sorted rule multiset exists to
        # remove: two policies stating the same rules in a different order, with
        # per-rule authority varying between rows, would have equal rules and
        # unequal positional extras. Only what could not be attributed is
        # compared here.
        "governing_extras": _strip_identity(_unattributable_extras(governing_extras, rules)),
    }


def policy_semantic_fingerprint(payload: dict, *, governing_extras: dict | None = None) -> str:
    """A stable digest of :func:`policy_semantic_core`.

    Equal fingerprints mean the two published records govern identically in every
    respect this system stores. Unequal fingerprints mean nothing stronger than
    "not proven identical" — which is the safe direction, because an unequal pair
    is simply read as two policies, exactly as it was before this existed.

    This is the **only** thing that may justify calling one policy a duplicate of
    another. :func:`policy_normative_group_key` is deliberately weaker and must
    never be used for that.
    """

    return canonical_hash(policy_semantic_core(payload, governing_extras=governing_extras))


#: Named on the retrieval disclosure so a reader can tell which ordering produced
#: a retained set, and so a later ordering is a different, visible thing.
POLICY_NORMATIVE_GROUP_VERSION: Final[str] = "normative_content_v1"


def policy_normative_group_key(payload: dict, *, governing_extras: dict | None = None) -> str:
    """What two policies *require*, ignoring how a drafter grouped them for reading.

    WHAT THIS IS FOR, AND WHAT IT IS NOT

    This is an **ordering** key. It says "these two candidates say the same thing
    normatively, so reading both before reading something else is a poor use of a
    five-policy budget". It says nothing about identity, it never justifies a
    `duplicate_policy_content` discard, and a policy deferred by it is reported
    exactly as any other policy that did not place inside the budget.

    WHY IT HAD TO BE SEPARATE FROM EQUALITY

    The live hardware pair is the case. Two published copies of one entitlement
    provision agree on every sentence, effect, date, scope and required fact, and
    differ in that one records forty-two `related_rule_ids` and the other records
    none. That is a real difference in the record, so
    :func:`policy_semantic_fingerprint` refuses to call them identical and the
    duplicate collapse correctly leaves both. But they still took ranks 0 and 3
    of five between them, and the provision that decided the case ranked sixth.

    Being *told* which rules to read together is not a term binding anyone; it is
    a reading aid. So it is dropped here and only here. Everything that decides
    an outcome is kept — every source sentence, condition, effect, type, mode,
    stored required fact, authority, priority, scope, effective window, carve-out
    and piece of advice, and **supersession**, because a policy that displaces one
    rule and a policy that displaces another do different things and must never
    share a group.

    Nothing about a heading, a project, a language, a question's words or any
    identifier reaches this key: it is :func:`policy_semantic_core` with one
    named field withheld.
    """

    return canonical_hash(
        policy_semantic_core(
            payload,
            governing_extras=governing_extras,
            relationship_keys=DECISIVE_RELATIONSHIP_KEYS,
        )
    )
