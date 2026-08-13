"""Turning clauses into candidate rules, and deciding what can be computed.

The pipeline runs in two model stages and then stops using the model. Stage one
(`passage_extractor`) lifts passages verbatim; stage two (`policy_formulator`)
proposes a canonical policy and a DMN projection. Everything after that is
plain Python.

`formulation_mapping` is where the compiler lives, and it runs here, once. An
expression it does not fully understand yields no condition rather than a
guess, because a synthesised always-false node is a constraint the document
never stated. Nothing re-derives executable logic on read: doing so would
change what an approved rule does without anyone reviewing the change, which is
why the compiler is in extraction and not in a mapper.

`policy_facts`, `policy_parties` and `evaluability` decide what a record can
support -- which facts it publishes, who it binds, and whether the source
states a computable test at all. That last one produces `evaluation_mode`, and
it is a route rather than a verdict: `deterministic` when the source states a
threshold, date or count; `ai_ready` when the source states it in words a
reader must weigh. Neither is a defect, and ten of the recorded mutations sit
in this package holding that line.

The prompts stay one level up, in `infrastructure/prompts/`, because
`correlation_agent` reads from the same directory and because a package-data
declaration is keyed to `policy_platform.infrastructure` -- moving them would
drop them from a built wheel while every test still passed.
"""
from __future__ import annotations
