"""Locate prompt assets independently of where the calling module lives.

Three agents each resolved their own prompt with
``Path(__file__).parent / "prompts" / ...``. That ties the asset's location to
the *caller's* location, so moving an agent into a sub-package silently moves
the directory it looks in.

The failure mode is what makes this worth a module. Every one of those reads
happens inside a function — two of them behind ``lru_cache`` — so a wrong path
raises nothing at import and nothing at collection. It surfaces on a real
extraction run, as a missing file from an agent that had been working, at the
point where a document is being processed.

Anchoring here gives the prompt directory exactly one definition. A caller may
sit anywhere in the package and does not need to know where the assets are.
"""
from __future__ import annotations

from pathlib import Path

#: The one definition of where prompt assets live.
#:
#: Tests import this rather than rebuilding the path from their own location,
#: so a guard cannot end up scanning a directory that no longer exists.
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def prompt_path(name: str) -> Path:
    """Absolute path to a prompt asset, having confirmed it is there.

    Raises rather than returning a path that does not exist. A prompt read as
    an empty string would send the model a request carrying only the transport
    addendum, and the reply would be judged as a bad model rather than read as
    a packaging error — the expensive kind of wrong, because it looks like a
    result.
    """

    path = PROMPTS_DIR / name
    if not path.is_file():
        available = (
            sorted(p.name for p in PROMPTS_DIR.glob("*.md"))
            if PROMPTS_DIR.is_dir()
            else "<directory missing>"
        )
        raise FileNotFoundError(
            f"prompt asset {name!r} not found in {PROMPTS_DIR} (available: {available})"
        )
    return path


def load_prompt(name: str) -> str:
    """Read a prompt asset, trailing whitespace removed.

    Callers append their own transport addendum, which begins with its own
    separator, so the stored asset is stripped rather than joined blindly.
    """

    return prompt_path(name).read_text(encoding="utf-8").rstrip()
