"""Frozen UUID-era attempts survive upgrade without guessing IDs or duplicating saves."""

from uuid import uuid4

import psycopg
import pytest
from playwright.sync_api import expect

from tests.database import disposable_database
from tests.fixtures.legacy_database import dbmate, migrate_legacy, seed_legacy_graph

LEGACY_KEY = "onboard-hq:pending-checklist-edit"


@pytest.fixture
def upgraded_server(app_server):
    with disposable_database() as url:
        migrate_legacy(url)
        graph = seed_legacy_graph(url)
        result = dbmate(url, "up")
        assert result.returncode == 0, result.stderr
        original = app_server.database_url
        app_server.stop()
        app_server.database_url = url
        app_server.start()
        try:
            yield app_server, graph, url
        finally:
            app_server.stop()
            app_server.database_url = original


def legacy_attempt(graph):
    return {
        "providerId": str(graph.provider_key),
        "providerName": "Dr. Synthetic Upgrade",
        "requirementId": str(graph.requirement_id),
        "confirmed": False,
        "body": {
            "id": str(graph.operation_key),
            "expected_version": 6,
            "status": "Completed",
            "scheduled_date": "2026-10-29",
            "deadline": "2026-11-02",
        },
    }


def load_attempt(page, server, attempt):
    posts = []
    page.on(
        "request",
        lambda request: posts.append(request.url) if request.method == "POST" else None,
    )
    page.goto(server.url)
    page.evaluate(
        '(attempt) => sessionStorage.setItem("onboard-hq:pending-checklist-edit",JSON.stringify(attempt))',
        attempt,
    )
    page.reload()
    return posts


def stored_attempt(page):
    return page.evaluate(
        'JSON.parse(sessionStorage.getItem("onboard-hq:pending-checklist-edit"))'
    )


def test_legacy_committed_attempt_recovers_without_replaying_later_progress(
    page, upgraded_server
):
    server, graph, url = upgraded_server
    with psycopg.connect(url) as conn:
        conn.execute(
            "UPDATE requirements SET status='Incomplete',version=8,scheduled_date='2026-11-03'"
        )
    posts = load_attempt(page, server, legacy_attempt(graph))
    expect(page.locator("#legacy-checklist-status")).to_contain_text("already saved")
    expect(page.locator("#requirements")).to_contain_text("Incomplete")
    expect(page.locator("#requirements")).to_contain_text("2026-11-03")
    assert stored_attempt(page) is None
    assert posts == []
    with psycopg.connect(url) as conn:
        assert conn.execute("SELECT count(*) FROM checklist_edits").fetchone() == (1,)
        assert conn.execute("SELECT status,version FROM requirements").fetchone() == (
            "Incomplete",
            8,
        )


def test_unresolved_legacy_draft_remains_readable_until_explicit_dismissal(
    page, upgraded_server
):
    server, graph, _ = upgraded_server
    attempt = legacy_attempt(graph)
    attempt["body"]["id"] = str(uuid4())
    posts = load_attempt(page, server, attempt)
    notice = page.get_by_role("region", name="Older checklist save", exact=True)
    expect(notice).to_contain_text("unavailable")
    expect(notice).to_contain_text("Completed")
    expect(notice).to_contain_text("2026-10-29")
    expect(notice).to_contain_text("2026-11-02")
    assert stored_attempt(page) == attempt
    page.reload()
    expect(notice).to_contain_text("unavailable")
    assert stored_attempt(page) == attempt
    notice.get_by_role("button", name="Dismiss older save", exact=True).click()
    expect(notice).to_be_hidden()
    assert stored_attempt(page) is None
    assert posts == []


def test_archived_legacy_match_opens_view_only_without_new_saves(page, upgraded_server):
    server, graph, url = upgraded_server
    with psycopg.connect(url) as conn:
        conn.execute("UPDATE providers SET archived_at=now()")
    posts = load_attempt(page, server, legacy_attempt(graph))
    expect(page.locator("#legacy-checklist-status")).to_contain_text("already saved")
    expect(page.locator("#provider-state")).to_have_value("archived")
    expect(page.locator("#provider-description")).to_contain_text("Archived")
    page.get_by_label("Simulated role", exact=True).select_option("manager")
    expect(page.get_by_role("button", name="Edit", exact=True)).to_have_count(0)
    expect(
        page.get_by_role("button", name="Analyze update", exact=True)
    ).to_be_disabled()
    assert posts == []
    assert stored_attempt(page) is None


def test_missing_provider_does_not_recreate_or_match_a_duplicate_name(
    page, upgraded_server
):
    server, graph, url = upgraded_server
    with psycopg.connect(url) as conn:
        template = conn.execute(
            "SELECT checklist_template_id FROM providers"
        ).fetchone()[0]
        conn.execute("DELETE FROM providers")
        conn.execute(
            "INSERT INTO providers(creation_request_id,name,checklist_template_id) VALUES (gen_random_uuid(),'Dr. Synthetic Upgrade',%s)",
            (template,),
        )
    attempt = legacy_attempt(graph)
    posts = load_attempt(page, server, attempt)
    expect(page.locator("#legacy-checklist-status")).to_contain_text("unavailable")
    assert stored_attempt(page) == attempt
    assert posts == []
    with psycopg.connect(url) as conn:
        assert conn.execute("SELECT count(*) FROM providers").fetchone() == (1,)
        assert conn.execute(
            "SELECT count(*) FROM providers WHERE creation_request_id=%s",
            (graph.provider_key,),
        ).fetchone() == (0,)


def test_mismatched_operation_values_are_not_confirmed_or_replayed(
    page, upgraded_server
):
    server, graph, _ = upgraded_server
    attempt = legacy_attempt(graph)
    attempt["body"]["status"] = "Incomplete"
    posts = load_attempt(page, server, attempt)
    expect(page.locator("#legacy-checklist-status")).to_contain_text("different")
    assert stored_attempt(page) == attempt
    assert posts == []


def test_failed_legacy_lookup_can_be_checked_again_without_a_post(
    page, upgraded_server
):
    server, graph, _ = upgraded_server
    page.route(
        "**/providers?state=all",
        lambda route: route.fulfill(status=503, json={"detail": "Unavailable"}),
    )
    attempt = legacy_attempt(graph)
    posts = load_attempt(page, server, attempt)
    expect(page.locator("#legacy-checklist-status")).to_contain_text("unavailable")
    assert stored_attempt(page) == attempt
    page.unroute("**/providers?state=all")
    page.get_by_role("button", name="Check older save", exact=True).click()
    expect(page.locator("#legacy-checklist-status")).to_contain_text("already saved")
    assert stored_attempt(page) is None
    assert posts == []
