"""Application services — the layer between an HTTP route and the machinery.

A service here owns a *use case*, not a table and not an endpoint. It is where
the ordering that makes a use case correct lives: which write must be committed
before an expensive call, what happens when that call fails, and which of
several routes may reach the same behaviour.

There is one today, `policy_case_decision`, and it exists because two endpoints
must share one decider without sharing its consequences. The rule it enforces —
that only this package calls `ai_case_project.answer_project_case` — is asserted
by a test, so a third caller cannot appear quietly.
"""
