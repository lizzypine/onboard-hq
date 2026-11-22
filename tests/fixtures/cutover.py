"""Guarded local cutover artifacts and backup tools; never application credentials."""

import os
import subprocess
import tarfile
from pathlib import Path

from psycopg.conninfo import conninfo_to_dict

from tests.database import ROOT, require_disposable_database
from tests.local_postgres import postgres_binaries

LEGACY_REVISION = "3f498780ab4703ec04363a6c0eafaac2db4c8430"


def extract_legacy(directory: Path) -> Path:
    directory.mkdir()
    archive = directory.parent / "legacy.tar"
    result = subprocess.run(
        [
            "git",
            "archive",
            "--format=tar",
            "--output",
            str(archive),
            LEGACY_REVISION,
            "app",
            "db",
            "tests",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, (
        "Pinned legacy revision must exist locally; CI needs fetch-depth: 0."
    )
    with tarfile.open(archive) as contents:
        contents.extractall(directory, filter="data")
    archive.unlink()
    assert not (directory / ".env").exists()
    return directory


def backup_environment(url: str) -> dict[str, str]:
    require_disposable_database(url, os.environ.get("DATABASE_URL"))
    options = conninfo_to_dict(url)
    return {
        "PATH": os.environ["PATH"],
        "PGHOST": options["host"],
        "PGPORT": options.get("port", "5432"),
        "PGUSER": options.get("user", "postgres"),
        "PGDATABASE": options["dbname"],
        "PGPASSWORD": options.get("password", ""),
        "PGSSLMODE": options.get("sslmode", "disable"),
        "PGCONNECT_TIMEOUT": "5",
        "PGPASSFILE": "/dev/null",
        "PGSERVICEFILE": "/dev/null",
    }


def dump_database(url: str, archive: Path) -> None:
    result = subprocess.run(
        [
            str(postgres_binaries() / "pg_dump"),
            "--format=custom",
            "--no-owner",
            "--no-acl",
            "--file",
            str(archive),
        ],
        env=backup_environment(url),
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, "Disposable PostgreSQL backup failed."
    assert archive.stat().st_size > 0


def restore_database(url: str, archive: Path) -> None:
    environment = backup_environment(url)
    result = subprocess.run(
        [
            str(postgres_binaries() / "pg_restore"),
            "--exit-on-error",
            "--no-owner",
            "--no-acl",
            "--dbname",
            environment["PGDATABASE"],
            str(archive),
        ],
        env=environment,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, (
        "Restore into the empty disposable PostgreSQL database failed."
    )
