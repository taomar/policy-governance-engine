"""How much would each consolidation tier touch, across every run we have?

Consolidation is three different operations wearing one name, and they carry
very different risk. Sizing them separately is what decides whether each is
worth building at all — a tier that would touch nothing is not worth the code,
and a tier that would touch hundreds of records is not something to automate.

The signals are the committed ones. Tier 1 reuses `repeated_records` from the
consolidation package, which in turn builds on the delta projection's
`semantic_core`; tiers 2 and 3 reuse `decision_families` and
`promoted_qualifiers`. Nothing here re-implements a measure that already exists
in the product, because a second implementation of a measure is how two numbers
quietly disagree.

Read-only. It writes nothing and consolidates nothing.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import defaultdict

from policy_platform.infrastructure.consolidation.duplicate_records import (
    record_key,
    repeated_records,
    source_span,
)
from policy_platform.infrastructure.extraction.decision_families import (
    FamilyMember,
    decision_families,
    promoted_qualifiers,
)
from policy_platform.infrastructure.projection.rule_delta import identify

#: An element id carries its page and a document-wide ordinal, e.g. `p9-E000140`.
#: The ordinal is what puts two spans in reading order.
_ELEMENT = re.compile(r"E(\d+)")


def load(policy_set_key: str) -> list[dict]:
    query = (
        "select payload_json from candidate_rules c "
        "join policy_sets p on p.id = c.policy_set_id "
        f"where p.key = '{policy_set_key}' and c.superseded_at is null"
    )
    out = subprocess.run(
        [
            "docker", "exec", "policy-postgres", "psql",
            "-U", "policy_admin", "-d", "policy_platform_advtool",
            "-t", "-A", "-c", query,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return [json.loads(line) for line in out.stdout.splitlines() if line.strip()]


def _ordinal(span: str) -> int:
    """First element ordinal in a span, for putting spans in reading order."""
    found = _ELEMENT.findall(span)
    return int(found[0]) if found else -1


def _member(payload: dict) -> FamilyMember | None:
    formulation = payload.get("formulation") or {}
    canonical = formulation.get("canonical") if isinstance(formulation, dict) else None
    if not isinstance(canonical, dict):
        return None
    core = canonical.get("rule")
    if not isinstance(core, dict):
        return None
    return FamilyMember(
        rule_id=payload.get("rule_id", ""),
        sentence=canonical.get("source_text") or "",
        core=_Core(core),
    )


class _Core:
    """Attribute access over a canonical rule dict, which is what the detectors read."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def __getattr__(self, name: str):
        return self._data.get(name)


def size_tiers(payloads: list[dict]) -> dict:
    spans: dict[str, list[dict]] = defaultdict(list)
    span_less = 0
    for payload in payloads:
        span = source_span(payload)
        if span is None:
            span_less += 1
            continue
        spans[span].append(payload)

    # --- Tier 1: same span, same record. Measured with the production function
    #     rather than a local reimplementation of it, so this table cannot
    #     disagree with what the pass would actually do.
    keyed = [(f"{index}", payload) for index, payload in enumerate(payloads)]
    by_index = dict(keyed)
    repeats = repeated_records(keyed)
    tier1_groups = len(repeats)
    tier1_redundant = sum(len(r.redundant) for r in repeats)
    tier1_detail = [
        (r.span, r.copies, (by_index[r.keep].get("title") or "")[:70]) for r in repeats
    ]

    same_span_different_content = 0
    # The same question with prose ignored: same span, same meaning, wording not
    # compared. Kept beside Tier 1 so the cost of insisting on the wording is
    # visible rather than assumed. Where the two agree, the copies were identical
    # in their words too, and requiring that cost nothing.
    loose_groups = 0
    loose_redundant = 0
    for span, group in spans.items():
        if len({record_key(payload) for payload in group}) > 1:
            same_span_different_content += 1

        by_loose: dict[str, list[dict]] = defaultdict(list)
        for payload in group:
            by_loose[identify(payload).content_fingerprint].append(payload)
        for copies in by_loose.values():
            if len(copies) > 1:
                loose_groups += 1
                loose_redundant += len(copies) - 1

    # The case Tier 1 must never touch: a document that states the same
    # obligation in two different places has stated two facts.
    by_content_globally: dict[str, set[str]] = defaultdict(set)
    for span, group in spans.items():
        for payload in group:
            by_content_globally[record_key(payload)].add(span)
    restated_elsewhere = sum(1 for s in by_content_globally.values() if len(s) > 1)

    # --- Tier 2: one clause, a detected family.
    members = [m for m in (_member(p) for p in payloads) if m is not None]
    families = decision_families(members)
    promotions = promoted_qualifiers(members)
    tier2_records = (
        {rid for f in families for rid in f.rule_ids}
        | {p.qualifier_rule_id for p in promotions}
        | {rid for p in promotions for rid in p.antecedent_rule_ids}
    )

    # --- Tier 3: the same family signal, allowed to cross into the next span.
    #     Reuses `decision_families` unchanged by presenting each adjacent pair
    #     of spans to it as if it were one statement. Anything it then reports
    #     was invisible to Tier 2 precisely because the records came from
    #     different spans.
    by_rule_span = {}
    for span, group in spans.items():
        for payload in group:
            by_rule_span[payload.get("rule_id", "")] = span
    members_by_span: dict[str, list[FamilyMember]] = defaultdict(list)
    for member in members:
        span = by_rule_span.get(member.rule_id)
        if span is not None:
            members_by_span[span].append(member)

    ordered = sorted(members_by_span, key=_ordinal)
    tier3_records: set[str] = set()
    tier3_pairs = 0
    tier3_detail: list[tuple[str, tuple[str, ...], int]] = []
    # A second, deliberately looser reading of "neighbouring records that might
    # match": adjacent spans holding records with the same subject. It is not a
    # proposal-worthy signal on its own — it is here to bound how big Tier 3
    # could get under a generous definition, so the decision whether to build it
    # does not rest on my choice of the narrow one.
    tier3_wide_records: set[str] = set()
    for left, right in zip(ordered, ordered[1:]):
        window = [
            FamilyMember(rule_id=m.rule_id, sentence="window", core=m.core)
            for m in members_by_span[left] + members_by_span[right]
        ]
        for family in decision_families(window):
            touched = set(family.rule_ids)
            # Only count it when the family actually crosses the boundary;
            # a family wholly inside one span is already Tier 2.
            if len({by_rule_span.get(r) for r in touched}) < 2:
                continue
            tier3_pairs += 1
            tier3_records |= touched
            tier3_detail.append((f"{left} | {right}", family.varying, len(touched)))

        left_subjects = {
            (getattr(m.core, "subject", None) or "").strip().casefold(): m.rule_id
            for m in members_by_span[left]
        }
        for m in members_by_span[right]:
            subject = (getattr(m.core, "subject", None) or "").strip().casefold()
            if subject and subject in left_subjects:
                tier3_wide_records |= {m.rule_id, left_subjects[subject]}

    return {
        "records": len(payloads),
        "examined": len(members),
        "span_less": span_less,
        "distinct_spans": len(spans),
        "tier1_groups": tier1_groups,
        "tier1_redundant": tier1_redundant,
        "tier1_detail": tier1_detail,
        "loose_groups": loose_groups,
        "loose_redundant": loose_redundant,
        "same_span_different_content": same_span_different_content,
        "restated_elsewhere": restated_elsewhere,
        "tier2_families": len(families),
        "tier2_promotions": len(promotions),
        "tier2_records": len(tier2_records),
        "tier3_pairs": tier3_pairs,
        "tier3_records": len(tier3_records),
        "tier3_wide_records": len(tier3_wide_records),
        "tier3_detail": tier3_detail,
    }


def main() -> int:
    keys = sys.argv[1:] or [
        "ais-employee-handbook",
        "ais-handbook-formulator-v2",
        "ais-handbook-formulator-v3",
    ]
    sized = {key: size_tiers(load(key)) for key in keys}

    width = max(len(k) for k in keys) + 3
    print(f"{'measure':<38}" + "".join(f"{k:<{width}}" for k in keys))
    print("-" * (38 + width * len(keys)))

    def row(label: str, field: str, pct_of: str | None = None) -> None:
        cells = []
        for key in keys:
            value = sized[key][field]
            if pct_of and sized[key][pct_of]:
                cells.append(f"{value} ({100 * value / sized[key][pct_of]:.1f}%)")
            else:
                cells.append(str(value))
        print(f"{label:<38}" + "".join(f"{c:<{width}}" for c in cells))

    row("records", "records")
    row("  examined (have a canonical core)", "examined")
    row("  no recorded span (ineligible)", "span_less", "records")
    row("distinct source spans", "distinct_spans")
    print()
    print("TIER 1 - same span, same record (automatic)")
    row("  groups", "tier1_groups")
    row("  redundant records", "tier1_redundant", "records")
    row("  same span, meaning only (prose ignored)", "loose_groups")
    row("  same span, meaning only: records", "loose_redundant")
    print()
    print("TIER 2 - one clause, detected family (re-formulate)")
    row("  split families", "tier2_families")
    row("  promoted qualifiers", "tier2_promotions")
    row("  records touched", "tier2_records", "records")
    print()
    print("TIER 3 - neighbouring spans, same signal (propose only)")
    row("  cross-span families", "tier3_pairs")
    row("  records touched", "tier3_records", "records")
    row("  [loosest reading: shared subject]", "tier3_wide_records", "records")
    print()
    print("guards - counts that must NOT be consolidated")
    row("  same content in another span", "restated_elsewhere")
    row("  spans holding differing content", "same_span_different_content")

    for key in keys:
        data = sized[key]
        print()
        print(f"=== {key}: tier 1 groups")
        for span, size, title in data["tier1_detail"] or []:
            print(f"  {size}x  {span[:44]:<46} {title!r}")
        if not data["tier1_detail"]:
            print("  (none)")
        print(f"=== {key}: tier 3 cross-span families (first 12)")
        for pair, varying, size in data["tier3_detail"][:12]:
            print(f"  {size} records differ in {', '.join(varying)}: {pair[:70]}")
        if not data["tier3_detail"]:
            print("  (none)")

    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
