"""Every quality scope the database can hold has wording in the surface.

WHAT CLASS THIS CLOSES

The register showed quality results for published-scope runs only. On a
portfolio where nothing has been published that discarded every quality run
that existed, so the surface said "Not evaluated" while real findings sat
stored against the candidate generation. Admitting both scopes fixed the
instance; it also created the conditions for the recurring defect in this
repository, which is that a code and the words describing it drift apart.

Now that more than one scope reaches a reviewer, the surface has to name which
population a finding count describes. A scope added later would arrive with no
wording, and the failure mode is silent: the label lookup misses, and the
reviewer is shown either a raw identifier or nothing at all where an
explanation belongs.

So the codes are enumerated from their definition rather than from a list kept
here, and the surface is required to word all of them.

FLOOR PLACEMENT

The verdict is a set difference -- "which defined codes are missing from the
map" -- so the floors go FIRST, before the difference is computed. If the map
extraction goes blind it returns nothing, every code is reported unmapped, and
the failure is a confident, precise and entirely wrong bug report naming code
that is in fact correctly handled. Asserting both sides were actually read
first means a blind parse fails as a broken test rather than as a false
accusation against the tree.

WHAT THIS GUARD DELIBERATELY DOES NOT DO

It does not check how an unmapped code degrades. That belongs to behaviour,
not to text: a first attempt asserted it here by pattern-matching the returned
expression, and a leak written as `?? \\`scope ${scope}\\`` walked straight
past it while the guard reported green. The same restatement weakness has
defeated a pattern-based check on this repository three times. The fallback is
therefore asserted in `apps/web/src/qualityTrend.test.ts`, where the function
can be called and its actual output inspected, which no rephrasing can evade.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MODELS = REPO / "src" / "policy_platform" / "domain" / "models.py"
QUALITY_TREND = REPO / "apps" / "web" / "src" / "qualityTrend.ts"


def _defined_scopes() -> set[str]:
    """The scope codes as declared on the QualityRun model.

    `quality_runs.scope` is a plain varchar rather than an enum, so its
    permitted values are documented in the trailing comment on the column.
    That comment IS the definition; reading it here means a code added there
    is immediately required to have wording, which is the point.
    """
    text = MODELS.read_text(encoding="utf-8")
    match = re.search(
        r"^\s*scope:\s*Mapped\[str\][^\n]*#(?P<comment>[^\n]*)$",
        text,
        re.MULTILINE,
    )
    assert match is not None, (
        "Could not find the `scope` column declaration on QualityRun in "
        f"{MODELS}. If the column moved or its documenting comment was "
        "removed, this guard can no longer tell which scopes exist and must "
        "be pointed at the new definition rather than deleted."
    )
    return set(re.findall(r'"([a-z_]+)"', match.group("comment")))


def _mapped_scopes() -> set[str]:
    """The scope codes the web surface has words for."""
    text = QUALITY_TREND.read_text(encoding="utf-8")
    match = re.search(
        r"QUALITY_SCOPE_LABELS:\s*Record<string,\s*string>\s*=\s*\{(?P<body>.*?)\}",
        text,
        re.DOTALL,
    )
    assert match is not None, (
        f"Could not find QUALITY_SCOPE_LABELS in {QUALITY_TREND}. The surface "
        "must keep a lookup this guard can read, or a scope can lose its "
        "wording without anything noticing."
    )
    return set(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:", match.group("body"), re.MULTILINE))


def test_every_defined_quality_scope_has_wording() -> None:
    defined = _defined_scopes()
    mapped = _mapped_scopes()

    # Floors first -- see the module docstring. A blind read of either side
    # would otherwise produce a confident and entirely wrong verdict.
    assert defined, (
        "No quality scopes were extracted from the model definition. The guard "
        "is blind, not the tree clean."
    )
    assert mapped, (
        "No scope labels were extracted from the web surface. The guard is "
        "blind, not the surface empty."
    )

    missing = sorted(defined - mapped)
    assert not missing, (
        "These quality scopes can be stored but the surface has no wording for "
        f"them: {missing}. A reviewer would be shown a raw identifier or an "
        "empty space where the population being described belongs. Add them to "
        f"QUALITY_SCOPE_LABELS in {QUALITY_TREND.relative_to(REPO)}."
    )
