"""Limits that apply across a set of rules rather than within one.

A single rule answers a question about one request. An aggregate limit answers
one about a run of them -- how much has already been drawn against a cap, and
whether this request still fits.

`aggregate_eligibility` decides which rules a limit may legitimately be drawn
from; `aggregate_preview` shows what a proposed limit would have done, by
calling the evaluator rather than by describing it; `ai_aggregate_proposal`
drafts a limit for a human to accept or reject. The draft is a proposal and
nothing more: the limit that takes effect is the one a person published.
"""
from __future__ import annotations
