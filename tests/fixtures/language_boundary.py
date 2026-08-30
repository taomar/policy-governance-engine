"""A double for the language boundary, so no test crosses it over the network.

WHY THIS EXISTS AS A SHARED FIXTURE

`ai_case_language` makes model calls, and it makes them from inside
`decide_project_case` — which several suites drive end to end. A suite that
reached the real deployment would be slow, non-deterministic, and would depend
on whatever the person running it has in their `.env`, which is exactly the
dependency `tests/conftest.py` exists to remove for identity settings.

So the boundary is stubbed the way the embedding client and the gather already
are, and it is stubbed **in one place** rather than per file: a test that forgot
would not fail, it would silently start calling a live endpoint, and a hazard
that fails silently is one that comes back.

The default behaviour is an identity crossing — the question is reported as
already being in the processing language and is returned unchanged — because
that is what makes every existing assertion in the suites that predate the
boundary mean what it meant before. A test that wants a real crossing, or a
failing one, says so.
"""
from __future__ import annotations

from typing import Any

from policy_platform.infrastructure.assistants import ai_case_language


class LanguageBoundarySpy:
    """Answers the three crossings, and records exactly what was asked of each.

    `scenarios` and `guidances` hold the text each inbound call was given, which
    is what a test asserting "the original never went downstream" reads. `prose`
    holds each outbound payload — the whole point being that it must contain
    field identifiers and prose and nothing else.
    """

    def __init__(
        self,
        *,
        source_language: str = ai_case_language.PROCESSING_LANGUAGE,
        english: str | None = None,
        guidance_english: str | None = None,
        rendered: dict[str, str] | None = None,
        render_suffix: str | None = None,
        scenario_error: Exception | None = None,
        guidance_error: Exception | None = None,
        render_error: Exception | None = None,
    ) -> None:
        self.source_language = source_language
        self.english = english
        self.guidance_english = guidance_english
        self.rendered = rendered
        self.render_suffix = render_suffix
        self.scenario_error = scenario_error
        self.guidance_error = guidance_error
        self.render_error = render_error

        self.scenarios: list[str] = []
        self.guidances: list[dict[str, Any]] = []
        self.prose: list[dict[str, str]] = []
        self.render_targets: list[str] = []

    # ── in ────────────────────────────────────────────────────────────

    async def normalise_scenario(self, scenario: str):
        self.scenarios.append(scenario)
        if self.scenario_error is not None:
            raise self.scenario_error
        english = self.english if self.english is not None else scenario
        return ai_case_language.NormalisedScenario(
            source_language=self.source_language,
            english=english,
            boundary_state=(
                ai_case_language.BOUNDARY_IDENTITY
                if self.source_language == ai_case_language.PROCESSING_LANGUAGE
                else ai_case_language.BOUNDARY_RENDERED
            ),
        )

    async def normalise_guidance(self, guidance: str, *, source_language: str):
        self.guidances.append({"guidance": guidance, "source_language": source_language})
        text = (guidance or "").strip()
        if not text or source_language == ai_case_language.PROCESSING_LANGUAGE:
            return ai_case_language.RenderedGuidance(
                text=guidance, state=ai_case_language.GUIDANCE_NOT_REQUIRED
            )
        if self.guidance_error is not None:
            return ai_case_language.RenderedGuidance(
                text="", state=ai_case_language.GUIDANCE_DROPPED
            )
        return ai_case_language.RenderedGuidance(
            text=self.guidance_english if self.guidance_english is not None else text,
            state=ai_case_language.GUIDANCE_RENDERED,
        )

    # ── out ───────────────────────────────────────────────────────────

    async def render_prose(self, fields, *, target_language: str) -> dict[str, str]:
        payload = dict(fields)
        self.prose.append(payload)
        self.render_targets.append(target_language)
        if self.render_error is not None:
            raise self.render_error
        if self.rendered is not None:
            return dict(self.rendered)
        suffix = self.render_suffix if self.render_suffix is not None else f" [{target_language}]"
        return {key: f"{value}{suffix}" for key, value in payload.items()}


def install_language_boundary(monkeypatch, **behaviour: Any) -> LanguageBoundarySpy:
    """Replace the three crossings for the duration of one test.

    Patched on the module rather than on the application's reference to it, so a
    caller reached through any import path gets the double — there is no second
    way in that a test could miss.
    """

    spy = LanguageBoundarySpy(**behaviour)
    monkeypatch.setattr(ai_case_language, "normalise_scenario", spy.normalise_scenario)
    monkeypatch.setattr(ai_case_language, "normalise_guidance", spy.normalise_guidance)
    monkeypatch.setattr(ai_case_language, "render_prose", spy.render_prose)
    return spy
