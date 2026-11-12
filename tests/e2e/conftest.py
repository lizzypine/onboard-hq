"""Real HTTP server lifecycle with a guarded database and no application secrets."""

import os
import socket
import subprocess
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen

import pytest
from playwright.sync_api import sync_playwright

from tests.database import ROOT, require_disposable_database


class AppServer:
    def __init__(self, database_url, log_path):
        require_disposable_database(database_url, None)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self.database_url = database_url
        self.scenario = "completed"
        self.log_path = log_path
        self.process = None
        self.log_handle = None

    def start(self):
        require_disposable_database(self.database_url, None)
        self.log_handle = self.log_path.open("a")
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tests.e2e.server",
                "--port",
                str(self.port),
                "--scenario",
                self.scenario,
            ],
            cwd=ROOT,
            env={
                "PATH": os.environ["PATH"],
                "DATABASE_URL": self.database_url,
                "PYTHONPATH": str(ROOT),
                "PYTHONUNBUFFERED": "1",
            },
            stdout=self.log_handle,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"Test server exited; inspect {self.log_path}")
            try:
                with urlopen(self.url, timeout=0.3) as response:
                    if response.status == 200:
                        return
            except (URLError, TimeoutError):
                threading.Event().wait(0.05)
        raise RuntimeError(f"Test server did not become ready; inspect {self.log_path}")

    def stop(self):
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            self.process = None
        if self.log_handle is not None:
            self.log_handle.close()
            self.log_handle = None

    def restart(self, scenario=None):
        self.stop()
        if scenario is not None:
            self.scenario = scenario
        self.start()


@pytest.fixture
def app_server(db_url, seeded_provider, tmp_path):
    server = AppServer(db_url, tmp_path / "test-server.log")
    try:
        server.start()
        yield server
    finally:
        server.stop()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call":
        item.browser_test_failed = report.failed


@pytest.fixture
def page(app_server, request):
    """Close Playwright's event loop before the next synchronous/asyncio test."""
    with sync_playwright() as engine:
        browser = engine.chromium.launch()
        context = browser.new_context()
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        current_page = context.new_page()
        try:
            yield current_page
        finally:
            if getattr(request.node, "browser_test_failed", False):
                directory = ROOT / "test-results"
                directory.mkdir(exist_ok=True)
                context.tracing.stop(path=directory / (request.node.name + ".zip"))
            else:
                context.tracing.stop()
            context.close()
            browser.close()
