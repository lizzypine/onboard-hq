"""Rehearse an authentic old browser save, atomic cutover, and backup recovery."""

from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest
from playwright.sync_api import expect

from tests.database import ROOT, disposable_database
from tests.e2e.conftest import AppServer
from tests.e2e.test_checklist_edits import editor, row
from tests.e2e.test_provider_creation import fill_form, save_form
from tests.fixtures.cutover import dump_database, extract_legacy, restore_database
from tests.fixtures.legacy_database import (
    LegacyGraph,
    dbmate,
    migrate_legacy,
    seed_legacy_graph,
)


@dataclass
class Rehearsal:
    server: AppServer
    graph: LegacyGraph
    url: str
    legacy_root: Path
    backup: Path
    pending: dict


@pytest.fixture
def legacy_cutover(page, app_server, tmp_path):
    legacy_root = extract_legacy(tmp_path / "legacy")
    with disposable_database() as url:
        migrate_legacy(url)
        graph = seed_legacy_graph(url)
        app_server.stop()
        server = AppServer(
            url, tmp_path / "cutover-server.log", source_root=legacy_root
        )
        server.port, server.url = app_server.port, app_server.url
        try:
            server.start()
            page.goto(server.url)
            expect(page.locator("#requirements")).to_contain_text("Completed")
            page.get_by_label("Original update", exact=True).fill(
                "Drug screening completed."
            )
            page.get_by_role("button", name="Analyze update", exact=True).click()
            expect(page.locator("#request-status")).to_contain_text(
                "Update and suggestions saved"
            )
            page.get_by_label("Simulated role", exact=True).select_option("manager")
            row(page).get_by_role("button", name="Edit", exact=True).click()
            group = editor(page)
            group.get_by_role(
                "combobox", name="Checklist status", exact=True
            ).select_option("Incomplete")
            group.get_by_label("Requirement date", exact=True).fill("2026-11-21")
            group.get_by_label("Deadline", exact=True).fill("2026-11-30")

            def lose_response(route):
                route.fetch()
                route.abort("failed")

            page.route("**/edits", lose_response)
            group.get_by_role("button", name="Save changes", exact=True).click()
            expect(page.locator("#checklist-status")).to_contain_text(
                "could not be confirmed"
            )
            page.unroute("**/edits", lose_response)
            pending = page.evaluate(
                'JSON.parse(sessionStorage.getItem("onboard-hq:pending-checklist-edit"))'
            )
            assert pending["providerId"] == str(graph.provider_key)
            assert pending["body"]["expected_version"] == 7
            server.stop()
            backup = tmp_path / "final-pre-cutover.dump"
            dump_database(url, backup)
            # Verify the final backup before modifying the source database.
            with disposable_database() as verification_url:
                restore_database(verification_url, backup)
                with psycopg.connect(verification_url) as conn:
                    assert conn.execute(
                        "SELECT status,version FROM requirements"
                    ).fetchone() == ("Incomplete", 8)
                    assert conn.execute(
                        "SELECT count(*) FROM checklist_edits WHERE id=%s",
                        (pending["body"]["id"],),
                    ).fetchone() == (1,)
            yield Rehearsal(server, graph, url, legacy_root, backup, pending)
        finally:
            server.stop()


def test_real_old_browser_cutover_preserves_history_and_all_current_flows(
    page, legacy_cutover
):
    rehearsal = legacy_cutover
    server, graph = rehearsal.server, rehearsal.graph
    result = dbmate(rehearsal.url, "up")
    assert result.returncode == 0, result.stderr
    server.source_root = ROOT
    server.start()
    page.reload()
    expect(page.locator("#legacy-checklist-status")).to_contain_text("already saved")
    expect(row(page)).to_contain_text("Incomplete")
    expect(row(page)).to_contain_text("2026-11-21")
    expect(row(page)).to_contain_text("2026-11-30")
    assert (
        page.evaluate('sessionStorage.getItem("onboard-hq:pending-checklist-edit")')
        is None
    )
    providers = page.request.get(server.url + "/providers").json()
    provider = providers[0]
    assert type(provider["id"]) is int
    assert provider["creation_request_id"] == str(graph.provider_key)
    history = page.request.get(
        server.url + f"/providers/{provider['id']}/updates"
    ).json()
    historical = next(
        update for update in history if update["request_id"] == str(graph.request_key)
    )
    captured = historical["provider_snapshot"]["requirements"][0]
    assert (captured["status"], captured["version"], captured["scheduled_date"]) == (
        "Scheduled",
        3,
        "2026-10-22",
    )
    assert historical["ambiguities"] == ["Confirm the date"]
    assert historical["suggestions"][0]["decision"]["outcome"] == "corrected"
    page.get_by_label("Original update", exact=True).fill("Drug screening completed.")
    page.get_by_role("button", name="Analyze update", exact=True).click()
    expect(page.locator("#request-status")).to_contain_text(
        "Update and suggestions saved"
    )
    page.get_by_label("Simulated role", exact=True).select_option("manager")
    card = page.get_by_role("article", name="Drug screening", exact=True).first
    card.get_by_role("button", name="Approve", exact=True).click()
    expect(row(page)).to_contain_text("Completed")
    row(page).get_by_role("button", name="Edit", exact=True).click()
    group = editor(page)
    group.get_by_label("Deadline", exact=True).fill("2026-12-01")
    group.get_by_role("button", name="Save changes", exact=True).click()
    expect(page.locator("#checklist-status")).to_contain_text("Checklist changes saved")
    expect(row(page)).to_contain_text("2026-12-01")
    page.get_by_role("button", name="Add provider", exact=True).click()
    form = page.locator("#provider-form")
    fill_form(form, provider["name"], "")
    save_form(page, server, form)
    expect(form).to_be_hidden()
    labels = (
        page.get_by_label("Provider", exact=True)
        .get_by_role("option")
        .all_text_contents()
    )
    assert len(labels) == len(set(labels)) == 2
    current = page.request.get(server.url + f"/providers/{provider['id']}").json()
    assert (
        current["requirements"][0]["status"],
        current["requirements"][0]["version"],
    ) == ("Completed", 10)
    page.get_by_label("Provider", exact=True).select_option(str(provider["id"]))
    expect(row(page)).to_contain_text("Completed")
    assert page.request.get(
        server.url + f"/providers/{provider['id']}/checklist-edits"
    ).json()[0]["operation_id"]


def test_backup_restore_runs_old_app_with_original_uuid_history(page, legacy_cutover):
    rehearsal = legacy_cutover
    assert dbmate(rehearsal.url, "up").returncode == 0
    before = []
    with psycopg.connect(rehearsal.url) as conn:
        before = conn.execute("SELECT id,creation_request_id FROM providers").fetchall()
    # Remove the empty QA and source schemas before the historical rollback.
    assert dbmate(rehearsal.url, "rollback").returncode == 0
    assert dbmate(rehearsal.url, "rollback").returncode == 0
    # The additions migration has an explicitly empty down section: it changes
    # only dbmate's bookkeeping on rollback, leaving all schema/data intact.
    assert dbmate(rehearsal.url, "rollback").returncode == 0
    with psycopg.connect(rehearsal.url) as conn:
        assert conn.execute("SELECT initial_status FROM requirements").fetchall() == [
            (None,)
        ]
    refused = dbmate(rehearsal.url, "rollback")
    assert refused.returncode != 0
    with psycopg.connect(rehearsal.url) as conn:
        assert (
            conn.execute("SELECT id,creation_request_id FROM providers").fetchall()
            == before
        )
    with disposable_database() as restored_url:
        restore_database(restored_url, rehearsal.backup)
        rehearsal.server.database_url = restored_url
        rehearsal.server.source_root = rehearsal.legacy_root
        rehearsal.server.start()
        try:
            page.goto(rehearsal.server.url)
            expect(row(page)).to_contain_text("Incomplete")
            expect(row(page)).to_contain_text("2026-11-21")
            provider = page.request.get(
                rehearsal.server.url + f"/providers/{rehearsal.graph.provider_key}"
            ).json()
            assert provider["id"] == str(rehearsal.graph.provider_key)
            assert provider["requirements"][0]["id"] == str(
                rehearsal.graph.requirement_id
            )
            assert provider["requirements"][0]["version"] == 8
            with psycopg.connect(restored_url) as conn:
                assert conn.execute(
                    "SELECT count(*) FROM schema_migrations"
                ).fetchone() == (3,)
                assert conn.execute("SELECT count(*) FROM updates").fetchone() == (2,)
                assert conn.execute(
                    "SELECT count(*) FROM checklist_edits"
                ).fetchone() == (2,)
                snapshot = conn.execute(
                    "SELECT provider_snapshot FROM updates WHERE request_id=%s",
                    (rehearsal.graph.request_key,),
                ).fetchone()[0]
                assert snapshot["requirements"][0]["status"] == "Scheduled"
        finally:
            rehearsal.server.stop()
