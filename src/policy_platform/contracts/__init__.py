"""policy_platform.contracts

Provider-neutral canonical policy representation (Section 14 of the spec).

This package MUST NOT import anything from policy_platform.infrastructure,
policy_platform.api, or any Azure/AI/HTTP SDK. It is pure data modeling
(Pydantic v2) consumed by both the evaluator and the API layer.
"""
