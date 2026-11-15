"""Lazy, test-only ownership of a temporary loopback PostgreSQL 18 cluster."""

import atexit
import os
import shutil
import socket
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LocalCluster:
    directory: Path
    binaries: Path
    url: str


_cluster: LocalCluster | None = None


def postgres_binaries() -> Path:
    candidates = [
        os.environ.get("PG18_BIN", ""),
        "/opt/homebrew/opt/postgresql@18/bin",
        "/usr/local/opt/postgresql@18/bin",
        "/usr/lib/postgresql/18/bin",
    ]
    for candidate in candidates:
        if candidate and (Path(candidate) / "initdb").is_file():
            result = subprocess.run(
                [str(Path(candidate) / "initdb"), "--version"],
                capture_output=True,
                text=True,
                check=True,
            )
            if " 18." in result.stdout:
                return Path(candidate)
    raise RuntimeError(
        "Install PostgreSQL 18 tools and set PG18_BIN to their bin directory."
    )


def run_tool(cluster: LocalCluster, tool: str, *arguments: str) -> None:
    subprocess.run(
        [str(cluster.binaries / tool), *arguments],
        env={
            key: value for key, value in os.environ.items() if not key.startswith("PG")
        },
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )


def stop_local_database() -> None:
    global _cluster
    if _cluster is None:
        return
    cluster = _cluster
    data = cluster.directory / "data"
    if (data / "postmaster.pid").exists():
        run_tool(cluster, "pg_ctl", "-D", str(data), "stop", "-m", "fast")
    shutil.rmtree(cluster.directory)
    if os.environ.get("TEST_DATABASE_URL") == cluster.url:
        del os.environ["TEST_DATABASE_URL"]
    _cluster = None


def local_database_url() -> str:
    global _cluster
    if _cluster is not None:
        return _cluster.url
    binaries = postgres_binaries()
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    directory = Path(tempfile.mkdtemp(prefix="onboard-test-"))
    url = (
        f"postgresql://postgres@127.0.0.1:{port}/onboard_hq_test_local?sslmode=disable"
    )
    _cluster = LocalCluster(directory, binaries, url)
    data = str(directory / "data")
    try:
        run_tool(
            _cluster,
            "initdb",
            "-D",
            data,
            "-U",
            "postgres",
            "-A",
            "trust",
            "--no-locale",
            "-E",
            "UTF8",
        )
        run_tool(
            _cluster,
            "pg_ctl",
            "-D",
            data,
            "-l",
            str(directory / "postgres.log"),
            "-o",
            f"-h 127.0.0.1 -p {port} -k ''",
            "start",
        )
        run_tool(
            _cluster,
            "createdb",
            "-h",
            "127.0.0.1",
            "-p",
            str(port),
            "-U",
            "postgres",
            "onboard_hq_test_local",
        )
    except BaseException:
        stop_local_database()
        raise
    os.environ["TEST_DATABASE_URL"] = url
    return url


atexit.register(stop_local_database)
