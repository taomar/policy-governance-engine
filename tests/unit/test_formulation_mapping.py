"""Mapping from the canonical record into a platform rule."""

from __future__ import annotations

from policy_platform.contracts.formulation import CanonicalPolicyRule, CanonicalRuleType
from policy_platform.infrastructure.formulation_mapping import _exceptions_for


class TestCanonicalExceptionReachesTheRule:
    """The formulator captured carve-out language and the mapping dropped it.

    Across the whole AD-103 corpus no rule carried a single RuleException while
    the canonical records held the exception text all along — AI-c3e9ccec25
    carries "Unless otherwise stipulated in the employment contract".
    """

    def _canonical(self, exception=None):
        return CanonicalPolicyRule(
            rule_type=CanonicalRuleType.CALCULATION,
            subject="The housing allowance per calendar year (12 months)",
            predicate="is calculated",
            calculation="as twice the monthly basic salary",
            exception=exception,
        )

    def test_the_exception_text_survives(self):
        excs = _exceptions_for(self._canonical("Unless otherwise stipulated in the employment contract"))
        assert len(excs) == 1
        assert excs[0].description == "Unless otherwise stipulated in the employment contract"

    def test_no_condition_or_override_is_invented(self):
        """The source says what the exception *is*, not what it tests or what
        it changes the outcome to. RuleException allows a prose carve-out with
        neither, so nothing has to be manufactured to record it."""

        excs = _exceptions_for(self._canonical("Unless otherwise stipulated in the employment contract"))
        assert excs[0].condition is None
        assert excs[0].effect_override is None
        assert excs[0].limit_value is None

    def test_no_exception_yields_an_empty_list(self):
        assert _exceptions_for(self._canonical(None)) == []
        assert _exceptions_for(self._canonical("   ")) == []
        assert _exceptions_for(None) == []

    def test_the_id_is_stable_across_runs(self):
        """A UUID would make an unchanged document report a changed rule on
        every re-extraction, because exceptions are part of the delta
        fingerprint."""

        text = "Unless otherwise stipulated in the employment contract"
        assert _exceptions_for(self._canonical(text))[0].exception_id == (
            _exceptions_for(self._canonical(text))[0].exception_id
        )

    def test_the_id_ignores_whitespace_and_case(self):
        a = _exceptions_for(self._canonical("Unless otherwise stipulated"))[0]
        b = _exceptions_for(self._canonical("unless   otherwise\n\nstipulated"))[0]
        assert a.exception_id == b.exception_id

    def test_different_exceptions_get_different_ids(self):
        a = _exceptions_for(self._canonical("Unless otherwise stipulated in the contract"))[0]
        b = _exceptions_for(self._canonical("Except for probationary employees"))[0]
        assert a.exception_id != b.exception_id
