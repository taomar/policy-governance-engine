"""Restating an approved rule in another vocabulary, without re-deciding it.

A projection describes the record it is attached to. It never re-answers the
question from the formulation, because those are different questions and they
come apart the moment either side changes -- which is what
`tests/unit/test_derived_views_do_not_contradict.py` exists to catch.

`xacml_projection` renders a rule in XACML 3.0 terms, the vocabulary this
platform adopted so a reviewer reads one screen in the same language as the
next. `dmn_parity` checks a compiled condition against the DMN table it came
from, so a mismatch is reported rather than silently preferred. `rule_delta`
and `export` are the other two ways a rule leaves the system: as a difference
against a previous version, and as a file.

All of it is deterministic. Nothing here calls a model, and nothing here
compiles logic -- the compiler runs once, at extraction, because re-deriving
executable logic on read would change what an approved rule does without anyone
reviewing the change.

Not to be confused with `search/projection.py`, which projects rules into the
Search index. Both are projections in the same sense -- a rule restated for a
consumer that needs it in different terms -- so they share the word
deliberately rather than by accident, and their dotted paths keep them apart.
Renaming one would put two vocabularies on one concept, which is the thing
`docs/how-we-work.md` warns costs a reader more than the ambiguity does.
"""
from __future__ import annotations
