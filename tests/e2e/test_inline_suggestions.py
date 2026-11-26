"""Pending proposals live beside saved rows; only decisions enter review history."""

from playwright.sync_api import expect

from tests.e2e.test_checklist_edits import (
    editor,
    history,
    load,
    open_history,
    row,
    second_provider,
)


def analyze(page, message="Drug screening completed."):
    page.get_by_label("Original update", exact=True).fill(message)
    page.get_by_role("button", name="Analyze update", exact=True).click()
    expect(page.locator("#request-status")).to_contain_text(
        "Update and suggestions saved"
    )


def pending(page, name="Drug screening"):
    return page.locator(".requirement-suggestions").get_by_role(
        "article", name=name, exact=True
    )


def test_pending_proposal_is_below_saved_row_and_moves_to_history_after_review(
    page, app_server, seeded_provider
):
    load(page, app_server)
    expect(
        page.get_by_label("Simulated role").get_by_role("option").first
    ).to_have_text("Non-manager")
    analyze(page, "A fictional update: Drug screening completed.")
    card = pending(page)
    expect(card).to_be_visible()
    expect(row(page).locator("xpath=following-sibling::tr[1]")).to_contain_text(
        "A fictional update: Drug screening completed."
    )
    expect(card).to_contain_text("Drug screening completed.")
    expect(row(page).locator(".status-badge")).to_have_text("Scheduled")
    expect(page.locator("#pending-suggestions")).to_have_text("1 pending suggestion")
    expect(history(page)).to_be_hidden()
    assert not history(page).evaluate("e => e.open")
    expect(page.locator("#request-status")).to_contain_text("Onboarding checklist")
    page.reload()
    expect(pending(page)).to_be_visible()
    page.get_by_label("Simulated role").select_option("manager")
    pending(page).get_by_role("button", name="Approve", exact=True).click()
    expect(pending(page)).to_have_count(0)
    expect(row(page).locator(".status-badge")).to_have_text("Completed")
    expect(page.locator("#pending-suggestions")).to_have_text("0 pending suggestions")
    assert not history(page).evaluate("e => e.open")
    open_history(page)
    expect(history(page).get_by_role("heading", name="Update history")).to_be_visible()
    expect(
        history(page).get_by_role("article", name="Review: Drug screening")
    ).to_contain_text("Approved")


def test_multiple_proposals_keep_order_and_review_drafts_during_manual_redraw(
    page, app_server
):
    load(page, app_server)
    analyze(page, "First synthetic update: Drug screening completed.")
    analyze(page, "Second synthetic update: Drug screening completed.")
    expect(pending(page)).to_have_count(2)
    expect(pending(page).first).to_contain_text("Second synthetic update")
    page.get_by_label("Simulated role").select_option("manager")
    card = pending(page).first
    card.get_by_label("Reviewed status", exact=True).select_option("Incomplete")
    row(page).get_by_role("button", name="Edit", exact=True).click()
    expect(card.get_by_label("Reviewed status", exact=True)).to_have_value("Incomplete")
    editor(page).get_by_role("button", name="Cancel", exact=True).click()
    expect(card.get_by_label("Reviewed status", exact=True)).to_have_value("Incomplete")
    card.get_by_role("button", name="Reject", exact=True).click()
    expect(pending(page)).to_have_count(1)
    expect(pending(page)).to_contain_text("First synthetic update")
    expect(row(page).locator(".status-badge")).to_have_text("Scheduled")
    open_history(page)
    expect(
        history(page).get_by_role("article", name="Review: Drug screening")
    ).to_contain_text("Rejected")


def test_inline_warnings_roles_provider_scope_and_narrow_layout(
    page, app_server, seeded_provider
):
    app_server.restart("warning")
    other = second_provider(page, app_server)
    load(page, app_server)
    original = str(seeded_provider.id)
    page.get_by_label("Provider", exact=True).select_option(original)
    analyze(
        page, "Synthetic administrative context. " * 20 + "Drug screening completed."
    )
    expect(pending(page)).to_contain_text("Scheduled date is missing.")
    expect(
        pending(page).get_by_role("button", name="Approve", exact=True)
    ).to_have_count(0)
    page.get_by_label("Simulated role").select_option("manager")
    expect(pending(page).get_by_label("Reviewed status", exact=True)).to_be_enabled()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert (
        pending(page)
        .locator("blockquote")
        .first.evaluate(
            "e => e.getBoundingClientRect().right <= e.closest('.table-scroll').getBoundingClientRect().right"
        )
    )
    page.get_by_label("Simulated role").select_option("proposer")
    expect(pending(page).get_by_label("Reviewed status", exact=True)).to_have_count(0)
    page.get_by_label("Provider", exact=True).select_option(str(other["id"]))
    expect(page.get_by_label("Provider", exact=True)).to_be_enabled()
    expect(pending(page)).to_have_count(0)
    page.get_by_label("Provider", exact=True).select_option(original)
    expect(pending(page)).to_be_visible()


def test_analysis_without_suggestions_points_to_history_even_with_older_pending(
    page, app_server
):
    load(page, app_server)
    analyze(page)
    expect(pending(page)).to_be_visible()
    app_server.restart("empty")
    page.reload()
    page.get_by_label("Original update", exact=True).fill("No actionable information.")
    page.get_by_role("button", name="Analyze update", exact=True).click()
    expect(page.locator("#request-status")).to_contain_text("All update history")
    expect(pending(page)).to_have_count(1)
    assert not history(page).evaluate("e => e.open")
    open_history(page)
    expect(history(page)).to_contain_text("Insufficient information.")
