"""Search-client stub helpers shared by the retrieval tests.

WHY THIS EXISTS

Retrieval asks the index one question before it asks it anything else: is this
project's corpus rendered under the projection a query is rendered under, and did
the rebuild that rendered it finish? A stub that cannot answer that question
answers "no", and every test built on it would then exercise the refusal path
rather than the path it was written for.

The question is one filtered lookup for the project's manifest document, so the
helper is one function: recognise that filter, answer it, and leave every other
lookup to the stub that owns it. Kept here rather than copied into each test file
so the shape of the probe lives in one place — if it changes, the tests that
depend on it change once.
"""
from __future__ import annotations

import json
from collections.abc import Sequence

#: The id a stub returns for a ready manifest. Its value is never read — the
#: probe asks whether anything matched, not what — so a fixed marker is clearer
#: than a plausible-looking digest that might be mistaken for one.
MANIFEST_ID = "manifest-stub"


def is_projection_probe(filter_expr: str) -> bool:
    """Whether this lookup is the readiness probe rather than a document sweep."""

    return "manifest_state" in (filter_expr or "")


def manifest_ids(
    filter_expr: str,
    *,
    ready: bool = True,
    otherwise: Sequence[str] | None = None,
) -> list[str]:
    """Answer the readiness probe; pass every other lookup through to ``otherwise``.

    ``ready=False`` is how a test says "this project's index carries no usable
    projection" without having to know how that is written down.
    """

    if is_projection_probe(filter_expr):
        return [MANIFEST_ID] if ready else []
    return list(otherwise or [])


def contained_payload(user_content: str) -> dict:
    """Recover the JSON object a projection prompt carried, as the model would.

    The corpus renderer delivers its payload as one JSON string on a single line
    between two nonce-bearing markers. A stub standing in for the model has to
    read it the same way, and doing that in one place keeps every stub honest
    about the containment rather than each inventing its own parsing.
    """

    body = user_content.split("-----\n", 1)[1].rsplit("\n-----", 1)[0]
    return json.loads(json.loads(body))


def echoing_projection_client(*, corrupt=None):
    """A model stub whose rendering returns each value it was given, unchanged.

    That is exactly what a faithful rendering of text already in the processing
    language does, so a rebuild driven by this stub produces documents carrying
    the text the corpus already held — and every preservation check the renderer
    applies still runs against it.

    ``corrupt`` is an optional ``(key, text) -> text`` used to make one value come
    back damaged, which is how a test exercises a check rather than describing it.
    """

    class _Client:
        def __init__(self, settings=None) -> None:
            self.settings = settings
            self.batches: list[dict] = []

        async def embed(self, texts):
            return [[float(index), 0.0, 1.0] for index, _text in enumerate(texts)]

        async def chat(self, messages, **_kwargs):
            payload = contained_payload(messages[-1]["content"])
            self.batches.append(payload)
            rendered = {
                key: (corrupt(key, value) if corrupt else value)
                for key, value in payload.items()
            }
            return json.dumps(rendered, ensure_ascii=False)

    return _Client

