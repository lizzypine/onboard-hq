"""Database configuration and isolation must reject unsafe targets without secrets."""

import pytest


@pytest.mark.parametrize("value", ["", "https://example.test/db", "postgresql:///db"])
def test_database_configuration_rejects_invalid_urls(monkeypatch, value):
    from app.database import DatabaseConfigurationError, database_url

    monkeypatch.setenv("DATABASE_URL", value)
    with pytest.raises(DatabaseConfigurationError):
        database_url()


def test_configuration_errors_do_not_echo_credentials(monkeypatch):
    from app.database import DatabaseConfigurationError, database_url

    monkeypatch.setenv("DATABASE_URL", "https://user:sentinel-secret@example.test/db")
    with pytest.raises(DatabaseConfigurationError) as error:
        database_url()
    assert "sentinel-secret" not in str(error.value)


def test_database_configuration_preserves_postgresql_connection_options(monkeypatch):
    from app.database import database_url

    url = "postgresql://user:secret@localhost/onboard?sslmode=require"
    monkeypatch.setenv("DATABASE_URL", url)
    assert database_url() == url


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://user:sentinel-secret@ep-demo-pooler.neon.tech/app",
        "postgresql://localhost/production",
        "postgresql://localhost/postgres",
        "postgresql://user:secret@remote.example/onboard_hq_test_x",
    ],
)
def test_test_database_guard_rejects_unsafe_targets(url):
    from tests.database import require_disposable_database

    with pytest.raises(ValueError) as error:
        require_disposable_database(url, url.replace("-pooler", ""))
    assert "sentinel-secret" not in str(error.value)


def test_test_database_guard_accepts_isolated_loopback_target():
    from tests.database import require_disposable_database

    require_disposable_database(
        "postgresql://localhost:55432/onboard_hq_test_local", None
    )


def test_test_database_guard_rejects_application_database_even_on_loopback():
    from tests.database import require_disposable_database

    url = "postgresql://localhost/onboard_hq_test_app"
    with pytest.raises(ValueError):
        require_disposable_database(url, url)
