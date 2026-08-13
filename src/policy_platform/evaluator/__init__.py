"""policy_platform.evaluator

Deterministic policy evaluation engine (Section 15).

HARD CONSTRAINT (Section 5.4 / ADR-0002 / ADR-0003): this package must never
import policy_platform.infrastructure, policy_platform.api, or any
network/AI/Search SDK. Only the Python standard library and
policy_platform.contracts may be imported here.
"""
