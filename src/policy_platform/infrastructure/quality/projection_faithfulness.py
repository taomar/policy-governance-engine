"""Whether a retrieval projection is a projection *of the record it claims*.

WHY THIS EXISTS

`search/english_projection` checks one rendering against one source: it is
non-empty, it is plausibly the same size, and every number and identifier
survived. Those are the checks a *transport* can make, and they are real — but
they are all satisfied by a rendering that carried the digits of one record and
the meaning of another. A schedule row rendered as its neighbour keeps every
number in the batch. A reply that returned the values under shifted keys keeps
all of them. A rendering that dropped the operative clause and kept the
boilerplate keeps the codes.

So a successful rendering, a successful embedding and a successful upload
together prove **transport**, and transport is not fidelity. Until this module
existed, transport was the whole basis on which a corpus became a load-bearing
`ready` index — and every downstream refusal reads that one bit. This module is
the second question, asked before the first bit is allowed to mean anything:

    Is what the index holds a rendering of the record the database holds?

WHAT IT ASKS, IN TWO KINDS

  * **Deterministic, over the whole build.** Not one document at a time — the
    failures that matter here are failures of a *set*. Every expected document
    is present exactly once and nothing else is; every rule document's parent is
    present; every document names the version and the contract it was built
    under; no document carries the authoritative record; and rule documents
    exist for exactly the provisions that are large enough to have them. Each is
    a fact about a set, and none of them is visible from inside a single
    document, which is why the renderer cannot ask them.
  * **Semantic, per aligned pair.** The authoritative retrieval text and the
    projection built from it are embedded with the **same multilingual
    embedding deployment the corpus is retrieved with**, and each pair is
    compared by cosine. Deliberately not a prose judge: asking a generative
    model whether its own rendering is faithful is asking the thing that made
    the claim to certify it, and it returns prose that has to be parsed, in a
    call that costs a token budget per document. An embedding comparison is a
    number, from the model that already decides what matches what.

WHAT THE SEMANTIC CHECK CAN AND CANNOT SEE — READ THIS BEFORE TRUSTING IT

A cosine over a multilingual embedding separates *aboutness*. It catches a
projection that is a rendering of a different record, one that lost most of its
content, one that was written under a different subject, and outputs that were
swapped between two records. Those are the failure shapes a batch-oriented
rendering pipeline actually produces.

It does **not** separate a statement from its negation. A sentence and its
inversion are near neighbours in every embedding space published, and a floor
low enough to admit a faithful cross-language rendering is far below the
similarity an inversion keeps. Claiming otherwise would be the more comfortable
sentence to write and it would be false, so it is written here instead: **the
semantic floor is a gross-mismatch gate, not a meaning-preservation proof.**
What guards the operative content is the layer below — every number and every
identifier is checked deterministically, and those are what a governance record
is decided by.

WHAT IT REFUSES TO DO

  * **It never repairs.** A projection that fails is marked failed; it is not
    re-rendered here and it is not edited. Deciding what a record should have
    said is the one thing no part of this pipeline may do.
  * **It never carries text.** Not the source, not the projection, not in a
    finding, not in a log, not in the report the API serves. A finding is a code
    this module declared and a document key. :class:`QualityFinding` is what
    makes that a property of the type rather than a rule someone has to keep.
  * **It never passes on missing evidence.** An embedding that did not arrive,
    a batch that came back the wrong length, a vector of the wrong width, an
    unconfigured deployment — every one of them is
    :data:`QUALITY_UNAVAILABLE`, and the readiness gate treats that exactly as
    it treats a failure. A check that cannot be made has not been passed.
"""
from __future__ import annotations

import logging
import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final, Literal

from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.projection.policy_rule_slice import (
    LARGE_POLICY_RULE_THRESHOLD,
)
from policy_platform.infrastructure.search.english_projection import preservation_failure

logger = logging.getLogger(__name__)

__all__ = [
    "FINDING_AUTHORITATIVE_RECORD_EMBEDDED",
    "FINDING_DOCUMENT_MISSING",
    "FINDING_DOCUMENT_REPEATED",
    "FINDING_DOCUMENT_UNEXPECTED",
    "FINDING_EMBEDDING_COUNT_MISMATCH",
    "FINDING_EMBEDDING_SHAPE_MISMATCH",
    "FINDING_EMBEDDING_UNAVAILABLE",
    "FINDING_PARENT_LINK_MISSING",
    "FINDING_PRESERVATION_FAILED",
    "FINDING_PROFILE_MISMATCH",
    "FINDING_PROJECTED_TEXT_EMPTY",
    "FINDING_RULE_DOCUMENTS_MISSING",
    "FINDING_RULE_DOCUMENTS_UNEXPECTED",
    "FINDING_SIMILARITY_BELOW_FLOOR",
    "FINDING_VERSION_MISMATCH",
    "PROJECTION_QUALITY_PROFILE",
    "ProjectedRecord",
    "ProjectionQualityProfile",
    "ProjectionQualityReport",
    "QUALITY_FAILED",
    "QUALITY_PASSED",
    "QUALITY_UNAVAILABLE",
    "QualityFinding",
    "known_quality_profile",
    "quality_profile",
    "structural_findings",
    "unvalidated_report",
    "validate_projection",
]


# ── the state a corpus's projection is in ────────────────────────────

#: Every check ran and every check held. The **only** value that may open the
#: readiness gate.
QUALITY_PASSED: Final[str] = "passed"
#: A check ran and did not hold. The corpus stays in the index — nothing here
#: deletes anything — and stays unreachable.
QUALITY_FAILED: Final[str] = "failed"
#: A check could not be made: no embedding deployment, a service that refused, a
#: reply that could not be aligned. Not a pass. A validation nobody could
#: perform is exactly as much evidence as a validation that failed, and the gate
#: treats the two identically on purpose — the alternative is a corpus becoming
#: load-bearing because a check was unavailable the moment it was asked.
QUALITY_UNAVAILABLE: Final[str] = "unavailable"

QualityState = Literal["passed", "failed", "unavailable"]


# ── what a finding may say ───────────────────────────────────────────

#: A document the build expected and the index does not hold.
FINDING_DOCUMENT_MISSING: Final[str] = "document_missing"
#: A document the index holds under this project that the build did not expect.
#: A superseded version's leftovers, or a sweep that did not run.
FINDING_DOCUMENT_UNEXPECTED: Final[str] = "document_unexpected"
#: One key, twice. A set that reaches its expected size by repetition is short
#: by exactly as many documents as it repeated.
FINDING_DOCUMENT_REPEATED: Final[str] = "document_repeated"
#: A rule document whose parent provision's own document is not in the set. It
#: would surface and be unattributable.
FINDING_PARENT_LINK_MISSING: Final[str] = "parent_link_missing"
#: A document built for a version other than the one this build is for.
FINDING_VERSION_MISMATCH: Final[str] = "version_mismatch"
#: A document carrying a rendering contract other than the expected one. It
#: would be filtered out of every query and silently reduce the corpus.
FINDING_PROFILE_MISMATCH: Final[str] = "profile_mismatch"
#: A document carrying a nested structure. The index holds identifiers, counts,
#: headings, retrieval text and a vector; a mapping, or a sequence of mappings,
#: is the shape of the authoritative record itself, and the index may not become
#: a second copy of what a citation resolves to.
FINDING_AUTHORITATIVE_RECORD_EMBEDDED: Final[str] = "authoritative_record_embedded"
#: A provision small enough to read as one statement, carrying per-rule
#: documents anyway.
FINDING_RULE_DOCUMENTS_UNEXPECTED: Final[str] = "rule_documents_unexpected"
#: A provision past the threshold whose rows got no documents of their own, so a
#: row past its provision's retrieval-text ceiling cannot surface at all.
FINDING_RULE_DOCUMENTS_MISSING: Final[str] = "rule_documents_missing"
#: A document indexed with no retrieval text. It can never match anything, and
#: it is counted in a corpus that reports itself complete.
FINDING_PROJECTED_TEXT_EMPTY: Final[str] = "projected_text_empty"
#: The deterministic checks the renderer applies, re-applied to what the index
#: actually holds rather than to what a call returned. The two are different
#: facts: one is what came back, this is what landed.
FINDING_PRESERVATION_FAILED: Final[str] = "preservation_check_failed"
#: This projection is not close enough to its source to be a rendering of it.
FINDING_SIMILARITY_BELOW_FLOOR: Final[str] = "similarity_below_floor"
#: The embedding call returned a number of vectors that cannot be aligned with
#: the texts it was given, so no pair can be attributed. Fails closed.
FINDING_EMBEDDING_COUNT_MISMATCH: Final[str] = "embedding_count_mismatch"
#: Two vectors that cannot be compared — different widths, or one with no
#: magnitude. A cosine over them is not a low score, it is not a score.
FINDING_EMBEDDING_SHAPE_MISMATCH: Final[str] = "embedding_shape_mismatch"
#: No embedding could be obtained at all.
FINDING_EMBEDDING_UNAVAILABLE: Final[str] = "embedding_unavailable"

#: The most findings one report carries outward. The **counts** are always
#: exact; this bounds only the itemised list, so a wholly broken build produces
#: a report a person can read and an API can serve rather than one document per
#: row of a schedule.
_MAX_REPORTED_FINDINGS: Final[int] = 50


@dataclass(frozen=True, slots=True)
class QualityFinding:
    """One thing that was wrong, in a shape that cannot hold prose.

    Two fields, and neither can carry a sentence: a code this module declared,
    and the key of the document it concerns. A document key is a digest of
    identifiers this platform generated — it is not text anyone wrote and it
    names no content — so it is safe to report and it is the one thing an
    operator needs in order to look the document up.

    Deliberately not a message. A message is where the source text would end up
    the first time somebody wanted a finding to be more helpful.
    """

    code: str
    document_id: str | None = None

    def __str__(self) -> str:
        return f"{self.code}@{self.document_id}" if self.document_id else self.code


# ── the profile: what "close enough" means, and which version of it ──


@dataclass(frozen=True, slots=True)
class ProjectionQualityProfile:
    """A named, versioned statement of what this gate requires.

    It is a *profile* and not a constant for the same reason the rendering
    contract is: the number below decides whether a corpus is usable, so a
    change to it changes what "validated" means, and a corpus validated under
    one statement of it must not silently satisfy another. The name travels onto
    the manifest and into the record, and the gate compares names — so raising
    or lowering the floor invalidates prior validations rather than
    retroactively reinterpreting them.

    ABOUT `minimum_pair_similarity`

    It is chosen from the shape of the space, not fitted to any corpus, and the
    three bands it sits between are properties of multilingual sentence
    embeddings generally:

      * a passage and a faithful rendering of it into another language sit high,
        and stay high across scripts — that is what "multilingual" means and it
        is why the same deployment is used here as for retrieval;
      * a passage and an unrelated passage *from the same document* sit far
        lower, because shared boilerplate and shared subject matter do not carry
        a pair anywhere near a rendering pair; and
      * between them is a wide, empty gap, which is the only reason a single
        number can work at all.

    The floor is placed low in that gap rather than in the middle. This gate can
    block a corpus, and a corpus wrongly blocked is an outage; a floor that
    admits a marginal-but-genuine rendering and refuses a substitution is the
    error direction to prefer, because the substitutions this exists to catch —
    a swapped output, a dropped record, a rendering of the wrong row — do not
    land in the gap at all, they land in the unrelated band.

    It is emphatically **not** tuned against any corpus this platform has been
    run on. Nothing here was fitted, and the tests that hold it are synthetic
    and unrelated to one another by construction.

    MEASURED, AND THE THIRD BAND ABOVE IS INCOMPLETE
    *(2026-08-30, 27 synthetic pairs drawn from several unrelated domains;
    reproduce with `scripts/measure_projection_floor.py`)*

    The three bands above were reasoned from the shape of the space rather than
    measured. Measured, two of them hold and a **fourth band exists that this
    argument did not consider**:

    | Band | Observed |
    |---|---|
    | faithful rendering | 0.7120 – 0.8437 |
    | unrelated record, same document | 0.2535 – 0.4759 |
    | unrelated domain | 0.1835 – 0.2423 |
    | **sibling record: same subject, same sentence shape, different rule** | **0.5808 – 0.8371** |

    The fourth band **overlaps the first by 0.1251**: a rendering of a sibling
    record reached 0.8371, higher than the weakest genuine rendering at 0.7120.
    Sibling records are alike by construction — they share subject, register and
    sentence shape, and differ only in the identifiers, quantities and
    comparators that carry their meaning. Similarity is computed over what they
    share, which is nearly all of it.

    **Consequence, stated plainly: no single cosine threshold separates a
    faithful rendering from a sibling-record substitution.** The floor is
    therefore not raised, and raising it is not the repair: any value above the
    sibling band sits above genuine renderings and converts a silent admission
    into a guaranteed outage.

    **What this gate does and does not catch, corrected.** It remains decisive
    against gross substitution — a dropped record, a swapped output, a rendering
    of an unrelated record, an empty or wrong-profile document — all of which
    sit below 0.48, comfortably clear of the floor. It is **blind to the
    fine-grained case**: a rendering of a sibling record. That is exactly the
    defect AD-7.11 warns is invisible to citation-integrity checks, and it is
    worst in precisely the records this gate matters most for — any schedule of
    many similar rows, where every row is a sibling of its neighbours.

    Closing it needs a different mechanism, not a different number: per-record
    alignment on the identifiers, quantities and comparators the records differ
    *by*, rather than similarity over what they hold in common. That is a design
    decision and is deliberately not taken here.
    """

    name: str
    #: A pair below this is not a rendering of its source. Any one pair failing
    #: fails the corpus: a mean would let a schedule of good rows carry a row
    #: that is about something else entirely, and that row is precisely the one
    #: a question about it would retrieve.
    minimum_pair_similarity: float
    #: How many texts one embedding call carries, and how much text. Both bound
    #: the call rather than being derived from the corpus, for the same reason
    #: the rendering budgets are: a call the deployment refuses costs the whole
    #: validation, and sending less never does.
    embedding_batch_items: int = 32
    embedding_batch_chars: int = 60_000
    #: The most of one text that is compared. A single vector over a very long
    #: passage represents less of it the longer it gets, so a ceiling here is a
    #: bound on what the comparison can mean — and both sides are cut to the
    #: same *fraction* of themselves rather than to the same character count, so
    #: a language that renders longer or shorter than its source is still
    #: compared like for like.
    compare_chars: int = 8_000


#: The profile in force. `v1` is the first statement of this gate.
#:
#: Versioned separately from the rendering contract, and it has to be: they
#: answer different questions and change for different reasons. The rendering
#: contract moves when the *text in the index* would change; this moves when
#: what counts as *acceptable* changes. A corpus rendered under one contract can
#: be validated, re-validated under a stricter statement of quality, and fail —
#: without a single document changing. Collapsing them into one name would make
#: that impossible to express, and would force a full re-render of every corpus
#: to restate a threshold.
PROJECTION_QUALITY_PROFILE: Final[str] = "policy-projection-quality-v1"

_PROFILES: Final[dict[str, ProjectionQualityProfile]] = {
    PROJECTION_QUALITY_PROFILE: ProjectionQualityProfile(
        name=PROJECTION_QUALITY_PROFILE,
        minimum_pair_similarity=0.60,
    ),
}


def known_quality_profile(name: str | None) -> bool:
    """Whether this name is a profile this build can actually apply."""

    return name in _PROFILES


def quality_profile(name: str | None = None) -> ProjectionQualityProfile:
    """The named profile, or the one in force.

    A name this build does not carry is refused rather than defaulted. Falling
    back would mean validating under one statement of quality while recording
    another, which is the one way this whole mechanism could lie.
    """

    resolved = name or PROJECTION_QUALITY_PROFILE
    profile = _PROFILES.get(resolved)
    if profile is None:
        raise ValueError(f"no such projection quality profile: {resolved!r}")
    return profile


# ── what the caller has to hand over ─────────────────────────────────


@dataclass(frozen=True, slots=True)
class ProjectedRecord:
    """One document the build expected, and the authoritative text behind it.

    This is the alignment, and it is the caller's to state because only the
    caller knows it: the index holds a rendering with no pointer back to what it
    was rendered from, and re-deriving that association from what is in the
    index would be trusting the thing under test to describe itself.

    `source_text` is the authoritative retrieval text — what PostgreSQL holds,
    cut exactly as the builder cut it before rendering, so the comparison is
    between the two things that were actually meant to correspond and not
    between a whole record and a truncated rendering of it.
    """

    document_id: str
    policy_version_id: str
    source_text: str
    #: The policy document this one hangs from, or None when this *is* the
    #: policy document. It is how a rule document is told from a provision's own
    #: without this module knowing what either is called.
    parent_document_id: str | None = None
    #: How many rules the provision holds. Read only against the threshold, so
    #: the one question asked of it is a size question.
    provision_rule_count: int = 0


@dataclass(frozen=True, slots=True)
class ProjectionQualityReport:
    """Everything a validation may say, and nothing it may not.

    Counts, scores, profile names and document keys. No text, in any field, on
    any path — which is a property of the fields that exist rather than of what
    each caller remembers not to put in them.
    """

    state: QualityState
    profile: str
    checked_documents: int
    structural_findings: int
    below_floor: int
    minimum_similarity: float | None
    mean_similarity: float | None
    validated_at: str
    findings: tuple[QualityFinding, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        return self.state == QUALITY_PASSED

    def as_payload(self) -> dict:
        """The report as an API/manifest payload. Still no text."""

        return {
            "state": self.state,
            "profile": self.profile,
            "checked_documents": self.checked_documents,
            "structural_findings": self.structural_findings,
            "below_floor": self.below_floor,
            "minimum_similarity": self.minimum_similarity,
            "mean_similarity": self.mean_similarity,
            "validated_at": self.validated_at,
            "findings": [
                {"code": finding.code, "document_id": finding.document_id}
                for finding in self.findings
            ],
        }


def unvalidated_report(
    *, profile: str | None = None, validated_at: datetime | None = None, code: str
) -> ProjectionQualityReport:
    """A report for a validation that could not be made at all.

    Used where the check never started — no embedding deployment, no documents
    to read — so that "we did not check" is a recorded state with a reason code
    rather than an absent field a reader has to interpret.
    """

    return ProjectionQualityReport(
        state=QUALITY_UNAVAILABLE,
        profile=profile or PROJECTION_QUALITY_PROFILE,
        checked_documents=0,
        structural_findings=0,
        below_floor=0,
        minimum_similarity=None,
        mean_similarity=None,
        validated_at=_timestamp(validated_at),
        findings=(QualityFinding(code=code),),
    )


# ── the deterministic half ───────────────────────────────────────────


def structural_findings(
    *,
    records: Sequence[ProjectedRecord],
    documents: Sequence[Mapping[str, object]],
    expected_profile: str,
    ignore_document_ids: Collection[str] = (),
    rule_threshold: int = LARGE_POLICY_RULE_THRESHOLD,
) -> list[QualityFinding]:
    """Every deterministic thing wrong with this build, as a set.

    Asked over the whole corpus because that is the only place the answers live.
    A document that is present twice, a rule document whose parent never
    uploaded, a leftover from the version this build replaces — each of those is
    individually a perfectly well-formed document, and each of them makes the
    corpus something other than what the manifest is about to claim.

    ``ignore_document_ids`` is how the manifest is excluded: it is not content,
    it is the statement *about* the content, and counting it would make every
    corpus one document larger than itself.
    """

    findings: list[QualityFinding] = []
    ignored = set(ignore_document_ids)

    expected_by_id: dict[str, ProjectedRecord] = {}
    for record in records:
        if record.document_id in expected_by_id:
            findings.append(
                QualityFinding(
                    code=FINDING_DOCUMENT_REPEATED, document_id=record.document_id
                )
            )
            continue
        expected_by_id[record.document_id] = record

    seen: dict[str, Mapping[str, object]] = {}
    for document in documents:
        key = _text(document.get("id"))
        if not key or key in ignored:
            continue
        if key in seen:
            findings.append(
                QualityFinding(code=FINDING_DOCUMENT_REPEATED, document_id=key)
            )
            continue
        seen[key] = document
        if key not in expected_by_id:
            findings.append(
                QualityFinding(code=FINDING_DOCUMENT_UNEXPECTED, document_id=key)
            )

    for key in expected_by_id:
        if key not in seen:
            findings.append(
                QualityFinding(code=FINDING_DOCUMENT_MISSING, document_id=key)
            )

    for key, record in expected_by_id.items():
        document = seen.get(key)
        if document is None:
            continue
        findings.extend(
            _document_findings(
                record=record,
                document=document,
                expected_profile=expected_profile,
                present=seen,
            )
        )

    findings.extend(_rule_coverage_findings(expected_by_id, rule_threshold=rule_threshold))
    return findings


def _document_findings(
    *,
    record: ProjectedRecord,
    document: Mapping[str, object],
    expected_profile: str,
    present: Mapping[str, Mapping[str, object]],
) -> list[QualityFinding]:
    """The checks one document answers on its own, once the set is known."""

    findings: list[QualityFinding] = []
    key = record.document_id

    if _text(document.get("policy_version_id")) != record.policy_version_id:
        findings.append(QualityFinding(code=FINDING_VERSION_MISMATCH, document_id=key))

    if _text(document.get("projection_profile")) != expected_profile:
        findings.append(QualityFinding(code=FINDING_PROFILE_MISMATCH, document_id=key))

    parent = _text(document.get("parent_document_id")) or None
    if record.parent_document_id != parent or (
        parent is not None and parent not in present
    ):
        findings.append(QualityFinding(code=FINDING_PARENT_LINK_MISSING, document_id=key))

    if _carries_a_record(document):
        findings.append(
            QualityFinding(code=FINDING_AUTHORITATIVE_RECORD_EMBEDDED, document_id=key)
        )

    projected = _text(document.get("retrieval_text"))
    if not projected.strip():
        findings.append(
            QualityFinding(code=FINDING_PROJECTED_TEXT_EMPTY, document_id=key)
        )
    elif preservation_failure(record.source_text, projected) is not None:
        # The reason is deliberately dropped rather than carried. It names which
        # check failed and never quotes the text, but it is prose, and a field
        # that can hold prose is a field that will hold a policy sentence the
        # first time somebody makes a finding more helpful.
        findings.append(
            QualityFinding(code=FINDING_PRESERVATION_FAILED, document_id=key)
        )

    return findings


def _rule_coverage_findings(
    expected_by_id: Mapping[str, ProjectedRecord], *, rule_threshold: int
) -> list[QualityFinding]:
    """Rule documents exist for exactly the provisions large enough to have them.

    Both directions, because they are different defects. A provision at or under
    the threshold reads as one governing statement and its own document already
    carries every rule, so per-rule documents there are duplicates competing with
    their own parent for rank. A provision past it is a schedule of independent
    rows, and a row with no document of its own past the parent's retrieval-text
    ceiling cannot surface at all — the corpus would be complete by count and
    unreachable in exactly the part that needed the split.

    The whole decision is a count against a threshold. Nothing here reads a
    heading, a key, or anything a document says.
    """

    findings: list[QualityFinding] = []
    children: dict[str, int] = {}
    for record in expected_by_id.values():
        if record.parent_document_id is not None:
            children[record.parent_document_id] = (
                children.get(record.parent_document_id, 0) + 1
            )

    for key, record in expected_by_id.items():
        if record.parent_document_id is not None:
            continue
        count = children.get(key, 0)
        if record.provision_rule_count > rule_threshold and count == 0:
            findings.append(
                QualityFinding(code=FINDING_RULE_DOCUMENTS_MISSING, document_id=key)
            )
        elif record.provision_rule_count <= rule_threshold and count > 0:
            findings.append(
                QualityFinding(code=FINDING_RULE_DOCUMENTS_UNEXPECTED, document_id=key)
            )

    return findings


def _carries_a_record(document: Mapping[str, object]) -> bool:
    """Whether any field of this document holds a structure rather than a value.

    Structural, and it needs no list of field names to be right. An index
    document's fields are identifiers, counts, headings, one passage of
    retrieval text and one vector: scalars, and a sequence of numbers. The
    authoritative record is the other shape entirely — mappings, and sequences
    of mappings. So "is any value a mapping, or a sequence containing one" is
    exactly the question, and it stays exactly the question when a field is
    added.
    """

    for value in document.values():
        if isinstance(value, Mapping):
            return True
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            continue
        if any(isinstance(item, Mapping) for item in value):
            return True
    return False


# ── the semantic half ────────────────────────────────────────────────


def _cosine(left: Sequence[float], right: Sequence[float]) -> float | None:
    """Cosine of two vectors, or None when they cannot be compared.

    None rather than zero, and the distinction is the whole point. Two vectors
    of different widths, or one with no magnitude, do not produce a *low*
    similarity — they produce no similarity, and a caller handed `0.0` would
    record a failing score for a comparison that never happened. Everything
    below treats None as a shape failure and fails closed on it.
    """

    if len(left) != len(right) or not left:
        return None
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for a, b in zip(left, right):
        dot += a * b
        left_norm += a * a
        right_norm += b * b
    if left_norm <= 0.0 or right_norm <= 0.0:
        return None
    similarity = dot / math.sqrt(left_norm * right_norm)
    # Floating-point accumulation can carry an identical pair a hair past 1.
    return max(-1.0, min(1.0, similarity))


def _comparable_pair(source: str, projected: str, *, ceiling: int) -> tuple[str, str]:
    """Both sides cut to the same fraction of themselves, never to the same length.

    A rendering legitimately runs longer or shorter than its source — that is
    what rendering between languages does — so cutting both to the same
    character count would compare a passage against a *different span* of its
    own rendering and score a faithful pair as a mismatch. Cutting both to the
    same proportion keeps the comparison like for like without this module
    knowing anything about either language.
    """

    longest = max(len(source), len(projected))
    if longest <= ceiling:
        return source, projected
    fraction = ceiling / longest
    return (
        source[: max(1, math.ceil(len(source) * fraction))],
        projected[: max(1, math.ceil(len(projected) * fraction))],
    )


def _embedding_batches(
    pairs: Sequence[tuple[str, str, str]], *, profile: ProjectionQualityProfile
) -> list[list[tuple[str, str, str]]]:
    """Split the pairs into calls **without ever splitting a pair**.

    A pair is the unit, and both of its texts go in the same call. That is not
    an optimisation — it is what makes a partial or reordered reply
    unattributable rather than quietly wrong. If the two halves of one pair
    could land in different calls, a service that returned one call short would
    leave a source aligned against some other record's projection, and the
    comparison would still produce a number.

    Order is preserved, so the same corpus always produces the same calls.
    """

    batches: list[list[tuple[str, str, str]]] = []
    current: list[tuple[str, str, str]] = []
    chars = 0
    for pair in pairs:
        cost = len(pair[1]) + len(pair[2])
        if current and (
            len(current) >= profile.embedding_batch_items
            or chars + cost > profile.embedding_batch_chars
        ):
            batches.append(current)
            current = []
            chars = 0
        current.append(pair)
        chars += cost
    if current:
        batches.append(current)
    return batches


async def _similarity_by_document(
    pairs: Sequence[tuple[str, str, str]],
    *,
    openai_client: AzureOpenAIClient,
    profile: ProjectionQualityProfile,
) -> tuple[dict[str, float], list[QualityFinding]]:
    """Cosine per aligned pair, or a finding saying why there is not one.

    Each call carries its batch **interleaved** — source, projection, source,
    projection — and the reply is required to be exactly twice the batch's
    length. Both facts are checked before a single score is read: a reply of the
    wrong length cannot be attributed to any pair, so it produces one finding
    per pair in that batch rather than a best guess at which ones survived.
    """

    scores: dict[str, float] = {}
    findings: list[QualityFinding] = []

    for batch in _embedding_batches(pairs, profile=profile):
        texts: list[str] = []
        for _key, source, projected in batch:
            texts.append(source)
            texts.append(projected)
        try:
            vectors = await openai_client.embed(texts)
        except Exception as exc:  # noqa: BLE001 - the reason is a service's, not a corpus'
            # Logged as a class and a size. The texts are not logged, and the
            # service's own words are not repeated: this runs over the whole
            # corpus, so anything echoed here is echoed once per document.
            logger.warning(
                "projection validation could not embed a batch of %s pairs: %s",
                len(batch),
                type(exc).__name__,
            )
            findings.extend(
                QualityFinding(code=FINDING_EMBEDDING_UNAVAILABLE, document_id=key)
                for key, _source, _projected in batch
            )
            continue

        if not isinstance(vectors, Sequence) or len(vectors) != len(texts):
            findings.extend(
                QualityFinding(code=FINDING_EMBEDDING_COUNT_MISMATCH, document_id=key)
                for key, _source, _projected in batch
            )
            continue

        for index, (key, _source, _projected) in enumerate(batch):
            similarity = _cosine(vectors[index * 2], vectors[index * 2 + 1])
            if similarity is None:
                findings.append(
                    QualityFinding(
                        code=FINDING_EMBEDDING_SHAPE_MISMATCH, document_id=key
                    )
                )
                continue
            scores[key] = similarity

    return scores, findings


# ── the two halves, answered as one state ────────────────────────────


async def validate_projection(
    *,
    records: Sequence[ProjectedRecord],
    documents: Sequence[Mapping[str, object]],
    expected_profile: str,
    openai_client: AzureOpenAIClient | None,
    ignore_document_ids: Collection[str] = (),
    profile: ProjectionQualityProfile | None = None,
    rule_threshold: int = LARGE_POLICY_RULE_THRESHOLD,
    validated_at: datetime | None = None,
) -> ProjectionQualityReport:
    """Whether this corpus' projection may be matched against.

    THE ORDER, AND WHY IT IS THIS ORDER

    The deterministic checks run first and over everything, because they are
    free, they are certain, and they answer the question the semantic check
    cannot even be asked without: *which projection corresponds to which
    record*. A build whose set is wrong has no aligned pairs to score.

    Then every pair is scored — **all of them, including the ones that already
    failed a structural check**. A report that stopped at the first finding
    would send an operator round a loop of one repair per run against a corpus
    of thousands. The counts are the whole corpus's counts.

    A corpus passes only when both halves hold and there was something to check.
    An empty corpus is a coherent thing to have — a project with no published
    policies — and it passes: there is no projection in it that could be wrong.

    Nothing here writes anything. This function computes a verdict; the caller
    is what records it, which is what lets the same verdict be reached during a
    rebuild and against an index that was built weeks ago.
    """

    resolved = profile or quality_profile()
    now = _timestamp(validated_at)

    findings = structural_findings(
        records=records,
        documents=documents,
        expected_profile=expected_profile,
        ignore_document_ids=ignore_document_ids,
        rule_threshold=rule_threshold,
    )
    structural_count = len(findings)

    by_id = {
        _text(document.get("id")): document
        for document in documents
        if _text(document.get("id"))
    }
    pairs: list[tuple[str, str, str]] = []
    for record in records:
        document = by_id.get(record.document_id)
        if document is None:
            continue
        projected = _text(document.get("retrieval_text"))
        if not projected.strip() or not record.source_text.strip():
            continue
        source, rendered = _comparable_pair(
            record.source_text, projected, ceiling=resolved.compare_chars
        )
        pairs.append((record.document_id, source, rendered))

    scores: dict[str, float] = {}
    if pairs:
        if openai_client is None:
            findings.extend(
                QualityFinding(code=FINDING_EMBEDDING_UNAVAILABLE, document_id=key)
                for key, _source, _projected in pairs
            )
        else:
            scores, semantic = await _similarity_by_document(
                pairs, openai_client=openai_client, profile=resolved
            )
            findings.extend(semantic)

    below = [
        key
        for key, similarity in scores.items()
        if similarity < resolved.minimum_pair_similarity
    ]
    findings.extend(
        QualityFinding(code=FINDING_SIMILARITY_BELOW_FLOOR, document_id=key)
        for key in sorted(below)
    )

    values = list(scores.values())
    minimum = round(min(values), 4) if values else None
    mean = round(sum(values) / len(values), 4) if values else None

    # THREE STATES, AND THE ORDER THEY ARE DECIDED IN.
    #
    # A **proven** failure outranks a missing check. A build whose set is wrong,
    # or a pair that scored below the floor, is failed on evidence, and it stays
    # failed whether or not some other batch's embeddings arrived — reporting it
    # `unavailable` would describe a corpus that is definitely bad as one nobody
    # could assess, and would send an operator to fix a deployment instead of
    # rebuilding a corpus.
    #
    # Only with nothing proven wrong does missing evidence decide, and then it
    # decides against passing. `unavailable` is kept apart from `failed` because
    # the repairs differ, but the gate treats them identically: neither opens
    # it, because a check that was not made has not been passed.
    unscored = len(pairs) - len(scores)
    if structural_count or below:
        state: QualityState = QUALITY_FAILED
    elif unscored > 0:
        state = QUALITY_UNAVAILABLE
    elif findings:
        state = QUALITY_FAILED
    else:
        state = QUALITY_PASSED

    return ProjectionQualityReport(
        state=state,
        profile=resolved.name,
        checked_documents=len(scores),
        structural_findings=structural_count,
        below_floor=len(below),
        minimum_similarity=minimum,
        mean_similarity=mean,
        validated_at=now,
        findings=tuple(findings[:_MAX_REPORTED_FINDINGS]),
    )


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _timestamp(value: datetime | None) -> str:
    return (value or datetime.now(UTC)).astimezone(UTC).isoformat()
