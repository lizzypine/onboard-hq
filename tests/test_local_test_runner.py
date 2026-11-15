"""Verify bare pytest owns and cleans up only disposable local PostgreSQL."""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import psycopg
import pytest

from tests.database import ROOT, configured_test_url, require_disposable_database
from tests.local_postgres import LocalCluster, postgres_binaries, run_tool

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


def test_sigterm_cleans_owned_database(tmp_path: Path):
    capture = tmp_path / "terminated-database.json"
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DATABASE_", "TEST_DATABASE_", "LLM_", "PG"))
    }
    environment.update(PYTHONPATH=str(ROOT), CAPTURE_DATABASE=str(capture))
    if "PG18_BIN" in os.environ:
        environment["PG18_BIN"] = os.environ["PG18_BIN"]
    script = """
import json, os, signal
from pathlib import Path
import psycopg
from tests.local_postgres import local_database_url
url = local_database_url()
with psycopg.connect(url) as connection:
    directory = connection.execute("SHOW data_directory").fetchone()[0]
Path(os.environ["CAPTURE_DATABASE"]).write_text(json.dumps({"url": url, "directory": directory}))
signal.pause()
"""
    saved = None
    with subprocess.Popen(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as child:
        try:
            deadline = time.monotonic() + 30
            while (
                not capture.exists()
                and child.poll() is None
                and time.monotonic() < deadline
            ):
                time.sleep(0.05)
            assert capture.exists(), "Child did not start its owned test database"
            saved = json.loads(capture.read_text())
            require_disposable_database(saved["url"], None)
            child.send_signal(signal.SIGTERM)
            child.communicate(timeout=15)
            assert child.returncode != 0
            assert not Path(saved["directory"]).exists()
            with pytest.raises(psycopg.OperationalError):
                psycopg.connect(saved["url"], connect_timeout=2)
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate(timeout=10)
            # Remove only this reproduction's cluster, even while the regression is RED.
            if saved and Path(saved["directory"]).exists():
                directory = Path(saved["directory"])
                cluster = LocalCluster(
                    directory.parent, postgres_binaries(), saved["url"]
                )
                if (directory / "postmaster.pid").exists():
                    run_tool(
                        cluster, "pg_ctl", "-D", str(directory), "stop", "-m", "fast"
                    )
                shutil.rmtree(directory.parent)
