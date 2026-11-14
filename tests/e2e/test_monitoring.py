"""Monitoring uses the real saved checklist, manager decisions, and server date."""

from datetime import date

import psycopg
import pytest
from playwright.sync_api import expect

from tests.database import ROOT, configured_test_url
from tests.e2e.test_review_workflow import drug_card, drug_row, open_history, propose


@pytest.fixture(autouse=True)
def monitoring_records(seeded_provider):
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "UPDATE requirements SET deadline='2026-11-10' WHERE provider_id=%s AND name='Offer letter'",
            (seeded_provider.id,),
        )
        conn.execute(
            "UPDATE requirements SET deadline='2026-11-18' WHERE provider_id=%s AND name='Drug screening'",
            (seeded_provider.id,),
        )
        conn.execute(
            "UPDATE requirements SET status='Incomplete',deadline='2026-11-10' WHERE provider_id=%s AND name='Insurance credentialing'",
            (seeded_provider.id,),
        )


def set_drug(provider, status, deadline):
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "UPDATE requirements SET status=%s,deadline=%s WHERE provider_id=%s AND name='Drug screening'",
            (status, deadline, provider.id),
        )


def counts(page, finished=2, remaining=3, overdue=1, needs_review=0):
    summary = page.get_by_role("region", name="Monitoring summary", exact=True)
    expect(summary).to_be_visible()
    for label, value in (
        ("Finished", finished),
        ("Remaining", remaining),
        ("Overdue", overdue),
        ("Needs review", needs_review),
    ):
        expect(summary.get_by_label(label, exact=True)).to_have_text(str(value))


def indicator(page, name="Drug screening"):
    return (
        page.get_by_role("table", name="Onboarding checklist")
        .get_by_role("row")
        .filter(has_text=name)
        .get_by_role("cell")
        .nth(4)
    )


@pytest.mark.parametrize(
    "name,status,deadline,label,finished,remaining",
    [
        ("Offer letter", "Signed", "2026-11-10", "Finished", 2, 3),
        ("Drug screening", "Scheduled", "2026-11-18", "Outstanding", 2, 3),
        ("Drug screening", "Completed", "2026-11-10", "Finished", 3, 2),
        ("Insurance credentialing", "Incomplete", "2026-11-10", "Overdue", 2, 3),
    ],
)
def test_monitoring_acceptance_cases(
    page, app_server, seeded_provider, name, status, deadline, label, finished, remaining
):
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "UPDATE requirements SET status=%s,deadline=%s WHERE provider_id=%s AND name=%s",
            (status, deadline, seeded_provider.id, name),
        )
    page.goto(app_server.url)
    expect(page.get_by_role("columnheader", name="Monitoring", exact=True)).to_be_visible()
    expect(indicator(page, name)).to_have_text(label)
    counts(page, finished, remaining)


def test_monitoring_approval_reversal_and_restart(page, app_server, seeded_provider):
    set_drug(seeded_provider, "Scheduled", "2026-11-10")
    propose(page, app_server)
    expect(drug_card(page)).to_be_visible()
    counts(page, overdue=2)
    page.get_by_label("Simulated role").select_option("manager")
    counts(page, overdue=2)
    drug_card(page).get_by_role("button", name="Approve", exact=True).click()
    expect(indicator(page)).to_have_text("Finished")
    counts(page, 3, 2)
    page.get_by_role("button", name="Analyze update", exact=True).click()
    newest = drug_card(page).first
    newest.get_by_label("Reviewed status").select_option("Incomplete")
    newest.get_by_role("button", name="Approve with corrections", exact=True).click()
    expect(indicator(page)).to_have_text("Overdue")
    counts(page, overdue=2)
    app_server.restart()
    page.reload()
    open_history(page)
    expect(drug_row(page)).to_contain_text("Incomplete")
    expect(indicator(page)).to_have_text("Overdue")
    counts(page, overdue=2)
    page.get_by_label("Original update").fill("Drug screening completed.")
    page.get_by_role("button", name="Analyze update", exact=True).click()
    page.get_by_label("Simulated role").select_option("manager")
    drug_card(page).first.get_by_role("button", name="Reject", exact=True).click()
    expect(page.locator("#request-status")).to_contain_text("Manager decision saved")
    expect(drug_card(page).first).to_contain_text("Rejected")
    counts(page, overdue=2)


def test_unknown_past_status_is_visible_and_text_safe(page, app_server, seeded_provider):
    raw = "<script>window.injected = true</script>"
    set_drug(seeded_provider, raw, "2026-11-10")
    page.goto(app_server.url)
    expect(drug_row(page)).to_contain_text(raw)
    expect(indicator(page)).to_have_text("Deadline passed — needs review")
    counts(page, needs_review=1)
    assert page.evaluate("window.injected") is None


@pytest.mark.parametrize(
    "deadline,label",
    [
        ("2026-11-11", "Outstanding — due today"),
        ("2026-11-12", "Outstanding"),
        (None, "Outstanding"),
    ],
)
def test_due_today_and_date_label_use_server_day(
    page, app_server, seeded_provider, deadline, label
):
    # At this instant both UTC and Tokyo are on Nov 12; Hawaii is still Nov 11.
    page.clock.install(time="2026-11-12T08:00:00Z")
    assert page.evaluate("new Date().getTimezoneOffset()") == -540
    set_drug(seeded_provider, "Scheduled", deadline)
    page.goto(app_server.url)
    expect(indicator(page)).to_have_text(label)
    expect(page.get_by_text("As of 2026-11-11 · Hawaii (Pacific/Honolulu)", exact=True)).to_be_visible()
    counts(page)


def test_empty_checklist_has_zero_counts_without_readiness_claim(
    page, app_server, seeded_provider
):
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute("DELETE FROM requirements WHERE provider_id=%s", (seeded_provider.id,))
    page.goto(app_server.url)
    counts(page, 0, 0, 0, 0)
    expect(page.get_by_text("No checklist requirements are saved for this provider.", exact=True)).to_be_visible()
    expect(page.get_by_text("Ready to start", exact=False)).to_have_count(0)


def test_saved_review_with_failed_dashboard_refresh_is_reported_honestly(
    page, app_server
):
    propose(page, app_server)
    expect(drug_card(page)).to_be_visible()
    page.get_by_label("Simulated role").select_option("manager")

    def fail_refresh(route):
        route.fulfill(status=503, json={"detail": "Saved data is unavailable."})

    page.route("**/providers/*/dashboard", fail_refresh)
    drug_card(page).get_by_role("button", name="Approve", exact=True).click()
    expect(page.locator("#request-status")).to_contain_text("Decision saved, but the view could not refresh")
    expect(drug_row(page)).to_contain_text("Scheduled")
    expect(indicator(page)).to_have_text("Outstanding")
    counts(page)
    page.unroute("**/providers/*/dashboard", fail_refresh)
    page.get_by_role("button", name="Refresh data", exact=True).click()
    expect(indicator(page)).to_have_text("Finished")
    expect(drug_row(page)).to_contain_text("Completed")
    counts(page, 3, 2)


def test_failed_dashboard_load_clears_every_part_of_snapshot(page, app_server):
    page.goto(app_server.url)
    counts(page)

    def fail_refresh(route):
        route.fulfill(status=503, json={"detail": "Saved data is unavailable."})

    page.route("**/providers/*/dashboard", fail_refresh)
    page.get_by_role("button", name="Refresh data", exact=True).click()
    expect(page.locator("#request-status")).to_contain_text("unavailable")
    expect(page.get_by_role("region", name="Monitoring summary", exact=True)).to_be_hidden()
    expect(page.locator("#requirements")).to_be_empty()
    expect(page.locator("#provider-description")).to_be_empty()
    expect(page.get_by_role("button", name="Analyze update", exact=True)).to_be_disabled()
    page.reload()
    expect(page.locator("#request-status")).to_contain_text("unavailable")
    expect(page.get_by_role("region", name="Monitoring summary", exact=True)).to_be_hidden()
    expect(page.get_by_role("button", name="Analyze update", exact=True)).to_be_disabled()


def test_monitoring_refresh_uses_new_server_date(page, app_server):
    page.goto(app_server.url)
    counts(page)
    app_server.as_of = date(2026, 11, 19)
    app_server.restart()
    page.get_by_role("button", name="Refresh data", exact=True).click()
    expect(page.get_by_text("As of 2026-11-19 · Hawaii (Pacific/Honolulu)", exact=True)).to_be_visible()
    expect(indicator(page)).to_have_text("Overdue")
    counts(page, overdue=2)


def test_monitoring_layout_and_keyboard_access(page, app_server):
    page.goto(app_server.url)
    counts(page)
    directory = ROOT / ".superpowers/sdd/2026-11-11-status-deadline-monitoring"
    directory.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=directory / "monitoring-desktop.png", full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    scroll = page.get_by_role("region", name="Scrollable checklist", exact=True)
    scroll.focus()
    expect(scroll).to_be_focused()
    page.keyboard.press("End")
    page.keyboard.press("Tab")
    expect(page.get_by_label("Original update", exact=True)).to_be_focused()
    page.screenshot(path=directory / "monitoring-narrow.png", full_page=True)
