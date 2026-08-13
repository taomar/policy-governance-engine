"""Infrastructure layer: everything that touches the outside world.

Grouped into sub-packages by the question each answers rather than by the
technology each uses, so a module that calls a model sits with the capability
it serves. `persistence`, `ingestion`, `docling`, `extraction`, `projection`,
`quality`, `correlation`, `aggregates`, `policy_tests`, `assistants`, and the
`ai` and `search` clients. `docs/architecture.md` carries the table.

Two modules stay here rather than in a sub-package. `settings` is imported
across every one of them, so it is genuinely cross-cutting. `prompt_assets`
locates the `prompts/` directory relative to itself and has to sit level with
it -- and `prompts/` stays put because two different sub-packages read from it
and because the package-data declaration in `pyproject.toml` is keyed to this
package, so moving it would drop the prompts from a built wheel while every
test still passed.
"""
from __future__ import annotations
