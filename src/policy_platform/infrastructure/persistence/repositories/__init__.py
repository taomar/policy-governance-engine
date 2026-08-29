"""Every repository, grouped by what its rows describe.

One module per part of the lifecycle rather than one file of sixteen
classes. The names are re-exported here because that is how this package
is consumed and how `policy_platform.domain` already presents itself: a
caller asks for a repository, not for the module it happens to live in.

Enforces Rule 5.3 -- approved artifacts are immutable, so the versions module
is insert-only and never updates a published row in place.

The module this replaced opened by calling itself "the only place that issues
SQL against domain entities". That was not true when it was written and is not
true now: seventeen `session.execute` calls sit in six files under `api/`. The
intent is right and the claim was not, so it is stated as an intent here. What
the layer does guarantee is that everything routed through it goes through a
repository; what it cannot guarantee is that everything goes through it. The
count is tracked in `docs/known-limitations.md`.
"""
from __future__ import annotations

from policy_platform.infrastructure.persistence.repositories.policy_sets import (
    PolicyAuthorityRepository,
    PolicySetRepository,
)
from policy_platform.infrastructure.persistence.repositories.documents import (
    ClauseRepository,
    EvidenceReferenceRepository,
)
from policy_platform.infrastructure.persistence.repositories.candidates import (
    CandidateRuleRepository,
    ExtractionRunRepository,
    QualityRunRepository,
)
from policy_platform.infrastructure.persistence.repositories.versions import (
    ApprovedPolicyVersionRepository,
)
from policy_platform.infrastructure.persistence.repositories.evaluations import (
    EvaluationRepository,
)
from policy_platform.infrastructure.persistence.repositories.case_decisions import (
    PolicyCaseDecisionRepository,
)
from policy_platform.infrastructure.persistence.repositories.policy_tests import (
    PolicyTestBatchRepository,
    PolicyTestRepository,
    PolicyTestRunRepository,
)
from policy_platform.infrastructure.persistence.repositories.governance import (
    NoteRepository,
    PolicyAttestationRepository,
    PolicyExceptionRepository,
)
from policy_platform.infrastructure.persistence.repositories.review_requests import (
    PolicyReviewRequestRepository,
)

__all__ = [
    "ApprovedPolicyVersionRepository",
    "CandidateRuleRepository",
    "ClauseRepository",
    "EvaluationRepository",
    "EvidenceReferenceRepository",
    "ExtractionRunRepository",
    "NoteRepository",
    "PolicyAttestationRepository",
    "PolicyAuthorityRepository",
    "PolicyCaseDecisionRepository",
    "PolicyExceptionRepository",
    "PolicySetRepository",
    "PolicyTestBatchRepository",
    "PolicyTestRepository",
    "PolicyTestRunRepository",
    "PolicyReviewRequestRepository",
    "QualityRunRepository",
]
