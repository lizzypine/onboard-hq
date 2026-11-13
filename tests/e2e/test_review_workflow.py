"""Full browser → app → PostgreSQL workflows with TestModel at the external boundary."""

from uuid import uuid4

import psycopg
import pytest
from playwright.sync_api import expect
from psycopg.types.json import Jsonb

from tests.database import configured_test_url, disposable_database


def propose(page, app_server, text="Drug screening completed."):
    page.goto(app_server.url)
    expect(page.get_by_label("Simulated role")).to_have_value("proposer")
    page.get_by_label("Original update").fill(text)
    page.get_by_role("button", name="Analyze update", exact=True).click()
    open_history(page)


def open_history(page):
    disclosure = page.locator("#review-disclosure")
    if not disclosure.evaluate("e => e.open"):
        disclosure.locator("summary").click()


def drug_card(page):
    return page.get_by_role("article", name="Drug screening", exact=True)


def drug_row(page):
    return (
        page.get_by_role("table", name="Onboarding checklist")
        .get_by_role("row")
        .filter(has_text="Drug screening")
    )


def test_manager_approval_survives_refresh_and_server_restart(page, app_server):
    propose(page, app_server)
    expect(drug_card(page)).to_be_visible()
    expect(page.get_by_role("button", name="Approve", exact=True)).to_have_count(0)
    page.reload()
    open_history(page)
    expect(drug_card(page)).to_be_visible()
    page.get_by_label("Simulated role").select_option("manager")
    page.get_by_role("button", name="Approve", exact=True).click()
    expect(drug_row(page)).to_contain_text("Completed")
    expect(drug_card(page)).to_contain_text("Approved")
    app_server.restart()
    page.reload()
    open_history(page)
    expect(drug_row(page)).to_contain_text("Completed")
    expect(drug_card(page)).to_contain_text("Drug screening completed.")


def test_manager_can_correct_date_and_confirmation_resets_after_editing(
    page, app_server, tmp_path
):
    app_server.restart("inferred")
    propose(page, app_server, "Drug screening on the 18th.")
    expect(drug_card(page)).to_be_visible()
    page.get_by_label("Simulated role").select_option("manager")
    card = drug_card(page)
    confirmation = card.get_by_label("Confirm inferred date")
    confirmation.check()
    card.get_by_label("Reviewed date", exact=True).fill("2026-11-17")
    expect(confirmation).not_to_be_checked()
    expect(
        card.get_by_role("button", name="Approve with corrections", exact=True)
    ).to_be_disabled()
    confirmation.check()
    screenshot_dir = tmp_path
    page.screenshot(path=screenshot_dir / "manager-desktop.png", full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=screenshot_dir / "manager-narrow.png", full_page=True)
    card.get_by_role("button", name="Approve with corrections", exact=True).click()
    expect(drug_row(page)).to_contain_text("2026-11-17")
    expect(drug_card(page)).to_contain_text("Approved with corrections")


def test_multiple_suggestions_have_independent_review_decisions(page, app_server):
    app_server.restart("multiple")
    propose(page, app_server, "Drug completed; credentialing returned.")
    expect(
        page.get_by_role("article", name="Insurance credentialing", exact=True)
    ).to_be_visible()
    page.get_by_label("Simulated role").select_option("manager")
    drug_card(page).get_by_role("button", name="Approve", exact=True).click()
    credentialing = page.get_by_role(
        "article", name="Insurance credentialing", exact=True
    )
    credentialing.get_by_role("button", name="Reject", exact=True).click()
    expect(credentialing).to_contain_text("Rejected")
    expect(drug_row(page)).to_contain_text("Completed")
    credential_row = (
        page.get_by_role("table", name="Onboarding checklist")
        .get_by_role("row")
        .filter(has_text="Insurance credentialing")
    )
    expect(credential_row).to_contain_text("Pending")


@pytest.mark.parametrize(
    "scenario,expected",
    [
        ("empty", "Insufficient information"),
        ("failure", "Unable to analyze update"),
        ("warning", "Scheduled date is missing"),
    ],
)
def test_empty_failed_and_warning_updates_remain_visible(
    page, app_server, scenario, expected
):
    app_server.restart(scenario)
    propose(page, app_server, "Synthetic update.")
    expect(page.get_by_text(expected, exact=False).first).to_be_visible()
    page.reload()
    open_history(page)
    expect(page.get_by_text(expected, exact=False).first).to_be_visible()


def test_supporting_text_is_safe_and_page_fits_narrow_viewport(page, app_server):
    app_server.restart("html")
    page.set_viewport_size({"width": 390, "height": 844})
    propose(page, app_server)
    expect(drug_card(page)).to_contain_text("<script>window.injected = true</script>")
    assert page.evaluate("window.injected") is None
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.get_by_label("Simulated role").focus()
    page.keyboard.press("m")
    page.keyboard.press("Enter")
    expect(page.get_by_label("Simulated role")).to_be_focused()


def test_status_correction_and_date_clearing_keep_deadline(page, app_server):
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "UPDATE requirements SET scheduled_date='2026-11-20',deadline='2026-11-30' WHERE name='Drug screening'"
        )
    propose(page, app_server)
    expect(drug_card(page)).to_be_visible()
    page.get_by_label("Simulated role").select_option("manager")
    card = drug_card(page)
    card.get_by_label("Reviewed status").select_option("Incomplete")
    card.get_by_label("Reviewed date", exact=True).fill("")
    card.get_by_role("button", name="Approve with corrections", exact=True).click()
    expect(drug_row(page)).to_contain_text("Incomplete")
    expect(drug_row(page)).to_contain_text("Not set")
    expect(drug_row(page)).to_contain_text("2026-11-30")
    expect(card).to_contain_text("Proposed status: Completed")


def test_lost_analysis_response_reuses_request_without_creating_second_update(
    page, app_server, seeded_provider
):
    def lose_response(route):
        route.fetch()
        route.abort("failed")

    page.route("**/updates/analyze", lose_response)
    propose(page, app_server)
    expect(drug_card(page)).to_be_visible()
    page.unroute("**/updates/analyze", lose_response)
    page.get_by_role("button", name="Analyze update", exact=True).click()
    expect(page.locator("#request-status")).to_contain_text(
        "Update and suggestions saved"
    )
    history = page.request.get(
        app_server.url + f"/providers/{seeded_provider.id}/updates"
    ).json()
    assert len(history) == 1



@pytest.mark.parametrize("endpoint", ["updates", "dashboard"])
def test_saved_analysis_with_failed_refresh_reuses_request_on_retry(
    page, app_server, seeded_provider, endpoint
):
    page.goto(app_server.url)
    expect(drug_row(page)).to_contain_text("Scheduled")

    def fail_refresh(route):
        route.fulfill(status=503, json={"detail": "Saved data is unavailable."})

    pattern = "**/providers/*/" + endpoint
    page.route(pattern, fail_refresh)
    page.get_by_label("Original update").fill("Drug screening completed.")
    analyze = page.get_by_role("button", name="Analyze update", exact=True)
    analyze.click()
    expect(page.locator("#request-status")).not_to_have_text("Analyzing update…")
    expect(analyze).to_be_enabled()
    saved_status = page.locator("#request-status").inner_text()
    page.unroute(pattern, fail_refresh)
    analyze.click()
    expect(page.locator("#request-status")).to_contain_text(
        "Update and suggestions saved"
    )
    history = page.request.get(
        app_server.url + f"/providers/{seeded_provider.id}/updates"
    ).json()
    assert len(history) == 1
    assert "Update saved, but the view could not refresh" in saved_status


def test_stale_manager_view_refreshes_after_conflict_and_can_reject_old_proposal(
    page, app_server, seeded_provider
):
    propose(page, app_server)
    expect(drug_card(page)).to_be_visible()
    page.get_by_role("button", name="Analyze update", exact=True).click()
    expect(
        page.get_by_role("article", name="Drug screening", exact=True)
    ).to_have_count(2)
    page.get_by_label("Simulated role").select_option("manager")
    history = page.request.get(
        app_server.url + f"/providers/{seeded_provider.id}/updates"
    ).json()
    old_id = history[-1]["suggestions"][0]["id"]
    other_manager = page.request.post(
        app_server.url + f"/suggestions/{old_id}/review",
        data={"action": "approve"},
        headers={"X-Demo-Role": "manager"},
    )
    assert other_manager.status == 200
    newest = page.get_by_role("article", name="Drug screening", exact=True).first
    newest.get_by_role("button", name="Approve", exact=True).click()
    expect(page.locator("#request-status")).to_contain_text("checklist changed")
    expect(newest.get_by_role("button", name="Approve", exact=True)).to_be_disabled()
    newest.get_by_role("button", name="Reject", exact=True).click()
    expect(newest).to_contain_text("Rejected")
    expect(drug_row(page)).to_contain_text("Completed")


def test_unfinished_analysis_has_no_review_actions(page, app_server, seeded_provider):
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "INSERT INTO updates(id,request_id,provider_id,original_text,provider_snapshot,processing_state,message) VALUES (%s,%s,%s,'Interrupted synthetic update',%s,'processing','In progress')",
            (
                uuid4(),
                uuid4(),
                seeded_provider.id,
                Jsonb(seeded_provider.model_dump(mode="json")),
            ),
        )
    page.goto(app_server.url)
    open_history(page)
    expect(page.get_by_text("Analysis unfinished.", exact=False)).to_be_visible()
    page.get_by_label("Simulated role").select_option("manager")
    expect(page.get_by_role("button", name="Approve", exact=True)).to_have_count(0)


def test_missing_database_schema_is_visible_and_disables_submission(page, app_server):
    with disposable_database() as empty:
        app_server.stop()
        app_server.database_url = empty
        try:
            app_server.start()
            page.goto(app_server.url)
            expect(page.locator("#request-status")).to_contain_text("unavailable")
            expect(
                page.get_by_role("button", name="Analyze update", exact=True)
            ).to_be_disabled()
        finally:
            app_server.stop()
