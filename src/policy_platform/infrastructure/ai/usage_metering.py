"""Ambient collection of the token usage a model call reports.

Every Azure OpenAI chat response carries a ``usage`` block —
``prompt_tokens``, ``completion_tokens``, ``total_tokens`` and, on reasoning
deployments, a nested ``reasoning_tokens``. Until now the client read that block
only to explain a truncation and threw it away on the success path, so the one
cost figure the service hands back on every call reached no reader at all.

This module is the seam that lets a caller ask for those figures without every
one of :meth:`AzureOpenAIClient.chat`'s callers changing shape. ``chat`` returns
a bare string; threading a usage object back through its return type would touch
every call site, most of which do not want it. Instead the client *publishes*
each call's usage into whatever collection scope is active
(:func:`record_call_usage`), and a caller that wants the total opens a scope
around its work (:func:`collect_token_usage`) and reads the report afterwards.
A caller that opens no scope pays nothing and changes nothing: an un-collected
call is the "nobody asked" state, which this module keeps distinct from a call
that reported nothing.

Four outcomes are held apart deliberately, because collapsing them reports a
cost that did not happen (see the handover's constraint on absent/empty/
refused/failed):

* **reported** — the service returned figures (possibly zeros); they are summed.
* **no usage** — the call returned but carried no readable usage block; it is
  counted (``calls`` and ``calls_without_usage`` rise) but adds nothing to the
  sums, which stay absent rather than gaining a fabricated 0.
* **failed before the model** — the call never reached a response, so the client
  never records it here; it is simply absent from the scope.
* **not collected** — no scope was open, so :func:`record_call_usage` is a
  no-op; the figure was never asked for, which is not the same as zero.

No observed token count or model name is written here: this module names fields
and reports the numbers the service gave, and converts nothing to money —
pricing is per-model and per-date and lives outside this repository.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TokenUsage:
    """One model call's reported token usage.

    A field is ``None`` when the service did not report it. ``None`` is absent,
    which is not zero: a call that reported ``prompt_tokens = 0`` and a call that
    reported no usage block at all are different facts, and this type keeps them
    apart rather than defaulting the missing one to a count that never happened.
    """

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None

    @property
    def reported(self) -> bool:
        """True when the service returned at least one token figure for this call.

        False is the absent state — no usage block, or one holding nothing this
        module could read as a count — and is deliberately distinct from a call
        that reported zeros, which is ``True`` with zero values.
        """
        return any(
            value is not None
            for value in (
                self.prompt_tokens,
                self.completion_tokens,
                self.total_tokens,
                self.reasoning_tokens,
            )
        )


@dataclass(frozen=True)
class UsageReport:
    """The token usage of every model call made inside one collection scope.

    ``calls`` counts model calls that returned a response while the scope was
    active; ``calls_without_usage`` is how many of those returned no readable
    usage figure. When the two are equal nothing was reported and every token
    field is ``None`` — absent, not zero. Each token field is a sum over the
    calls that reported it, so a non-``None`` total taken together with
    ``calls_without_usage > 0`` is a floor rather than an exact figure, and the
    reader is told which by that count rather than by a silently-completed
    number.
    """

    calls: int = 0
    calls_without_usage: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None


class UsageScope:
    """Accumulates the usage of model calls made while it is the active scope.

    Created and installed by :func:`collect_token_usage`; a caller reads it back
    through :meth:`report`. It is not constructed directly by callers, but is
    public so a reader can name the type its ``with`` block yields.
    """

    def __init__(self) -> None:
        self._calls = 0
        self._calls_without_usage = 0
        self._prompt: int | None = None
        self._completion: int | None = None
        self._total: int | None = None
        self._reasoning: int | None = None

    def _record(self, usage: TokenUsage) -> None:
        self._calls += 1
        if not usage.reported:
            # A call happened but told us no tokens. Count it, and leave the sums
            # untouched: folding an absent figure in as 0 would report a cost of
            # zero where the truth is that the cost is unknown.
            self._calls_without_usage += 1
            return
        self._prompt = _add_optional(self._prompt, usage.prompt_tokens)
        self._completion = _add_optional(self._completion, usage.completion_tokens)
        self._total = _add_optional(self._total, usage.total_tokens)
        self._reasoning = _add_optional(self._reasoning, usage.reasoning_tokens)

    def report(self) -> UsageReport:
        """The usage accumulated so far, as an immutable snapshot."""
        return UsageReport(
            calls=self._calls,
            calls_without_usage=self._calls_without_usage,
            prompt_tokens=self._prompt,
            completion_tokens=self._completion,
            total_tokens=self._total,
            reasoning_tokens=self._reasoning,
        )


#: The scope model calls publish into. ``None`` means nobody is collecting, so a
#: recorded call has nowhere to go and is dropped — the "not collected" state.
#: A ContextVar rather than a module global so concurrent asks (the server serves
#: many at once) each meter only their own call, and a nested scope takes over
#: from its parent for its own duration without leaking across the boundary.
_active_scope: ContextVar[UsageScope | None] = ContextVar(
    "policy_platform_active_token_usage_scope", default=None
)


@contextmanager
def collect_token_usage() -> Iterator[UsageScope]:
    """Meter the token usage of model calls made inside this block.

    Opens a scope, yields it, and restores the previous scope on exit even if
    the block raises. Read the total from the yielded scope's
    :meth:`UsageScope.report` after the block::

        with collect_token_usage() as scope:
            await client.chat(messages, ...)
        usage = scope.report()

    Calls made with no scope open record nothing, so wrapping is opt-in: a code
    path that does not care about cost is unchanged and pays nothing.
    """
    scope = UsageScope()
    token = _active_scope.set(scope)
    try:
        yield scope
    finally:
        _active_scope.reset(token)


def record_call_usage(usage_block: Mapping[str, Any] | None) -> None:
    """Publish one model call's usage into the active scope, if one is open.

    Called by the client once per logical chat call, on the path where a
    response arrived — a retried call reaches here only after a response finally
    came back, so three HTTP attempts still record once, and a call that failed
    before any response never reaches here at all.

    ``usage_block`` is the raw ``usage`` object from the response, or ``None``
    when the response carried none. Either way a call is counted; a missing or
    unreadable block counts as a call that reported no tokens, its figures left
    absent rather than defaulted to zero. With no scope open this is a no-op.
    """
    scope = _active_scope.get()
    if scope is None:
        return
    scope._record(_parse_usage_block(usage_block))


def _parse_usage_block(block: Mapping[str, Any] | None) -> TokenUsage:
    """Read a response ``usage`` object into a :class:`TokenUsage`.

    Anything that is not a mapping of counts — ``None``, or a malformed block —
    becomes an all-absent usage, i.e. a call that reported nothing. A field that
    is present is read as-is (including a genuine 0); a field that is missing
    stays ``None``.
    """
    if not isinstance(block, Mapping):
        return TokenUsage()
    details = block.get("completion_tokens_details")
    reasoning = details.get("reasoning_tokens") if isinstance(details, Mapping) else None
    return TokenUsage(
        prompt_tokens=_int_or_none(block.get("prompt_tokens")),
        completion_tokens=_int_or_none(block.get("completion_tokens")),
        total_tokens=_int_or_none(block.get("total_tokens")),
        reasoning_tokens=_int_or_none(reasoning),
    )


def _int_or_none(value: Any) -> int | None:
    """A count, or absent. A ``bool`` is an ``int`` in Python but never a token
    count, so a stray flag is treated as absent rather than silently counted as
    0 or 1; a non-integer is likewise absent rather than coerced."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _add_optional(accumulated: int | None, value: int | None) -> int | None:
    """Sum that keeps absence absent.

    ``None`` on the left means no call has reported this field yet. Adding a
    reported value (including 0) makes it present; adding an absent value leaves
    it as it was. So a field becomes a number only once some call reported one,
    and a reported 0 is kept as 0 rather than folded back into "never reported".
    """
    if value is None:
        return accumulated
    if accumulated is None:
        return value
    return accumulated + value
