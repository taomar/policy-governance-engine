"""Putting a case to a *project's* published policies: retrieve the ones that
bear on the question, discard the rest, and evaluate only the survivors.

WHY THIS EXISTS

The per-policy path (`ai_case_intent.answer_policy_case`, the `/policy-case/answer`
endpoint) answers one policy a reviewer has already chosen. A reviewer can also put
a case to the whole project without naming a policy — and there the instruction is
explicit and load-bearing:

    "u never run against all published, u must use AI search and any technique
     possible to retrieve highest policies match before evaluation, non matching
     policies are discarded"

So this module never evaluates against every policy. It *retrieves first*: it
embeds the question and searches the project's own policy index, whose unit is a
published policy at the latest approved version. Retrieved policy documents are
mapped back to the lean published payload by ``policy_version_id`` plus
``provision_key`` — identity that survives clause re-parsing. The rest are
discarded, and which were considered, retained, and discarded — and on what basis —
is reported, because a reviewer must always be able to see that narrowing happened
and how much (constraint 10).

WHY NO FAN-OUT

The retained policies are evaluated together, in one gather over their combined
lean records, not one call per policy: "u dont loop in code one policy after other,
u have the json light already to evaluate against." The combined size is measured
and reported (constraint 11), and if it ever exceeds the one-gather budget the
answer is refused rather than trimmed — the refusal is `ai_case_intent`'s, kept in
one place.

NARROWING HAPPENS TWICE, AND THE SECOND TIME IS ABOUT SIZE

Ranking by relevance and fitting into one grounded pass are two different
questions, and treating them as one produced a real defect: a question about
annual vacation retained the Annual Vacation policy at rank 0 (ten rules) and,
at rank 3, a Table of Violations and Penalties with seventy-four rules that had
nothing to do with it. Together they measured 229,389 characters against a
200,000 budget, so the gather refused the *whole set* — and a reviewer whose
answer was sitting in the rank-0 policy was told nothing at all.

So after ranking and before the gather, whole policy records are admitted in rank
order while they still fit (:func:`fit_within_payload_budget`). A policy that
would overflow is discarded with ``outside_payload_budget`` and later, smaller
policies are still tried, so one oversized record costs only itself. No policy is
ever trimmed to fit, and none is dropped silently: the discard reason and the
``policies_over_payload_budget`` count are in the retrieval disclosure like every
other narrowing. When the highest-ranked policy alone is too large, nothing is
dropped and the honest oversize refusal stands — an empty retained set would read
as "no policy matched", which would be false.

AND THE BUDGET COUNTS DISTINCT POLICIES, NOT COPIES

A third defect, and the earliest of the three in the pipeline. Receipt
`76a5e936-7ea4-4cc3-828a-0fb099c2ee5b` asked what the policies say about laptop
replacement eligibility and whether a 26-month-old laptop is eligible. The
information track answered; the verdict came back ``not_settled_by_rules``. The
five retained policies were two copies of `2.1 Standard entitlement`, two copies
of `4.2 Accidental damage`, and `4.4 Lost/stolen`. `3.1 Standard refresh
interval` — the provision that decides a 26-month-old laptop — ranked sixth and
was discarded ``outside_budget``.

Nothing ranked wrongly. The corpus held two policies twice, under provisions with
different ids and different keys because they came from two document versions,
and half the answer slots went to saying one thing twice. So before the retention
budget is applied, hits whose policies govern *identically* are collapsed into one
(:func:`collapse_duplicate_policies`), and the budget counts distinct policies.
Equivalence is an exact match of
:func:`~policy_platform.infrastructure.projection.policy_semantic_identity.policy_semantic_fingerprint`
— everything the policy governs, with only identity and provenance removed —
never a heading, a title or an authority on its own; two policies sharing a
heading but differing in any rule, sentence, date, scope or carve-out are two
policies and both are read.

The collapse is disclosed like every other narrowing and is the only one whose
content still reached the gather: each collapsed copy stays in `considered` with
its own rank and score, carries ``duplicate_policy_content``, and names the
representative in ``duplicate_of_provision_key``, so a reader sees that the terms
were read without being told this record was.

THE STATES A RETRIEVAL CAN BE IN, KEPT APART

Ten facts about a search are not one fact (constraint 5), and none of them may
degrade silently to "answer against all" (constraint 10):

  - ``narrowed``               — retrieval kept a subset and set the rest aside.
  - ``not_narrowed``           — retrieval ran and discarded nothing, because the
                                 project has no more published policies than the
                                 retention budget. Every one was evaluated, and
                                 none of them was *selected* — saying otherwise
                                 would credit search with a choice it never made.
  - ``no_match``               — retrieval ran on the current published policy
                                 index, but no policy matched this question.
  - ``no_published_version``   — the project has no active approved version, so
                                 there is no published project scope to test.
  - ``index_not_built``        — the project's policy index does not exist yet.
  - ``index_stale``            — the index exists, but not for the active
                                 published version.
  - ``index_empty``            — the index exists and holds no documents at all
                                 for this project.
  - ``index_projection_unavailable`` — the index exists and holds documents, but
                                 not rendered into the language a question is
                                 matched in: no projection, one built under a
                                 superseded contract, or one a rebuild left
                                 half-written. **The only one of these that is
                                 raised rather than returned.** The others leave
                                 a query that could have been made against a
                                 comparable corpus, so reporting them with an
                                 empty result is complete and honest. This one
                                 does not: a rendered question matched against an
                                 unrendered corpus scores near zero on every
                                 policy, and near zero is indistinguishable from
                                 "nothing here bears on your question". So it
                                 fails the call, both routes answer ``503``, and
                                 the audited one writes a failed receipt.
  - ``unavailable``            — search is not configured on this server at all.
  - ``failed``                 — the search call itself raised.
  - ``empty``                  — the active version has no published policy rules.
  - ``bypassed``               — a single policy was named, so retrieval did not
                                 run; and ``policy_not_published`` when that
                                 policy is not in the published version.

The three that a rebuild repairs — ``index_not_built``, ``index_stale`` and
``index_empty`` — say so in their reason, and the client offers the repair for
exactly those three. `test_the_index_repair_offer_matches_the_backend` fails if
that set and this one ever come apart, because an instruction the product cannot
carry out is worse than no instruction. ``index_projection_unavailable`` is
repaired by the same rebuild but is not in that set: it never reaches the client
as a retrieval status, because the call it belongs to did not return one.

TWO SEARCHES, ONE QUESTION
--------------------------
A policy document carries one vector over a bounded amount of its retrieval
text. For an ordinary provision that is the provision. For a schedule of
seventy-four independent rows it is a summary of the first few, and every row
past the bound is not ranked low but **absent** — so the provision that answers
a question about the fortieth row could only ever be found by what its opening
rows happened to say.

So the index also holds one document per rule for any provision above the
rule-slicing threshold, and retrieval runs two filtered searches over one
embedding of the question: one over policy documents, one over rule documents.
Their rankings are fused by reciprocal rank, so a provision found by both
outranks one found by either, and a provision found *only* by one of its rows is
in the ranking at all — which it could not have been before. Everything after
that point is unchanged: the same duplicate collapse, the same normative
diversity ordering, the same retention budget of distinct policies.

The one thing forbidden — falling back to evaluating every policy — is never done
in any of these states. When retrieval cannot be relied on, the reviewer is told,
and the escape hatch is the single-policy scope: naming a ``provision_id`` bypasses
retrieval entirely, because a reviewer who has chosen one policy has already done
the narrowing.

Nothing in this module names a domain. It works from the project's own published
version and policy identity, so it holds for any governance corpus (constraint 1).
The counts it reports are policies first, then rules (constraint 2).
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import DocumentProvision
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient
from policy_platform.infrastructure.assistants.ai_case_intent import (
    _MAX_RECORD_CHARS,
    answer_case_over_policies,
)
from policy_platform.infrastructure.assistants.ai_case_language import (
    ENGLISH_PROJECTION_PROFILE,
    EnglishProjectionReadiness,
    INDEX_PROJECTION_UNAVAILABLE,
)
from policy_platform.infrastructure.projection.policy_case_payload import to_compact
from policy_platform.infrastructure.projection.policy_rule_slice import (
    LARGE_POLICY_RULE_THRESHOLD,
    RULE_INDEX_DEGRADED,
    RULE_INDEX_MATCHED,
    RULE_INDEX_UNAVAILABLE,
    SELECTED_RULE_BUDGET,
    RRF_K,
    select_rules_for_scenario,
)
from policy_platform.infrastructure.projection.policy_semantic_identity import (
    POLICY_NORMATIVE_GROUP_VERSION,
    policy_normative_group_key,
    policy_semantic_fingerprint,
)
from policy_platform.infrastructure.projection.text_canonical import canonical_tokens
from policy_platform.infrastructure.projection.published_case_payload import (
    active_version_for_policy_set,
    published_case_payload_with_extras_for_policy,
    published_case_payloads_with_extras,
)
from policy_platform.infrastructure.search.policy_index import (
    CONTENT_TYPE_POLICY,
    CONTENT_TYPE_RULE,
    POLICY_SEMANTIC_CONFIG,
    odata_string,
    policy_document_id,
    policy_index_filter,
    policy_index_name,
    read_projection_readiness,
)
from policy_platform.infrastructure.search.search_client import AzureSearchClient
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)


#: How far down the ranked policy hits a policy may be found and still be retained.
#: A policy ranking in the top of the search is what keeps it in, and everything
#: below it is discarded. Making this the retention threshold rather than a score
#: threshold is deliberate: RRF-hybrid scores are close together, so rank is the
#: discriminator. Over-keeping is the safe error here: the gather re-checks each
#: rule's bearing and cites only those that speak to the question, so a policy
#: retained but not bearing costs a little context, never a false citation;
#: under-keeping would drop a policy that bears, which is the one outcome the user
#: forbade. Named as a budget, not a measurement of any corpus.
RETRIEVAL_POLICY_BUDGET = 5

#: How many ranked policies are examined at all, a cost bound on the search. Wider
#: than the retention budget so a policy that surfaced but ranked out is reported
#: *with its score* — a reviewer sees it was seen and set aside, not that it never
#: appeared — while policies beyond it are honestly "did not surface".
RETRIEVAL_POLICY_SCAN = 40

#: How many rule documents the discovery pass examines. Wider than the policy
#: scan because the unit is smaller: a schedule contributes one policy document
#: and as many rule documents as it has rows, so a rule scan the size of the
#: policy scan could be filled by two schedules and never reach a third
#: provision's rows. It is a cost bound on the same one search call, not a second
#: budget: what a rule hit can do is elevate the provision that holds it, and the
#: retention budget of distinct policies is unchanged.
RETRIEVAL_RULE_SCAN = 120

#: How many rule documents the ranking pass examines, scoped to the provisions
#: that were actually retained. Deeper than the discovery scan and over far fewer
#: documents, because this is the ranking that decides which rows of a retained
#: schedule a gather reads — a rank that stopped at the discovery depth would be
#: a rank over whichever rows happened to place globally.
RETRIEVAL_RULE_RANK_SCAN = 200

# Azure AI Search only sends the top 50 initial results to semantic reranking.
# Broader scans remain useful as hybrid discovery, but only results carrying an
# actual reranker score may satisfy the absolute rule-rescue gate.
SEMANTIC_RERANKER_LIMIT = 50

#: The characters of the retained policies' combined record the gather may read in
#: one pass — the same ceiling `ai_case_intent` applies to a single policy's
#: record, shared so the size budget has one source of truth rather than two.
PAYLOAD_BUDGET_CHARS = _MAX_RECORD_CHARS

#: The retrieval method named in the response, so the reviewer knows which path
#: produced the narrowing. Two rankings of the same policy documents may be
#: fused symmetrically; rule documents never enter that fusion and can only
#: rescue a parent through independently strong semantic evidence.
RETRIEVAL_METHOD_LEGACY = "hybrid_policy_rule_rrf_v1"
RETRIEVAL_METHOD = "direct_policy_rrf_elbow_rule_rescue_v1"
LIGHT_RETRIEVAL_METHOD = "semantic_policy_elbow_v1"

#: Retrieval-only callers value a small, precise context over the decision
#: path's deliberate recall bias. Semantic scores are cut at the first meaningful
#: elbow; when the ranking has no such elbow, three policies remain available
#: rather than the decision path's five.
LIGHT_RETRIEVAL_POLICY_BUDGET = 3
LIGHT_RETRIEVAL_MAX_POLICIES = RETRIEVAL_POLICY_BUDGET
LIGHT_SEMANTIC_GAP = 0.15
DECISION_SEMANTIC_GAP = 0.08
DECISION_STRONG_SEMANTIC_GAP = 0.30
DECISION_COVERAGE_MIN_SCORE = 0.5
DECISION_COVERAGE_SEMANTIC_FLOOR = 1.75
DECISION_COVERAGE_IDF_SMOOTHING = 0.25
DIRECT_POLICY_ORDER_SEMANTIC = "semantic_strong_lead_v1"
DIRECT_POLICY_ORDER_RRF = "rrf_hybrid_semantic_v1"
DIRECT_POLICY_ORDER_HYBRID = "hybrid_search_order_v1"

#: A rule may rescue a policy the direct semantic policy ranking omitted, but it
#: must be strong in absolute terms and materially stronger than the weakest
#: directly selected policy. That preserves true row-only recall without letting
#: a large schedule win merely because it participates in two ranking channels.
DECISION_RULE_RESCUE_FLOOR = 2.5
DECISION_RULE_RESCUE_MARGIN = 0.3

#: The method a receipt written before rule documents existed carries. Kept named
#: so the change is legible rather than a string that silently moved.
RETRIEVAL_METHOD_POLICY_ONLY = "hybrid_vector_topk"

#: What a rule-document query selects. The shared default field list does not
#: name the fields that make a rule hit usable — which rule it is, where it sits
#: in its policy, which policy document holds it, and the English projection the
#: request-side selection scores against — so this names them explicitly. It is a
#: superset of the default, so nothing a caller already read is lost.
_RULE_SELECT = (
    "id,policy_id,document_id,document_version,clause_id,clause_number,"
    "section_heading,heading,body,status,content_type,rule_id,rule_ordinal,"
    "parent_document_id,provision_key,retrieval_text,projection_profile"
)

#: The two scopes a case can be put in. Named, because a reviewer who chose one
#: policy and a reviewer who put a question to the project are doing two different
#: things, and only the second one retrieves.
SCOPE_SINGLE = "single"
SCOPE_PROJECT = "project"


def _gather_kwargs(additional_instructions: str) -> dict:
    """The guidance argument, present only when there is guidance to pass.

    Not `additional_instructions=""`. Passing the keyword with an empty value
    would be equivalent *in behaviour* and different at the boundary: every
    existing caller and every existing test double of
    :func:`answer_case_over_policies` would suddenly receive an argument it was
    never written to accept, and several of them raise `TypeError` on exactly
    that. "Preserve the default behaviour" has to mean the call itself is
    unchanged, not merely that the answer comes out the same — a signature is
    part of the behaviour when doubles exist.
    """

    return {"additional_instructions": additional_instructions} if additional_instructions else {}

#: The honest states a retrieval can be in, plus ``bypassed`` for the
#: single-policy scope where retrieval does not run at all. Kept apart on purpose
#: (constraint 5); collapsing any pair reports one situation as another, and none
#: of them is ever "evaluate against all" (constraint 10).
RETRIEVAL_NARROWED = "narrowed"
#: Retrieval ran and set nothing aside, because the project has no more published
#: policies than the retention budget. Kept apart from ``narrowed`` because
#: reporting "search kept the highest matching policies and discarded the rest"
#: when nothing was discarded tells a reviewer that search selected these
#: policies, when in fact it selected nothing: they are simply all of them. The
#: gather still decides bearing, so this is not a weaker answer — it is the same
#: answer with an honest account of how its inputs were chosen.
RETRIEVAL_NOT_NARROWED = "not_narrowed"
RETRIEVAL_NO_MATCH = "no_match"
RETRIEVAL_INDEX_EMPTY = "index_empty"
RETRIEVAL_NO_PUBLISHED_VERSION = "no_published_version"
RETRIEVAL_INDEX_NOT_BUILT = "index_not_built"
RETRIEVAL_INDEX_STALE = "index_stale"
RETRIEVAL_UNAVAILABLE = "unavailable"
RETRIEVAL_FAILED = "failed"
RETRIEVAL_EMPTY_SET = "empty"
RETRIEVAL_BYPASSED = "bypassed"
RETRIEVAL_POLICY_NOT_PUBLISHED = "policy_not_published"
#: The index exists and holds documents, but not in the language this pipeline
#: matches in — no projection at all, one built under a superseded contract, or
#: one a rebuild left half-written. A third fact, and a reader who could not tell
#: it from `index_not_built` or `index_stale` could not tell a missing rebuild
#: from a missing projection. It is the one retrieval state that is **not**
#: answered with a 200 and an empty result: matching a rendered question against
#: an unrendered corpus scores near zero on every policy, so an answer produced
#: that way would read as "nothing bears on your question" when the truth is
#: "nothing could be compared".
RETRIEVAL_INDEX_PROJECTION_UNAVAILABLE = INDEX_PROJECTION_UNAVAILABLE

#: Why a candidate policy was discarded, told apart so "seen and set aside" never
#: reads the same as "never surfaced".
DISCARD_OUTSIDE_BUDGET = "outside_budget"  # surfaced in the scan but did not place inside the budget
DISCARD_NO_MATCH = "no_retrieval_match"  # it did not surface in the scan at all
DISCARD_STALE_VERSION = "stale_index_version"  # surfaced, but not for the active version
#: It ranked inside the retention budget and was still set aside, because adding
#: its *whole* record would have pushed the combined payload past what one
#: grounded pass can read. Kept apart from ``outside_budget`` because the two are
#: different facts about the same policy: one says search ranked it too low, the
#: other says search ranked it highly enough and it did not fit. A reviewer
#: reading "outside budget" against a rank-0 policy would be reading a lie.
DISCARD_OUTSIDE_PAYLOAD_BUDGET = "outside_payload_budget"
#: It ranked, and an identically-governing policy ranked above it. The corpus
#: holds the same policy twice — two provisions, two ids, two keys, one set of
#: terms — and the retention budget is a budget of *distinct policies to read*.
#: Kept apart from every other discard because it is the only one that says the
#: policy's content *was* read, in the representative named beside it.
DISCARD_DUPLICATE_POLICY_CONTENT = "duplicate_policy_content"

#: How the retained set was chosen from the ranked hits: by relevance, then by
#: normative-content diversity. Named on every retrieval block so the ordering a
#: receipt was produced under is on the receipt, and a later ordering is a
#: different, visible thing rather than a silent change of meaning.
POLICY_SELECTION_ORDER = f"relevance_then_{POLICY_NORMATIVE_GROUP_VERSION}"


class ProvisionNotInProject(LookupError):
    """Raised when a named provision exists but belongs to a different project.

    A distinct fact from an unknown id: the reviewer named a real policy, only not
    one of this project's, so the endpoint answers 404 without pretending the id
    was malformed.
    """


class IndexProjectionUnavailable(RuntimeError):
    """This project's index cannot be matched against by a rendered question.

    Raised rather than returned, and it is the only retrieval state that is. The
    other states that stop short of an answer — the index is absent, the index is
    stale, search is unavailable — all leave a query that *could* have been made
    against a comparable corpus, so a 200 carrying "no evaluation was made, and
    here is why" is a complete and honest answer to the question that was asked.

    This one is different. A question reduced to the processing language matched
    against a corpus that was never rendered into it does not score badly, it
    scores near zero on every policy — and a near-zero ranking is indistinguishable
    from a real "nothing bears on this". Answering 200 here would therefore mean
    serving "no published policy matched your question" when the truth is that no
    comparison was possible. So the whole call fails, both routes report `503`
    with :data:`INDEX_PROJECTION_UNAVAILABLE`, and the audited one writes a failed
    receipt — the same shape the language boundary's own refusals take, for the
    same reason.

    `readiness` carries what was probed, so a caller reports which profile was
    expected rather than a bare outage.
    """

    def __init__(self, readiness: EnglishProjectionReadiness, message: str) -> None:
        super().__init__(message)
        self.code = INDEX_PROJECTION_UNAVAILABLE
        self.readiness = readiness


def is_rule_hit(hit: dict) -> bool:
    """Whether this search result is a rule document, on its own evidence.

    Read from the document rather than inferred from which query returned it.
    Two reasons, and the second is the load-bearing one: a filter is a request
    and a `content_type` is a fact, and a document that came back from a
    rule-scoped query without being a rule document must not be counted as one
    — that would be trusting the filter to have been applied.
    """

    if str(hit.get("content_type") or "") == CONTENT_TYPE_RULE:
        return True
    return bool(hit.get("rule_id")) and bool(hit.get("parent_document_id"))


def select_semantic_policy_hits(
    hits: list[dict],
    *,
    default_budget: int = LIGHT_RETRIEVAL_POLICY_BUDGET,
    max_budget: int = LIGHT_RETRIEVAL_MAX_POLICIES,
    minimum_gap: float = LIGHT_SEMANTIC_GAP,
) -> tuple[list[dict], dict]:
    """Cut a semantic policy ranking at its first meaningful relevance elbow.

    Retrieval-only mode uses the smaller default budget. The decision path uses
    the same domain-neutral elbow with its five-policy recall budget, then permits
    independently strong rule-only evidence to rescue an omitted parent. Neither
    path sums a second ranking channel into a direct policy score.

    Azure's reranker score is domain-neutral and already compares the question
    with each policy's English projection. A clear adjacent drop chooses the
    smaller set above it. If no drop reaches the configured floor, the bounded
    default is used. Missing reranker scores degrade to the same bounded count,
    never back to all candidates.
    """

    if not hits:
        return [], {
            "precision_mode": LIGHT_RETRIEVAL_METHOD,
            "semantic_candidates": 0,
            "semantic_selected": 0,
        }

    ranked = [
        dict(hit)
        for hit in hits
        if isinstance(hit.get("@search.rerankerScore"), (int, float))
    ]
    if not ranked:
        selected = [dict(hit) for hit in hits[:default_budget]]
        return selected, {
            "precision_mode": f"{LIGHT_RETRIEVAL_METHOD}_score_unavailable",
            "semantic_candidates": len(hits),
            "semantic_selected": len(selected),
            "semantic_largest_gap": None,
            "semantic_cutoff_score": None,
        }

    ranked.sort(
        key=lambda hit: (
            -float(hit["@search.rerankerScore"]),
            str(hit.get("id") or ""),
        )
    )
    window = ranked[:max_budget]
    gaps = [
        float(window[index]["@search.rerankerScore"])
        - float(window[index + 1]["@search.rerankerScore"])
        for index in range(len(window) - 1)
    ]
    largest_gap = max(gaps) if gaps else 0.0
    if gaps and largest_gap >= minimum_gap:
        count = gaps.index(largest_gap) + 1
    else:
        count = min(default_budget, len(window))
    selected = window[: max(1, count)]
    for hit in selected:
        # `select_retained` exposes `@search.score` as `best_score`. In precision
        # mode the semantic score, not the pre-rerank hybrid score, is the value
        # that decided inclusion.
        hit["@search.score"] = float(hit["@search.rerankerScore"])

    return selected, {
        "precision_mode": LIGHT_RETRIEVAL_METHOD,
        "semantic_candidates": len(hits),
        "semantic_selected": len(selected),
        "semantic_largest_gap": largest_gap,
        "semantic_cutoff_score": float(selected[-1]["@search.rerankerScore"]),
    }


def select_decision_policy_hits(
    policy_hits: list[dict],
    rule_hits: list[dict],
    *,
    rescue_floor: float = DECISION_RULE_RESCUE_FLOOR,
    rescue_margin: float = DECISION_RULE_RESCUE_MARGIN,
) -> tuple[list[dict], list[dict], dict[str, list[dict]], dict]:
    """Select decision policies without rewarding a second ranking channel.

    A semantic elbow determines how many direct policy documents have defensible
    separation. When it exists, those identities are chosen by symmetric RRF
    over hybrid and semantic ranks of the same policy documents; when it does
    not, the full hybrid direct-policy pool reaches the final diversity budget.
    Rule documents never enter that fusion. They can only rescue an omitted
    parent when their best semantic score is independently strong and materially
    above the direct cutoff, so corpus size cannot create an extra score channel.
    Returns the precision candidates, the full ranked direct/rescue disclosure,
    rule hits grouped by parent, and the selection metadata.
    """

    semantic_direct, semantic = select_semantic_policy_hits(
        policy_hits,
        default_budget=RETRIEVAL_POLICY_BUDGET,
        max_budget=RETRIEVAL_POLICY_BUDGET,
        minimum_gap=DECISION_SEMANTIC_GAP,
    )
    indexed = list(enumerate(policy_hits))

    def hybrid_order(item: tuple[int, dict]) -> tuple:
        index, hit = item
        score = hit.get("@search.score")
        if isinstance(score, (int, float)):
            return (0, -float(score), str(hit.get("id") or ""))
        return (1, index, str(hit.get("id") or ""))

    hybrid_direct = [dict(hit) for _, hit in sorted(indexed, key=hybrid_order)]
    scored_in_window = min(
        RETRIEVAL_POLICY_BUDGET,
        len(
            [
                hit
                for hit in policy_hits
                if isinstance(hit.get("@search.rerankerScore"), (int, float))
            ]
        ),
    )
    elbow_applied = bool(
        scored_in_window > 1
        and semantic.get("semantic_largest_gap") is not None
        and float(semantic["semantic_largest_gap"]) >= DECISION_SEMANTIC_GAP
        and len(semantic_direct) < scored_in_window
    )
    semantic_gap = float(semantic.get("semantic_largest_gap") or 0.0)
    strong_semantic_lead = elbow_applied and semantic_gap >= DECISION_STRONG_SEMANTIC_GAP
    if strong_semantic_lead:
        ranked_direct = sorted(
            (dict(hit) for hit in policy_hits),
            key=lambda hit: (
                0
                if isinstance(hit.get("@search.rerankerScore"), (int, float))
                else 1,
                -float(hit.get("@search.rerankerScore") or 0.0),
                str(hit.get("id") or ""),
            ),
        )
        for hit in ranked_direct:
            if isinstance(hit.get("@search.rerankerScore"), (int, float)):
                hit["@search.score"] = float(hit["@search.rerankerScore"])
        direct = ranked_direct[: len(semantic_direct)]
        direct_policy_order = DIRECT_POLICY_ORDER_SEMANTIC
    elif elbow_applied:
        # Semantic ranking establishes a defensible cardinality. Identities are
        # chosen by symmetric RRF over the two rankings of the same policy
        # documents: hybrid lexical/vector rank and semantic reranker rank.
        # Every policy has exactly the same two opportunities to participate;
        # rule documents remain outside this fusion and can only rescue.
        semantic_ranked = sorted(
            (dict(hit) for hit in policy_hits),
            key=lambda hit: (
                0
                if isinstance(hit.get("@search.rerankerScore"), (int, float))
                else 1,
                -float(hit.get("@search.rerankerScore") or 0.0),
                str(hit.get("id") or ""),
            ),
        )
        hybrid_rank = {
            str(hit.get("id")): rank
            for rank, hit in enumerate(hybrid_direct)
            if hit.get("id")
        }
        semantic_rank = {
            str(hit.get("id")): rank
            for rank, hit in enumerate(semantic_ranked)
            if hit.get("id")
        }
        ranked_direct = []
        for hit in policy_hits:
            identity = str(hit.get("id") or "")
            if not identity or identity not in hybrid_rank or identity not in semantic_rank:
                continue
            ranked = dict(hit)
            ranked["@search.score"] = (
                1.0 / (RRF_K + hybrid_rank[identity])
                + 1.0 / (RRF_K + semantic_rank[identity])
            )
            ranked_direct.append(ranked)
        ranked_direct.sort(
            key=lambda hit: (
                -float(hit["@search.score"]),
                str(hit.get("id") or ""),
            )
        )
        direct = ranked_direct[: len(semantic_direct)]
        direct_policy_order = DIRECT_POLICY_ORDER_RRF
    else:
        # A flat semantic ranking has not established a precision boundary. Keep
        # the direct policy pool in hybrid-search order so the existing
        # duplicate/diversity pass can spend the final five-policy budget across
        # genuinely different rules. Truncating here would turn semantic
        # uncertainty into false confidence and make later diversity unreachable.
        ranked_direct = hybrid_direct
        direct = ranked_direct
        semantic["semantic_selected"] = len(direct)
        semantic["semantic_cutoff_score"] = None
        direct_policy_order = DIRECT_POLICY_ORDER_HYBRID

    direct_ids = {str(hit.get("id")) for hit in direct if hit.get("id")}
    policy_by_id = {str(hit.get("id")): hit for hit in policy_hits if hit.get("id")}
    by_parent: dict[str, list[dict]] = {}
    for hit in rule_hits:
        parent = str(hit.get("parent_document_id") or hit.get("document_id") or "")
        if parent:
            by_parent.setdefault(parent, []).append(hit)

    cutoff = semantic.get("semantic_cutoff_score")
    rescues: list[tuple[float, str, dict]] = []
    for parent, children in by_parent.items():
        if parent in direct_ids:
            continue
        scores = [
            float(hit["@search.rerankerScore"])
            for hit in children
            if isinstance(hit.get("@search.rerankerScore"), (int, float))
        ]
        if not scores:
            continue
        score = max(scores)
        required = rescue_floor if cutoff is None else max(rescue_floor, float(cutoff) + rescue_margin)
        if score < required:
            continue
        source = policy_by_id.get(parent)
        if source is None:
            first = children[0]
            source = {
                "id": parent,
                "policy_id": first.get("policy_id"),
                "document_id": first.get("document_id"),
                "document_version": first.get("document_version"),
                "content_type": CONTENT_TYPE_POLICY,
            }
        rescued = dict(source)
        rescued["@search.score"] = score
        rescued["@search.rerankerScore"] = score
        rescued["elevated_by_rule"] = True
        rescues.append((score, parent, rescued))

    rescues.sort(key=lambda item: (-item[0], item[1]))
    # Do not cap before duplicate collapse. Several policy ids can carry the same
    # governing content; capping here would let five copies exclude the first
    # distinct rescue before the downstream content-aware pass can see it.
    admitted = [item[2] for item in rescues]
    if elbow_applied:
        selected = sorted(
            [*direct, *admitted],
            key=lambda hit: (
                -float(hit.get("@search.rerankerScore") or 0.0),
                bool(hit.get("elevated_by_rule")),
                str(hit.get("id") or ""),
            ),
        )
    else:
        # A rule-only parent that clears the absolute semantic floor is stronger
        # evidence than a flat direct pool. Give it a place in the final budget,
        # then preserve direct hybrid order for the remaining candidates.
        selected = [*admitted, *direct]
    ranked_hits: list[dict] = []
    ranked_ids: set[str] = set()
    for hit in [*selected, *ranked_direct]:
        identity = str(hit.get("id") or "")
        if not identity or identity in ranked_ids:
            continue
        ranked_ids.add(identity)
        ranked_hits.append(hit)

    return selected, ranked_hits, by_parent, {
        **semantic,
        "precision_mode": RETRIEVAL_METHOD,
        "semantic_elbow_applied": elbow_applied,
        "direct_policy_order": direct_policy_order,
        "rule_rescue_candidates": len(rescues),
        "rule_rescued_policies": len(admitted),
        "rule_rescue_floor": rescue_floor,
        "rule_rescue_margin": rescue_margin,
        "rule_semantic_window": SEMANTIC_RERANKER_LIMIT,
        "rule_semantic_candidates": sum(
            1
            for hit in rule_hits
            if isinstance(hit.get("@search.rerankerScore"), (int, float))
        ),
        "coverage_semantic_floor": DECISION_COVERAGE_SEMANTIC_FLOOR,
    }


def expand_policy_query_coverage(
    selected: list[dict],
    ranked: list[dict],
    *,
    scenario: str,
    budget: int = RETRIEVAL_POLICY_BUDGET,
    minimum_score: float = DECISION_COVERAGE_MIN_SCORE,
    semantic_floor: float = DECISION_COVERAGE_SEMANTIC_FLOOR,
) -> tuple[list[dict], int]:
    """Add direct policies that cover query terms absent from the precision cut.

    The terms come only from the processed-language question and English indexed
    headings. Body text is used to recognize what the selected policies already
    cover, but cannot add a policy: expansion is reserved for an explicit aspect
    named in a heading. Each newly covered term is consumed once, preventing
    several copies of one aspect from filling the budget.
    """

    if len(selected) >= budget:
        return list(selected), 0

    query = set(canonical_tokens(scenario, min_chars=4))
    if not query:
        return list(selected), 0

    documents: list[tuple[int, dict, set[str], set[str]]] = []
    document_frequency: dict[str, int] = {}
    for rank, hit in enumerate(ranked):
        heading = " ".join(
            str(hit.get(field) or "") for field in ("section_heading", "heading")
        )
        heading_tokens = set(canonical_tokens(heading, min_chars=4))
        body_tokens = set(
            canonical_tokens(str(hit.get("body") or ""), min_chars=4)
        )
        tokens = heading_tokens | body_tokens
        documents.append((rank, hit, heading_tokens, tokens))
        for token in query & tokens:
            document_frequency[token] = document_frequency.get(token, 0) + 1

    total = max(1, len(documents))
    weights = {
        token: max(
            0.0,
            math.log(
                (total + 1) / (1 + document_frequency.get(token, 0))
            )
            + DECISION_COVERAGE_IDF_SMOOTHING,
        )
        for token in query
    }
    selected_ids = {str(hit.get("id") or "") for hit in selected}
    covered: set[str] = set()
    for _rank, hit, _heading_tokens, tokens in documents:
        if str(hit.get("id") or "") in selected_ids:
            covered.update(query & tokens)

    def one_edit_apart(left: str, right: str) -> bool:
        if left == right or abs(len(left) - len(right)) > 1:
            return left == right
        if len(left) > len(right):
            left, right = right, left
        index_left = index_right = differences = 0
        while index_left < len(left) and index_right < len(right):
            if left[index_left] == right[index_right]:
                index_left += 1
                index_right += 1
                continue
            differences += 1
            if differences > 1:
                return False
            if len(left) == len(right):
                index_left += 1
            index_right += 1
        return differences + (len(right) - index_right) <= 1

    def heading_query_terms(heading_tokens: set[str]) -> set[str]:
        return {
            query_token
            for query_token in query
            if any(
                query_token == heading_token
                or (
                    len(query_token) >= 4
                    and len(heading_token) >= 4
                    and query_token[:2] == heading_token[:2]
                    and one_edit_apart(query_token, heading_token)
                )
                for heading_token in heading_tokens
            )
        }

    candidates: list[tuple[float, int, str, dict, set[str]]] = []
    for rank, hit, heading_tokens, tokens in documents:
        identity = str(hit.get("id") or "")
        if not identity or identity in selected_ids:
            continue
        semantic_score = hit.get("@search.rerankerScore")
        if not isinstance(semantic_score, (int, float)) or semantic_score < semantic_floor:
            continue
        novel_heading = heading_query_terms(heading_tokens) - covered
        score = sum(weights[token] for token in novel_heading)
        if score < minimum_score:
            continue
        candidates.append((-score, rank, identity, hit, novel_heading))

    expanded = list(selected)
    added = 0
    for _negative_score, _rank, identity, hit, _novel in sorted(candidates):
        if len(expanded) >= budget:
            break
        heading = set(
            canonical_tokens(
                " ".join(
                    str(hit.get(field) or "")
                    for field in ("section_heading", "heading")
                ),
                min_chars=4,
            )
        )
        still_novel = heading_query_terms(heading) - covered
        if sum(weights[token] for token in still_novel) < minimum_score:
            continue
        expanded.append(hit)
        selected_ids.add(identity)
        covered.update(still_novel)
        covered.update(query & set(canonical_tokens(str(hit.get("body") or ""), min_chars=4)))
        added += 1

    return expanded, added


def expand_policy_coverage_after_duplicate_collapse(
    selected: list[dict],
    ranked: list[dict],
    *,
    scenario: str,
    by_search_id: dict[str, dict],
) -> tuple[list[dict], list[str], dict[str, dict], int]:
    """Apply the coverage budget to distinct policy content, not raw hits.

    Rule-only rescue is deliberately uncapped before the repository's exact
    duplicate pass. Coverage must follow the same rule: provisional copies cannot
    consume five slots and prevent a distinct requested aspect from being seen.
    The original hits remain in the returned list so the receipt still reports
    every collapsed copy and its representative.
    """

    def coverage_identity(hit: dict) -> tuple[str, str]:
        identity = str(hit.get("id") or "")
        candidate = by_search_id.get(identity)
        payload = (candidate or {}).get("payload")
        if not isinstance(payload, dict):
            return ("id", identity)
        return (
            "fingerprint",
            policy_semantic_fingerprint(
                payload,
                governing_extras=candidate.get("governing_extras"),
            ),
        )

    seen_groups: set[tuple[str, str]] = set()
    distinct_selected: list[dict] = []
    for hit in selected:
        group = coverage_identity(hit)
        if group in seen_groups:
            continue
        seen_groups.add(group)
        distinct_selected.append(hit)

    distinct_ranked = list(distinct_selected)
    for hit in ranked:
        group = coverage_identity(hit)
        if group in seen_groups:
            continue
        seen_groups.add(group)
        distinct_ranked.append(hit)

    expanded_distinct, added = expand_policy_query_coverage(
        distinct_selected,
        distinct_ranked,
        scenario=scenario,
    )
    original_ids = {str(hit.get("id") or "") for hit in selected}
    expanded = list(selected)
    expanded.extend(
        hit
        for hit in expanded_distinct
        if str(hit.get("id") or "") not in original_ids
    )
    distinct_ids, duplicates = collapse_duplicate_policies(
        expanded, by_search_id
    )
    return expanded, distinct_ids, duplicates, added


@dataclass(frozen=True, slots=True)
class ProjectCaseAnswer:
    """The answer plus the facts only the decider knows about how it decided.

    Returned **only** when a caller passes ``with_context=True`` to
    :func:`answer_project_case`; every existing caller keeps receiving the bare
    ``response`` dict unchanged. The split exists because an audited receipt must
    name the exact published version the answer was drawn from, and the only
    honest source of that is the load this function actually performed. Reading
    "the active version" again after the call is a different question asked at a
    different time: a project that publishes mid-call would make the receipt
    attest to a version the answer never saw.

    ``context`` carries what is knowable and nothing else — the version the
    decider loaded, where that load came from, and the search index it consulted
    when retrieval ran. Keys are absent rather than null-filled when the path
    taken never produced them.
    """

    response: dict
    context: dict


@dataclass(frozen=True, slots=True)
class ProjectPolicyRetrieval:
    """The filtered policy records plus the version/search context that selected them.

    This is deliberately not a decision. It carries a precision-ranked subset
    from the same approved index and uses the same rule slicing and payload
    fitting, but no classifier, plan, verdict, explanation, citation synthesis,
    or receipt lifecycle has run.
    """

    response: dict
    context: dict


def _record_version_context(
    context: dict | None,
    *,
    source: str,
    version_id: object = None,
    version_number: object = None,
    effective_from: object = None,
    effective_to: object = None,
) -> None:
    """Note the version the decider loaded, when a caller asked to be told.

    A no-op without a context dict, so the default path costs nothing and cannot
    change behaviour. Values are read defensively because the version object is
    stubbed in tests and may not carry effective dates.
    """

    if context is None:
        return
    context["version_source"] = source
    context["policy_version_id"] = str(version_id) if version_id else None
    context["version_number"] = version_number
    context["effective_from"] = effective_from
    context["effective_to"] = effective_to


def published_policy_search_id(payload: dict) -> str | None:
    """The stable search key for a published policy document."""

    envelope = payload.get("envelope") or {}
    policy_version_id = envelope.get("policy_version_id")
    provision_key = envelope.get("provision_key")
    if not policy_version_id or not provision_key:
        return None
    return policy_document_id(policy_version_id=str(policy_version_id), provision_key=str(provision_key))


def _max_score(scores: list) -> float | None:
    present = [s for s in scores if isinstance(s, (int, float))]
    return max(present) if present else None


def _identity(candidate: dict) -> dict:
    return {
        "provision_id": candidate["provision_id"],
        "provision_key": candidate["provision_key"],
        "heading_path": candidate["heading_path"],
        "rules": candidate["rules"],
    }


def collapse_duplicate_policies(
    hits: list[dict], by_search_id: dict[str, dict]
) -> tuple[list[str], dict[str, dict]]:
    """Group the ranked hits by what their policies *govern*, before the budget.

    WHY THIS RUNS BEFORE THE RETENTION BUDGET

    The budget answers "how many policies may one case read". A corpus that holds
    the same policy twice — two provisions extracted from two document versions,
    two ids, two keys, one identical set of terms — spends two of those slots
    saying one thing. That is what denied receipt
    `76a5e936-7ea4-4cc3-828a-0fb099c2ee5b` its verdict: two copies of `2.1
    Standard entitlement` and two of `4.2 Accidental damage` filled four of five
    slots, and `3.1 Standard refresh interval`, the provision that decides the
    case, ranked sixth. Collapsing after the cut would repair nothing, because by
    then the slot is already spent.

    WHAT IT MAY AND MAY NOT CONCLUDE

    Two hits collapse only on an exact match of
    :func:`policy_semantic_fingerprint` — everything the policy governs, with
    only identity and provenance removed. A hit whose policy is not among the
    candidates cannot be fingerprinted, and is never collapsed: matching on
    absence would set a policy aside on the strength of what was not recorded
    about it.

    THE REPRESENTATIVE, AND WHY IT IS CHOSEN THIS WAY

    Within a group the representative is the copy with the highest score, ties
    broken by search document id. Score first because that is the copy search
    ranked best; id second because two copies of one policy score *identically*
    far more often than not, and a tie resolved by whichever order the index
    happened to return would make the receipt — and the decision hash — differ
    between two runs of the same question. The group takes its position in the
    ranking from its best-ranked member, so collapsing never moves a policy up
    past one that outranked it.

    Returns the distinct search document ids in ranked order, and a map from each
    collapsed copy's search id to ``{"representative_search_id", "rank",
    "score"}`` — the copy's *own* rank and score, so the report can say where it
    really surfaced without claiming it was read.
    """

    groups: dict[str, list[tuple[int, str, object]]] = {}
    order: list[str] = []
    distinct: list[str] = []

    for rank, hit in enumerate(hits):
        hid = hit.get("id")
        if hid is None:
            continue
        hid = str(hid)
        candidate = by_search_id.get(hid)
        payload = (candidate or {}).get("payload")
        if not isinstance(payload, dict):
            # Not fingerprintable, so not provably a copy of anything. It stands
            # on its own, exactly as it did before this pass existed.
            distinct.append(hid)
            continue
        fingerprint = policy_semantic_fingerprint(
            payload, governing_extras=candidate.get("governing_extras")
        )
        if fingerprint not in groups:
            groups[fingerprint] = []
            order.append(fingerprint)
        groups[fingerprint].append((rank, hid, hit.get("@search.score")))
        if len(groups[fingerprint]) == 1:
            distinct.append(hid)

    duplicates: dict[str, dict] = {}
    for fingerprint in order:
        members = groups[fingerprint]
        if len(members) < 2:
            continue
        representative = sorted(
            members,
            key=lambda m: (-(m[2] if isinstance(m[2], (int, float)) else float("-inf")), m[1]),
        )[0]
        placeholder = members[0][1]
        # The group holds its best-ranked member's place in the ordering, and the
        # representative stands in that place — so a tie resolved by id cannot
        # reorder the retained set.
        distinct[distinct.index(placeholder)] = representative[1]
        for rank, hid, score in members:
            if hid == representative[1]:
                continue
            duplicates[hid] = {
                "representative_search_id": representative[1],
                "rank": rank,
                "score": score,
            }

    return distinct, duplicates


def order_by_normative_diversity(
    distinct: list[str], by_search_id: dict[str, dict]
) -> tuple[list[str], set[str]]:
    """Reorder the surviving candidates so one budget buys one thing once.

    WHY ORDERING AND NOT COLLAPSING

    :func:`collapse_duplicate_policies` may only act on proof: two records that
    are identical in everything stored. The live hardware pair fails that test
    honestly — one copy records forty-two `related_rule_ids` and the other
    records none — and so both survive, and between them they took ranks 0 and 3
    of a five-policy budget while the provision that decided the case ranked
    sixth. Equality was the wrong tool, but rank alone is not enough either:
    ranking answers "how well does this match" and never "have I already read
    this".

    So this reorders, and only reorders. Candidates are grouped by
    :func:`policy_normative_group_key` — what they require, with the drafter's
    read-together markers withheld and supersession kept — and the highest-ranked
    member of each group is offered first, in the rank order of those firsts.
    Only once every distinct normative group has been offered are the remaining
    members considered, again in rank order.

    WHAT IT DOES NOT CLAIM

    A member held back is not a duplicate and is never reported as one. It keeps
    its own rank and score, and if it ends up outside the budget it carries
    ``outside_budget`` like any other policy that did not place — which is now
    what that reason means: not "ranked too low" but "did not place inside the
    retention budget", by rank or by this ordering. Deferring is not discarding:
    a group's second member is read whenever the budget reaches it.

    Returns the reordered ids and the subset that was deferred behind a
    same-group member. Being deferred is not the same as being *displaced*: a
    member that ranked outside the retention budget anyway lost nothing to this
    pass. The caller, which is the only party that knows the budget, intersects
    the two to report what the ordering actually cost.
    """

    firsts: list[str] = []
    later: list[str] = []
    seen: dict[str, str] = {}

    for hid in distinct:
        candidate = by_search_id.get(hid)
        payload = (candidate or {}).get("payload")
        if not isinstance(payload, dict):
            # Nothing to group on. Never grouped, never deferred.
            firsts.append(hid)
            continue
        key = policy_normative_group_key(
            payload, governing_extras=candidate.get("governing_extras")
        )
        if key in seen:
            later.append(hid)
        else:
            seen[key] = hid
            firsts.append(hid)

    return firsts + later, set(later)


def select_retained(
    candidates: list[dict],
    hits: list[dict],
    *,
    budget: int,
    in_budget_ids: set[str] | None = None,
    duplicates: dict[str, dict] | None = None,
) -> dict:
    """Split the candidate policies into the ones retrieval kept and the ones it
    discarded, by mapping the ranked policy hits back to the published payloads.

    ``candidates`` each carry their ``search_document_id`` (from
    :func:`published_policy_search_id`); ``hits`` are the ranked search results,
    each an ``id`` (a policy search key) and its ``@search.score``. A policy is
    retained when it ranks inside ``budget``; otherwise it is discarded, and a
    policy that surfaced lower in the scan is told apart from one that never
    surfaced at all.

    ``in_budget_ids`` and ``duplicates`` come from
    :func:`collapse_duplicate_policies` and are optional: without them the budget
    is applied to raw rank, which is what happens when the caller has not
    collapsed anything. With them, the budget is applied to the *distinct*
    policies while ``best_rank`` and ``best_score`` stay the raw ones — where the
    policy really surfaced is a fact about the search, and renumbering it to hide
    a collapse would put a rank in the receipt that never happened.

    Returns ``{"retained", "discarded", "considered", "policies_retrieved"}``.
    ``considered`` lists every candidate in document order with a ``retained``
    flag — every raw candidate, including each collapsed copy, so the narrowing is
    fully visible (constraint 10); ``retained`` is ordered by how high the policy
    ranked. No payload rides in any of these entries — they are the report, not
    the records.
    """

    ranked: list[tuple[int, str, object]] = []
    for rank, hit in enumerate(hits):
        hid = hit.get("id")
        if hid is None:
            continue
        ranked.append((rank, str(hid), hit.get("@search.score")))

    duplicates = duplicates or {}
    key_by_search_id = {
        str(c.get("search_document_id")): c.get("provision_key")
        for c in candidates
        if c.get("search_document_id")
    }

    retained: list[dict] = []
    discarded: list[dict] = []
    considered: list[dict] = []

    for candidate in candidates:
        key = candidate.get("search_document_id")
        keys = {str(key)} if key else set()
        matches = [(rank, hid, score) for (rank, hid, score) in ranked if hid in keys]
        if in_budget_ids is None:
            in_budget = [m for m in matches if m[0] < budget]
        else:
            in_budget = [m for m in matches if m[1] in in_budget_ids]
        identity = _identity(candidate)
        collapsed = duplicates.get(str(key)) if key else None

        if collapsed is not None:
            # It surfaced, and an identically-governing policy surfaced above it.
            # Its own rank and score are kept — it really did rank there — and the
            # representative is named rather than implied, so a reader can see
            # that the content reached the gather without this record doing so.
            representative = collapsed.get("representative_search_id")
            entry = {
                **identity,
                "retained": False,
                "best_rank": collapsed.get("rank"),
                "best_score": collapsed.get("score"),
                "matched_policies": 0,
                "discard_reason": DISCARD_DUPLICATE_POLICY_CONTENT,
                "duplicate_of_provision_key": key_by_search_id.get(str(representative)),
            }
            discarded.append(entry)
        elif in_budget:
            entry = {
                **identity,
                "retained": True,
                "best_rank": min(m[0] for m in in_budget),
                "best_score": _max_score([m[2] for m in matches]),
                "matched_policies": len({m[1] for m in in_budget}),
            }
            retained.append(entry)
        else:
            if matches:
                best_rank: int | None = min(m[0] for m in matches)
                best_score = _max_score([m[2] for m in matches])
                reason = DISCARD_OUTSIDE_BUDGET
            else:
                best_rank = None
                best_score = None
                reason = DISCARD_NO_MATCH
            entry = {
                **identity,
                "retained": False,
                "best_rank": best_rank,
                "best_score": best_score,
                "matched_policies": 0,
                "discard_reason": reason,
            }
            discarded.append(entry)
        considered.append(entry)

    retained.sort(key=lambda e: e["best_rank"] if e["best_rank"] is not None else 1_000_000)
    return {
        "retained": retained,
        "discarded": discarded,
        "considered": considered,
        "policies_retrieved": len(ranked),
    }


async def load_project_scope(session: AsyncSession, policy_set_id) -> dict:
    """Read the project's active published policies.

    Project-wide cases intentionally use published policies at the active approved
    version only. A project with draft/live candidate rules but no active approved
    version is therefore not an empty search result; it has no published project
    scope to test yet.
    """

    psid = policy_set_id if isinstance(policy_set_id, uuid.UUID) else uuid.UUID(str(policy_set_id))
    active_version = await active_version_for_policy_set(session, psid)
    if active_version is None:
        return {
            "has_published_version": False,
            "active_version_id": None,
            "active_version_number": None,
            "active_version_effective_from": None,
            "active_version_effective_to": None,
            "candidates": [],
            "excluded": [],
        }

    payloads = await published_case_payloads_with_extras(session, psid)

    candidates: list[dict] = []
    excluded: list[dict] = []
    for payload, governing_extras in payloads:
        envelope = payload.get("envelope") or {}
        rule_count = len(payload.get("rules") or [])
        provision_key = str(envelope.get("provision_key") or "")
        if rule_count <= 0:
            excluded.append(
                {
                    "provision_id": None,
                    "provision_key": provision_key,
                    "heading_path": envelope.get("heading_path") or [],
                    "reason": "no_published_rules",
                }
            )
            continue
        search_document_id = published_policy_search_id(payload)
        if search_document_id is None:  # pragma: no cover - active published payloads carry this envelope
            continue
        candidates.append(
            {
                "provision_id": envelope.get("provision_id"),
                "provision_key": provision_key,
                "heading_path": envelope.get("heading_path") or [],
                "rules": rule_count,
                "policy_version_id": str(envelope.get("policy_version_id")),
                "version_number": envelope.get("version_number"),
                "search_document_id": search_document_id,
                "payload": payload,
                # Governing fields the lean payload does not carry, read only by
                # the duplicate-policy equivalence test. Never sent to a gather.
                "governing_extras": governing_extras,
            }
        )

    return {
        "has_published_version": True,
        "active_version_id": str(active_version.id),
        "active_version_number": active_version.version_number,
        # The version's effective window, carried so an audited receipt can name
        # the period the deciding version was in force without a second read
        # around a call that may straddle a publication. Additive: every existing
        # reader of this dict indexes the keys it already knew.
        "active_version_effective_from": getattr(active_version, "effective_from", None),
        "active_version_effective_to": getattr(active_version, "effective_to", None),
        "candidates": candidates,
        "excluded": excluded,
    }


def _combined_chars(records: list[dict]) -> int:
    """The exact transport size of these records as the gather will see them.

    Measured by building the same ``to_compact`` payload the gather is handed,
    not by summing the policies. A sum is not the size: the wrapper, the list
    separators and the per-entry keys are real characters, and a budget check
    that under-counted by a few hundred would let through exactly the payload it
    exists to refuse.
    """

    return len(
        to_compact({"policies": [{"policy": r["policy"], "record": r["payload"]} for r in records]})
    )


def _size_report(records: list[dict]) -> dict:
    """How large the retained policies' combined record is, against the one-gather
    budget — measured and reported so a payload that must be capped is a visible
    decision, never a silent trim (constraint 11)."""

    size = _combined_chars(records)
    return {
        "combined_chars": size,
        "budget_chars": PAYLOAD_BUDGET_CHARS,
        "oversize": size > PAYLOAD_BUDGET_CHARS,
    }


def fit_within_payload_budget(
    pairs: list[tuple[dict, dict]], *, budget_chars: int = PAYLOAD_BUDGET_CHARS
) -> tuple[list[tuple[dict, dict]], list[dict]]:
    """Keep the highest-ranked *whole* policies that fit one grounded pass.

    WHY THIS EXISTS

    Retrieval ranks policies and keeps the top few. Rank says nothing about size,
    and the two came apart in production: a question about annual vacation
    retained the Annual Vacation policy at rank 0 (ten rules) alongside a Table of
    Violations and Penalties at rank 3 (seventy-four rules). Their combined record
    was 229,389 characters against a 200,000 budget, so the gather refused the
    *whole set* and the reviewer was told nothing — not because the policy that
    governed their case was unreadable, but because a policy that did not govern
    it was large. A question with a perfectly good answer in the corpus returned
    no answer at all.

    THE RULE, AND WHAT IT REFUSES TO DO

    Policies are offered in rank order and each is admitted only if its **whole**
    record still fits beside everything already admitted. Three things follow, and
    each is a deliberate refusal of an easier design:

      * **No policy is ever trimmed.** Dropping some rules to make a policy fit
        would let an answer be composed from part of a policy while presenting as
        that policy's answer — the one narrowing a reviewer cannot see, because
        nothing on screen would say a rule went unread.
      * **No policy is silently omitted.** One that does not fit is returned to
        the caller with ``outside_payload_budget``, and shows up in `considered`
        and in the discarded counts like any other narrowing.
      * **A large policy does not end the scan.** Rank order is preserved and
        later, smaller policies are still tried, so one oversized record costs
        only itself. Stopping at the first overflow would discard policies that
        fit for no reason a reviewer could defend.

    WHEN THE FIRST POLICY ALONE IS TOO LARGE

    Nothing fits, and this returns it anyway — as the single kept pair, with an
    empty discard list. That is deliberate: dropping it would leave an empty
    retained set, which reads as "no published policy matched your question" when
    the truth is "the policy that matched is larger than one pass can read". The
    honest outcome is the existing oversize refusal, with `size.oversize` true and
    the gather declining, so this hands the problem to the code that already
    reports it truthfully rather than inventing a second story.

    ``pairs`` is ``(report entry, record)`` in rank order. Returns the pairs that
    fit and the report entries that did not.
    """

    kept: list[tuple[dict, dict]] = []
    over_budget: list[dict] = []

    for entry, record in pairs:
        # Measured against the real transport each time rather than accumulated,
        # because the combined encoding is not the sum of its parts.
        if _combined_chars([r for _, r in kept] + [record]) <= budget_chars:
            kept.append((entry, record))
        else:
            over_budget.append(entry)

    if not kept and pairs:
        # The highest-ranked policy does not fit on its own. Keep it and let the
        # gather refuse honestly; see above for why an empty retained set would
        # be the worse answer.
        first = pairs[0]
        kept.append(first)
        over_budget = [entry for entry, _ in pairs[1:]]

    return kept, over_budget


def _mark_over_payload_budget(
    entry: dict, *, retained: list[dict], discarded: list[dict]
) -> None:
    """Move one report entry from retained to discarded, in place.

    In place because `considered` holds the *same* dict objects as `retained` and
    `discarded` — that is how the narrowing report stays one description rather
    than three that can disagree. Rewriting the entry here therefore updates
    every list that mentions it, and `best_rank` and `best_score` survive: the
    policy really did surface and really did rank where it ranked, and a reader
    comparing it against what was kept needs both.

    WHY `rule_selection` DOES NOT SURVIVE

    Slicing runs before fitting, so a large policy set aside here already had a
    selection written onto its entry by :func:`_sliced_record`. That selection
    describes rules that were *chosen*, not rules that were *read* — this policy
    reached no gather at all, whole or sliced. Leaving it on would put a
    `selected_rule_ids` list on the receipt for a policy nothing was evaluated
    from, and the v2 decision hash seals those ids, so the seal would cover rule
    text no model ever saw. The honest report of "nothing was selected from it"
    is no selection, which is exactly what `_policy_ref` documents as the absent
    case. The count of sliced policies is taken from what actually fit, so it
    stays consistent with this.

    A policy that *was* evaluated keeps its selection, including the sole
    oversized policy: `fit_within_payload_budget` keeps that one rather than
    discarding it, so it never reaches here, and its slice is the narrowest
    relevant set presented — honestly — as oversize.
    """

    entry["retained"] = False
    entry["discard_reason"] = DISCARD_OUTSIDE_PAYLOAD_BUDGET
    entry["matched_policies"] = 0
    entry.pop("rule_selection", None)
    for index, candidate in enumerate(retained):
        if candidate is entry:
            retained.pop(index)
            break
    discarded.append(entry)


def _bare_considered(candidates: list[dict]) -> list[dict]:
    """The candidate policies listed without a retrieval verdict — for the states
    where retrieval could not produce one (unavailable, failed, index-empty). They
    are still shown, so a reviewer sees the testable policies the project holds and
    the top-level status says why none was retained."""

    return [{**_identity(c), "retained": False} for c in candidates]


def _retrieval_block(
    status: str,
    *,
    considered: list[dict],
    retained: list[dict],
    discarded: list[dict],
    excluded: list[dict],
    policies_retrieved: int,
    reason: str | None = None,
    policies_over_payload_budget: int = 0,
    policies_rule_sliced: int = 0,
    policies_duplicate_collapsed: int = 0,
    policies_diversity_deferred: int = 0,
    projection_profile: str | None = None,
    projection_ready: bool | None = None,
    policy_documents_matched: int = 0,
    rule_documents_matched: int = 0,
    policies_elevated_by_rule: int = 0,
    rule_index_state: str | None = None,
    retrieval_method: str = RETRIEVAL_METHOD,
    precision_mode: str | None = None,
    semantic_candidates: int | None = None,
    semantic_selected: int | None = None,
    semantic_largest_gap: float | None = None,
    semantic_cutoff_score: float | None = None,
    semantic_elbow_applied: bool | None = None,
    direct_policy_order: str | None = None,
    coverage_expanded_policies: int | None = None,
    coverage_semantic_floor: float | None = None,
    rule_rescue_candidates: int | None = None,
    rule_rescued_policies: int | None = None,
    rule_rescue_floor: float | None = None,
    rule_rescue_margin: float | None = None,
    rule_semantic_window: int | None = None,
    rule_semantic_candidates: int | None = None,
) -> dict:
    block = {
        "status": status,
        "method": retrieval_method,
        "policy_budget": RETRIEVAL_POLICY_BUDGET,
        "policy_scan": RETRIEVAL_POLICY_SCAN,
        "rule_scan": RETRIEVAL_RULE_SCAN,
        "policies_retrieved": policies_retrieved,
        # Kept temporarily for API compatibility with callers already reading the
        # old field name; the value now counts policy documents, not clauses.
        "clauses_retrieved": policies_retrieved,
        "policies_considered": len(considered),
        "policies_retained": len(retained),
        "policies_discarded": len(discarded),
        "policies_untestable": len(excluded),
        # The second narrowing, disclosed in its own right. A policy set aside
        # for size ranked *inside* the retention budget, so folding it into
        # `policies_discarded` alone would let a reader conclude search rejected
        # it. Both numbers are reported; this one is a subset of that one.
        "payload_budget_chars": PAYLOAD_BUDGET_CHARS,
        "policies_over_payload_budget": policies_over_payload_budget,
        # The third: how many retained policies were large enough to be read
        # rule by rule rather than whole. The per-policy counts are on each
        # `considered` entry's `rule_selection`; this is the headline so a reader
        # knows to look for them.
        "large_policy_rule_threshold": LARGE_POLICY_RULE_THRESHOLD,
        "selected_rule_budget": SELECTED_RULE_BUDGET,
        "policies_rule_sliced": policies_rule_sliced,
        # The fourth, and the only one that happens *before* the retention
        # budget: copies of a policy already retained, collapsed so they cannot
        # each consume an answer slot. Also a subset of `policies_discarded`, and
        # the one discard whose content still reached the gather — in the
        # representative each collapsed entry names.
        "policies_duplicate_collapsed": policies_duplicate_collapsed,
        # The fifth, and the only one that is not a discard at all: candidates
        # offered *later* than their rank because a policy requiring the same
        # thing was offered first. Reported with the ordering that produced it,
        # because without both a reader cannot explain why a rank-3 policy sits
        # outside the budget while a rank-5 policy was retained.
        "policy_selection_order": POLICY_SELECTION_ORDER,
        "policies_diversity_deferred": policies_diversity_deferred,
        # What was searched, and whether it could be. `projection_profile` names
        # the rendering contract the corpus was matched under — a query and the
        # text it is scored against are only comparable when both were made
        # under it — and the three counts say where the ranking came from.
        # `policies_elevated_by_rule` is the one that answers "did rule-level
        # retrieval actually do anything here": it counts provisions the policy
        # documents' own ranking placed lower or not at all, and one of their
        # rows lifted.
        "projection_profile": projection_profile,
        "projection_ready": projection_ready,
        "policy_documents_matched": policy_documents_matched,
        "rule_documents_matched": rule_documents_matched,
        "policies_elevated_by_rule": policies_elevated_by_rule,
        "rule_index_state": rule_index_state,
    }
    if precision_mode is not None:
        block["precision_mode"] = precision_mode
        block["semantic_candidates"] = semantic_candidates
        block["semantic_selected"] = semantic_selected
        block["semantic_largest_gap"] = semantic_largest_gap
        block["semantic_cutoff_score"] = semantic_cutoff_score
        block["semantic_elbow_applied"] = semantic_elbow_applied
        block["direct_policy_order"] = direct_policy_order
        block["coverage_expanded_policies"] = coverage_expanded_policies
        block["coverage_semantic_floor"] = coverage_semantic_floor
        block["rule_rescue_candidates"] = rule_rescue_candidates
        block["rule_rescued_policies"] = rule_rescued_policies
        block["rule_rescue_floor"] = rule_rescue_floor
        block["rule_rescue_margin"] = rule_rescue_margin
        block["rule_semantic_window"] = rule_semantic_window
        block["rule_semantic_candidates"] = rule_semantic_candidates
    if reason is not None:
        block["reason"] = reason
    return block


def _project_response(
    *,
    policy_set_key: str,
    status: str,
    considered: list[dict],
    retained: list[dict],
    discarded: list[dict],
    excluded: list[dict],
    policies_retrieved: int,
    evaluation: dict | None,
    size: dict,
    reason: str | None = None,
    policies_over_payload_budget: int = 0,
    policies_rule_sliced: int = 0,
    policies_duplicate_collapsed: int = 0,
    policies_diversity_deferred: int = 0,
    projection_profile: str | None = None,
    projection_ready: bool | None = None,
    policy_documents_matched: int = 0,
    rule_documents_matched: int = 0,
    policies_elevated_by_rule: int = 0,
    rule_index_state: str | None = None,
    policy_records: list[dict] | None = None,
    retrieval_method: str = RETRIEVAL_METHOD,
    precision_mode: str | None = None,
    semantic_candidates: int | None = None,
    semantic_selected: int | None = None,
    semantic_largest_gap: float | None = None,
    semantic_cutoff_score: float | None = None,
    semantic_elbow_applied: bool | None = None,
    direct_policy_order: str | None = None,
    coverage_expanded_policies: int | None = None,
    coverage_semantic_floor: float | None = None,
    rule_rescue_candidates: int | None = None,
    rule_rescued_policies: int | None = None,
    rule_rescue_floor: float | None = None,
    rule_rescue_margin: float | None = None,
    rule_semantic_window: int | None = None,
    rule_semantic_candidates: int | None = None,
) -> dict:
    response = {
        "scope": SCOPE_PROJECT,
        "policy_set_key": policy_set_key,
        "retrieval": _retrieval_block(
            status,
            considered=considered,
            retained=retained,
            discarded=discarded,
            excluded=excluded,
            policies_retrieved=policies_retrieved,
            reason=reason,
            policies_over_payload_budget=policies_over_payload_budget,
            policies_rule_sliced=policies_rule_sliced,
            policies_duplicate_collapsed=policies_duplicate_collapsed,
            policies_diversity_deferred=policies_diversity_deferred,
            projection_profile=projection_profile,
            projection_ready=projection_ready,
            policy_documents_matched=policy_documents_matched,
            rule_documents_matched=rule_documents_matched,
            policies_elevated_by_rule=policies_elevated_by_rule,
            rule_index_state=rule_index_state,
            retrieval_method=retrieval_method,
            precision_mode=precision_mode,
            semantic_candidates=semantic_candidates,
            semantic_selected=semantic_selected,
            semantic_largest_gap=semantic_largest_gap,
            semantic_cutoff_score=semantic_cutoff_score,
            semantic_elbow_applied=semantic_elbow_applied,
            direct_policy_order=direct_policy_order,
            coverage_expanded_policies=coverage_expanded_policies,
            coverage_semantic_floor=coverage_semantic_floor,
            rule_rescue_candidates=rule_rescue_candidates,
            rule_rescued_policies=rule_rescued_policies,
            rule_rescue_floor=rule_rescue_floor,
            rule_rescue_margin=rule_rescue_margin,
            rule_semantic_window=rule_semantic_window,
            rule_semantic_candidates=rule_semantic_candidates,
        ),
        "considered": considered,
        "excluded": excluded,
        "evaluation": evaluation,
        "size": size,
    }
    if policy_records is not None:
        response["policies"] = policy_records
    return response


async def _provision_in_project(session: AsyncSession, *, policy_set, provision_id):
    """The named provision, or `ProvisionNotInProject` if it is not this project's.

    Kept apart from "this policy is not published": an id that names nothing, or
    names a policy in a different project, is a caller error the endpoint answers
    404 to. A policy that exists here but is absent from the published version is
    a legitimate question with an honest answer, and must not be reported as if
    the reviewer had asked for something that does not exist.
    """

    pid = provision_id if isinstance(provision_id, uuid.UUID) else uuid.UUID(str(provision_id))
    provision = await session.get(DocumentProvision, pid)
    if provision is None:
        raise ProvisionNotInProject(f"No provision with id {provision_id!r}")
    if str(provision.policy_set_id) != str(policy_set.id):
        raise ProvisionNotInProject(
            f"Provision {provision_id!r} does not belong to project {policy_set.key!r}"
        )
    return provision


async def _answer_single_scope(
    session: AsyncSession,
    *,
    policy_set,
    provision_id,
    scenario: str,
    reasoning_effort: str,
    additional_instructions: str = "",
    context: dict | None = None,
) -> dict:
    """The reviewer chose one policy: bypass retrieval and answer that policy.

    Retrieval does not run — the narrowing a reviewer would ask retrieval for has
    already been done by choosing the policy. The policy is projected from the
    project's *active approved version*, the same source the project scope reads,
    so naming a policy cannot silently switch the answer to the draft set. It is
    evaluated through the same multi-policy gather (a set of one), so a single-scope
    answer carries the same per-policy citations and fabrication guarantees as a
    project one.

    A provision can exist and still not be answerable here, in two different ways
    that a reviewer acts on differently: the project may have nothing published at
    all, or this particular policy may not be in the version that is published.
    Both are reported, and neither is answered from drafts.
    """

    provision = await _provision_in_project(session, policy_set=policy_set, provision_id=provision_id)

    def unanswerable(status: str, reason: str) -> dict:
        return {
            "scope": SCOPE_SINGLE,
            "policy_set_key": policy_set.key,
            "provision": {
                "provision_id": str(provision.id),
                "provision_key": provision.provision_key,
                "heading_path": provision.heading_path_json,
                "rules": 0,
            },
            "retrieval": {"status": status, "reason": reason},
            "evaluation": None,
            "size": _size_report([]),
        }

    version = await active_version_for_policy_set(session, policy_set.id)
    if version is None:
        _record_version_context(context, source="single_scope_no_published_version")
        return unanswerable(
            RETRIEVAL_NO_PUBLISHED_VERSION,
            "this project has no published version yet, so there is nothing approved to test against",
        )

    _record_version_context(
        context,
        source="single_scope",
        version_id=getattr(version, "id", None),
        version_number=getattr(version, "version_number", None),
        effective_from=getattr(version, "effective_from", None),
        effective_to=getattr(version, "effective_to", None),
    )

    published = await published_case_payload_with_extras_for_policy(
        session, policy_set.id, provision.provision_key
    )
    if published is None:
        return unanswerable(
            RETRIEVAL_POLICY_NOT_PUBLISHED,
            "this policy is not in the published version; only published policies are tested here",
        )
    payload, governing_extras = published

    envelope = payload.get("envelope") or {}
    identity = {
        "provision_id": envelope.get("provision_id"),
        "provision_key": envelope.get("provision_key"),
        "heading_path": envelope.get("heading_path"),
        "rules": len(payload.get("rules") or []),
    }
    # A reviewer who names a policy that is really a table gets the same
    # rule-level narrowing the project scope performs, and the same disclosure.
    # Refusing to slice here would hand them the oversize non-answer this exists
    # to remove, on the one path they took deliberately.
    record = _sliced_record(
        identity, payload, scenario=scenario, governing_extras=governing_extras
    )
    gather_started = time.perf_counter()
    evaluation = await answer_case_over_policies(
        [record],
        scenario=scenario,
        reasoning_effort=reasoning_effort,
        **_gather_kwargs(additional_instructions),
    )
    if context is not None:
        timings = context.setdefault("timings_ms", {})
        timings.update(getattr(evaluation, "stage_latency_ms", {}))
        timings["gather_total"] = max(
            0, int((time.perf_counter() - gather_started) * 1000)
        )

    return {
        "scope": SCOPE_SINGLE,
        "policy_set_key": policy_set.key,
        "provision": identity,
        "retrieval": {
            "status": RETRIEVAL_BYPASSED,
            "reason": "the reviewer chose one policy; retrieval does not run",
        },
        "evaluation": evaluation,
        "size": _size_report([record]),
    }


def _sliced_record(
    entry: dict,
    payload: dict,
    *,
    scenario: str,
    governing_extras: dict | None = None,
    rule_hits: dict[str, int] | None = None,
    rule_projections: dict[str, str] | None = None,
    rule_index_state: str = RULE_INDEX_UNAVAILABLE,
) -> dict:
    """One retained policy's record, rule-selected when the policy is a table.

    Writes the selection back onto ``entry`` — the *same* dict the narrowing
    report holds — so `considered` says "74 rules · 8 selected for this case"
    without a second description that could disagree with this one. A policy at
    or under the threshold records `whole_policy` and its payload is the object
    it always was.

    The selection is written before the payload-budget fitting pass runs, so it
    is provisional until that pass decides: a policy this narrowed and the
    fitting pass then set aside has its selection removed again by
    :func:`_mark_over_payload_budget`, because nothing was read from it.

    ``rule_hits`` is the rule index's own ranking of this policy's rules, and
    ``rule_projections`` their English projections — both read straight off the rule
    documents the search returned. Passing them is what lets the selection rank a
    rendered question against rendered rules and fuse that with the index's own
    ranking; passing neither leaves the selection exactly as it was.
    """

    policy = {
        "provision_id": entry["provision_id"],
        "provision_key": entry["provision_key"],
        "heading_path": entry["heading_path"],
    }
    selected, selection = select_rules_for_scenario(
        payload,
        policy=policy,
        scenario=scenario,
        governing_extras=governing_extras,
        rule_hits=rule_hits,
        rule_projections=rule_projections,
        rule_index_state=rule_index_state,
    )
    entry["rule_selection"] = selection
    return {"policy": policy, "payload": selected}


async def _answer_project_scope(
    session: AsyncSession,
    *,
    policy_set,
    scenario: str,
    reasoning_effort: str,
    additional_instructions: str = "",
    context: dict | None = None,
    policies_only: bool = False,
) -> dict:
    """No policy was named: retrieve the ones that bear on the question, discard
    the rest, and evaluate only the survivors — never the whole set.

    ``additional_instructions`` is deliberately absent from everything above the
    gather. The embedding below is taken over ``scenario`` alone and the search
    is run on ``scenario`` alone, because retrieval decides *which policies are
    read at all* — and a caller who could steer that could steer the answer past
    the policy that governs it, by shifting the query away from it. Which
    policies bear on a question is a property of the question and the corpus,
    never of the caller's presentation preferences.
    """

    timings: dict[str, int] | None = None
    if context is not None:
        timings = context.setdefault("timings_ms", {})

    def elapsed_ms(started: float) -> int:
        return max(0, int((time.perf_counter() - started) * 1000))

    scope_started = time.perf_counter()
    scope = await load_project_scope(session, policy_set.id)
    if timings is not None:
        timings["scope_load"] = elapsed_ms(scope_started)
    candidates = scope["candidates"]
    excluded = scope["excluded"]
    active_version_id = scope.get("active_version_id")

    _record_version_context(
        context,
        source="project_scope" if active_version_id else "project_scope_no_published_version",
        version_id=active_version_id,
        version_number=scope.get("active_version_number"),
        effective_from=scope.get("active_version_effective_from"),
        effective_to=scope.get("active_version_effective_to"),
    )

    empty_size = _size_report([])

    # What the retrieval disclosure says about the search itself, filled in as
    # the facts become known and merged into every response below. A dict the
    # responder reads, rather than an argument every `respond` call has to
    # remember to pass: a counter that is true of the search is true of whichever
    # state the search ended in, and one omitted at one exit would be a receipt
    # that quietly disagrees with the others.
    disclosure: dict = {}
    policy_records: list[dict] | None = [] if policies_only else None
    retrieval_method = LIGHT_RETRIEVAL_METHOD if policies_only else RETRIEVAL_METHOD

    def respond(
        status: str,
        *,
        considered,
        retained,
        discarded,
        policies_retrieved,
        evaluation,
        size,
        reason=None,
        policies_over_payload_budget=0,
        policies_rule_sliced=0,
        policies_duplicate_collapsed=0,
        policies_diversity_deferred=0,
    ):
        return _project_response(
            policy_set_key=policy_set.key,
            status=status,
            considered=considered,
            retained=retained,
            discarded=discarded,
            excluded=excluded,
            policies_retrieved=policies_retrieved,
            evaluation=evaluation,
            size=size,
            reason=reason,
            policies_over_payload_budget=policies_over_payload_budget,
            policies_rule_sliced=policies_rule_sliced,
            policies_duplicate_collapsed=policies_duplicate_collapsed,
            policies_diversity_deferred=policies_diversity_deferred,
            policy_records=policy_records,
            retrieval_method=retrieval_method,
            **disclosure,
        )

    if not candidates:
        if not scope.get("has_published_version", True):
            return respond(
                RETRIEVAL_NO_PUBLISHED_VERSION,
                considered=[],
                retained=[],
                discarded=[],
                policies_retrieved=0,
                evaluation=None,
                size=empty_size,
                reason="the project has no published version yet; publish a version before testing the whole project",
            )
        return respond(
            RETRIEVAL_EMPTY_SET,
            considered=[],
            retained=[],
            discarded=[],
            policies_retrieved=0,
            evaluation=None,
            size=empty_size,
            reason="the active published version has no policy rules to test",
        )

    settings = get_settings()
    if not settings.search_enabled:
        # The one thing forbidden is falling back to "all policies". Retrieval
        # cannot run, so no evaluation is made and the reviewer is told why; the
        # single-policy scope is the escape hatch.
        return respond(
            RETRIEVAL_UNAVAILABLE,
            considered=_bare_considered(candidates),
            retained=[],
            discarded=[],
            policies_retrieved=0,
            evaluation=None,
            size=empty_size,
            reason=(
                "search is not configured on this server, so the policies bearing on the question "
                "cannot be retrieved; no evaluation was made. Choose a single policy to test it directly."
            ),
        )

    index_name = policy_index_name(policy_set.key)
    if context is not None:
        # Named only now, on the path where the index is genuinely consulted. A
        # receipt must not claim an index was used on the paths above, where
        # search was unavailable or the project had nothing to search.
        context["index_name"] = index_name
        context["index_version_id"] = active_version_id
        context["retrieval_method"] = retrieval_method
    rule_index_state = RULE_INDEX_UNAVAILABLE
    try:
        # Measured, because it is not a local check. `index_exists` opens its own
        # connection and makes a live round trip to the search service, exactly
        # like the readiness gate below it — and left unmeasured it was the
        # single largest unattributed span in the request, sitting in the gap
        # between `scope_load` and `projection_readiness` where nothing was
        # timed. Recorded in `finally` so a probe that fails is still counted:
        # the time was spent either way, and a stage that vanishes on the error
        # path is exactly the blind spot this key exists to remove.
        # Constructed before the clock starts. It only stores a settings
        # reference — no I/O — so including it would add nothing to the span
        # except the possibility of the key going missing when the constructor
        # is what failed, which is precisely what this key promises not to do.
        search_client = AzureSearchClient(settings)
        index_probe_started = time.perf_counter()
        try:
            index_present = await search_client.index_exists(index_name)
        finally:
            if timings is not None:
                timings["index_probe"] = elapsed_ms(index_probe_started)
        if not index_present:
            return respond(
                RETRIEVAL_INDEX_NOT_BUILT,
                considered=_bare_considered(candidates),
                retained=[],
                discarded=[],
                policies_retrieved=0,
                evaluation=None,
                size=empty_size,
                reason=(
                    "this project's published-policy search index has not been built yet, so retrieval cannot be "
                    "relied on for it; no evaluation was made. Republish or rebuild the policy index."
                ),
            )

        # THE GATE, BEFORE THE QUERY.
        #
        # Asked first and answered from the index itself, because the failure it
        # catches is invisible afterwards: a question rendered into the
        # processing language, matched against a corpus that was never rendered
        # into it, comes back with a low score on every policy — which is exactly
        # what "no policy bears on this question" looks like. There is no point
        # downstream at which that can still be told apart, so it is told apart
        # here or not at all.
        readiness_started = time.perf_counter()
        readiness = await read_projection_readiness(
            search_client,
            index_name,
            policy_set_key=policy_set.key,
            expected_profile=ENGLISH_PROJECTION_PROFILE,
        )
        if timings is not None:
            timings["projection_readiness"] = elapsed_ms(readiness_started)
        if context is not None:
            context["projection_profile"] = (
                readiness.profile if readiness.ready else None
            )
        if not readiness.ready:
            raise IndexProjectionUnavailable(
                readiness,
                "this project's published-policy index carries no retrieval projection under "
                f"`{readiness.profile}`, or a rebuild left one incomplete, so a question cannot be "
                "matched against it in one language; no evaluation was made. Rebuild the policy "
                "index, then retry.",
            )

        async def policy_search() -> list[dict]:
            started = time.perf_counter()
            try:
                return await search_client.vector_search(
                    index_name,
                    query_text=scenario,
                    vector=vector,
                    top=RETRIEVAL_POLICY_SCAN,
                    filter_expr=policy_index_filter(
                        policy_set.key,
                        content_type=CONTENT_TYPE_POLICY,
                        projection_profile=readiness.profile,
                    ),
                    semantic_configuration=POLICY_SEMANTIC_CONFIG,
                )
            finally:
                if timings is not None:
                    timings["policy_search"] = elapsed_ms(started)

        vector: list[float] | None = None
        if policies_only:
            policy_task = asyncio.create_task(policy_search())
            policy_scan = await policy_task
            rule_scan = []
            rule_index_state = RULE_INDEX_UNAVAILABLE
            hits = policy_scan
            rule_hits_by_document = {}
        else:
            embedding_started = time.perf_counter()
            ai_client = AzureOpenAIClient(settings)
            [vector] = await ai_client.embed([scenario])
            if timings is not None:
                timings["embedding"] = elapsed_ms(embedding_started)

            async def rule_search() -> tuple[list[dict], str]:
                started = time.perf_counter()
                try:
                    return (
                        await search_client.vector_search(
                            index_name,
                            query_text=scenario,
                            vector=vector,
                            top=RETRIEVAL_RULE_SCAN,
                            filter_expr=policy_index_filter(
                                policy_set.key,
                                content_type=CONTENT_TYPE_RULE,
                                projection_profile=readiness.profile,
                            ),
                            select=_RULE_SELECT,
                            semantic_configuration=POLICY_SEMANTIC_CONFIG,
                        ),
                        RULE_INDEX_MATCHED,
                    )
                except Exception as exc:  # noqa: BLE001 - recoverable and disclosed
                    logger.warning(
                        "project-case rule retrieval failed for set %s: %s",
                        policy_set.key,
                        exc,
                    )
                    return [], RULE_INDEX_DEGRADED
                finally:
                    if timings is not None:
                        timings["rule_discovery"] = elapsed_ms(started)

            discovery_started = time.perf_counter()
            policy_task = asyncio.create_task(policy_search())
            rule_task = asyncio.create_task(rule_search())
            policy_scan, (rule_scan, rule_index_state) = await asyncio.gather(
                policy_task, rule_task
            )
            if timings is not None:
                timings["retrieval_discovery_wall"] = elapsed_ms(discovery_started)
            hits = [*policy_scan, *rule_scan]
            rule_hits_by_document = {}
    except IndexProjectionUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - a failed search is its own reported state
        logger.warning("project-case retrieval failed for set %s: %s", policy_set.key, exc)
        return respond(
            RETRIEVAL_FAILED,
            considered=_bare_considered(candidates),
            retained=[],
            discarded=[],
            policies_retrieved=0,
            evaluation=None,
            size=empty_size,
            reason=f"the search call failed: {exc}",
        )

    disclosure.update(
        {
            "projection_profile": readiness.profile,
            "projection_ready": True,
            "policy_documents_matched": len([h for h in policy_scan if not is_rule_hit(h)]),
            "rule_documents_matched": len([h for h in rule_scan if is_rule_hit(h)]),
            "policies_elevated_by_rule": 0,
            "rule_index_state": rule_index_state,
        }
    )

    if not hits:
        # Nothing came back. Tell apart a project whose active published version
        # is absent from the index from one where the current index genuinely did
        # not match the question.
        #
        # Both probes are scoped to **policy documents**. The unscoped filter
        # selects everything this project holds, which is what the stale sweep
        # needs and what these probes must not have: the manifest is one of that
        # project's documents and it is guaranteed to be there — the readiness
        # gate above only let this code run because it was — so an unscoped probe
        # would answer "yes, something is indexed" for every project and
        # `index_empty` would become unreachable.
        # Two more live round trips, on a path a real question reaches whenever
        # nothing matched. Measured for the same reason as the probe above: this
        # is where an "empty result" request spends its time, and an unmeasured
        # diagnostic is one that cannot itself be diagnosed.
        state_probe_started = time.perf_counter()
        try:
            current_indexed = await search_client.find_ids_by_filter(
                index_name,
                filter_expr=policy_index_filter(
                    policy_set.key, active_version_id, content_type=CONTENT_TYPE_POLICY
                ),
                page_size=1,
            )
            any_indexed = await search_client.find_ids_by_filter(
                index_name,
                filter_expr=policy_index_filter(
                    policy_set.key, content_type=CONTENT_TYPE_POLICY
                ),
                page_size=1,
            )
        except Exception as exc:  # noqa: BLE001 - fall back to the honest weaker claim
            logger.warning("project-case index probe failed for set %s: %s", policy_set.key, exc)
            return respond(
                RETRIEVAL_FAILED,
                considered=_bare_considered(candidates),
                retained=[],
                discarded=[],
                policies_retrieved=0,
                evaluation=None,
                size=empty_size,
                reason=(
                    "the search returned no policy and the follow-up probe that would say why "
                    f"also failed, so which of the honest states this is cannot be established: {exc}"
                ),
            )
        finally:
            if timings is not None:
                timings["index_state_probe"] = elapsed_ms(state_probe_started)
        if current_indexed:
            return respond(
                RETRIEVAL_NO_MATCH,
                considered=_bare_considered(candidates),
                retained=[],
                discarded=[],
                policies_retrieved=0,
                evaluation=None,
                size=empty_size,
                reason="no published policy matched this question",
            )
        if any_indexed:
            return respond(
                RETRIEVAL_INDEX_STALE,
                considered=_bare_considered(candidates),
                retained=[],
                discarded=[],
                policies_retrieved=0,
                evaluation=None,
                size=empty_size,
                reason=(
                    "this project's published-policy index has no documents for the active approved version, so "
                    "retrieval cannot be relied on for it; no evaluation was made. Republish or rebuild the policy index."
                ),
            )
        return respond(
            RETRIEVAL_INDEX_EMPTY,
            considered=_bare_considered(candidates),
            retained=[],
            discarded=[],
            policies_retrieved=0,
            evaluation=None,
            size=empty_size,
            reason=(
                "this project's published-policy index is empty, so retrieval cannot be relied on for it; "
                "no evaluation was made. Republish or rebuild the policy index."
            ),
        )

    stale_policy_ids = {
        str(
            hit.get("parent_document_id")
            if is_rule_hit(hit)
            else hit.get("id") or hit.get("document_id") or ""
        )
        for hit in hits
        if str(hit.get("document_version")) != str(active_version_id)
    }
    stale_policy_ids.discard("")
    current_policy_hits = [
        hit for hit in policy_scan if str(hit.get("document_version")) == str(active_version_id)
    ]
    current_rule_hits = [
        hit for hit in rule_scan if str(hit.get("document_version")) == str(active_version_id)
    ]
    by_search_id = {c["search_document_id"]: c for c in candidates}
    selection_started = time.perf_counter()
    if policies_only:
        current_hits, precision = select_semantic_policy_hits(current_policy_hits)
        ranked_current_hits = sorted(
            (dict(hit) for hit in current_policy_hits),
            key=lambda hit: (
                0
                if isinstance(hit.get("@search.rerankerScore"), (int, float))
                else 1,
                -float(hit.get("@search.rerankerScore") or 0.0),
                str(hit.get("id") or ""),
            ),
        )
        for hit in ranked_current_hits:
            if isinstance(hit.get("@search.rerankerScore"), (int, float)):
                hit["@search.score"] = float(hit["@search.rerankerScore"])
        disclosure.update(precision)
    else:
        (
            current_hits,
            ranked_current_hits,
            rule_hits_by_document,
            precision,
        ) = select_decision_policy_hits(current_policy_hits, current_rule_hits)
        disclosure.update(precision)
    if timings is not None:
        timings["policy_selection"] = elapsed_ms(selection_started)
    if hits and not current_hits:
        stale_considered = []
        for candidate in candidates:
            entry = {
                **_identity(candidate),
                "retained": False,
                "best_rank": None,
                "best_score": None,
                "matched_policies": 0,
                "discard_reason": DISCARD_STALE_VERSION,
            }
            stale_considered.append(entry)
        return respond(
            RETRIEVAL_INDEX_STALE,
            considered=stale_considered,
            retained=[],
            discarded=stale_considered,
            policies_retrieved=len(stale_policy_ids),
            evaluation=None,
            size=empty_size,
            reason=(
                "the policy index returned only documents from a superseded published version, so retrieval cannot "
                "be relied on for the active version; no evaluation was made. Republish or rebuild the policy index."
            ),
        )

    # The same policy held twice is one policy. Collapsed *before* the retention
    # budget, because the budget counts distinct policies to read and a copy that
    # consumed a slot is a slot the provision deciding the case never got.
    if (
        not policies_only
        and precision["direct_policy_order"] == DIRECT_POLICY_ORDER_RRF
    ):
        (
            current_hits,
            distinct_ids,
            duplicate_policies,
            coverage_added,
        ) = expand_policy_coverage_after_duplicate_collapse(
            current_hits,
            ranked_current_hits,
            scenario=scenario,
            by_search_id=by_search_id,
        )
        disclosure["coverage_expanded_policies"] = coverage_added
    else:
        distinct_ids, duplicate_policies = collapse_duplicate_policies(
            current_hits, by_search_id
        )
    # Then order what survived so one budget buys one thing once. This is an
    # ordering, not a claim of equality: a candidate held back here keeps its own
    # rank and is read as soon as the budget reaches it.
    ordered_ids, diversity_deferred = order_by_normative_diversity(distinct_ids, by_search_id)
    in_budget_ids = set(ordered_ids[:RETRIEVAL_POLICY_BUDGET])
    rescued_ids = {
        str(hit.get("id"))
        for hit in current_hits
        if hit.get("id") and hit.get("elevated_by_rule")
    }
    final_rescued = len(in_budget_ids & rescued_ids)
    disclosure["rule_rescued_policies"] = final_rescued
    disclosure["policies_elevated_by_rule"] = final_rescued
    # What the ordering actually *cost* a candidate: it would have been read on
    # rank alone and is not read now. A later group member that ranked outside
    # the budget anyway was not displaced by anything — counting it would put a
    # number on the receipt beside prose claiming it ranked inside, which would
    # be false. When no group has two members inside the budget, this is zero and
    # the ordering is a no-op it correctly reports as such.
    ranked_in_budget = set(distinct_ids[:RETRIEVAL_POLICY_BUDGET])
    displaced_by_diversity = len((ranked_in_budget - in_budget_ids) & diversity_deferred)

    selection = select_retained(
        candidates,
        ranked_current_hits,
        budget=RETRIEVAL_POLICY_BUDGET,
        in_budget_ids=in_budget_ids,
        duplicates=duplicate_policies,
    )
    retained = selection["retained"]
    discarded = selection["discarded"]
    considered = selection["considered"]
    policies_retrieved = selection["policies_retrieved"]

    if not retained:
        matched_candidate_ids = {entry["provision_key"] for entry in considered if entry.get("best_rank") is not None}
        if current_hits and not matched_candidate_ids:
            return respond(
                RETRIEVAL_INDEX_STALE,
                considered=considered,
                retained=retained,
                discarded=discarded,
                policies_retrieved=policies_retrieved,
                evaluation=None,
                size=empty_size,
                reason=(
                    "the policy index returned current-version documents that are not present in the active "
                    "published payload, so retrieval cannot be relied on; no evaluation was made. Republish or "
                    "rebuild the policy index."
                ),
            )
        # The search surfaced current-version policies, but none inside the
        # budget belongs to a testable policy. A real "no policy matched",
        # distinct from the index being absent/stale and from search unavailable.
        return respond(
            RETRIEVAL_NO_MATCH,
            considered=considered,
            retained=retained,
            discarded=discarded,
            policies_retrieved=policies_retrieved,
            evaluation=None,
            size=empty_size,
            reason="no published policy matched this question",
        )

    # Rule-level retrieval first, per policy. A policy that is really a table of
    # independent rows is narrowed to the rows that bear on the question before
    # anything measures the set — otherwise the payload budget is spent on rules
    # nobody asked about, which is how a seventy-four-row penalties table denied
    # an answer that was sitting in a ten-rule leave policy.
    candidates_by_entry = {
        id(entry): by_search_id[
            policy_document_id(
                policy_version_id=str(active_version_id),
                provision_key=str(entry["provision_key"]),
            )
        ]
        for entry in retained
    }

    # A second, deeper rule query, scoped to the provisions that were actually
    # retained. The discovery scan above ranks rows against the whole corpus,
    # which is the right question for "which provisions bear"; it is the wrong
    # question for "which rows of *this* schedule bear", because the rows that
    # place globally are not the rows that place within one document. Scoped, the
    # ranking is over one or two provisions' rows and is deep enough to be
    # stable. Run only when a retained policy is actually large enough to be read
    # rule by rule — for a project of ordinary provisions there is nothing to
    # rank and no call is made.
    rule_rank_started = time.perf_counter()
    retained_rule_hits, retained_rule_projections, rule_index_state = await _rank_rules_for_retained(
        search_client,
        index_name,
        policy_set_key=policy_set.key,
        scenario=scenario,
        vector=vector,
        readiness=readiness,
        retained=retained,
        candidates_by_entry=candidates_by_entry,
        discovery_hits=rule_hits_by_document,
        rule_index_state=rule_index_state,
        semantic_configuration=POLICY_SEMANTIC_CONFIG if policies_only else None,
    )
    if timings is not None:
        timings["retained_rule_ranking"] = elapsed_ms(rule_rank_started)
    disclosure["rule_index_state"] = rule_index_state

    slice_started = time.perf_counter()
    ranked_pairs = [
        (
            entry,
            _sliced_record(
                entry,
                candidates_by_entry[id(entry)]["payload"],
                scenario=scenario,
                governing_extras=candidates_by_entry[id(entry)].get("governing_extras"),
                rule_hits=retained_rule_hits.get(str(entry["provision_key"])),
                rule_projections=retained_rule_projections.get(str(entry["provision_key"])),
                rule_index_state=rule_index_state,
            ),
        )
        for entry in retained
    ]

    # Then the whole-record fitting across policies, unchanged and still the
    # backstop: slicing makes each record smaller, it does not promise that
    # several of them together fit.
    fitted_pairs, over_budget = fit_within_payload_budget(ranked_pairs)
    for entry in over_budget:
        _mark_over_payload_budget(entry, retained=retained, discarded=discarded)

    records = [record for _, record in fitted_pairs]
    if timings is not None:
        timings["rule_slice_and_fit"] = elapsed_ms(slice_started)

    if policy_records is not None:
        retained_by_key = {
            str(entry.get("provision_key")): entry
            for entry, _ in fitted_pairs
        }
        for record in records:
            policy = dict(record["policy"])
            entry = retained_by_key.get(str(policy.get("provision_key")), {})
            match = {
                "best_rank": entry.get("best_rank"),
                "best_score": entry.get("best_score"),
            }
            if entry.get("rule_selection") is not None:
                match["rule_selection"] = entry["rule_selection"]
            policy_records.append(
                {
                    "policy": policy,
                    "match": match,
                    "payload": record["payload"],
                }
            )

    evaluation = None
    if not policies_only:
        gather_started = time.perf_counter()
        gather_kwargs = _gather_kwargs(additional_instructions)
        evaluation = await answer_case_over_policies(
            records,
            scenario=scenario,
            reasoning_effort=reasoning_effort,
            **gather_kwargs,
        )
        if timings is not None:
            timings.update(getattr(evaluation, "stage_latency_ms", {}))
            timings["gather_total"] = elapsed_ms(gather_started)

    if over_budget:
        reason = (
            f"{len(over_budget)} policy(ies) ranked inside the retention budget and were still set "
            f"aside: adding their whole records would have pushed the combined payload past the "
            f"{PAYLOAD_BUDGET_CHARS}-character budget one grounded pass can read. The highest-ranked "
            "policies that fit whole were evaluated; none was trimmed, and each policy set aside for "
            f"size carries `{DISCARD_OUTSIDE_PAYLOAD_BUDGET}`."
        )
    elif discarded:
        reason = None
    else:
        reason = (
            "every published policy in this project was evaluated: there are no more of them "
            f"than the retention budget of {RETRIEVAL_POLICY_BUDGET}, so search had nothing to "
            "set aside. The policies listed were not selected as matching — they are all of them."
        )

    collapsed = [
        entry
        for entry in discarded
        if entry.get("discard_reason") == DISCARD_DUPLICATE_POLICY_CONTENT
    ]
    if collapsed:
        detail = "; ".join(
            f"{' > '.join(str(part) for part in entry.get('heading_path') or []) or entry['provision_key']}"
            f" (`{entry['provision_key']}`) duplicates `{entry.get('duplicate_of_provision_key')}`"
            for entry in collapsed
        )
        addition = (
            f"{len(collapsed)} published policy(ies) govern identically to a policy already retrieved "
            f"and were collapsed before the retention budget of {RETRIEVAL_POLICY_BUDGET} was applied, "
            "so one policy held twice could not consume two answer slots — "
            f"{detail}. Each carries `{DISCARD_DUPLICATE_POLICY_CONTENT}` and names the policy that "
            "stood in for it; their terms were read, in that policy, and the slot they would have "
            "taken went to the next distinct policy."
        )
        reason = f"{reason} {addition}" if reason else addition

    if displaced_by_diversity:
        addition = (
            f"{displaced_by_diversity} published policy(ies) ranked inside the retention budget "
            f"of {RETRIEVAL_POLICY_BUDGET} and were displaced out of it, because a policy "
            "requiring the same thing — the same sentences, effects, dates, scope, carve-outs "
            "and supersession, differing only in which rules a drafter marked as read-together "
            "— was offered first. They are **not** duplicates and are not reported as any: each "
            "keeps its own rank and score and carries "
            f"`{DISCARD_OUTSIDE_BUDGET}`, which here means it did not place inside the budget "
            "rather than that it ranked below one. The slot went to the next policy saying "
            "something different."
        )
        reason = f"{reason} {addition}" if reason else addition

    sliced = [
        entry
        for entry, _ in fitted_pairs
        if (entry.get("rule_selection") or {}).get("sliced")
    ]
    if sliced:
        detail = "; ".join(
            f"{' > '.join(str(part) for part in entry.get('heading_path') or []) or entry['provision_key']}"
            f" · {entry['rule_selection']['total_rules']} rules"
            f" · {entry['rule_selection']['selected_rules']} selected for this case"
            for entry in sliced
        )
        addition = (
            f"{len(sliced)} retained policy(ies) hold more than {LARGE_POLICY_RULE_THRESHOLD} rules "
            f"and were read rule by rule rather than whole — {detail}. Each policy's "
            "`rule_selection` names the rules that were read; the rest of that policy was not "
            "evaluated and no answer may claim otherwise."
        )
        reason = f"{reason} {addition}" if reason else addition

    return respond(
        RETRIEVAL_NARROWED if discarded else RETRIEVAL_NOT_NARROWED,
        considered=considered,
        retained=retained,
        discarded=discarded,
        policies_retrieved=policies_retrieved,
        evaluation=evaluation,
        size=_size_report(records),
        reason=reason,
        policies_over_payload_budget=len(over_budget),
        policies_rule_sliced=len(sliced),
        policies_duplicate_collapsed=len(duplicate_policies),
        policies_diversity_deferred=displaced_by_diversity,
    )


async def _rank_rules_for_retained(
    search_client,
    index_name: str,
    *,
    policy_set_key: str,
    scenario: str,
    vector: list | None,
    readiness,
    retained: list[dict],
    candidates_by_entry: dict,
    discovery_hits: dict[str, list[dict]],
    rule_index_state: str,
    semantic_configuration: str | None = None,
) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, str]], str]:
    """The rule index's ranking of the retained large policies' own rules.

    Returns ``(ranks, texts, state)`` keyed by provision key: for each large
    retained policy, a map of rule id to its zero-based rank, and a map of rule
    id to the English projection the index holds for it.

    WHY A SECOND QUERY

    The discovery scan ranks every indexed row of the project against the
    question. That is the right ranking for "which provisions bear on this",
    because a row of a schedule is evidence about the schedule. It is the wrong
    ranking for "which rows of *this* schedule bear", because only the rows that
    placed globally are in it — a provision retained on the strength of two rows
    would be sliced on the strength of those two rows and nothing else. Scoped to
    the retained provisions and run deeper, the ranking covers their rows
    properly, and the two are merged with the scoped one taking precedence for
    the provisions it covers.

    WHY THE PROJECTIONS COME BACK WITH IT

    The rule documents' `retrieval_text` **is** the English projection. Carrying
    it back is what lets the request-side selection score a rendered question
    against rendered rules rather than against the document's own language —
    without a second store, a second rendering, or a projection column in
    PostgreSQL, where the authoritative record lives and must stay untouched.

    A failure here is recoverable and disclosed: the scoped ranking is dropped,
    whatever the discovery scan found is kept, and the state moves to `degraded`
    so the method a receipt names says a ranking was missing.
    """

    ranks: dict[str, dict[str, int]] = {}
    texts: dict[str, dict[str, str]] = {}

    large_keys: list[str] = []
    for entry in retained:
        candidate = candidates_by_entry.get(id(entry)) or {}
        payload = candidate.get("payload") or {}
        if len(payload.get("rules") or []) > LARGE_POLICY_RULE_THRESHOLD:
            large_keys.append(str(entry["provision_key"]))

    scoped: list[dict] = []
    if large_keys and (
        rule_index_state == RULE_INDEX_MATCHED or semantic_configuration is not None
    ):
        try:
            scoped = await search_client.vector_search(
                index_name,
                query_text=scenario,
                vector=vector,
                top=(
                    min(RETRIEVAL_RULE_RANK_SCAN, SEMANTIC_RERANKER_LIMIT)
                    if semantic_configuration is not None
                    else RETRIEVAL_RULE_RANK_SCAN
                ),
                filter_expr=(
                    policy_index_filter(
                        policy_set_key,
                        content_type=CONTENT_TYPE_RULE,
                        projection_profile=readiness.profile,
                    )
                    + " and "
                    + _provision_key_filter(large_keys)
                ),
                select=_RULE_SELECT,
                semantic_configuration=semantic_configuration,
            )
            rule_index_state = RULE_INDEX_MATCHED
        except Exception as exc:  # noqa: BLE001 - recoverable, and said so
            logger.warning(
                "project-case scoped rule ranking failed for set %s: %s", policy_set_key, exc
            )
            scoped = []
            rule_index_state = RULE_INDEX_DEGRADED

    # The discovery scan first, so every provision has whatever it found, then
    # the scoped ranking over the provisions it covers — which replaces rather
    # than merges, because two rankings of one provision's rows produced by two
    # queries of different depth are not one ranking and interleaving them would
    # be an order neither search returned.
    for entry in retained:
        key = str(entry["provision_key"])
        candidate = candidates_by_entry.get(id(entry)) or {}
        document_id = str(candidate.get("search_document_id") or "")
        found = discovery_hits.get(document_id) or []
        if found:
            ranks[key] = {
                str(hit.get("rule_id")): rank
                for rank, hit in enumerate(found)
                if hit.get("rule_id")
            }
            texts[key] = {
                str(hit.get("rule_id")): str(hit.get("retrieval_text") or "")
                for hit in found
                if hit.get("rule_id")
            }

    if scoped:
        by_key: dict[str, list[dict]] = {}
        for hit in scoped:
            if not is_rule_hit(hit):
                continue
            key = str(hit.get("provision_key") or "")
            if key:
                by_key.setdefault(key, []).append(hit)
        for key, found in by_key.items():
            ranks[key] = {
                str(hit.get("rule_id")): rank
                for rank, hit in enumerate(found)
                if hit.get("rule_id")
            }
            texts[key] = {
                str(hit.get("rule_id")): str(hit.get("retrieval_text") or "")
                for hit in found
                if hit.get("rule_id")
            }

    return ranks, texts, rule_index_state


def _provision_key_filter(keys: list[str]) -> str:
    """An OData clause selecting documents belonging to any of these provisions.

    Written as an explicit disjunction of equalities rather than `search.in`,
    because a provision key is opaque platform-generated text and `search.in`
    takes a delimiter-separated list — a key containing the delimiter would
    silently select the wrong documents. Equalities escape the value properly and
    have no delimiter to collide with.
    """

    quoted = [f"provision_key eq {odata_string(key)}" for key in sorted(set(keys))]
    return "(" + " or ".join(quoted) + ")"


async def answer_project_case(
    session: AsyncSession,
    *,
    policy_set,
    scenario: str,
    provision_id: str | None = None,
    reasoning_effort: str = "medium",
    additional_instructions: str = "",
    with_context: bool = False,
) -> dict | ProjectCaseAnswer:
    """Answer a case put to a project, at the scope the reviewer chose.

    When ``provision_id`` is given the reviewer has chosen one policy: retrieval is
    bypassed and that policy is answered. Otherwise the case is put to the project,
    and the policies bearing on the question are retrieved and the rest discarded
    before anything is evaluated — never the whole set.

    ``policy_set`` is the resolved project (the caller has already turned a key into
    a row and answered 404 if it did not exist). Raises :class:`ProvisionNotInProject`
    when a named provision is unknown or belongs to another project, ``ValueError``
    when an id is malformed (from the projection), and ``RuntimeError`` when the
    model is not configured — the endpoint maps these to 404, 422, and 503.

    ``with_context`` is the one addition an audited caller needs and an in-product
    one does not. Left at its default the return is the same bare dict it has
    always been, so every existing caller and test is untouched. Set, the return
    is a :class:`ProjectCaseAnswer` carrying that same dict plus the exact
    published version this call loaded — see that class for why re-reading "the
    active version" afterwards would not be the same fact.

    ``additional_instructions`` is optional caller guidance about how the answer
    should be presented. It reaches the evaluation gather only — never the
    retrieval query, never the intent classifier — and is wrapped there in the
    invariants it may not cross. Empty by default, in which case nothing about
    this function's behaviour changes at all.
    """

    context: dict | None = {} if with_context else None

    if provision_id is not None and str(provision_id).strip():
        response = await _answer_single_scope(
            session,
            policy_set=policy_set,
            provision_id=provision_id,
            scenario=scenario,
            reasoning_effort=reasoning_effort,
            additional_instructions=additional_instructions,
            context=context,
        )
    else:
        response = await _answer_project_scope(
            session,
            policy_set=policy_set,
            scenario=scenario,
            reasoning_effort=reasoning_effort,
            additional_instructions=additional_instructions,
            context=context,
        )

    if context is None:
        return response
    return ProjectCaseAnswer(response=response, context=context)


async def retrieve_project_policies(
    session: AsyncSession,
    *,
    policy_set,
    scenario: str,
    with_context: bool = False,
) -> dict | ProjectPolicyRetrieval:
    """Return a precision-ranked published policy subset without a decision.

    It shares the approved corpus, duplicate collapse, large-policy rule slicing,
    payload fitting, and disclosure machinery with :func:`answer_project_case`.
    Its policy cut is intentionally narrower: semantic policy ranking replaces
    the decision path's recall-heavy policy/rule fusion because no downstream
    gather exists to reject over-kept records.
    """

    context: dict | None = {} if with_context else None
    response = await _answer_project_scope(
        session,
        policy_set=policy_set,
        scenario=scenario,
        reasoning_effort="medium",
        additional_instructions="",
        context=context,
        policies_only=True,
    )
    if context is None:
        return response
    return ProjectPolicyRetrieval(response=response, context=context)
