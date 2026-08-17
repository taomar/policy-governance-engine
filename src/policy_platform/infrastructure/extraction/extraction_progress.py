"""Live progress for an in-flight AI extraction run.

Why this module exists
----------------------
`ai_extraction.extract_candidate_rules` is a long synchronous operation — tens
of model calls over tens of minutes for a real document. It already *knows* its
progress (which batch, which clauses, which pages, how many rules drafted, how
many skipped), but that knowledge only ever existed in local variables and died
with the call. The HTTP response is the single output channel and it does not
exist until the run has finished, so the UI could show nothing but a spinner and
a reviewer had no way to tell a working run from a hung one.

The responsibility of *publishing* progress belongs to the component that owns
the loop. The responsibility of *reading* it belongs to the API. This module is
the boundary between them, so `ai_extraction` never learns about HTTP, polling
or the UI, and the router never learns about batches or agent stages.

Why in-memory
-------------
This is observation telemetry, not a source of truth. The authoritative record
of what an extraction produced is the committed `candidate_rules` rows and the
`extraction_runs` status; progress is a view of work in flight and losing it has
no correctness consequence — worst case the UI falls back to a plain spinner,
which is exactly today's behaviour.

Storing it in Postgres instead would mean a schema migration and a write on the
hot path of every batch, to make a cosmetic readout durable. That trade is not
worth paying here.

KNOWN LIMITATION (accepted, deliberate): the registry is per-process, so it is
correct only while the API runs as a single process — which is how this platform
is deployed locally. Under multiple uvicorn workers a poll could land on a
worker that is not running the extraction and would see no progress. Fixing that
requires a shared store (Redis, or the DB columns rejected above) and should be
done when, and only when, multi-worker deployment becomes real.

INVARIANT: reporting must never change extraction's outcome. Every function here
is total — it does not raise, validate, or return anything the caller branches
on. A progress bug must not be able to fail a run.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field

#: Runs older than this are dropped on next write. A completed run is kept
#: briefly so the UI's final poll can show the terminal state instead of the
#: record vanishing mid-animation.
_RETENTION_SECONDS = 15 * 60


@dataclass
class ExtractionProgress:
    """A single run's live counters and its current human-readable stage."""

    document_version_id: str
    status: str = "running"
    #: One short sentence describing what is happening *right now*. Replaced on
    #: every update — this is a status line, not an append-only log.
    stage: str = "Starting…"
    total_clauses: int = 0
    processed_clauses: int = 0
    total_batches: int = 0
    processed_batches: int = 0
    total_pages: int = 0
    processed_pages: int = 0
    passages_found: int = 0
    rules_drafted: int = 0
    #: The drafted rules, tallied by the route the mapping assigned each as it
    #: was drafted: `rules_deterministic` where the source states a test the
    #: engine computes over named facts, `rules_ai_ready` where the source
    #: states its test in words and a judge reads the rule against a case. This
    #: is a run-scoped count of a value each rule already carries — `policy.py`
    #: keeps `evaluation_mode` derived rather than stored so a second copy
    #: cannot disagree with the condition it describes, and these honour that by
    #: counting what the mapping produced and persisting nothing.
    #:
    #: They are NOT assumed to sum to `rules_drafted`. A rule whose mode is
    #: absent, or is a route added to the model after this code was written, is
    #: counted by neither, so the difference between the two counters and
    #: `rules_drafted` stays visible as a gap rather than being charged to one
    #: side. A reader tells "the run has drafted nothing yet" (`rules_drafted`
    #: is 0) from "no rule took this route" (`rules_drafted` above 0 with the
    #: counter at 0) by reading each counter against `rules_drafted`, so 0 is
    #: never the only signal either counter carries.
    rules_deterministic: int = 0
    rules_ai_ready: int = 0
    #: Rules actually committed to the review queue. Distinct from
    #: `rules_drafted`: a rule is drafted by the formulator, but only counts as
    #: reviewable once its insert has committed. The two diverge whenever a
    #: batch's persistence fails, and the UI shows both so that divergence is
    #: visible rather than hidden behind one optimistic number.
    rules_committed: int = 0
    skipped: int = 0
    #: Rules that gained at least one confirmed relationship — a table row tied
    #: to its table, a subsection tied to the rule it qualifies. Reported
    #: because the linking pass runs after every batch and was otherwise
    #: invisible: the UI showed the run stall on the last batch for as long as
    #: linking took, with nothing saying what it was doing.
    linked: int = 0
    #: Unreviewed candidates from the previous run of this document that this
    #: run replaced. Zero until this run produces its first rule.
    superseded: int = 0
    # --- Delta against the previous extraction of the same document -------
    # Populated once, at the end of the run. The whole point of re-extraction is
    # to answer "what changed", so these are the numbers a reviewer actually
    # acts on: a run of 190 rules where all 190 are unchanged needs no review at
    # all, and saying so is more useful than reporting 190 rules found.
    delta_new: int = 0
    delta_changed: int = 0
    delta_unchanged: int = 0
    #: Rules the previous run produced that this one did not. They generate no
    #: row, so without this counter they would be invisible.
    delta_removed: int = 0
    #: Short human-facing reference for the run, so a reviewer can tie the rules
    #: in their queue back to the run that produced them.
    run_reference: str = ""
    error: str | None = None
    started_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["elapsed_seconds"] = round(time.time() - self.started_at, 1)
        return d


#: document_version_id -> latest progress record. Keyed by document version, not
#: run id, because the client cannot learn the run id until the POST returns —
#: which is after the run it wanted to watch has already finished.
_RUNS: dict[str, ExtractionProgress] = {}


def _prune() -> None:
    cutoff = time.time() - _RETENTION_SECONDS
    for key in [k for k, v in _RUNS.items() if v.updated_at < cutoff]:
        _RUNS.pop(key, None)


def start(document_version_id: str, *, total_clauses: int, total_batches: int, total_pages: int) -> None:
    """Begin (or restart) tracking for a document version."""
    _prune()
    _RUNS[document_version_id] = ExtractionProgress(
        document_version_id=document_version_id,
        total_clauses=total_clauses,
        total_batches=total_batches,
        total_pages=total_pages,
        stage=f"Preparing {total_clauses} clause(s) in {total_batches} batch(es)…",
    )


def update(document_version_id: str, **changes) -> None:
    """Apply field changes to a tracked run. Unknown keys and unknown runs are
    ignored — a reporting mistake must not surface as an extraction failure."""
    record = _RUNS.get(document_version_id)
    if record is None:
        return
    for key, value in changes.items():
        if hasattr(record, key):
            setattr(record, key, value)
    record.updated_at = time.time()


def advance(
    document_version_id: str,
    *,
    clauses: int = 0,
    pages: int = 0,
    passages: int = 0,
    drafted: int = 0,
    skipped: int = 0,
    linked: int = 0,
    deterministic: int = 0,
    ai_ready: int = 0,
) -> None:
    """Increment cumulative counters."""
    record = _RUNS.get(document_version_id)
    if record is None:
        return
    record.processed_clauses += clauses
    record.processed_pages = max(record.processed_pages, pages) if pages else record.processed_pages
    record.passages_found += passages
    record.rules_drafted += drafted
    record.skipped += skipped
    # Accumulated like `drafted`, and reported beside it: each batch passes the
    # route split of the rules it just drafted. Not assumed to sum to `drafted`
    # — a rule with an absent or unrecognised mode is added to neither, so the
    # caller can hand in fewer than it drafted and the difference stays a gap.
    record.rules_deterministic += deterministic
    record.rules_ai_ready += ai_ready
    # Assigned, not accumulated: the linking pass runs over every rule in the
    # run each time, so its result is a total rather than a delta. Adding it
    # would multiply the count by the number of batches.
    if linked:
        record.linked = linked
    record.updated_at = time.time()


def finish(document_version_id: str, *, status: str, stage: str, error: str | None = None) -> None:
    """Record the terminal state. Kept for `_RETENTION_SECONDS` so the UI's last
    poll sees the outcome rather than a missing record."""
    record = _RUNS.get(document_version_id)
    if record is None:
        return
    record.status = status
    record.stage = stage
    record.error = error
    record.updated_at = time.time()


def get(document_version_id: str) -> dict | None:
    record = _RUNS.get(document_version_id)
    return record.as_dict() if record else None


def clear() -> None:
    """Test hook — drop all tracked runs."""
    _RUNS.clear()
