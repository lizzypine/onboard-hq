"""Guard every destructive test database operation and migration."""

import os
import subprocess
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
from psycopg import ProgrammingError, sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

ROOT = Path(__file__).resolve().parents[1]


def _identity(options):
    host = options.get("host", "").replace("-pooler.", ".")
    return host, options.get("port", "5432"), options.get("dbname")


def require_disposable_database(test_url: str, application_url: str | None) -> None:
    """Only explicitly named loopback test databases may be changed by tests."""
    try:
        parsed = urlsplit(test_url)
        if parsed.scheme not in {"postgres", "postgresql"}:
            raise ValueError
        options = conninfo_to_dict(test_url)
        if application_url and _identity(options) == _identity(
            conninfo_to_dict(application_url)
        ):
            raise ValueError
        if options.get("host") not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError
        if options.get("hostaddr") not in {None, "127.0.0.1", "::1"} or options.get(
            "service"
        ):
            raise ValueError
        if not options.get("dbname", "").startswith("onboard_hq_test_"):
            raise ValueError
    except (ValueError, ProgrammingError):
        raise ValueError(
            "Tests require a separate loopback onboard_hq_test_* database."
        ) from None


def configured_test_url() -> str:
    value = os.environ.get("TEST_DATABASE_URL", "")
    if not value:
        raise ValueError(
            "Run bash scripts/test.sh uv run pytest to configure PostgreSQL tests."
        )
    require_disposable_database(value, os.environ.get("DATABASE_URL"))
    return value


def migrate_test_database(url: str) -> None:
    require_disposable_database(url, os.environ.get("DATABASE_URL"))
    result = subprocess.run(
        [str(ROOT / ".superpowers/bin/dbmate"), "--no-dump-schema", "migrate"],
        cwd=ROOT,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            "Isolated test migrations failed; check dbmate and PostgreSQL setup."
        )


@contextmanager
def disposable_database():
    base = configured_test_url()
    name = "onboard_hq_test_" + uuid4().hex
    with psycopg.connect(
        make_conninfo(base, dbname="postgres"), autocommit=True
    ) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        url = urlsplit(base)._replace(path="/" + name).geturl()
        try:
            yield url
        finally:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
