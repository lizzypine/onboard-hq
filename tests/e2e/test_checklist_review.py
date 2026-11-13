"""Managers compare saved values and directly edit independent proposed rows."""

import re

import psycopg
import pytest
from playwright.sync_api import expect

from tests.database import configured_test_url
from tests.e2e.test_review_workflow import drug_card, drug_row, propose


def manager_review(page, app_server):
    propose(page, app_server)
    expect(drug_card(page)).to_be_visible()
    expect(page.get_by_role("table", name="Review Drug screening", exact=True)).to_have_count(0)
    page.get_by_label("Simulated role").select_option("manager")
    table = page.get_by_role("table", name="Review Drug screening", exact=True)
    expect(table).to_be_visible()
    return table


def field_cell(table, field):
    return table.locator(f'[data-review-field="{field}"]')


def changed(cell, value=True):
    if value:
        expect(cell).to_have_class(re.compile(r"\breview-change\b"))
    else:
        expect(cell).not_to_have_class(re.compile(r"\breview-change\b"))


def seed_date(provider, *, status="Scheduled"):
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "UPDATE requirements SET scheduled_date='2026-11-20',deadline='2026-11-30',status=%s WHERE provider_id=%s AND name='Drug screening'",
            (status, provider.id),
        )


def saved_dashboard(page, app_server, provider):
    response = page.request.get(app_server.url + f"/providers/{provider.id}/dashboard")
    assert response.ok
    return response.json()


def test_review_row_highlights_proposed_status_and_keeps_evidence(
    page, app_server, seeded_provider
):
    table = manager_review(page, app_server)
    expect(table.get_by_role("columnheader")).to_have_text(
        ["Requirement", "Status", "Requirement date", "Deadline"]
    )
    expect(table.get_by_label("Reviewed status", exact=True)).to_have_value("Completed")
    status = field_cell(table, "status")
    expect(status).to_contain_text("Saved: Scheduled")
    expect(status).to_contain_text("Originally proposed: Completed")
    expect(status).to_contain_text("Proposed change")
    changed(status)
    changed(field_cell(table, "date"), False)
    expect(table.get_by_role("cell").first).to_have_text("Drug screening")
    expect(table.get_by_role("cell").last).to_have_text("Not set")
    expect(table.locator("input")).to_have_count(2)
    expect(page.get_by_label("Date change", exact=True)).to_have_count(0)
    before = saved_dashboard(page, app_server, seeded_provider)
    table.get_by_label("Reviewed status", exact=True).fill("Incomplete")
    expect(status).to_contain_text("Your correction")
    expect(status).to_contain_text("Originally proposed: Completed")
    expect(drug_row(page)).to_contain_text("Scheduled")
    assert saved_dashboard(page, app_server, seeded_provider) == before


def test_return_to_saved_status_is_a_correction_without_highlight(page, app_server):
    table = manager_review(page, app_server)
    table.get_by_label("Reviewed status", exact=True).fill("Scheduled")
    changed(field_cell(table, "status"), False)
    expect(field_cell(table, "status")).to_contain_text("Unchanged")
    expect(drug_card(page).get_by_role("button", name="Approve", exact=True)).to_be_disabled()
    drug_card(page).get_by_role("button", name="Approve with corrections", exact=True).click()
    expect(drug_card(page)).to_contain_text("Approved with corrections")
    expect(drug_card(page)).to_contain_text("Proposed status: Completed")
    expect(drug_card(page)).to_contain_text("Applied status: Scheduled")
    expect(drug_row(page)).to_contain_text("Scheduled")


def test_no_date_proposed_preserves_saved_date(page, app_server, seeded_provider):
    seed_date(seeded_provider)
    table = manager_review(page, app_server)
    expect(table.get_by_label("Reviewed date", exact=True)).to_have_value("2026-11-20")
    expect(field_cell(table, "date")).to_contain_text("Saved: 2026-11-20")
    expect(field_cell(table, "date")).to_contain_text("No date proposed")
    changed(field_cell(table, "date"), False)
    drug_card(page).get_by_role("button", name="Approve", exact=True).click()
    expect(drug_card(page)).to_contain_text("Approved")
    expect(drug_row(page)).to_contain_text("2026-11-20")
    expect(drug_row(page)).to_contain_text("2026-11-30")


@pytest.mark.parametrize(
    "edited,expected",
    [("2026-11-29", "2026-11-29"), ("", "Not set"), ("restore", "2026-11-20")],
)
def test_date_edits_set_clear_and_restore_comparison(
    page, app_server, seeded_provider, edited, expected
):
    seed_date(seeded_provider)
    table = manager_review(page, app_server)
    date_input = table.get_by_label("Reviewed date", exact=True)
    date_input.fill("2026-11-29" if edited == "restore" else edited)
    changed(field_cell(table, "date"))
    if edited == "restore":
        date_input.fill("2026-11-20")
        changed(field_cell(table, "date"), False)
        button = "Approve"
    else:
        expect(field_cell(table, "date")).to_contain_text(
            "Date will be cleared" if not edited else "Your correction"
        )
        button = "Approve with corrections"
    expect(drug_row(page)).to_contain_text("2026-11-20")
    drug_card(page).get_by_role("button", name=button, exact=True).click()
    expect(drug_card(page)).to_contain_text("Applied date:")
    expect(drug_row(page)).to_contain_text(expected)
    expect(drug_row(page)).to_contain_text("2026-11-30")


def test_partial_date_cannot_be_mistaken_for_clear(page, app_server, seeded_provider):
    seed_date(seeded_provider)
    table = manager_review(page, app_server)
    date_input = table.get_by_label("Reviewed date", exact=True)
    date_input.focus()
    date_input.press("Home")
    date_input.press("Delete")
    assert date_input.evaluate("e => e.validity.badInput")
    expect(field_cell(table, "date")).to_contain_text("Enter a complete valid date.")
    expect(drug_card(page).get_by_role("button", name="Approve", exact=True)).to_be_disabled()
    expect(drug_card(page).get_by_role("button", name="Approve with corrections", exact=True)).to_be_disabled()
    drug_card(page).get_by_role("button", name="Reject", exact=True).click()
    expect(drug_card(page)).to_contain_text("Rejected")
    expect(drug_row(page)).to_contain_text("2026-11-20")


def test_clearing_inferred_date_resets_confirmation_and_can_be_rejected(page, app_server):
    app_server.restart("inferred")
    table = manager_review(page, app_server)
    changed(field_cell(table, "date"))
    confirm = drug_card(page).get_by_label("Confirm inferred date", exact=True)
    confirm.check()
    table.get_by_label("Reviewed date", exact=True).fill("")
    expect(confirm).not_to_be_checked()
    expect(field_cell(table, "date")).to_contain_text("A date is required for this inferred suggestion.")
    expect(drug_card(page).get_by_role("button", name="Approve", exact=True)).to_be_disabled()
    expect(drug_card(page).get_by_role("button", name="Approve with corrections", exact=True)).to_be_disabled()
    drug_card(page).get_by_role("button", name="Reject", exact=True).click()
    expect(drug_card(page)).to_contain_text("Rejected")
    expect(drug_row(page)).to_contain_text("Scheduled")
    expect(drug_row(page)).to_contain_text("Not set")


def test_review_saved_status_is_text_safe(page, app_server, seeded_provider):
    raw = '<img src=x onerror="window.reviewInjected=true">'
    seed_date(seeded_provider, status=raw)
    table = manager_review(page, app_server)
    expect(field_cell(table, "status")).to_contain_text("Saved: " + raw)
    expect(table.locator("img")).to_have_count(0)
    assert page.evaluate("window.reviewInjected") is None


def test_review_row_is_keyboard_accessible_and_fits_narrow_screen(
    page, app_server, tmp_path
):
    table = manager_review(page, app_server)
    page.screenshot(path=tmp_path / "review-desktop.png", full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    scroll = drug_card(page).get_by_role("region", name="Scrollable manager decision", exact=True)
    assert scroll.evaluate("e => e.scrollWidth > e.clientWidth")
    scroll.focus()
    page.keyboard.press("Tab")
    expect(table.get_by_label("Reviewed status", exact=True)).to_be_focused()
    page.keyboard.press("Tab")
    expect(table.get_by_label("Reviewed date", exact=True)).to_be_focused()
    approve = drug_card(page).get_by_role("button", name="Approve", exact=True)
    for _ in range(5):
        page.keyboard.press("Tab")
        if approve.evaluate("e => e === document.activeElement"):
            break
    expect(approve).to_be_focused()
    page.screenshot(path=tmp_path / "review-narrow.png", full_page=True)
