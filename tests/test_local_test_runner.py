"""Verify bare pytest owns and cleans up only disposable local PostgreSQL."""

import json
import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

from tests.database import ROOT, configured_test_url, require_disposable_database

PLUGIN = """
import json
import os
from pathlib import Path
import psycopg

def pytest_runtest_call():
    if os.environ.get("FORCE_CHILD_FAILURE"):
        raise AssertionError("deliberate lifecycle failure")

def pytest_runtest_teardown():
    path = Path(os.environ["CAPTURE_DATABASE"])
    url = os.environ.get("TEST_DATABASE_URL")
    if url and not path.exists():
        with psycopg.connect(url) as connection:
            directory = connection.execute("SHOW data_directory").fetchone()[0]
        path.write_text(json.dumps({"url": url, "directory": directory}))
"""


@pytest.mark.parametrize("fail", [False, True])
def test_bare_pytest_cleans_owned_database(tmp_path: Path, fail: bool):
    (tmp_path / "capture_database.py").write_text(PLUGIN)
    capture = tmp_path / "database.json"
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DATABASE_", "TEST_DATABASE_", "LLM_", "PG"))
    }
    environment.update(
        PYTHONPATH=os.pathsep.join([str(tmp_path), str(ROOT)]),
        CAPTURE_DATABASE=str(capture),
    )
    if "PG18_BIN" in os.environ:
        environment["PG18_BIN"] = os.environ["PG18_BIN"]
    if fail:
        environment["FORCE_CHILD_FAILURE"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_queries.py",
            "-p",
            "capture_database",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == (1 if fail else 0), result.stdout + result.stderr
    assert capture.exists(), result.stdout + result.stderr
    saved = json.loads(capture.read_text())
    require_disposable_database(saved["url"], None)
    assert not Path(saved["directory"]).exists()
    with pytest.raises(psycopg.OperationalError):
        psycopg.connect(saved["url"], connect_timeout=2)


def test_explicit_unsafe_url_is_rejected_without_fallback(monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://example.invalid/production")
    with pytest.raises(ValueError, match="separate loopback"):
        configured_test_url()
