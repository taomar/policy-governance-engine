"""The audited receipt an external caller is answered with — `v1` and `v2`.

TWO ENVELOPES, ONE STORE

`case_decision_v2` is what a new decision is answered and stored as.
`case_decision_v1` is kept because rows written before it exist and must stay
readable: a receipt whose whole purpose is to be citable months later cannot be
made unreadable by a schema change. Nothing *writes* v1 any more. `GET` reads
whichever version the stored row says it is — the envelopes form a discriminated
union on `schema_version`, so a reader never has to guess.

WHY v2 EXISTS: A CASE ASKS FOR UP TO TWO THINGS

v1 assumed a case was one of two kinds and answered it in one branch, reported
through one scalar `decision_status`. That is not what a caller asks. A single
question can ask *what the retained published policies state* (information), and
it can ask *how the case comes out* (a verdict), and those are independent: a
question may want either, or both. Under v1 a mixed question lost half of its
answer — the branch that did not run simply was not there, and no field said so.

So v2 replaces the one scalar with two independent tracks:

  * `asked` — the two booleans the classifier returned, and nothing derived.
  * `outcome` — one enum per track, including `not_requested` (you did not ask
    for this) and `not_evaluated` (nothing was evaluated at all). Read this
    first, exactly as v1's `decision_status` was read first.
  * `information` — null, or what the policies state, with its own citations.
  * `verdict` — null, or the determination, with `missing_information` when the
    case cannot be decided until the caller supplies facts.

`missing_information` is the field the whole redesign is for on the verdict side:
a caller whose case is undecidable gets a *structured* list of what is missing —
the fact, a label, why it is needed, and the rules that need it — while still
receiving the information they asked for. Under v1 that caller got a status and
a flat list of strings, and no information at all.

THE INVARIANT THAT SURVIVED

`verdict.decision` is non-empty **iff** `verdict.reached` is true **iff**
`verdict.status` is `answered`. "No", "not compliant" and "denied" are reached
verdicts and are carried in `decision`; a case that was not decided has an empty
`decision` and `reached: false`, and can never be mistaken for one that was
decided against the caller. The model enforces this rather than documenting it.

WHY A SEPARATE CONTRACT

The project-case decider (`infrastructure/assistants/ai_case_project`) answers a
reviewer looking at a screen. Its reply is shaped for that reader: a retrieval
block, the policies considered, and the gather's answer. It carries no identity,
no caller, no version provenance and nothing an external system could cite three
months later — because nothing persisted it.

This module is the shape of the *receipt*. It says who asked, under which
authenticated identity, which project and which exact published version decided,
what was retrieved and what was discarded, what the decision was, what it cited,
and an integrity seal over the decision-defining subset of all of that. It is
versioned by name (`schema_version`) so a consumer can pin it.

THREE THINGS IT DELIBERATELY DOES NOT DO

1. **It never carries a full policy payload.** Policy records are large and
   already served, byte-for-byte, by `GET /api/policy-payload/{provision_id}`.
   Every policy reference here carries that URL instead. A receipt that embedded
   the record would double the corpus into the audit log and go stale the moment
   the projection changed.

2. **It never presents a non-answer as a verdict.** `outcome` sits above both
   semantic sections precisely so a client reads it first. A retrieval that
   found nothing, a model that declined, a gather that failed and a real
   determination are four different things, and only one of them has a verdict.
   `verdict.decision` is empty for the other three, and `verdict` itself is null
   when no verdict was asked for.

3. **It never invents trace metadata.** `trace` reports what is known truthfully:
   the prompt version the gather stamps on its own grounding block, the
   configured model deployment, the retrieval method, and the search index the
   decider actually consulted. It does **not** report the reasoning effort the
   model ran at: `ai_case_intent._chat_json` silently drops `reasoning_effort`
   and retries when a deployment rejects it, so the effort actually used is not
   knowable from here. What the caller *asked for* is knowable, and is reported
   as `request.reasoning_effort_requested`, which is named for what it is.

CALLER GUIDANCE IS ECHOED; THE SERVER'S PROMPT IS NOT

`request.additional_instructions` is the caller's own text, normalised and
returned exactly as it was applied, so an integration can show a user what was
actually sent rather than what they typed. The server's hidden instructions stay
hidden and are identified by `trace.prompt_version` and
`trace.instruction_profile` instead. That asymmetry is deliberate and is the
whole safety story of the field: what the caller can edit is theirs and is shown
back to them, and what they cannot edit is named but not exposed. Returning the
system prompt would turn an internal safeguard into a public surface, and the
first thing a public surface acquires is someone who wants to change it.

The guidance is bound into the idempotency request hash and sealed by digest in
`decision_hash`, because it changes the answer a caller receives even though it
cannot change what was decided.

THE HASH

`decision_hash` is an integrity seal, not a determinism claim — the same
scenario put twice to the same version may legitimately produce different prose,
because a language model is in the path. What the hash proves is that *this*
receipt's decision-defining content has not been altered since it was written.
`hash_basis` names the preimage rule so a future basis can be added without
making an old hash ambiguous. See `decision_hash_preimage` for the exact fields.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, Field, TypeAdapter, model_validator

from policy_platform.contracts.canonical import canonical_hash

#: The name of the envelope a receipt written before the two-track redesign
#: carries. Nothing writes it any more; it is named here because stored rows
#: carry it and `GET` must keep reading them.
SCHEMA_VERSION_V1: Final[str] = "case_decision_v1"

#: The name of the envelope every new decision is answered and stored as.
#: Carried in every response so a consumer can pin it and reject a shape it was
#: not written against.
SCHEMA_VERSION_V2: Final[str] = "case_decision_v2"

#: Retained alias. Existing imports of `SCHEMA_VERSION` mean *the version this
#: module was written around* at the time they were written, which is v1; new
#: code names the version it wants explicitly.
SCHEMA_VERSION: Final[str] = SCHEMA_VERSION_V1

#: What `decision_hash` means, per envelope. Stored beside the hash rather than
#: assumed, so a new preimage rule can be introduced without silently changing
#: what an already-written hash claims — which is exactly what v2 does.
HASH_BASIS_V1: Final[str] = "case_decision_v1"
HASH_BASIS_V2: Final[str] = "case_decision_v2"
HASH_BASIS_V2_WITH_VERIFICATION: Final[str] = "case_decision_v2_verification"

#: The basis every decision made under the language boundary is sealed with.
#: A receipt that adjudicated a rendering of the question must seal that
#: rendering: the English text **is** what was read, and a seal that omitted it
#: would let the decision-determining intermediate change without breaking.
#:
#: It is a new basis rather than a widened one because `hash_basis` is stored
#: per row and is already an argument to finalisation, so no stored receipt is
#: migrated and each verifies under the basis it was written with. A verifier
#: that recomputes a hash independently **must branch on `hash_basis`**.
#:
#: The schema version does not move with it. Every field the boundary adds is an
#: additive optional one, `validate_receipt` is untouched, and bumping to a
#: third envelope for additive fields would strand readers for no gain.
HASH_BASIS_V2_LANG: Final[str] = "case_decision_v2_lang"
HASH_BASIS_V2_LANG_WITH_VERIFICATION: Final[str] = (
    "case_decision_v2_lang_verification"
)
HASH_BASIS: Final[str] = HASH_BASIS_V1

#: The lifecycle of the stored receipt row, distinct from the decision's own
#: outcome. `pending` is reserved before the model is called, and a receipt that
#: never reached `completed` never carries a usable verdict.
RECEIPT_PENDING: Final[str] = "pending"
RECEIPT_COMPLETED: Final[str] = "completed"
RECEIPT_FAILED: Final[str] = "failed"
RECEIPT_STATUSES: Final[tuple[str, ...]] = (RECEIPT_PENDING, RECEIPT_COMPLETED, RECEIPT_FAILED)

#: A completed receipt whose retrieval produced no evaluation at all. This is a
#: legitimate outcome, not an error: the project may have published nothing, the
#: index may be missing, or no published policy may bear on the question. Kept
#: apart from every status the gather can return, so "nothing was evaluated" can
#: never be read as "the policies were evaluated and said nothing".
NOT_EVALUATED: Final[str] = "not_evaluated"

#: The closed set `decision_status` may take. The first six are
#: `ai_case_intent`'s own statuses (the union of the informational and decision
#: branches, which share a vocabulary); the seventh is this layer's.
DecisionStatus = Literal[
    "answered",
    "missing_required_facts",
    "not_settled_by_rules",
    "no_rule_bears",
    "declined",
    "failed",
    "not_evaluated",
]

#: Only this one carries a verdict. Named so a client's guard and this module's
#: own assembly cannot drift apart.
STATUS_WITH_VERDICT: Final[str] = "answered"

#: A track the caller did not ask for. Distinct from `not_evaluated`: one says
#: "you did not ask for this", the other says "nothing was evaluated at all".
#: Collapsing them would let a caller read their own silence as the corpus's.
NOT_REQUESTED: Final[str] = "not_requested"

#: The closed set an *information* track can report. The first four are the
#: informational gather's own states; the last two are this layer's.
InformationOutcome = Literal[
    "answered",
    "no_rule_bears",
    "declined",
    "failed",
    "not_requested",
    "not_evaluated",
]

#: What the information section itself may be in. A section only exists when the
#: track ran, so `not_requested` and `not_evaluated` cannot appear here — they
#: are outcomes of *not having* a section.
InformationStatus = Literal["answered", "no_rule_bears", "declined", "failed"]

#: The closed set a *verdict* track can report, with the two ways a relevant
#: policy can still not settle a case kept apart from the ways nothing bore on it.
VerdictOutcome = Literal[
    "answered",
    "missing_required_facts",
    "not_settled_by_rules",
    "no_rule_bears",
    "declined",
    "failed",
    "not_requested",
    "not_evaluated",
]

VerdictStatus = Literal[
    "answered",
    "missing_required_facts",
    "not_settled_by_rules",
    "no_rule_bears",
    "declined",
    "failed",
]

#: Which of the two tracks a merged citation was cited by. A rule cited by both
#: appears once, carrying both tags — see `MergedCitationRef`.
SERVES_INFORMATION: Final[str] = "information"
SERVES_VERDICT: Final[str] = "verdict"
CitationServes = Literal["information", "verdict"]

#: The gather branch a section was produced by, in the decider's own vocabulary.
#: Reported so a reader is never left inferring which prompt composed the prose.
ROUTE_INFORMATIONAL: Final[str] = "informational"
ROUTE_DECISION: Final[str] = "decision"

#: How the caller reached the decider. One value today; named rather than
#: hardcoded because a receipt that cannot say which channel produced it cannot
#: be filtered by one later.
CHANNEL_API: Final[str] = "api"

#: The most caller guidance a decision will accept, measured **after**
#: normalisation. A ceiling exists for two reasons and only incidentally for
#: cost: a receipt stores this text in clear and must stay readable, and a very
#: long block of caller text sitting beside the policy records starts to compete
#: with them for the model's attention — which is precisely the thing the
#: guidance is not allowed to do.
MAX_ADDITIONAL_INSTRUCTIONS_CHARS: Final[int] = 2000


def normalise_additional_instructions(value: str | None) -> str:
    """The caller's guidance, in the one form that is stored, hashed and sent.

    Normalisation is not cosmetic here. The same guidance must produce the same
    idempotency binding whether it arrived with a trailing newline, with CRLF
    line endings from a Windows client, or re-indented by a form control — and
    without this, a caller retrying byte-for-byte from a text area would be told
    their request body had changed.

    So: line endings are unified, runs of blank lines collapse to one, spaces
    and tabs inside a line collapse to a single space, each line is stripped,
    and the whole is stripped. Line structure survives, because a caller writing
    a short list of preferences means the list.
    """

    if not value:
        return ""

    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in text.split("\n")]

    collapsed: list[str] = []
    for line in lines:
        if not line and (not collapsed or not collapsed[-1]):
            continue
        collapsed.append(line)

    return "\n".join(collapsed).strip()


def additional_instructions_hash(value: str) -> str:
    """A digest of the normalised guidance, for correlating and for the seal.

    Kept beside `scenario_hash` and computed the same way, so the two halves of
    what a caller sent are covered symmetrically. An empty string hashes to a
    stable value rather than to `None`: "no guidance was given" is a fact worth
    sealing, and a null would let it be confused with "this receipt predates the
    field".
    """

    return canonical_hash({"additional_instructions": value})


# ── caller and request ───────────────────────────────────────────────


class CallerRef(BaseModel):
    """Who called, established and declared, never conflated.

    `principal_identity` is what the server *proved* — the identity out of a
    validated bearer token. `calling_system_identity` is what the caller *said
    about itself*, an unverified free-text label useful for grouping a fleet of
    workers under one name. They are stored and returned as two fields on
    purpose: presenting a self-declared label beside a proved identity, in one
    field, is how an audit trail acquires a caller it never authenticated.
    """

    principal_identity: str = Field(
        description="The authenticated identity the server established from the caller's token."
    )
    principal_role: str = Field(description="The role that identity holds in this product.")
    authentication_source: str = Field(
        description="How the identity was established (for example `token` or `local-token`)."
    )
    calling_system_identity: str | None = Field(
        default=None,
        description=(
            "A label the caller declared about itself. Unverified: it is stored for grouping "
            "and reporting, never as evidence of who called."
        ),
    )
    channel: str = Field(default=CHANNEL_API, description="The channel the decision was requested through.")


class RequestRef(BaseModel):
    """What was asked, and the hash of the question as it was received."""

    scenario: str = Field(description="The caller's question, stored verbatim so the receipt shows it.")
    scenario_hash: str = Field(
        description="SHA-256 over the scenario text alone, for correlating repeats without reading them."
    )
    additional_instructions: str = Field(
        default="",
        description=(
            "Caller-supplied guidance about how to present the explanation, normalised and echoed "
            "exactly as it was applied. It shapes emphasis, length and format only: it cannot change "
            "which policies were retrieved, what a rule means, the decision status, the citation "
            "requirement, or anything else in the authoritative policy contract. Empty when none was "
            "given."
        ),
    )
    additional_instructions_hash: str = Field(
        default="",
        description=(
            "SHA-256 over the normalised guidance. Sealed alongside the scenario so a stored "
            "receipt's record of what the caller asked for cannot be altered unnoticed."
        ),
    )
    scope: str = Field(description="`project` when retrieval ran, `single` when one policy was named.")
    requested_provision_id: str | None = Field(
        default=None, description="The policy the caller named, when they named one."
    )
    reasoning_effort_requested: str = Field(
        description=(
            "The reasoning effort the caller asked for. Named `requested` because a deployment "
            "may reject it, in which case the call is retried without it and the effort actually "
            "used is not observable."
        )
    )
    received_at: datetime = Field(description="When the request was accepted and its receipt reserved.")


class LanguageRef(BaseModel):
    """Which language each stage worked in, and what was actually adjudicated.

    **Additive, and present on every decision made under the boundary.** It is
    absent — null — on a receipt written before the boundary existed, which is a
    different fact from a boundary that reported nothing, and the two must stay
    distinguishable.

    WHY THE RENDERED QUESTION IS ON THE RECEIPT

    Because it is what was read. Retrieval, classification and adjudication all
    ran against `processing_scenario`; a receipt that showed only the caller's
    own words would hide the text the decision was actually made from, and a
    reviewer comparing the two is the only person who can catch a rendering that
    changed the question. It is carried in full *and* by digest: the digest is
    what the seal covers, the text is what a person reads.

    WHAT IT DOES NOT DO

    Nothing here changes what was decided. `request.scenario`,
    `request.scenario_hash` and the idempotency binding are all over the
    caller's own bytes, exactly as they were before the boundary existed — a
    rendering must never enter them, or a caller's byte-for-byte retry would
    look like a different request every time a rendering varied.
    """

    source_language: str = Field(
        description=(
            "The IETF BCP 47 tag the inbound rendering observed the question to be in. `und` "
            "when the tag it reported was not well-formed — the decision is unaffected, because "
            "the pipeline reasons in `processing_language` whatever the question was written in."
        )
    )
    processing_language: str = Field(
        description=(
            "The language every stage of the decision worked in: retrieval, classification and "
            "both gathers. One value, always, and the reason this block exists."
        )
    )
    response_language: str = Field(
        description=(
            "The language the prose in this receipt is written in. Equals `processing_language` "
            "when the question arrived in it, or when no usable target tag was observed."
        )
    )
    boundary_state: str = Field(
        description=(
            "`rendered` when the question was carried into the processing language, `identity` "
            "when the rendering call reported it was already in it. Never absent: an unmade call "
            "and an identity rendering are different facts."
        )
    )
    output_rendering_state: str = Field(
        description=(
            "`rendered` when the whitelisted prose was carried back to the caller's language; "
            "`target_unknown` when no usable tag was observed and the prose is returned as it "
            "was reasoned; `not_required` when no rendering was made because none was needed — "
            "either the answer was owed in `processing_language`, or the evaluation composed no "
            "prose at all (nothing was retrieved, no rule bore on the question, or a track "
            "failed). Read it with `source_language` to tell those two apart. When this is not "
            "`rendered`, `output_translation_profile` is null and `response_language` is "
            "`processing_language`, because no string in this receipt is written in another."
        )
    )
    guidance_rendering_state: str = Field(
        description=(
            "`not_required`, `rendered`, or `unrendered_dropped` — the last meaning the caller's "
            "presentation guidance could not be carried across and was dropped rather than "
            "applied un-rendered. The decision itself is unaffected either way."
        )
    )
    input_translation_profile: str = Field(
        description=(
            "Identifier of the versioned contract the question was rendered under. Sealed, "
            "because two contracts can reduce one question to two different English texts."
        )
    )
    output_translation_profile: str | None = Field(
        default=None,
        description="The contract the prose was rendered back under. Null when nothing was rendered.",
    )
    processing_scenario: str = Field(
        description=(
            "The question as every stage of the decision read it. Equal to `request.scenario` "
            "when the question arrived in the processing language."
        )
    )
    processing_scenario_hash: str = Field(
        description=(
            "SHA-256 over `processing_scenario`. Sealed by `decision_hash`, so the text that was "
            "actually adjudicated cannot be altered on a stored receipt without breaking it."
        )
    )
    processing_additional_instructions: str = Field(
        default="",
        description=(
            "The caller's guidance as the gather read it. Equal to "
            "`request.additional_instructions` when no rendering was needed, and empty when the "
            "guidance was dropped. The caller's own bytes and their digest are unchanged beside it."
        ),
    )
    projection_profile: str | None = Field(
        default=None,
        description=(
            "Identifier of the corpus projection the retrieval index was built under, once one "
            "exists. Null until the index carries one — a query and the text it is scored "
            "against must be in one language, and this is what says whether they were."
        ),
    )


# ── project, version, policies ───────────────────────────────────────


class PolicySetRef(BaseModel):
    """The project, by all three of its names.

    `key` is the routing identifier and the only one an external caller should
    build a URL from. `id` is trace identity — returned so a receipt joins to a
    row, never routed on. `name` is for display.
    """

    id: str
    key: str
    name: str


class VersionRef(BaseModel):
    """The exact published version the decision was made against.

    Nullable at the envelope level, because a project with nothing published is
    a legitimate case outcome rather than an error. When present, this is the
    version the decider itself loaded — not a re-read of "the active version"
    around a call that takes ten seconds and could straddle a publication.
    """

    version_id: str
    version_number: int | None = None
    effective_from: date | None = None
    effective_to: date | None = None


class RuleSelectionRef(BaseModel):
    """Which of a policy's rules were actually put in front of the model.

    A policy holding more rules than one case can read is narrowed to the rules
    that bear on the question — see
    `infrastructure/projection/policy_rule_slice`. This is what stops that being
    a hidden narrowing: a receipt that reported the policy without reporting the
    slice would imply all of its rules were weighed, and for a
    seventy-four-row penalties table that is the difference between "the schedule
    was considered" and "eight of its rows were".

    `method` names how the rules were chosen rather than describing it, so a
    reader can tell a relevance selection from the fallback that runs when no
    rule matched the question's terms — the two are very different claims about
    how much attention the policy received.
    """

    total_rules: int = Field(description="How many rules the published policy holds.")
    selected_rules: int = Field(
        description=(
            "How many of them were put in front of the model — the total, including any context "
            "rules. Never more than the `selected_rule_budget` the retrieval block reports."
        )
    )
    selected_rule_ids: list[str] = Field(
        default_factory=list,
        description="Exactly which rules were read, so the claim is checkable rather than counted.",
    )
    rules_discarded: int = Field(
        default=0, description="`total_rules` less `selected_rules`. Not read, and not evaluated."
    )
    method: str = Field(
        description=(
            "`whole_policy` — the policy is small enough to read entire, and nothing was "
            "selected. `hybrid_rule_v1` — the rule index took part: the rule's own search "
            "rank, a relevance rank over the English projection of each rule, and a "
            "quantity-compatibility rank were fused by reciprocal rank, ties broken on "
            "document order. `scenario_relevance_v3` — rule documents exist under the expected "
            "projection and the query against them failed recoverably, so the same selection "
            "ran over the English projection without the index's ranking. "
            "`scenario_relevance_v2` — the rule index was not consulted, and rules were ranked "
            "against the question by the policy's own stored words. On every one of these, "
            "exactly-identical rules are collapsed first, and passage diversity is guaranteed "
            "for at most half the budget rather than for the whole of it. `document_order` — "
            "nothing placed at all, so the first rules were taken and the miss is disclosed "
            "rather than hidden. The version suffix moves when the selection algorithm changes, "
            "so a stored receipt names the algorithm that produced it."
        )
    )
    sliced: bool = Field(
        default=False,
        description="True when fewer than all of the policy's rules were read.",
    )
    context_rules_added: int = Field(
        default=0,
        description=(
            "Rules pulled in behind a selected one because it explicitly names them — what it "
            "supersedes, what the drafter marked as read-together. Not selected on their own "
            "relevance, and counted inside `selected_rules`: context fills the slots the "
            "selection left unused and never extends the rule budget."
        ),
    )
    context_rules_omitted: list[str] = Field(
        default_factory=list,
        description=(
            "Context a selected rule names that was not admitted — because the rule budget was "
            "already spent on rules that bear on the question, or because the record budget had "
            "no room. Named rather than dropped in silence: a rule read without the rule it "
            "overrides is read incompletely, and a reader is owed the chance to fetch it."
        ),
    )
    duplicate_rules_collapsed: int = Field(
        default=0,
        description=(
            "Rules of this policy that were not candidates for selection because an earlier rule "
            "of the same policy governs identically — same condition, effect, type, mode, stored "
            "required facts, authority, scope, effective window, carve-outs and relationship "
            "targets. A copy is not a second rule and may not take a second slot."
        ),
    )
    represented_rule_ids: list[str] = Field(
        default_factory=list,
        description=(
            "Rules that were not read and did not need to be: each is an exact copy of a rule "
            "that was. Part of `rules_discarded`, named so that number is not read as 'unknown "
            "content'. None of these was put in front of the model."
        ),
    )
    chars: int | None = Field(default=None, description="The record's transport size after selection.")
    budget_chars: int | None = Field(default=None, description="The per-policy ceiling it was measured against.")
    oversize: bool = Field(
        default=False,
        description=(
            "True when the selected rules do not themselves fit. Nothing was trimmed to make them "
            "— the record is refused whole downstream instead."
        ),
    )
    rule_index_state: str | None = Field(
        default=None,
        description=(
            "Whether the rule index took part in *this policy's* selection: `matched`, "
            "`degraded` or `unavailable`. Per policy as well as per retrieval, because a "
            "project-wide degradation and a policy with no rule documents are different facts "
            "about different policies in one answer."
        ),
    )
    rule_index_hits: int | None = Field(
        default=None,
        description=(
            "How many of this policy's rules the rule index ranked for this question. Zero with "
            "`matched` is a real answer — the index was asked and placed none of them — and is "
            "not the same as `unavailable`, where it was not asked."
        ),
    )
    lexical_candidates: int | None = Field(
        default=None,
        description="Rules the relevance ranking placed, over whichever corpus it scored.",
    )
    quantity_candidates: int | None = Field(
        default=None,
        description=(
            "Rules stating a quantity that admits a quantity the question states — a value "
            "inside a stated interval, or equal to a stated value, in a matching unit. A "
            "retrieval rank only: it decides whether a rule is worth reading, never what the "
            "rule decides."
        ),
    )
    fused_candidates: int | None = Field(
        default=None,
        description=(
            "Rules at least one ranking placed, and therefore the pool the budget selected from. "
            "When this is zero the method is `document_order`."
        ),
    )
    evidence_diversity_quota: int | None = Field(
        default=None,
        description=(
            "How many of the budget's slots were reserved so that distinct source passages are "
            "covered before a passage's second rule competes. Half the budget, rounded up: the "
            "remaining slots are filled on fused rank alone, so a second strongly relevant rule "
            "from a passage already covered stays reachable."
        ),
    )
    rules_without_projection: int | None = Field(
        default=None,
        description=(
            "Rules the relevance ranking could not score because the index returned no English "
            "projection for them. They score zero rather than being scored against the "
            "document's own language — one language on both sides of a match, always — and can "
            "still be placed by the rule index or the quantity rank."
        ),
    )


class PolicyRef(BaseModel):
    """One policy the decision saw, and where to read it in full.

    `payload_url` is the whole of the policy's content in this receipt: the lean
    published record is served there and is not copied in here.
    """

    provision_id: str | None = None
    provision_key: str | None = None
    heading_path: list[str] = Field(default_factory=list)
    rules: int | None = None
    retained: bool | None = Field(
        default=None,
        description=(
            "Whether this policy was carried into the evaluation. In project scope that is "
            "retrieval's own verdict; in single scope, where retrieval is bypassed, it records "
            "whether the named policy was published and therefore evaluated."
        ),
    )
    best_rank: int | None = None
    best_score: float | None = None
    discard_reason: str | None = None
    duplicate_of_provision_key: str | None = Field(
        default=None,
        description=(
            "Set only on a policy discarded as `duplicate_policy_content`: the provision key of "
            "the identically-governing policy that was retrieved in its place. It names where "
            "this policy's terms were in fact read, without claiming this record was read."
        ),
    )
    reason: str | None = None
    payload_url: str | None = Field(
        default=None,
        description="Where the policy's full lean record is served. The record itself is never inlined.",
    )
    rule_selection: RuleSelectionRef | None = Field(
        default=None,
        description=(
            "Which of the policy's rules were read, when the policy was large enough to be "
            "narrowed to a slice. Absent on a receipt written before rule-level retrieval existed "
            "and on a policy that was never carried into an evaluation."
        ),
    )


class RetrievalRef(BaseModel):
    """What narrowing happened, in the decider's own vocabulary.

    Mirrors the retrieval block the decider reports, so the receipt and the
    in-product answer describe one event rather than two.

    Three narrowings are reported, not one, and each is a different fact:
    search discards by *relevance*, the payload budget discards whole policies by
    *size*, and a policy holding more rules than one case can read is narrowed to
    a *slice* of its rules — the per-policy detail for which is on each
    `considered` entry's `rule_selection`.
    """

    status: str
    method: str | None = None
    precision_mode: str | None = Field(
        default=None,
        description=(
            "Versioned policy-selection strategy used before records are exposed or evaluated."
        ),
    )
    semantic_candidates: int | None = None
    semantic_selected: int | None = None
    semantic_largest_gap: float | None = None
    semantic_cutoff_score: float | None = None
    semantic_elbow_applied: bool | None = Field(
        default=None,
        description=(
            "Whether a meaningful semantic score drop narrowed the direct policy pool. False means "
            "semantic scores were too flat to justify a cut, so hybrid direct-policy order remained "
            "available to the final duplicate/diversity budget."
        ),
    )
    direct_policy_order: str | None = Field(
        default=None,
        description=(
            "How direct policy identities were ordered after semantic cardinality was assessed."
        ),
    )
    coverage_expanded_policies: int | None = Field(
        default=None,
        description=(
            "Direct policies added because an English indexed heading covered explicit query "
            "terms not represented by the precision-selected records."
        ),
    )
    coverage_semantic_floor: float | None = Field(
        default=None,
        description=(
            "Minimum direct semantic reranker score a policy must carry before heading coverage "
            "can expand a precision-selected decision context."
        ),
    )
    rule_rescue_candidates: int | None = Field(
        default=None,
        description=(
            "Omitted policy parents whose strongest rule independently cleared the configured "
            "rescue threshold before the final policy budget was applied."
        ),
    )
    rule_rescued_policies: int | None = Field(
        default=None,
        description="Strong rule-only matches admitted without adding rule scores to direct policy scores.",
    )
    rule_rescue_floor: float | None = None
    rule_rescue_margin: float | None = None
    rule_semantic_window: int | None = Field(
        default=None,
        description=(
            "Maximum initial rule results Azure AI Search can pass through semantic reranking. "
            "Only candidates with an observed reranker score can satisfy rule rescue."
        ),
    )
    rule_semantic_candidates: int | None = Field(
        default=None,
        description="Returned rule documents that actually carried a semantic reranker score.",
    )
    policy_budget: int | None = None
    policy_scan: int | None = None
    policies_retrieved: int | None = None
    policies_considered: int | None = None
    policies_retained: int | None = None
    policies_discarded: int | None = None
    policies_untestable: int | None = None
    payload_budget_chars: int | None = Field(
        default=None,
        description="The combined-record ceiling one grounded pass reads, in characters.",
    )
    policies_over_payload_budget: int | None = Field(
        default=None,
        description=(
            "Policies that ranked inside the retention budget and were still set aside because "
            "their whole record would not fit. A subset of `policies_discarded`, reported apart "
            "so search is not blamed for a size decision."
        ),
    )
    large_policy_rule_threshold: int | None = Field(
        default=None,
        description="Above this many rules a policy is read rule by rule rather than whole.",
    )
    selected_rule_budget: int | None = Field(
        default=None, description="How many rules of such a policy may be selected for one case."
    )
    policies_rule_sliced: int | None = Field(
        default=None,
        description=(
            "Retained policies that were read as a slice of their rules. Each one's "
            "`rule_selection` says which rules, and how many were not read."
        ),
    )
    policies_duplicate_collapsed: int | None = Field(
        default=None,
        description=(
            "Policies collapsed before the retention budget was applied because they govern "
            "identically to a policy already retrieved. A subset of `policies_discarded`, and the "
            "only discard whose terms still reached the gather — each one names the representative "
            "it was collapsed into. Reported apart so a reader is never left to infer that the "
            "corpus held one policy where it held two copies of one."
        ),
    )
    policy_selection_order: str | None = Field(
        default=None,
        description=(
            "How the retained set was chosen from the ranked hits. Relevance first, then "
            "normative-content diversity: among candidates that require the same thing, the "
            "highest-ranked is offered before any second member of that group. Named so a reader "
            "can explain a highly-ranked policy sitting outside the budget."
        ),
    )
    policies_diversity_deferred: int | None = Field(
        default=None,
        description=(
            "Policies that ranked inside the retention budget and were **displaced out of it** "
            "because a policy requiring the same thing was offered first. Counts only what the "
            "ordering actually cost: a same-group member that ranked outside the budget anyway "
            "is not counted, because nothing displaced it. **Not duplicates** — they are not "
            "proven identical and are not reported as such; each keeps its own rank and score "
            "and carries the ordinary `outside_budget` reason."
        ),
    )
    rule_scan: int | None = Field(
        default=None,
        description=(
            "How many rule-level documents the discovery search examined. A rule document is "
            "one authoritative rule of a policy that holds more than "
            "`large_policy_rule_threshold` of them, indexed on its own so a rule can be found "
            "on its own terms rather than only through whatever its policy's combined text had "
            "room for."
        ),
    )
    projection_profile: str | None = Field(
        default=None,
        description=(
            "The versioned corpus projection the index was matched against. A question and the "
            "text it is scored against must be rendered under one contract or the two are not "
            "comparable, and this names the one that was used. Null when no index was consulted "
            "— the single-policy scope, or a state that stopped before the search."
        ),
    )
    projection_ready: bool | None = Field(
        default=None,
        description=(
            "Whether the index reported a complete corpus projection under the expected "
            "contract. Only ever true on a served answer: a project whose projection is absent, "
            "superseded or left incomplete by an unfinished rebuild is refused with "
            "`index_projection_unavailable` rather than answered from a corpus that cannot be "
            "compared against the question."
        ),
    )
    policy_documents_matched: int | None = Field(
        default=None,
        description="How many policy-level documents the search returned.",
    )
    rule_documents_matched: int | None = Field(
        default=None,
        description="How many rule-level documents the search returned.",
    )
    policies_elevated_by_rule: int | None = Field(
        default=None,
        description=(
            "Compatibility alias for policies admitted by independently strong rule-only evidence. "
            "Rule scores are never added to direct policy scores."
        ),
    )
    rule_index_state: str | None = Field(
        default=None,
        description=(
            "Whether the rule index took part. `matched` — it was queried and its ranking was "
            "available for rule-only rescue and within-policy slicing. `degraded` — rule documents "
            "exist under the expected "
            "projection and the query against them failed recoverably, so the selection ran "
            "without that ranking and each policy's `rule_selection.method` says "
            "`scenario_relevance_v3`. `unavailable` — it was not consulted."
        ),
    )
    reason: str | None = None


class CitationSourceRef(BaseModel):
    """The document's own words behind a citation, and where they were found.

    `state` distinguishes a quoted sentence from the three honest ways a quote
    can be missing (`no_citation`, `unresolved`, `not_stored`). Fields the
    projection did not carry are omitted rather than filled with a placeholder.
    """

    state: str
    text: str | None = None
    page: int | None = None
    section: str | None = None


class CitationRef(BaseModel):
    """One rule the decision rested on, traceable to the policy it came from."""

    rule_id: str
    policy: PolicyRef | None = None
    source: CitationSourceRef


class DecisionRef(BaseModel):
    """The gather's answer, with its status kept above its verdict.

    `explanation` is the gather's `answer` prose, renamed here because in a
    receipt "the answer" is the whole envelope. `decider_route` names which of
    the two branches ran — an informational gather states what the policies
    provide, a decision gather applies them — so a reader never mistakes a
    statement of what a policy says for a determination about a case.
    """

    intent: str | None = None
    classification_reasoning: str | None = None
    status: DecisionStatus
    verdict: str = Field(
        default="",
        description="Only ever populated when `status` is `answered`; empty for every other status.",
    )
    explanation: str = ""
    missing_required_facts: list[str] = Field(default_factory=list)
    note: str = ""
    decider_route: str | None = Field(
        default=None,
        description="`informational` or `decision` — which gather produced this. Null when nothing was evaluated.",
    )


class TokenUsageRef(BaseModel):
    """Service-reported model usage for one complete API operation."""

    calls: int = 0
    calls_without_usage: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None


class TraceRef(BaseModel):
    """What produced the answer, to the extent it is honestly knowable.

    Every field is nullable and omitted when unknown. In particular there is no
    "reasoning effort used": the gather drops that parameter and retries when a
    deployment rejects it, so the value cannot be reported truthfully from here.

    `prompt_version` and `instruction_profile` are the *server's* side of the
    prompt, named by identifier. The prompts themselves are deliberately not
    returned: a caller can see which contract their answer was produced under,
    and can see their own guidance echoed back in `request`, without the hidden
    instructions becoming a public API surface that could be edited by anyone
    who can read it.
    """

    prompt_version: str | None = None
    instruction_profile: str | None = Field(
        default=None,
        description=(
            "Identifier of the immutable server-side framing that caller guidance is applied "
            "under — the delimiting, the priority ordering and the invariants guidance cannot "
            "override. Changes when that framing changes; never contains the prompt text."
        ),
    )
    model_deployment: str | None = None
    retrieval_method: str | None = None
    index_name: str | None = None
    index_version_id: str | None = Field(
        default=None,
        description="The published version the retrieval index was filtered to, when retrieval ran.",
    )
    stage_latency_ms: dict[str, int] | None = Field(
        default=None,
        description=(
            "Observed wall-clock stage timings in milliseconds. Diagnostic only and excluded from "
            "the decision hash; they describe this execution, not policy meaning."
        ),
    )
    token_usage: TokenUsageRef | None = Field(
        default=None,
        description=(
            "Token counts reported by model and embedding calls in this execution. Null on "
            "historical receipts; missing figures remain null rather than being estimated."
        ),
    )


class SizeRef(BaseModel):
    """How large the evaluated record was against the one-gather budget."""

    combined_chars: int | None = None
    budget_chars: int | None = None
    oversize: bool | None = None


# ── the envelope ─────────────────────────────────────────────────────


class CaseDecisionEnvelope(BaseModel):
    """The full receipt for one audited external project-case decision, `v1`.

    **Historical.** Nothing writes this shape any more — a new decision is
    answered and stored as `CaseDecisionEnvelopeV2`. It is kept, unchanged in
    meaning, because rows written under it exist and a receipt that stopped
    being readable would defeat the point of having written one.
    """

    schema_version: Literal["case_decision_v1"] = Field(default="case_decision_v1")
    decision_id: str
    correlation_id: str
    idempotency_key: str | None = None

    policy_set: PolicySetRef
    active_version: VersionRef | None = Field(
        default=None,
        description="The exact version the decider loaded, or null when the project has published nothing.",
    )

    caller: CallerRef
    request: RequestRef

    decision_status: DecisionStatus = Field(
        description=(
            "Read this before `decision.verdict`. `not_evaluated` means retrieval produced no "
            "evaluation at all; every other value is the gather's own status."
        )
    )

    retrieval: RetrievalRef
    considered: list[PolicyRef] = Field(default_factory=list)
    excluded: list[PolicyRef] = Field(default_factory=list)

    decision: DecisionRef
    citations: list[CitationRef] = Field(default_factory=list)
    grounding: dict[str, Any] | None = Field(
        default=None,
        description=(
            "The gather's own grounding report, including `fabricated_citations` — the citations "
            "the fabrication guard refused — and `selectors_out_of_catalogue`, the outstanding-fact "
            "names the closed selector vocabulary refused, reported under "
            "`selector_catalogue_version`. Both are refusals made visible for the same reason: a "
            "guard that is only ever performed and never seen to refuse anything cannot be "
            "audited. This is the quality signal the case service provides; no other is invented "
            "here."
        ),
    )
    size: SizeRef | None = None

    trace: TraceRef

    decision_hash: str
    hash_basis: str = Field(default=HASH_BASIS)
    receipt_url: str
    decided_at: datetime
    latency_ms: int


# ── `case_decision_v2`: two independent tracks ───────────────────────


class ClassifierConsensusRef(BaseModel):
    """How many readings the classifier took, and how they split.

    The two booleans in `asked` decide **which tracks run**, so a flip does not
    degrade an answer — it replaces it with an answer to a different question.
    That is why they are read more than once and voted on, and why the vote is
    reported rather than kept: a disagreement *rate* can only be measured if the
    disagreements arrive on the receipt.

    Recorded, never sealed. It says how a reading was arrived at, not what was
    decided, so it belongs beside `classification_reasoning` and outside
    `decision_hash` for the same reason: two runs that read the question the same
    way must seal identically whether the samples agreed at once or not.

    Nothing here is voted except the two booleans. A verdict is adjudication and
    is never sampled or majority-voted anywhere in this system.
    """

    samples: int = Field(description="How many independent readings of the question were taken.")
    information_true: int = Field(
        description="How many readings said the question asks what the policies state."
    )
    information_false: int = Field(
        description="How many readings said it does not. Counted apart from unreadable ones."
    )
    verdict_true: int = Field(description="How many readings said the question asks for a verdict.")
    verdict_false: int = Field(
        description="How many readings said it does not. Counted apart from unreadable ones."
    )
    unreadable: int = Field(
        description=(
            "How many readings failed to state one of the booleans at all. Distinct from a "
            "stated `false`: only a reading nobody could read is evidence of nothing."
        )
    )
    agreed: bool = Field(
        description=(
            "True when every reading was readable and every reading said the same thing. "
            "The complement of this, aggregated over runs, is the disagreement rate."
        )
    )
    fell_back: bool = Field(
        description=(
            "True when consensus could not produce a usable requested-track pair — because of "
            "a tie, nothing readable, or unanimous `false` for both tracks — and both tracks "
            "were run rather than half or all of the question being dropped."
        )
    )


class AskedRef(BaseModel):
    """What the classifier read the question as asking for — nothing derived.

    Two independent booleans, from one classifier call. A question can be
    information-only, verdict-only, or both, and the two are not exclusive:
    "what does the policy say about overtime, and was my Tuesday shift within
    it?" asks for both, and the caller is owed both.

    The booleans are the *classifier's* reading, not the caller's request: there
    is no field on the request body that sets them. A caller who could declare
    "this is a verdict question" could choose the shape of their own answer,
    which is the first of the things caller guidance is not allowed to do, and
    putting it in a different field would not make it a different thing.

    `classification_reasoning` is prose and is deliberately **outside** the
    decision hash: it explains a routing decision, it is not part of what was
    decided, and sealing model prose that has no bearing on the outcome would
    make the seal move for a reason no auditor could act on.

    WHEN THE CLASSIFIER NEVER RAN

    A retrieval that produced no evaluation — a project with nothing published,
    an index not built, no policy bearing on the question — never reaches the
    classifier. Both booleans are then `false` and `classifier_version` is null,
    which is the truth: nothing was classified. `outcome` reports
    `not_evaluated` for both tracks in that case, which is why `outcome` is the
    field to read first and `asked` is the field that explains it.
    """

    information_requested: bool = Field(
        description="The question asks what the retained published policies state."
    )
    verdict_requested: bool = Field(
        description="The question asks for the case to be evaluated and a verdict returned."
    )
    classification_reasoning: str | None = Field(
        default=None,
        description=(
            "One or two sentences from the classifier saying why it read the question that way. "
            "Excluded from `decision_hash`: it explains routing, it is not part of the decision."
        ),
    )
    classifier_version: str | None = Field(
        default=None,
        description=(
            "Identifier of the classifier that produced the booleans. Null when no classifier "
            "ran, which happens when retrieval produced nothing to evaluate."
        ),
    )
    classifier_consensus: ClassifierConsensusRef | None = Field(
        default=None,
        description=(
            "How the repeated readings of the question split, when a classifier ran. Null when "
            "none ran. Excluded from `decision_hash`: it records how a reading was arrived at, "
            "not what was decided."
        ),
    )


class OutcomeRef(BaseModel):
    """One enum per track. **Read this before either section.**

    This is v2's replacement for v1's single `decision_status`, and it is two
    values rather than one because a case has two independently answerable
    halves. Each carries the same closed vocabulary the section can be in, plus:

      * `not_requested` — the classifier did not read the question as asking for
        this track, so it was never run and the section is null.
      * `not_evaluated` — nothing was evaluated at all. Retrieval produced no
        record to answer from, so neither track ran. A legitimate `200`.

    Only `verdict: "answered"` carries a determination.
    """

    information: InformationOutcome = Field(
        description="The information track's outcome, or why it has none."
    )
    verdict: VerdictOutcome = Field(description="The verdict track's outcome, or why it has none.")


class MergedCitationRef(CitationRef):
    """One rule the receipt rested on, and which track (or tracks) cited it.

    The two tracks cite independently and often overlap — the rule that *states*
    the weekly cap is frequently the same rule that *decides* whether a shift
    was within it. Listing it twice would make a reader count two authorities
    where the policies hold one, so the top-level list is deduplicated by
    `rule_id` and the tags accumulate instead.

    `serves` is part of the seal: a citation moving from one track to both is a
    different account of what rested on what.
    """

    serves: list[CitationServes] = Field(
        default_factory=list,
        description=(
            "`information`, `verdict`, or both. A rule cited by both tracks appears once here "
            "with both tags; each track's own `citations` list still carries it separately."
        ),
    )


class InformationSection(BaseModel):
    """What the retained published policies state on the subject asked about.

    Null on the envelope when the question did not ask for it, and null when
    nothing was evaluated. Present otherwise — including when the answer is that
    no retained rule bears on the subject, which is a real answer and is not the
    same as not having asked.

    `answered` is redundant with `status` on purpose. A client that branches on a
    boolean is a client that cannot mis-spell an enum member, and the model
    enforces that the two agree rather than trusting a producer to keep them in
    step.
    """

    status: InformationStatus
    answered: bool = Field(
        description="True exactly when `status` is `answered`. Enforced, not merely intended."
    )
    answer: str = Field(
        default="",
        description=(
            "What the policies state, in the language the question was asked in. Non-empty "
            "exactly when `answered` is true."
        ),
    )
    explanation: str | None = Field(
        default=None,
        description=(
            "Prose the gather composed when it did *not* answer — why it stood back, or what it "
            "found instead. Null when the track answered, because the substance is then in "
            "`answer` and returning it twice would invite a client to render it twice."
        ),
    )
    route: str = Field(
        default=ROUTE_INFORMATIONAL,
        description="Which gather composed this. `informational` for this section.",
    )
    citations: list[CitationRef] = Field(
        default_factory=list,
        description="The rules this statement rests on, with each rule's verbatim source sentence.",
    )
    note: str = Field(
        default="",
        description=(
            "The gather's own one-sentence caveat, including its statement that some caller "
            "guidance was not followed."
        ),
    )
    grounding: dict[str, Any] | None = Field(
        default=None,
        description=(
            "This track's grounding report, including `fabricated_citations` — the citations the "
            "fabrication guard refused — and `selectors_out_of_catalogue`, the outstanding-fact "
            "names the closed selector vocabulary refused, under `selector_catalogue_version`. "
            "Per track, because the two tracks ground separately."
        ),
    )

    @model_validator(mode="after")
    def _answered_agrees_with_status(self) -> "InformationSection":
        if self.answered != (self.status == STATUS_WITH_VERDICT):
            raise ValueError(
                "information.answered must be true exactly when information.status is 'answered'"
            )
        if self.answered and not self.answer.strip():
            raise ValueError("an answered information section must carry a non-empty answer")
        if not self.answered and self.answer:
            raise ValueError("only an answered information section may carry an answer")
        return self


class MissingInformationItem(BaseModel):
    """One fact the case needs before a verdict can be reached.

    This is the field the redesign exists for. A caller whose case cannot be
    decided used to receive a status and a list of bare strings; what they need
    is something a form can be built from — what the fact is, what to call it in
    front of a user, why it decides anything, and which rules are waiting on it.

    `required_by_rule_ids` is checked against the closed set of rules the gather
    was shown, exactly as a citation is. A rule id here that named no retained
    rule would be a fabrication wearing a different field name.
    """

    fact: str = Field(description="The fact as the policy record names it.")
    label: str = Field(
        description=(
            "A short human label for the fact, in the language the question was asked in. Falls "
            "back to `fact` when the gather offered no separate label."
        )
    )
    why_needed: str = Field(
        default="",
        description=(
            "One sentence saying which judgement turns on this fact. Empty when the gather "
            "supplied only the flat list and no reason was composed — never filled in here."
        ),
    )
    required_by_rule_ids: list[str] = Field(
        default_factory=list,
        description=(
            "The `rule_id`s that need this fact, restricted to rules that were actually in front "
            "of the gather. Empty when the gather named none."
        ),
    )


class VerificationRequirementItem(BaseModel):
    """One condition to confirm before acting on a verdict that *was* reached.

    The counterpart to :class:`MissingInformationItem`, and the difference
    between them is the whole reason both exist. A missing fact is something the
    determination hangs on: until it arrives there is no verdict. A verification
    requirement hangs on nothing — the rules settled the question that was
    asked — but it must be confirmed before anyone acts on the answer. A balance
    that has to be checked, an approval that has to be sought, a window that has
    to be observed, a category somebody who holds the record has to confirm.

    Before this field existed those conditions had one place to go, and it was
    `missing_information`, which meant naming any of them converted an answered
    case into a blocked one. A caller who asked whether something was conferred
    received an audit of their position in place of the answer.

    The safeguards are those of a missing fact, unchanged, because a caller acts
    on both: `fact` is resolved against the vocabulary the retained records
    themselves declare, and `required_by_rule_ids` is filtered to rules that were
    actually in front of the gather. What differs is only the consequence of
    failing them — a check that cannot be expressed in the records' vocabulary is
    dropped and reported, and the verdict it qualified, grounded separately,
    stands.
    """

    fact: str = Field(
        description="The condition's key, as the policy record names the thing to be confirmed."
    )
    label: str = Field(
        description=(
            "A short human label for the condition. Falls back to `fact` when the gather offered "
            "no separate label."
        )
    )
    why_needed: str = Field(
        default="",
        description=(
            "One sentence saying what has to be confirmed and why, before the verdict is acted "
            "on. Empty when the gather composed none — never filled in here."
        ),
    )
    required_by_rule_ids: list[str] = Field(
        default_factory=list,
        description=(
            "The `rule_id`s that impose this condition, restricted to rules that were actually in "
            "front of the gather. Empty when the gather named none."
        ),
    )


class VerdictSection(BaseModel):
    """The determination, or the honest account of why there is not one.

    Null on the envelope when no verdict was asked for, and null when nothing was
    evaluated. Present otherwise, including for every non-answer state.

    THE INVARIANT

    `decision` is non-empty **iff** `reached` is true **iff** `status` is
    `answered`, and the model refuses any other combination. This is what stops
    the one failure mode that matters here: a "no", a "not compliant" or a
    "denied" is a *reached* verdict and belongs in `decision`; a case that could
    not be decided has an empty `decision`, and no client can read the second as
    the first.

    `verification_requirements` is deliberately outside that invariant. It
    qualifies a verdict without unmaking it, so a reached verdict may carry any
    number of them and remain a reached verdict. `missing_information` remains
    exclusive to a blocked one, and nothing may be in both.
    """

    status: VerdictStatus
    reached: bool = Field(
        description="True exactly when `status` is `answered`. Enforced, not merely intended."
    )
    decision: str = Field(
        default="",
        description=(
            "The verdict itself — for example `compliant`, `not compliant`, `allowed`, "
            "`not allowed`. Non-empty exactly when `reached` is true. A refusal is a verdict and "
            "appears here; a case that was not decided leaves this empty."
        ),
    )
    explanation: str = Field(
        default="",
        description=(
            "The reasoning behind the verdict, or — for a non-answer status — what stopped one "
            "being reached, in the language the question was asked in."
        ),
    )
    missing_information: list[MissingInformationItem] = Field(
        default_factory=list,
        description=(
            "Structured facts the case must supply before a verdict can be reached. Populated "
            "only when `status` is `missing_required_facts`."
        ),
    )
    missing_required_facts: list[str] = Field(
        default_factory=list,
        description=(
            "The same facts as a flat list of labels, preserved so an existing client keeps "
            "working. `missing_information` is the field to build against."
        ),
    )
    verification_requirements: list[VerificationRequirementItem] = Field(
        default_factory=list,
        description=(
            "Conditions to confirm before acting on a verdict that was reached — a balance, an "
            "approval, a window, a category held elsewhere. Additive: they qualify the verdict "
            "and never negate it, so they appear only when `status` is `answered`, and they are "
            "not missing facts. Defaults to empty, so a receipt stored before this field existed "
            "reads and replays unchanged."
        ),
    )
    route: str = Field(
        default=ROUTE_DECISION,
        description="Which gather composed this. `decision` for this section.",
    )
    citations: list[CitationRef] = Field(
        default_factory=list,
        description="The rules the verdict — or the non-answer — rests on, with verbatim sources.",
    )
    note: str = Field(default="", description="The gather's own one-sentence caveat.")
    grounding: dict[str, Any] | None = Field(
        default=None, description="This track's grounding report, including refused citations."
    )

    @model_validator(mode="after")
    def _reached_agrees_with_status_and_decision(self) -> "VerdictSection":
        if self.reached != (self.status == STATUS_WITH_VERDICT):
            raise ValueError(
                "verdict.reached must be true exactly when verdict.status is 'answered'"
            )
        if self.reached and not self.decision.strip():
            raise ValueError("a reached verdict must carry a non-empty decision")
        if not self.reached and self.decision:
            raise ValueError(
                "only a reached verdict may carry a decision; a non-answer must leave it empty "
                "so a refusal can never be produced by a case that was never decided"
            )
        if self.status != "missing_required_facts" and (
            self.missing_information or self.missing_required_facts
        ):
            raise ValueError(
                "missing information belongs only to a verdict blocked on missing_required_facts"
            )
        if self.verification_requirements and not self.reached:
            # Which, with the two rules above, is what makes the two lists
            # mutually exclusive as a matter of shape rather than of discipline:
            # missing information belongs only to `missing_required_facts`, which
            # is never `reached`, and these belong only to a verdict that is. So
            # no value can appear in both, and there is nothing further to check.
            raise ValueError(
                "verification requirements qualify a verdict that was reached; a case with no "
                "verdict has nothing to verify before acting on"
            )
        return self


class CaseDecisionEnvelopeV2(BaseModel):
    """The full receipt for one audited external project-case decision, `v2`.

    Field order is the reading order a client should follow: identity, who asked
    and under what, **what was asked for** (`asked`), **how each track came out**
    (`outcome`), then the two sections, then the evidence and the seal.
    """

    schema_version: Literal["case_decision_v2"] = Field(default="case_decision_v2")
    receipt_status: Literal["completed"] = Field(
        default=RECEIPT_COMPLETED,
        description=(
            "The stored row's lifecycle, distinct from either track's outcome. Only a `completed` "
            "receipt is ever served as a body; `pending` and `failed` are answered as errors, so "
            "this is `completed` by construction and is carried so a reader need not infer it."
        ),
    )
    decision_id: str
    correlation_id: str
    idempotency_key: str | None = None

    policy_set: PolicySetRef
    active_version: VersionRef | None = Field(
        default=None,
        description="The exact version the decider loaded, or null when the project has published nothing.",
    )

    caller: CallerRef
    request: RequestRef
    language: LanguageRef | None = Field(
        default=None,
        description=(
            "Which language each stage worked in, and the question as it was actually "
            "adjudicated. Null only on a receipt written before the language boundary existed."
        ),
    )

    asked: AskedRef = Field(description="What the classifier read the question as asking for.")
    outcome: OutcomeRef = Field(
        description="How each track came out. Read this before `information` or `verdict`."
    )

    information: InformationSection | None = Field(
        default=None,
        description=(
            "What the policies state. Null when `outcome.information` is `not_requested` or "
            "`not_evaluated`, and non-null for every other value."
        ),
    )
    verdict: VerdictSection | None = Field(
        default=None,
        description=(
            "The determination, or why there is not one. Null when `outcome.verdict` is "
            "`not_requested` or `not_evaluated`, and non-null for every other value."
        ),
    )

    retrieval: RetrievalRef
    considered: list[PolicyRef] = Field(default_factory=list)
    excluded: list[PolicyRef] = Field(default_factory=list)

    citations: list[MergedCitationRef] = Field(
        default_factory=list,
        description=(
            "Every rule either track rested on, deduplicated by `rule_id` and tagged with the "
            "track or tracks that cited it. Each section also carries its own citations."
        ),
    )
    size: SizeRef | None = None

    trace: TraceRef

    decision_hash: str
    hash_basis: str = Field(default=HASH_BASIS_V2)
    receipt_url: str
    decided_at: datetime
    latency_ms: int

    @model_validator(mode="after")
    def _sections_agree_with_outcome(self) -> "CaseDecisionEnvelopeV2":
        """A section and its outcome are two views of one fact, so they must agree.

        Without this the envelope could report `outcome.verdict: "answered"` and
        carry no verdict, which is precisely the class of contradiction the
        two-track shape was introduced to make impossible.
        """

        for track, section, outcome in (
            ("information", self.information, self.outcome.information),
            ("verdict", self.verdict, self.outcome.verdict),
        ):
            if section is None:
                if outcome not in (NOT_REQUESTED, NOT_EVALUATED):
                    raise ValueError(
                        f"outcome.{track} is {outcome!r} but the {track} section is null"
                    )
            else:
                if outcome in (NOT_REQUESTED, NOT_EVALUATED):
                    raise ValueError(
                        f"outcome.{track} is {outcome!r} but a {track} section was carried"
                    )
                if section.status != outcome:
                    raise ValueError(
                        f"outcome.{track} is {outcome!r} but {track}.status is {section.status!r}"
                    )
        return self


# ── reading a stored receipt back, whichever version wrote it ────────

#: The two envelopes as one type, discriminated on `schema_version`. A reader
#: does not branch on the version by hand: the tag decides, and an unknown tag
#: is a validation error rather than a shape silently coerced into the wrong one.
CaseDecisionReceipt = Annotated[
    CaseDecisionEnvelope | CaseDecisionEnvelopeV2,
    Field(discriminator="schema_version"),
]

_RECEIPT_ADAPTER: Final[TypeAdapter] = TypeAdapter(CaseDecisionReceipt)


def validate_receipt(payload: Any) -> CaseDecisionEnvelope | CaseDecisionEnvelopeV2:
    """Read a stored receipt back as whichever envelope wrote it.

    The stored `schema_version` decides, which is the whole reason it is stored.
    A row written before the field was ever absent does not exist — v1 always
    defaulted it — but a mapping that somehow lacks it is read as v1 rather than
    refused, because the only receipts that could be in that state predate v2.
    """

    if isinstance(payload, dict) and "schema_version" not in payload:
        payload = {**payload, "schema_version": SCHEMA_VERSION_V1}
    return _RECEIPT_ADAPTER.validate_python(payload)


# ── the seal ─────────────────────────────────────────────────────────

#: The exact preimage `decision_hash` is taken over, stated once so the rule can
#: be read rather than reverse-engineered from the builder below.
#:
#: INCLUDED — everything that defines *what was decided*: the project's routing
#: key, the published version number, the hash of the question, the hash of the
#: caller's presentation guidance, the scope, the retrieval status, which
#: policies were retained or discarded (by their stable provision keys), the
#: decision's status/verdict/explanation/facts/note/route, and each citation's
#: rule id, source state and verbatim text.
#:
#: The guidance is sealed by its digest rather than its text, exactly as the
#: scenario is. It cannot change what was decided — that is the whole of its
#: contract — but it is part of what the caller sent, and a receipt whose record
#: of the request could be edited without breaking the seal would be weaker
#: evidence than one whose could not.
#:
#: EXCLUDED, and why:
#:   * record identity — `decision_id`, `correlation_id`, `idempotency_key`.
#:     These name the *call*, not the decision; two receipts of the same decided
#:     content should seal identically.
#:   * database surrogate keys — the policy set's and version's UUIDs. They
#:     differ between environments while the decision does not.
#:   * `decided_at`, `received_at`, `latency_ms` — a slower call did not decide
#:     something different.
#:   * `receipt_url` — a routing detail, and it contains the decision id.
#:   * `decision_hash` itself.
DECISION_HASH_INCLUDES: Final[tuple[str, ...]] = (
    "schema_version",
    "policy_set_key",
    "version_number",
    "scenario_hash",
    "additional_instructions_hash",
    "scope",
    "retrieval_status",
    "policies",
    "decision",
    "citations",
)


def decision_hash_preimage(envelope: CaseDecisionEnvelope) -> dict[str, Any]:
    """The decision-defining subset of `envelope`, as the hash sees it.

    Returned rather than hashed directly so a test — and a caller who wants to
    verify a receipt independently — can inspect exactly what was sealed.
    """

    policies = sorted(
        (
            {
                "provision_key": ref.provision_key,
                "retained": bool(ref.retained),
                "discard_reason": ref.discard_reason,
            }
            for ref in envelope.considered
        ),
        key=lambda entry: str(entry["provision_key"]),
    )

    citations = [
        {
            "rule_id": citation.rule_id,
            "policy_provision_key": citation.policy.provision_key if citation.policy else None,
            "source_state": citation.source.state,
            "source_text": citation.source.text,
        }
        for citation in envelope.citations
    ]

    return {
        "schema_version": envelope.schema_version,
        "policy_set_key": envelope.policy_set.key,
        "version_number": envelope.active_version.version_number if envelope.active_version else None,
        "scenario_hash": envelope.request.scenario_hash,
        "additional_instructions_hash": envelope.request.additional_instructions_hash,
        "scope": envelope.request.scope,
        "retrieval_status": envelope.retrieval.status,
        "policies": policies,
        "decision": {
            "intent": envelope.decision.intent,
            "status": envelope.decision.status,
            "verdict": envelope.decision.verdict,
            "explanation": envelope.decision.explanation,
            "missing_required_facts": list(envelope.decision.missing_required_facts),
            "note": envelope.decision.note,
            "decider_route": envelope.decision.decider_route,
        },
        "citations": citations,
    }


def compute_decision_hash(envelope: CaseDecisionEnvelope) -> str:
    """The integrity seal over `envelope`'s decision-defining content."""

    return canonical_hash(decision_hash_preimage(envelope))


# ── the v2 seal ──────────────────────────────────────────────────────

#: The preimage `decision_hash` is taken over for `case_decision_v2`, named
#: separately so an already-written v1 hash keeps meaning exactly what it meant.
#:
#: INCLUDED — everything that defines *what was decided*, on both tracks: the
#: project's routing key, the published version number, the digests of the
#: question and of the caller's presentation guidance, the scope, the retrieval
#: status, which policies were retained or discarded, **the two asked booleans**,
#: both outcomes, both semantic sections in full (including the structured
#: missing information *and* the verification requirements), and every merged
#: citation with the tracks it served.
#:
#: The verification requirements are sealed for the same reason the missing facts
#: are: they qualify what the determination permits. A receipt that could gain or
#: lose a condition on acting without moving its hash would be weaker evidence
#: than one that could not. They live inside the `verdict` entry, so the sealed
#: top-level field set below is unchanged, and the entry itself is written only
#: when there are checks to seal — so a receipt written before the field existed,
#: which reads back with an empty list, still produces the preimage it was sealed
#: under and verifies against its stored hash.
#:
#: The booleans are sealed because they decide what the receipt answers: a
#: receipt that could be re-labelled "you only asked for information" after the
#: fact would let a missing verdict be explained away.
#:
#: EXCLUDED, and why — everything v1 excluded (record identity, surrogate keys,
#: timestamps, latency, `receipt_url`, the hash itself), plus one more:
#:   * `asked.classification_reasoning` and `asked.classifier_version`. The
#:     reasoning is prose *about* a routing choice, not part of the decision;
#:     sealing it would move the hash when a classifier reworded itself, which is
#:     a change no auditor could act on and would obscure ones they could.
DECISION_HASH_V2_INCLUDES: Final[tuple[str, ...]] = (
    "schema_version",
    "policy_set_key",
    "version_number",
    "scenario_hash",
    "additional_instructions_hash",
    "scope",
    "retrieval_status",
    "policies",
    "asked",
    "outcome",
    "information",
    "verdict",
    "citations",
)


def _sealed_citations(citations: list[CitationRef]) -> list[dict[str, Any]]:
    """A track's citations as the seal sees them: identity, source, nothing else."""

    return [
        {
            "rule_id": citation.rule_id,
            "policy_provision_key": citation.policy.provision_key if citation.policy else None,
            "source_state": citation.source.state,
            "source_text": citation.source.text,
        }
        for citation in citations
    ]


def decision_hash_preimage_v2(envelope: CaseDecisionEnvelopeV2) -> dict[str, Any]:
    """The decision-defining subset of a v2 receipt, as the hash sees it.

    Returned rather than hashed directly so a test — and a caller verifying a
    receipt independently — can inspect exactly what was sealed.
    """

    policies = sorted(
        (
            {
                "provision_key": ref.provision_key,
                "retained": bool(ref.retained),
                "discard_reason": ref.discard_reason,
                # Which rules of the policy were read is part of what was
                # decided: the same policy read whole and read as a slice of
                # eight rows are two different accounts of the same question.
                # `method` and the counts are derivable from the ids, so the ids
                # alone are sealed.
                "selected_rule_ids": (
                    sorted(ref.rule_selection.selected_rule_ids)
                    if ref.rule_selection is not None
                    else None
                ),
                "total_rules": (
                    ref.rule_selection.total_rules if ref.rule_selection is not None else None
                ),
            }
            for ref in envelope.considered
        ),
        key=lambda entry: str(entry["provision_key"]),
    )

    information = (
        None
        if envelope.information is None
        else {
            "status": envelope.information.status,
            "answered": envelope.information.answered,
            "answer": envelope.information.answer,
            "explanation": envelope.information.explanation,
            "route": envelope.information.route,
            "note": envelope.information.note,
            "citations": _sealed_citations(envelope.information.citations),
        }
    )

    verdict = (
        None
        if envelope.verdict is None
        else {
            "status": envelope.verdict.status,
            "reached": envelope.verdict.reached,
            "decision": envelope.verdict.decision,
            "explanation": envelope.verdict.explanation,
            "missing_information": [
                {
                    "fact": item.fact,
                    "label": item.label,
                    "why_needed": item.why_needed,
                    "required_by_rule_ids": list(item.required_by_rule_ids),
                }
                for item in envelope.verdict.missing_information
            ],
            "missing_required_facts": list(envelope.verdict.missing_required_facts),
            "route": envelope.verdict.route,
            "note": envelope.verdict.note,
            "citations": _sealed_citations(envelope.verdict.citations),
        }
    )
    if verdict is not None and envelope.verdict.verification_requirements:
        # Sealed because they materially qualify what the verdict permits. A
        # receipt whose determination could gain or lose "confirm the balance
        # first" without moving its hash would let the conditions on acting be
        # rewritten after the fact, which is exactly the class of silent change
        # the seal exists to catch.
        #
        # The key is written only when there is something to seal, so a receipt
        # stored before the field existed — and any receipt that carries no
        # checks, which is the same decision — produces the identical preimage it
        # always did and still verifies against the hash it was written with.
        verdict["verification_requirements"] = [
            {
                "fact": item.fact,
                "label": item.label,
                "why_needed": item.why_needed,
                "required_by_rule_ids": list(item.required_by_rule_ids),
            }
            for item in envelope.verdict.verification_requirements
        ]

    citations = [
        {
            "rule_id": citation.rule_id,
            "policy_provision_key": citation.policy.provision_key if citation.policy else None,
            "source_state": citation.source.state,
            "source_text": citation.source.text,
            # Sorted so the tag set is what is sealed, not the order two tracks
            # happened to be merged in.
            "serves": sorted(citation.serves),
        }
        for citation in envelope.citations
    ]

    return {
        "schema_version": envelope.schema_version,
        "policy_set_key": envelope.policy_set.key,
        "version_number": envelope.active_version.version_number if envelope.active_version else None,
        "scenario_hash": envelope.request.scenario_hash,
        "additional_instructions_hash": envelope.request.additional_instructions_hash,
        "scope": envelope.request.scope,
        "retrieval_status": envelope.retrieval.status,
        "policies": policies,
        "asked": {
            "information_requested": envelope.asked.information_requested,
            "verdict_requested": envelope.asked.verdict_requested,
        },
        "outcome": {
            "information": envelope.outcome.information,
            "verdict": envelope.outcome.verdict,
        },
        "information": information,
        "verdict": verdict,
        "citations": citations,
    }


def compute_decision_hash_v2(envelope: CaseDecisionEnvelopeV2) -> str:
    """The integrity seal over a v2 receipt's decision-defining content.

    Dispatches on the receipt's own `hash_basis`, which is why that field is
    stored beside the hash rather than assumed. A receipt written under
    `case_decision_v2` is sealed by exactly the rule it was written with, and a
    receipt written under the language boundary is sealed by the wider one — so
    introducing the boundary neither migrates a stored receipt nor changes what
    an already-written hash claims.
    """

    if envelope.hash_basis in {
        HASH_BASIS_V2_LANG,
        HASH_BASIS_V2_LANG_WITH_VERIFICATION,
    }:
        return canonical_hash(decision_hash_preimage_v2_lang(envelope))
    if envelope.hash_basis in {
        HASH_BASIS_V2,
        HASH_BASIS_V2_WITH_VERIFICATION,
    }:
        return canonical_hash(decision_hash_preimage_v2(envelope))
    raise ValueError(f"unsupported case-decision hash basis {envelope.hash_basis!r}")


# ── the v2 seal, under the language boundary ─────────────────────────

#: What `case_decision_v2_lang` seals over and above `case_decision_v2`.
#:
#: INCLUDED — everything the v2 basis seals, plus the two facts the boundary
#: introduces:
#:   * `processing_scenario_hash`. The rendered question is what retrieval,
#:     classification and both gathers actually read. A seal that covered only
#:     the caller's bytes would leave the decision-determining intermediate free
#:     to change on a stored receipt without breaking anything.
#:   * `language`. The profiles a rendering was made under, and the languages
#:     each side of the boundary worked in. Two profiles can reduce one question
#:     to two different English texts, so a receipt that could be re-labelled
#:     with a different profile after the fact would be weaker evidence than one
#:     that could not. The prose the reader was given is already sealed by the
#:     `information` and `verdict` sections, which carry the *rendered* strings —
#:     the rendering happens before the envelope is built, so what is sealed is
#:     what was served.
#:
#: EXCLUDED — everything the v2 basis excludes, plus `processing_scenario` in
#: full: it is sealed by its digest for exactly the reason the caller's scenario
#: is, and sealing both the text and its hash would be sealing one fact twice.
DECISION_HASH_V2_LANG_INCLUDES: Final[tuple[str, ...]] = DECISION_HASH_V2_INCLUDES + (
    "processing_scenario_hash",
    "language",
)


def decision_hash_preimage_v2_lang(envelope: CaseDecisionEnvelopeV2) -> dict[str, Any]:
    """The v2 preimage, widened by what the language boundary decided.

    Built from :func:`decision_hash_preimage_v2` rather than beside it, so the
    two bases can never disagree about the part they share.

    A receipt claiming this basis without a `language` block is malformed rather
    than tolerated: the basis names a rule, and a rule that silently degraded to
    the narrower one would let a receipt claim a seal it does not have.
    """

    if envelope.language is None:
        raise ValueError(
            f"a receipt sealed under {envelope.hash_basis} must carry its language block"
        )

    language = envelope.language
    preimage = decision_hash_preimage_v2(envelope)
    preimage["processing_scenario_hash"] = language.processing_scenario_hash
    preimage["language"] = {
        "source_language": language.source_language,
        "processing_language": language.processing_language,
        "response_language": language.response_language,
        "boundary_state": language.boundary_state,
        "output_rendering_state": language.output_rendering_state,
        "guidance_rendering_state": language.guidance_rendering_state,
        "input_translation_profile": language.input_translation_profile,
        "output_translation_profile": language.output_translation_profile,
        "projection_profile": language.projection_profile,
    }
    return preimage


def scenario_hash(scenario: str) -> str:
    """A stable digest of the question alone.

    Separate from `decision_hash` and from the idempotency request hash: this
    one exists so repeated questions can be correlated in the log without the
    prose being read, which is the whole point of not logging it.
    """

    return canonical_hash({"scenario": scenario})


def request_hash(
    *,
    policy_set_key: str,
    scenario: str,
    provision_id: str | None,
    reasoning_effort: str,
    additional_instructions: str = "",
) -> str:
    """The canonical hash of the request an idempotency key is bound to.

    The correlation id is deliberately **not** part of it. A caller retrying the
    same request under a new correlation id is retrying the same request, and
    must be replayed the original receipt rather than told its body changed.

    The caller's guidance **is** part of it. It changes the answer the caller
    receives, so replaying an earlier receipt against changed guidance would
    hand back an explanation shaped by instructions that are no longer the
    caller's — a silent substitution, and precisely the kind an idempotency key
    is supposed to make impossible. `additional_instructions` must be the
    normalised form; see `normalise_additional_instructions` for why comparing
    the raw text would break a byte-for-byte retry.
    """

    return canonical_hash(
        {
            "policy_set_key": policy_set_key,
            "scenario": scenario,
            "provision_id": provision_id or None,
            "reasoning_effort": reasoning_effort,
            "additional_instructions": additional_instructions,
        }
    )
