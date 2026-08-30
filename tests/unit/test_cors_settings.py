"""Tests for CORS origin resolution.

CORS failures are uniquely unhelpful to debug: the browser blocks the request
and the server logs nothing, so it presents as a broken backend. These tests
pin the behaviour that makes the allowlist predictable — and, more importantly,
that an explicitly configured list is never quietly widened.
"""
from __future__ import annotations

import pytest

from policy_platform.infrastructure.settings import Settings


def _settings(**overrides) -> Settings:
    # Both CORS fields are pinned, not just the database URLs, and for the same
    # reason: `Settings` reads a developer's `.env` for anything not passed here.
    # A machine with `CORS_ALLOWED_ORIGINS` set -- which any developer running the
    # playground against a live API has -- silently satisfies the explicit branch
    # of `allowed_cors_origins`, so every derivation test below was asserting
    # against that machine's operational config instead of the committed default.
    # It read as several unrelated CORS regressions and was neither.
    #
    # Pinned rather than monkeypatched so the isolation is a property of the
    # helper every test already goes through, and cannot be forgotten by the next
    # test added here. Overrides still win, so the explicit-configuration tests
    # below set exactly what they mean to test.
    base = {
        "database_url": "postgresql+asyncpg://u:p@localhost:5433/db",
        "alembic_database_url": "postgresql+psycopg://u:p@localhost:5433/db",
        "cors_allowed_origins": "",
        "cors_dev_port_range": "5173-5180",
    }
    base.update(overrides)
    return Settings(**base)


class TestDerivedOrigins:
    def test_the_configured_ui_port_is_allowed(self) -> None:
        origins = _settings(web_dev_server_port=5490).allowed_cors_origins
        assert "http://localhost:5490" in origins

    def test_both_hostnames_are_allowed(self) -> None:
        """localhost and 127.0.0.1 are different origins to a browser, and
        which one a developer types is not predictable."""

        origins = _settings(web_dev_server_port=5490).allowed_cors_origins
        assert "http://localhost:5490" in origins
        assert "http://127.0.0.1:5490" in origins

    def test_the_vite_fallback_range_is_allowed(self) -> None:
        """Vite increments its port when the preferred one is taken."""

        origins = _settings(web_dev_server_port=5490).allowed_cors_origins
        for port in (5173, 5174, 5180):
            assert f"http://localhost:{port}" in origins

    def test_the_range_is_inclusive_of_its_upper_bound(self) -> None:
        origins = _settings(cors_dev_port_range="5173-5175").allowed_cors_origins
        assert "http://localhost:5175" in origins
        assert "http://localhost:5176" not in origins

    def test_an_unrelated_port_is_not_allowed(self) -> None:
        """The allowlist must actually exclude something, or it is not one."""

        origins = _settings(web_dev_server_port=5490).allowed_cors_origins
        assert "http://localhost:9999" not in origins

    def test_no_duplicate_origins_when_the_ui_port_is_inside_the_range(self) -> None:
        origins = _settings(web_dev_server_port=5174).allowed_cors_origins
        assert len(origins) == len(set(origins))


class TestExplicitOrigins:
    def test_an_explicit_list_is_used_verbatim(self) -> None:
        origins = _settings(
            cors_allowed_origins="https://policy.example.com"
        ).allowed_cors_origins
        assert origins == ["https://policy.example.com"]

    def test_an_explicit_list_is_not_widened_by_the_dev_range(self) -> None:
        """An operator who names origins means those and no others.

        Unioning them with a development range would silently widen production
        beyond what was configured.
        """

        origins = _settings(
            cors_allowed_origins="https://policy.example.com",
            web_dev_server_port=5490,
        ).allowed_cors_origins

        assert "http://localhost:5490" not in origins
        assert "http://localhost:5173" not in origins

    def test_multiple_origins_are_split_and_trimmed(self) -> None:
        origins = _settings(
            cors_allowed_origins=" https://a.example.com , https://b.example.com "
        ).allowed_cors_origins
        assert origins == ["https://a.example.com", "https://b.example.com"]

    def test_empty_entries_are_ignored(self) -> None:
        """A trailing comma must not produce an empty origin, which would be
        compared against and never match anything useful."""

        origins = _settings(
            cors_allowed_origins="https://a.example.com,,"
        ).allowed_cors_origins
        assert origins == ["https://a.example.com"]

    def test_a_whitespace_only_value_falls_back_to_derived(self) -> None:
        origins = _settings(cors_allowed_origins="   ", web_dev_server_port=5490).allowed_cors_origins
        assert "http://localhost:5490" in origins


class TestMalformedConfiguration:
    @pytest.mark.parametrize("value", ["", "not-a-range", "5173", "abc-def", "5173-"])
    def test_a_bad_range_falls_back_rather_than_failing_to_boot(self, value: str) -> None:
        """A typo in a port range is cosmetic; refusing to start over it would
        turn that into an outage."""

        origins = _settings(cors_dev_port_range=value, web_dev_server_port=5490).allowed_cors_origins

        assert "http://localhost:5490" in origins
        assert "http://localhost:5173" in origins


class TestApplicationWiring:
    def test_the_app_uses_the_configured_origins(self, monkeypatch) -> None:
        """Guards against the allowlist being computed but never applied."""

        import os

        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5433/db")
        monkeypatch.setenv("ALEMBIC_DATABASE_URL", "postgresql+psycopg://u:p@localhost:5433/db")
        monkeypatch.setenv("WEB_DEV_SERVER_PORT", "5490")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "")

        from policy_platform.infrastructure.settings import get_settings

        get_settings.cache_clear()
        try:
            from policy_platform.api.app import create_app

            app = create_app()
            configured = [
                middleware.kwargs.get("allow_origins")
                for middleware in app.user_middleware
                if "allow_origins" in getattr(middleware, "kwargs", {})
            ]
            assert configured, "no CORS middleware was registered"
            assert "http://localhost:5490" in configured[0]
        finally:
            get_settings.cache_clear()
            os.environ.pop("WEB_DEV_SERVER_PORT", None)
