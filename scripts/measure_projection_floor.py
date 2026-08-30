"""Measure the projection-quality floor against the real embedding deployment.

WHY THIS EXISTS

`ProjectionQualityProfile.minimum_pair_similarity` is 0.60, and its docstring
justifies that number with a claim about the *shape of the space*:

  * a passage and a faithful rendering of it sit high;
  * a passage and an unrelated passage from the same document sit far lower;
  * between them is a wide, empty gap.

The docstring is explicit that the number was chosen from that claimed shape and
"emphatically not tuned against any corpus". Which is the right way to choose it
-- and it means the claim itself has never been measured on the deployment this
platform actually calls. The unit tests use a deterministic stand-in, so they
prove the gate's logic and say nothing about whether the gap is real here.

WHAT THIS MEASURES, AND WHAT IT DELIBERATELY DOES NOT

A floor can be wrong in two directions and they are not symmetric:

  * **False pass** -- a substituted rendering scores ABOVE the floor, so the gate
    admits a corpus it exists to refuse. This is silent, and it is the dangerous
    one. It is decided by how HIGH unrelated and near-miss pairs sit, and it is
    fully measurable in English.
  * **False fail** -- a genuine rendering scores BELOW the floor, so a good
    corpus is blocked. This is an outage, and it is loud. It is decided by how
    LOW genuine cross-language rendering pairs sit -- which is a live non-English
    question and stays deferred (AD-7.10 / AD-7.11).

So this script answers the false-pass direction only, and says so. It writes
nothing: no index document, no database row. It makes embedding calls and prints
numbers.

Run:  python scripts/measure_projection_floor.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))

from policy_platform.infrastructure.settings import Settings  # noqa: E402
from policy_platform.infrastructure.ai.openai_client import AzureOpenAIClient  # noqa: E402
from policy_platform.infrastructure.quality.projection_faithfulness import (  # noqa: E402
    _comparable_pair,
    _cosine,
    quality_profile,
)

# ── the bands, in synthetic governance prose that names no real corpus ──

#: Band 1. The same statement, rendered differently. In English the projection is
#: identity, so this stands in for "a rendering that is genuinely of its source"
#: as closely as an English-only scope allows.
FAITHFUL = [
    (
        "An employee who has completed one continuous year of service is entitled "
        "to twenty-one days of paid annual leave in each subsequent year.",
        "A staff member with one unbroken year of service receives twenty-one days "
        "of paid yearly vacation in every following year.",
    ),
    (
        "A vessel that occupies a berth beyond the permitted period owes a mooring "
        "fee to the harbour authority for each further period begun.",
        "Where a ship remains at a berth after the allowed time, a mooring charge "
        "is payable to the port authority for every additional period started.",
    ),
    (
        "The operator shall admit an inspector to any part of the premises where "
        "animals are kept, at any reasonable hour.",
        "An inspector must be allowed into any area of the site housing animals, "
        "at any reasonable time of day.",
    ),
    (
        "Stationery ordered above the departmental threshold requires written "
        "approval from the head of procurement before the order is placed.",
        "Orders for office supplies exceeding the department's limit must be "
        "approved in writing by the procurement lead before being submitted.",
    ),
    (
        "Overtime worked on an official public holiday is compensated at twice the "
        "employee's ordinary hourly rate.",
        "Hours worked in excess of the normal schedule on a gazetted holiday are "
        "paid at double the worker's usual rate per hour.",
    ),
    (
        "An employee absent without authorisation for more than three consecutive "
        "days may be subject to a written warning from the head of department.",
        "Where a worker is away without permission for over three days in a row, "
        "the department head may issue a formal written caution.",
    ),
    (
        "A permit holder must display the permit at the entrance to the premises.",
        "The permit shall be shown at the entry point of the site by whoever holds "
        "it.",
    ),
]

#: Band 2. Two different rules from the same schedule. Shared register, shared
#: subject matter, shared boilerplate -- and about different things. This is the
#: substitution the gate exists to catch: a rendering of the wrong row.
SAME_DOCUMENT_NEIGHBOUR = [
    (
        "An employee who has completed one continuous year of service is entitled "
        "to twenty-one days of paid annual leave in each subsequent year.",
        "An employee absent without authorisation for more than three consecutive "
        "days may be subject to a written warning from the head of department.",
    ),
    (
        "An employee absent without authorisation for more than three consecutive "
        "days may be subject to a written warning from the head of department.",
        "Overtime worked on an official public holiday is compensated at twice the "
        "employee's ordinary hourly rate.",
    ),
    (
        "A vessel that occupies a berth beyond the permitted period owes a mooring "
        "fee to the harbour authority for each further period begun.",
        "The master of a vessel shall file a cargo manifest with the harbour "
        "authority before any unloading begins.",
    ),
]

#: Band 3. The hardest case, and the one that decides whether a single threshold
#: can work at all: same topic, same shape, different entitlement. If the gate
#: cannot separate these, a rendering of the neighbouring row passes as this one.
NEAR_MISS = [
    (
        "An employee who has completed one continuous year of service is entitled "
        "to twenty-one days of paid annual leave in each subsequent year.",
        "An employee who has completed one continuous year of service is entitled "
        "to thirty days of paid sick leave in each subsequent year.",
    ),
    (
        "Annual leave may be carried over to the following year only with the "
        "written approval of the head of department.",
        "Sick leave may not be carried over to the following year under any "
        "circumstances.",
    ),
    (
        "A vessel under twenty metres in length is exempt from the berthing fee.",
        "A vessel over forty metres in length pays the berthing fee at double the "
        "standard rate.",
    ),
    (
        "An employee may be granted unpaid leave of up to six months to accompany "
        "a spouse posted abroad.",
        "An employee may be granted unpaid leave of up to two years to complete a "
        "course of full-time study.",
    ),
    (
        "A first instance of unauthorised absence attracts a verbal warning.",
        "A third instance of unauthorised absence attracts dismissal without "
        "notice.",
    ),
    (
        "Overtime worked on a normal working day is compensated at one and a half "
        "times the ordinary hourly rate.",
        "Overtime worked on an official public holiday is compensated at twice the "
        "ordinary hourly rate.",
    ),
    (
        "The inspection fee for a kennel housing fewer than ten animals is payable "
        "annually.",
        "The inspection fee for a kennel housing more than fifty animals is payable "
        "quarterly.",
    ),
    (
        "A permit holder must display the permit at the entrance to the premises.",
        "A permit holder must surrender the permit to the authority on cessation "
        "of the activity.",
    ),
    (
        "Written approval from the head of procurement is required before an order "
        "above the departmental threshold is placed.",
        "Written approval from the finance director is required before a payment "
        "above the departmental threshold is released.",
    ),
    (
        "An employee on probation is entitled to seven days of paid leave.",
        "An employee on probation is not entitled to any paid leave.",
    ),
]

#: Band 4. Different domain entirely. The floor of the floor.
UNRELATED_DOMAIN = [
    (
        "An employee who has completed one continuous year of service is entitled "
        "to twenty-one days of paid annual leave in each subsequent year.",
        "A vessel under twenty metres in length is exempt from the berthing fee.",
    ),
    (
        "The operator shall admit an inspector to any part of the premises where "
        "animals are kept, at any reasonable hour.",
        "Overtime worked on an official public holiday is compensated at twice the "
        "employee's ordinary hourly rate.",
    ),
]

BANDS = {
    "1 faithful rendering  (must sit HIGH)": FAITHFUL,
    "2 same-doc neighbour  (must sit LOW)": SAME_DOCUMENT_NEIGHBOUR,
    "3 near miss, same topic (must sit LOW)": NEAR_MISS,
    "4 unrelated domain    (must sit LOW)": UNRELATED_DOMAIN,
}

FAITHFUL_BAND = "1 faithful rendering  (must sit HIGH)"


async def main() -> int:
    settings = Settings()
    if not settings.ai_enabled:
        print("AI is not enabled in this environment; nothing to measure.")
        return 2

    profile = quality_profile()
    client = AzureOpenAIClient(settings)

    # Every pair, interleaved exactly as `_similarity_by_document` interleaves
    # them, and cut by the same `_comparable_pair`, so what is measured here is
    # what the gate would measure and not an approximation of it.
    texts: list[str] = []
    index: list[tuple[str, int]] = []
    for band, pairs in BANDS.items():
        for n, (source, projected) in enumerate(pairs):
            left, right = _comparable_pair(
                source, projected, ceiling=profile.compare_chars
            )
            texts.append(left)
            texts.append(right)
            index.append((band, n))

    print(f"embedding {len(texts)} texts "
          f"({len(index)} pairs) on {settings.azure_openai_embedding_deployment}\n")
    vectors = await client.embed(texts)
    if len(vectors) != len(texts):
        print(f"deployment returned {len(vectors)} vectors for {len(texts)} texts")
        return 1

    scores: dict[str, list[float]] = {band: [] for band in BANDS}
    for position, (band, _n) in enumerate(index):
        similarity = _cosine(vectors[position * 2], vectors[position * 2 + 1])
        if similarity is None:
            print(f"{band}: a pair produced no comparable vectors")
            return 1
        scores[band].append(similarity)

    floor = profile.minimum_pair_similarity
    print(f"floor under {profile.name}: {floor}\n")
    print(f"{'band':40} {'min':>7} {'mean':>7} {'max':>7}   verdict")
    print("-" * 78)

    faithful_min = None
    other_max = None
    for band, values in scores.items():
        lo, hi = min(values), max(values)
        mean = sum(values) / len(values)
        if band.startswith("1"):
            faithful_min = lo
            verdict = "OK" if lo >= floor else "** BELOW FLOOR -- false-fail risk **"
        else:
            other_max = hi if other_max is None else max(other_max, hi)
            verdict = "OK" if hi < floor else "** ABOVE FLOOR -- FALSE-PASS RISK **"
        print(f"{band:40} {lo:7.4f} {mean:7.4f} {hi:7.4f}   {verdict}")

    print("-" * 78)
    if faithful_min is None or other_max is None:
        return 1

    # The offending pairs, named. A band summary says a threshold is unsafe; only
    # the pairs say what kind of text does it, which is what a reader needs in
    # order to judge whether the sample is fair or was constructed to fail.
    crossing = [
        (band, n, value)
        for band, values in scores.items()
        if not band.startswith("1")
        for n, value in enumerate(values)
        if value >= floor
    ]
    if crossing:
        print("\nWRONG PAIRS THAT CLEARED THE FLOOR")
        for band, n, value in sorted(crossing, key=lambda row: -row[2]):
            source, projected = BANDS[band][n]
            print(f"\n  {value:.4f}  [{band.strip()}]")
            print(f"    source    : {source[:96]}")
            print(f"    substitute: {projected[:96]}")

    weakest = min(
        ((n, v) for n, v in enumerate(scores[FAITHFUL_BAND])), key=lambda row: row[1]
    )
    print(f"\nWEAKEST FAITHFUL PAIR  {weakest[1]:.4f}")
    print(f"    source  : {FAITHFUL[weakest[0]][0][:96]}")
    print(f"    rendered: {FAITHFUL[weakest[0]][1][:96]}")

    gap = faithful_min - other_max
    print(f"\nlowest faithful pair : {faithful_min:.4f}")
    print(f"highest wrong pair   : {other_max:.4f}")
    print(f"observed gap         : {gap:+.4f}")
    print(f"floor {floor} sits {'INSIDE' if other_max < floor <= faithful_min else 'OUTSIDE'} the observed gap")

    if gap <= 0:
        print("\nThe bands OVERLAP on this deployment. No single threshold separates a")
        print("rendering from a substitution here, which is a finding about the gate's")
        print("central assumption and not about any corpus.")
        return 1
    headroom_below = faithful_min - floor
    headroom_above = floor - other_max
    print(f"headroom to false-fail: {headroom_below:+.4f}")
    print(f"headroom to false-pass: {headroom_above:+.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
