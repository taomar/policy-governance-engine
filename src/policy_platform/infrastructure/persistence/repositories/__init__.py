"""Every repository, grouped by what its rows describe.

One module per part of the lifecycle rather than one file of sixteen
classes. The names are re-exported here because that is how this package
is consumed and how `policy_platform.domain` already presents itself: a
caller asks for a repository, not for the module it happens to live in.
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
    PolicyAggregateLimitRepository,
)
from policy_platform.infrastructure.persistence.repositories.evaluations import (
    EvaluationRepository,
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

__all__ = [
    "ApprovedPolicyVersionRepository",
    "CandidateRuleRepository",
    "ClauseRepository",
    "EvaluationRepository",
    "EvidenceReferenceRepository",
    "ExtractionRunRepository",
    "NoteRepository",
    "PolicyAggregateLimitRepository",
    "PolicyAttestationRepository",
    "PolicyAuthorityRepository",
    "PolicyExceptionRepository",
    "PolicySetRepository",
    "PolicyTestBatchRepository",
    "PolicyTestRepository",
    "PolicyTestRunRepository",
    "QualityRunRepository",
]
