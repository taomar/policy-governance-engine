"""Things the platform offers a reviewer, none of which decide anything.

Chat grounded in indexed clauses, a drafted rule, a rewritten one, a summary, a
narrative for a version difference, and a scenario run against a rule to show
what it would do.

Every output here is a draft or an observation. It reaches a published version
only by a human accepting it, and the evaluator never reads any of it -- it
reads approved, versioned rules and nothing else. That is the trust boundary
`docs/architecture.md` describes, and this package sits entirely on the
probabilistic side of it.

`ai_scenario_engine` is the exception worth naming, because it looks like it
decides. It calls the deterministic evaluator to get the outcome and uses the
model only to describe the scenario, so the decision is code's and the prose is
the model's. Three of the recorded mutations live here, guarding that a rule
decided by reading is offered as a route rather than reported as a fault.

`rule_change_explainer` is here rather than with projection for the same
reason: `rule_delta` computes the difference deterministically, and this only
narrates what that computation found.
"""
from __future__ import annotations
