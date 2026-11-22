"""The real Add Provider modal stages additions and saves one reviewed checklist."""

import pytest
from playwright.sync_api import expect

from tests.database import ROOT
from tests.fixtures.current_database import configure_catalog


def open_wizard(page, app_server):
    page.goto(app_server.url)
    role = page.get_by_label("Simulated role", exact=True)
    expect(role).to_be_enabled()
    role.select_option("manager")
    page.get_by_role("button", name="Add provider", exact=True).click()
    dialog = page.get_by_role("dialog", name="Add a provider", exact=True)
    expect(dialog).to_be_visible()
    return dialog


def requirements_step(page, app_server, type_id=None):
    dialog = open_wizard(page, app_server)
    dialog.get_by_label("Provider name", exact=True).fill("Dr. Wizard Example")
    dialog.locator("#save-provider").click()
    picker = dialog.get_by_label("Provider type", exact=True)
    expect(picker).to_be_visible()
    expect(picker).to_have_value("")
    if type_id is None:
        type_id = page.request.get(app_server.url + "/provider-types").json()[0]["id"]
    picker.select_option(str(type_id))
    dialog.locator("#save-provider").click()
    expect(dialog.get_by_label("Proposed start date", exact=False)).to_have_value("")
    dialog.get_by_role("button", name="Skip for now", exact=False).click()
    return dialog


def edit_addition(dialog, name="Orientation", status="Completed", date="2026-12-10"):
    dialog.get_by_role("button", name="Add requirement", exact=True).click()
    group = dialog.get_by_role("group", name="New additional requirement", exact=True)
    group.get_by_label("Requirement name", exact=True).fill(name)
    group.get_by_label("Status", exact=True).select_option(status)
    if date:
        group.get_by_label("Expected completion date", exact=True).fill(date)
    return group


def save_provider(page, app_server, dialog):
    dialog.locator("#save-provider").click()
    expect(
        dialog.get_by_role("heading", name="Review before adding", exact=True)
    ).to_be_visible()
    expect(dialog.locator("#save-provider")).to_have_text("Add provider")
    with page.expect_response(
        lambda r: r.request.method == "POST" and r.url == app_server.url + "/providers"
    ) as response:
        dialog.locator("#save-provider").click()
    assert response.value.status == 201, response.value.text()
    expect(dialog).to_be_hidden()
    return response.value.json()


def test_one_requirement_is_saved_to_combined_draft_before_another(
    page, app_server, seeded_provider
):
    writes = []
    page.on("request", lambda r: writes.append(r.url) if r.method == "POST" else None)
    dialog = requirements_step(page, app_server)
    table = dialog.get_by_role(
        "table", name="New provider checklist preview", exact=True
    )
    expect(table.locator("tbody tr")).to_have_count(5)
    group = edit_addition(dialog)
    group.get_by_label("Deadline", exact=True).fill("2026-12-20")
    expect(table).not_to_contain_text("Orientation")
    expect(dialog.locator("#save-provider")).to_be_disabled()
    group.get_by_role("button", name="Save requirement", exact=True).click()
    expect(group).to_have_count(0)
    expect(table).to_contain_text("Orientation")
    expect(table).to_contain_text("Dec 10, 2026")
    expect(table.locator("tbody tr")).to_have_count(6)
    edit_addition(dialog, "IT access", "Scheduled", "").get_by_role(
        "button", name="Save requirement", exact=True
    ).click()
    expect(table.locator("tbody tr")).to_have_count(7)
    images = ROOT / ".superpowers/sdd/2026-11-22-add-provider-walkthrough"
    page.set_viewport_size({"width": 1200, "height": 1000})
    dialog.locator("#provider-step-content").evaluate("node => { node.scrollTop = 0; }")
    dialog.screenshot(path=images / "modal-requirements-desktop.png")
    page.set_viewport_size({"width": 390, "height": 844})
    dialog.screenshot(path=images / "modal-requirements-mobile.png")
    assert dialog.locator("#save-provider").bounding_box()["height"] < 55
    badge = table.get_by_text("Scheduled", exact=True)
    size = badge.bounding_box()
    assert size["width"] < 130 and size["height"] < 35
    dialog.get_by_role("button", name="Edit Orientation", exact=True).click()
    editor = dialog.get_by_role("group", name="Edit additional requirement", exact=True)
    editor.get_by_label("Requirement name", exact=True).fill("Canceled edit")
    expect(table).not_to_contain_text("Canceled edit")
    editor.get_by_role("button", name="Cancel requirement", exact=True).click()
    expect(table).to_contain_text("Orientation")
    assert writes == []
    saved = save_provider(page, app_server, dialog)
    assert len(saved["requirements"]) == 7 and len(writes) == 1
    expect(page.locator("#count-finished")).to_have_text("1")
    expect(page.locator("#count-remaining")).to_have_text("6")
    expect(page.locator("#requirements")).to_contain_text("Additional")
    original = page.request.get(
        app_server.url + f"/providers/{seeded_provider.id}"
    ).json()
    assert len(original["requirements"]) == 5
    app_server.restart()
    page.reload()
    page.get_by_label("Provider", exact=True).select_option(str(saved["id"]))
    expect(page.locator("#requirements")).to_contain_text("Orientation")


def test_addition_validation_remove_and_modal_keyboard_help(page, app_server):
    dialog = requirements_step(page, app_server)
    group = edit_addition(dialog, " drug screening ", "Scheduled")
    expect(
        group.get_by_role("button", name="Save requirement", exact=True)
    ).to_be_disabled()
    group.get_by_label("Requirement name", exact=True).fill(
        '<img src=x onerror="window.wizardInjected=true">'
    )
    group.get_by_role("button", name="Save requirement", exact=True).click()
    expect(dialog.locator("img")).to_have_count(0)
    assert page.evaluate("window.wizardInjected") is None
    dialog.get_by_role(
        "button",
        name='Remove <img src=x onerror="window.wizardInjected=true">',
        exact=True,
    ).click()
    expect(
        dialog.get_by_role("table", name="New provider checklist preview").locator(
            "tbody tr"
        )
    ).to_have_count(5)
    group = edit_addition(dialog, "Orientation", "Scheduled", "")
    help_button = group.get_by_role("button", name="About expected completion date")
    help_button.focus()
    page.evaluate("new Promise(resolve => requestAnimationFrame(resolve))")
    expect(help_button).to_be_focused()
    expect(page.get_by_role("tooltip")).to_be_visible()
    assert (
        page.get_by_role("tooltip").evaluate("e => e.closest('dialog')?.open") is True
    )
    page.keyboard.press("Escape")
    expect(page.get_by_role("tooltip")).to_be_hidden()
    expect(dialog).to_be_visible()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden()
    expect(page.get_by_role("button", name="Add provider", exact=True)).to_be_focused()
    assert len(page.request.get(app_server.url + "/providers").json()) == 1


def test_catalog_conflict_preserves_draft_and_requires_review_again(page, app_server):
    dialog = requirements_step(page, app_server)
    edit_addition(dialog).get_by_role(
        "button", name="Save requirement", exact=True
    ).click()
    dialog.locator("#save-provider").click()
    configure_catalog("Dentist", ["Drug screening", "New standard item"], version=2)
    dialog.locator("#save-provider").click()
    expect(
        dialog.get_by_role("table", name="New provider checklist preview")
    ).to_contain_text("New standard item")
    expect(dialog).to_contain_text("Orientation")
    assert len(page.request.get(app_server.url + "/providers").json()) == 1
    saved = save_provider(page, app_server, dialog)
    assert {r["name"] for r in saved["requirements"]} == {
        "Drug screening",
        "New standard item",
        "Orientation",
    }


def test_lost_creation_response_survives_reload_without_duplicate_provider(
    page, app_server
):
    dialog = requirements_step(page, app_server)
    edit_addition(dialog).get_by_role(
        "button", name="Save requirement", exact=True
    ).click()
    dialog.locator("#save-provider").click()
    bodies = []

    def lose_response(route):
        if route.request.method == "POST":
            bodies.append(route.request.post_data_json)
            route.fetch()
            route.abort("failed")
        else:
            route.continue_()

    page.route("**/providers", lose_response)
    dialog.locator("#save-provider").click()
    expect(dialog).to_contain_text("could not be confirmed")
    page.unroute("**/providers", lose_response)
    page.reload()
    expect(page.get_by_label("Simulated role", exact=True)).to_be_enabled()
    assert len(page.request.get(app_server.url + "/providers").json()) == 2
    expect(page.get_by_role("button", name="Add provider", exact=True)).to_have_count(0)
    page.get_by_label("Simulated role", exact=True).select_option("manager")
    page.get_by_role("button", name="Add provider", exact=True).click()
    dialog = page.get_by_role("dialog", name="Add a provider", exact=True)
    with page.expect_response(
        lambda r: r.request.method == "POST" and r.url == app_server.url + "/providers"
    ) as response:
        dialog.get_by_role("button", name="Retry save", exact=True).click()
    assert response.value.status == 201
    assert response.value.request.post_data_json == bodies[0]
    expect(dialog).to_be_hidden()
    assert len(page.request.get(app_server.url + "/providers").json()) == 2
    assert (
        page.evaluate("sessionStorage.getItem('onboard-hq:provider-creation:v1')")
        is None
    )


@pytest.mark.parametrize("conflict", ["duplicate", "status"])
def test_type_change_retains_additions_until_conflicts_are_resolved(
    page, app_server, conflict
):
    configure_catalog("Dentist", ["Drug screening"], version=2)
    other = configure_catalog("Synthetic Other", ["Other standard"])
    dialog = requirements_step(page, app_server, other.id)
    name = "Drug screening" if conflict == "duplicate" else "Offer letter"
    edit_addition(dialog, name, "Completed", "").get_by_role(
        "button", name="Save requirement", exact=True
    ).click()
    dialog.locator("#save-provider").click()
    dialog.get_by_role("button", name="Edit type", exact=True).click()
    kinds = page.request.get(app_server.url + "/provider-types").json()
    dentist = next(k for k in kinds if k["name"] == "Dentist")
    dialog.get_by_label("Provider type", exact=True).select_option(str(dentist["id"]))
    dialog.locator("#save-provider").click()
    expect(
        dialog.get_by_role("table", name="New provider checklist preview")
    ).to_be_visible()
    expect(dialog.locator("#save-provider")).to_be_disabled()
    dialog.get_by_role("button", name="Edit " + name, exact=True).click()
    editor = dialog.get_by_role("group", name="Edit additional requirement", exact=True)
    if conflict == "duplicate":
        editor.get_by_label("Requirement name", exact=True).fill("Additional screening")
    else:
        editor.get_by_label("Status", exact=True).select_option("Signed")
    editor.get_by_role("button", name="Save requirement", exact=True).click()
    expect(dialog.locator("#save-provider")).to_be_enabled()


def test_recovery_storage_failure_prevents_new_save(page, app_server):
    page.add_init_script(
        "Storage.prototype.setItem = function() { throw new DOMException('Blocked', 'SecurityError'); };"
    )
    dialog = requirements_step(page, app_server)
    dialog.locator("#save-provider").click()
    writes = []
    page.on(
        "request",
        lambda request: (
            writes.append(request.url) if request.method == "POST" else None
        ),
    )
    dialog.locator("#save-provider").click()
    expect(dialog).to_contain_text("No request was sent")
    assert writes == []
    assert len(page.request.get(app_server.url + "/providers").json()) == 1


def test_fast_double_submit_creates_only_one_provider(page, app_server):
    dialog = requirements_step(page, app_server)
    dialog.locator("#save-provider").click()
    held = []

    def hold(route):
        if route.request.method == "POST":
            held.append(route)
        else:
            route.continue_()

    page.route("**/providers", hold)
    with page.expect_request(
        lambda request: (
            request.method == "POST" and request.url == app_server.url + "/providers"
        )
    ):
        dialog.locator("#save-provider").evaluate(
            "button => { button.click(); button.click(); }"
        )
    try:
        assert len(held) == 1
        expect(dialog.locator("#save-provider")).to_be_disabled()
    finally:
        for route in held:
            route.continue_()
    expect(dialog).to_be_hidden()
    assert len(page.request.get(app_server.url + "/providers").json()) == 2
