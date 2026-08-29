"""`case_decision_v1` — the audited receipt an external caller is answered with.

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

2. **It never presents a non-answer as a verdict.** `decision_status` sits at the
   top level, above `decision`, precisely so a client reads the status first. A
   retrieval that found nothing, a model that declined, a gather that failed and
   a real determination are four different things, and only one of them has a
   verdict. `verdict` is empty for the other three.

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
from typing import Any, Final, Literal

from pydantic import BaseModel, Field

from policy_platform.contracts.canonical import canonical_hash

#: The name of this envelope. Carried in every response so a consumer can pin it
#: and reject a shape it was not written against.
SCHEMA_VERSION: Final[str] = "case_decision_v1"

#: What `decision_hash` means. Stored beside the hash rather than assumed, so a
#: future preimage rule can be introduced without silently changing what an
#: already-written hash claims.
HASH_BASIS: Final[str] = "case_decision_v1"

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
    reason: str | None = None
    payload_url: str | None = Field(
        default=None,
        description="Where the policy's full lean record is served. The record itself is never inlined.",
    )


class RetrievalRef(BaseModel):
    """What narrowing happened, in the decider's own vocabulary.

    Mirrors the retrieval block the decider reports, so the receipt and the
    in-product answer describe one event rather than two.
    """

    status: str
    method: str | None = None
    policy_budget: int | None = None
    policy_scan: int | None = None
    policies_retrieved: int | None = None
    policies_considered: int | None = None
    policies_retained: int | None = None
    policies_discarded: int | None = None
    policies_untestable: int | None = None
    reason: str | None = None


# ── the decision itself ──────────────────────────────────────────────


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


class SizeRef(BaseModel):
    """How large the evaluated record was against the one-gather budget."""

    combined_chars: int | None = None
    budget_chars: int | None = None
    oversize: bool | None = None


# ── the envelope ─────────────────────────────────────────────────────


class CaseDecisionEnvelope(BaseModel):
    """The full receipt for one audited external project-case decision."""

    schema_version: str = Field(default=SCHEMA_VERSION)
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
            "the fabrication guard refused. This is the quality signal the case service provides; "
            "no other is invented here."
        ),
    )
    size: SizeRef | None = None

    trace: TraceRef

    decision_hash: str
    hash_basis: str = Field(default=HASH_BASIS)
    receipt_url: str
    decided_at: datetime
    latency_ms: int


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
