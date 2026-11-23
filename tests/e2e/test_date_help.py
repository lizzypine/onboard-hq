"""Expected completion dates stay distinct from deadlines and have accessible help."""

import pytest
from playwright.sync_api import expect

from tests.e2e.test_checklist_edits import open_editor, open_history, row, save_editor


@pytest.mark.parametrize("interaction", ["hover", "focus", "click"])
def test_date_help_opens_for_mouse_keyboard_and_tap(page, app_server, interaction):
    page.goto(app_server.url)
    help_button = page.get_by_role(
        "button", name="About expected completion date"
    ).first
    expect(help_button).to_be_visible()
    getattr(help_button, interaction)()
    tooltip = page.get_by_role("tooltip")
    expect(tooltip).to_contain_text(
        "The deadline is the latest date it must be completed."
    )
    page.keyboard.press("Escape")
    expect(tooltip).to_be_hidden()


def test_expected_date_help_fits_mobile_and_can_be_toggled(page, app_server):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(app_server.url)
    button = page.get_by_role("button", name="About expected completion date").first
    button.click()
    tooltip = page.get_by_role("tooltip")
    expect(tooltip).to_be_visible()
    page.evaluate("window.scrollBy(0, -30)")
    expect(tooltip).to_be_visible()
    bounds = tooltip.bounding_box()
    assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 390
    button.click()
    expect(tooltip).to_be_hidden()


def test_hover_then_keyboard_focus_keeps_the_same_help_open(page, app_server):
    page.goto(app_server.url)
    button = page.get_by_role("button", name="About expected completion date").first
    button.hover()
    expect(page.get_by_role("tooltip")).to_be_visible()
    button.focus()
    page.evaluate("new Promise(resolve => requestAnimationFrame(resolve))")
    expect(button).to_be_focused()
    expect(page.get_by_role("tooltip")).to_be_visible()


def test_late_viewport_resize_repositions_focused_help_without_closing_it(
    page, app_server
):
    page.goto(app_server.url)
    button = page.get_by_role("button", name="About expected completion date").first
    button.focus()
    expect(page.get_by_role("tooltip")).to_be_visible()
    page.evaluate("window.dispatchEvent(new Event('resize'))")
    page.evaluate("new Promise(resolve => requestAnimationFrame(resolve))")
    expect(button).to_be_focused()
    expect(page.get_by_role("tooltip")).to_be_visible()


def test_expected_date_wording_and_help_in_editor_review_and_history(page, app_server):
    group = open_editor(page, app_server)
    field = group.get_by_label("Expected completion date", exact=True)
    field.fill("2026-12-10")
    button = group.get_by_role("button", name="About expected completion date")
    button.focus()
    expect(page.get_by_role("tooltip")).to_be_visible()
    field.focus()
    save_editor(page, group)
    open_history(page)
    history = page.get_by_role("article", name="Manager checklist edit: Drug screening")
    expect(history).to_contain_text("Expected completion date: Not set → 2026-12-10")
    page.get_by_label("Original update", exact=True).fill("Drug screening completed.")
    page.get_by_role("button", name="Analyze update", exact=True).click()
    card = page.get_by_role("article", name="Drug screening", exact=True)
    expect(card.get_by_role("columnheader").nth(2)).to_contain_text(
        "Expected completion date"
    )
    expect(
        card.get_by_role("button", name="About expected completion date")
    ).to_be_visible()
    expect(row(page)).to_contain_text("2026-12-10")
