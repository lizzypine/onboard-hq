"""Real browser creation, provider isolation, and recovery with TestModel only."""

from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
import pytest
from playwright.sync_api import expect

from tests.database import configured_test_url
from tests.e2e.test_review_workflow import open_history
from tests.fixtures.current_database import configure_catalog, provider_type_id


def providers(page, app_server):
    return page.request.get(app_server.url + "/providers").json()


def open_form(page, app_server, update_text=None):
    page.goto(app_server.url)
    role = page.get_by_label("Simulated role", exact=True)
    expect(role).to_be_enabled()
    if update_text is not None:
        page.get_by_label("Original update", exact=True).fill(update_text)
    expect(page.get_by_role("button", name="Add provider", exact=True)).to_have_count(0)
    role.select_option("manager")
    button = page.get_by_role("button", name="Add provider", exact=True)
    expect(button).to_be_visible()
    button.click()
    form = page.locator("#provider-form")
    expect(form).to_be_visible()
    expect(form.get_by_label("Provider name", exact=True)).to_be_enabled()
    return form


def fill_form(
    form, name="Dr. Avery Example", start="2027-01-15", *, type_id=None, review=True
):
    form.get_by_label("Provider name", exact=True).fill(name)
    form.locator("#save-provider").click()
    picker = form.get_by_label("Provider type", exact=True)
    expect(picker).to_be_visible()
    expect(picker).to_have_value("")
    if type_id is None:
        picker.select_option(index=1)
    else:
        picker.select_option(str(type_id))
    form.locator("#save-provider").click()
    expect(form.get_by_label("Proposed start date", exact=False)).to_have_value("")
    form.get_by_label("Proposed start date", exact=False).fill(start)
    form.locator("#save-provider").click()
    if review:
        form.locator("#save-provider").click()


def save_form(page, app_server, form):
    if not form.get_by_role("heading", name="Review before adding", exact=True).count():
        form.locator("#save-provider").click()
    with page.expect_response(
        lambda r: r.request.method == "POST" and r.url == app_server.url + "/providers"
    ) as response:
        form.get_by_role("button", name="Add provider", exact=True).click()
    assert response.value.status == 201
    created = response.value.json()
    expect(page.get_by_label("Provider", exact=True)).to_have_value(str(created["id"]))
    expect(form).to_be_hidden()
    return created


def assert_new_counts(page):
    summary = page.get_by_role("region", name="Monitoring summary", exact=True)
    for label, value in [
        ("Finished", "0"),
        ("Remaining", "5"),
        ("Overdue", "0"),
        ("Needs review", "0"),
    ]:
        expect(summary.get_by_label(label, exact=True)).to_have_text(value)


def test_manager_adds_and_selects_an_independent_provider(
    page, app_server, seeded_provider
):
    original = page.request.get(
        app_server.url + f"/providers/{seeded_provider.id}"
    ).json()
    form = open_form(page, app_server, update_text="Old provider draft")
    fill_form(form, review=False)
    preview = form.get_by_role(
        "table", name="New provider checklist preview", exact=True
    )
    expect(preview.locator("tbody tr")).to_have_count(5)
    expect(preview.get_by_role("cell", name="Outstanding", exact=True)).to_have_count(5)
    created = save_form(page, app_server, form)
    assert_new_counts(page)
    expect(page.get_by_label("Original update", exact=True)).to_have_value("")
    expect(page.locator("#provider-description")).to_contain_text("2027-01-15")
    expect(page.locator("#review-results")).to_contain_text("No saved updates yet")
    assert (
        page.request.get(app_server.url + f"/providers/{seeded_provider.id}").json()
        == original
    )
    assert len(providers(page, app_server)) == 2
    page.get_by_label("Provider", exact=True).select_option(str(seeded_provider.id))
    expect(
        page.get_by_role("region", name="Monitoring summary").get_by_label(
            "Finished", exact=True
        )
    ).to_have_text("2")
    page.get_by_label("Provider", exact=True).select_option(str(created["id"]))
    assert_new_counts(page)


def test_invalid_form_cancel_and_role_switch_do_not_create_records(page, app_server):
    form = open_form(page, app_server)
    submit = form.locator("#save-provider")
    expect(submit).to_be_disabled()
    form.get_by_label("Provider name", exact=True).fill(" ")
    expect(submit).to_be_disabled()
    fill_form(form)
    form.get_by_role("button", name="Edit date", exact=True).click()
    date = form.get_by_label("Proposed start date", exact=False)
    date.focus()
    date.press("Home")
    date.press("Delete")
    assert date.evaluate("e => e.validity.badInput")
    expect(submit).to_be_disabled()
    form.get_by_role("button", name="Cancel", exact=True).click()
    expect(form).to_be_hidden()
    page.get_by_role("button", name="Add provider", exact=True).click()
    expect(form).to_be_visible()
    form.get_by_role("button", name="Cancel", exact=True).click()
    page.get_by_label("Simulated role", exact=True).select_option("proposer")
    expect(form).to_be_hidden()
    expect(page.get_by_role("button", name="Add provider", exact=True)).to_have_count(0)
    assert len(providers(page, app_server)) == 1


def test_configured_type_preview_and_names_are_safe(page, app_server):
    requirement = '<img src=x onerror="window.providerInjected=true">'
    type_id = configure_catalog("Synthetic Other", [requirement]).id
    form = open_form(page, app_server)
    name = "<script>window.providerInjected=true</script>"
    fill_form(form, name, "", type_id=type_id, review=False)
    expect(
        form.get_by_role("table", name="New provider checklist preview")
    ).to_contain_text(requirement)
    created = save_form(page, app_server, form)
    assert created["name"] == name
    assert [r["name"] for r in created["requirements"]] == [requirement]
    expect(page.locator("#requirements img")).to_have_count(0)
    assert page.evaluate("window.providerInjected") is None
    expect(
        page.get_by_role("region", name="Monitoring summary").get_by_label(
            "Needs review", exact=True
        )
    ).to_have_text("1")


def test_duplicate_names_remain_distinct_selectable_records(
    page, app_server, seeded_provider
):
    form = open_form(page, app_server)
    fill_form(form, seeded_provider.name, "2026-12-01")
    created = save_form(page, app_server, form)
    options = page.get_by_label("Provider", exact=True).get_by_role("option")
    labels = options.all_text_contents()
    assert len(labels) == len(set(labels)) == 2
    assert all(seeded_provider.name in label for label in labels)
    page.get_by_label("Provider", exact=True).select_option(str(seeded_provider.id))
    expect(
        page.get_by_role("region", name="Monitoring summary").get_by_label(
            "Finished", exact=True
        )
    ).to_have_text("2")
    page.get_by_label("Provider", exact=True).select_option(str(created["id"]))
    assert_new_counts(page)


def test_manager_can_create_first_provider_when_templates_exist(page, app_server):
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute("DELETE FROM requirements")
        conn.execute("DELETE FROM providers")
    form = open_form(page, app_server)
    expect(page.locator("#submit-update")).to_be_disabled()
    fill_form(form, "First Fictional Provider", "")
    save_form(page, app_server, form)
    assert_new_counts(page)
    assert len(providers(page, app_server)) == 1


def test_missing_templates_disable_creation_without_fabricated_preview(
    page, app_server
):
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "INSERT INTO checklist_templates(provider_type_id,template_version) VALUES (%s,2)",
            (provider_type_id(),),
        )
    form = open_form(page, app_server)
    expect(page.locator("#provider-creation-status")).to_contain_text(
        "No configured requirements"
    )
    form.get_by_label("Provider name", exact=True).fill("Dr. Avery Example")
    expect(form.locator("#save-provider")).to_be_disabled()
    expect(
        form.get_by_role("table", name="New provider checklist preview")
    ).to_be_hidden()
    assert len(providers(page, app_server)) == 1


@pytest.mark.parametrize("close_reopen", [False, True])
def test_lost_creation_response_reuses_frozen_identity(page, app_server, close_reopen):
    form = open_form(page, app_server)
    fill_form(form)
    captured = []

    def lose_response(route):
        if route.request.method == "POST":
            captured.append(route.fetch().json())
            route.abort("failed")
        else:
            route.continue_()

    page.route("**/providers", lose_response)
    form.get_by_role("button", name="Add provider", exact=True).click()
    expect(page.locator("#provider-creation-status")).to_contain_text(
        "could not be confirmed"
    )
    page.unroute("**/providers", lose_response)
    expect(form.get_by_label("Provider name", exact=True)).to_have_count(0)
    if close_reopen:
        form.get_by_role("button", name="Cancel", exact=True).click()
        page.get_by_role("button", name="Add provider", exact=True).click()
    form.get_by_role("button", name="Retry save", exact=True).click()
    expect(form).to_be_hidden()
    expect(page.get_by_label("Provider", exact=True)).to_have_value(
        str(captured[0]["id"])
    )
    assert_new_counts(page)
    assert len(providers(page, app_server)) == 2
    assert (
        sum(p["name"] == "Dr. Avery Example" for p in providers(page, app_server)) == 1
    )


@pytest.mark.parametrize("failed_read", ["list", "dashboard", "history"])
def test_saved_creation_failed_refresh_recovers_new_selection(
    page, app_server, failed_read
):
    form = open_form(page, app_server)
    fill_form(form)
    saved_ids = []

    def intercept(route):
        path = urlsplit(route.request.url).path
        if route.request.method == "POST" and path == "/providers":
            response = route.fetch()
            saved_ids.append(response.json()["id"])
            route.fulfill(response=response)
        elif saved_ids and (
            (failed_read == "list" and path == "/providers")
            or (failed_read == "dashboard" and path.endswith("/dashboard"))
            or (failed_read == "history" and path.endswith("/updates"))
        ):
            route.fulfill(status=503, json={"detail": "Saved data is unavailable."})
        else:
            route.continue_()

    page.route("**/providers**", intercept)
    form.get_by_role("button", name="Add provider", exact=True).click()
    expect(page.locator("#provider-creation-status")).to_contain_text(
        "Provider saved, but"
    )
    expect(page.locator("#requirements")).to_be_empty()
    expect(page.locator("#provider-description")).to_be_empty()
    expect(
        page.get_by_role("region", name="Monitoring summary", exact=True)
    ).to_be_hidden()
    expect(page.locator("#submit-update")).to_be_disabled()
    page.unroute("**/providers**", intercept)
    form.get_by_role("button", name="Cancel", exact=True).click()
    page.get_by_role("button", name="Refresh data", exact=True).click()
    expect(page.get_by_label("Provider", exact=True)).to_have_value(str(saved_ids[0]))
    expect(form).to_be_hidden()
    assert_new_counts(page)
    assert len(providers(page, app_server)) == 2


def test_new_provider_analysis_and_review_stay_scoped_after_restart(
    page, app_server, seeded_provider
):
    original = page.request.get(
        app_server.url + f"/providers/{seeded_provider.id}"
    ).json()
    form = open_form(page, app_server)
    fill_form(form)
    created = save_form(page, app_server, form)
    app_server.restart("inferred")
    page.reload()
    page.get_by_label("Provider", exact=True).select_option(str(created["id"]))
    assert_new_counts(page)
    page.get_by_label("Original update", exact=True).fill("Drug screening on the 18th.")
    page.get_by_role("button", name="Analyze update", exact=True).click()
    open_history(page)
    card = page.get_by_role("article", name="Drug screening", exact=True)
    expect(card).to_contain_text("2026-12-18")
    page.get_by_label("Simulated role", exact=True).select_option("manager")
    card.get_by_label("Confirm inferred date", exact=True).check()
    card.get_by_role("button", name="Approve", exact=True).click()
    expect(card).to_contain_text("Approved")
    assert (
        page.request.get(app_server.url + f"/providers/{seeded_provider.id}").json()
        == original
    )
    assert (
        page.request.get(
            app_server.url + f"/providers/{seeded_provider.id}/updates"
        ).json()
        == []
    )
    history = page.request.get(
        app_server.url + f"/providers/{created['id']}/updates"
    ).json()
    assert history[0]["provider_snapshot"]["id"] == created["id"]
    assert all(
        r["status"] == "Outstanding"
        for r in history[0]["provider_snapshot"]["requirements"]
    )
    app_server.restart()
    page.reload()
    page.get_by_label("Provider", exact=True).select_option(str(created["id"]))
    expect(page.locator("#requirements")).to_contain_text("2026-12-18")


def test_creation_form_keyboard_and_narrow_layout(page, app_server, tmp_path):
    form = open_form(page, app_server)
    name = form.get_by_label("Provider name", exact=True)
    name.fill("Dr. Keyboard Example")
    name.focus()
    page.keyboard.press("Tab")
    expect(form.get_by_role("button", name="Cancel", exact=True)).to_be_focused()
    page.keyboard.press("Tab")
    expect(form.locator("#save-provider")).to_be_focused()
    page.keyboard.press("Enter")
    form.get_by_label("Provider type", exact=True).select_option(index=1)
    form.locator("#save-provider").click()
    form.get_by_label("Proposed start date", exact=False).fill("2027-01-15")
    form.screenshot(path=tmp_path / "provider-form-desktop.png")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    form.get_by_label("Proposed start date", exact=False).focus()
    save = form.locator("#save-provider")
    for _ in range(8):
        page.keyboard.press("Tab")
        if save.evaluate("e => e === document.activeElement"):
            break
    expect(save).to_be_focused()
    page.keyboard.press("Enter")
    save.click()
    close = form.get_by_role("button", name="Close Add provider", exact=True)
    close.focus()
    page.keyboard.press("Shift+Tab")
    expect(save).to_be_focused()
    page.keyboard.press("Tab")
    expect(close).to_be_focused()
    form.screenshot(path=tmp_path / "provider-form-narrow.png")


@pytest.mark.parametrize("populated", [False, True])
def test_creation_from_archived_view_selects_the_new_active_provider(
    page, app_server, seeded_provider, populated
):
    if populated:
        with psycopg.connect(configured_test_url()) as conn:
            conn.execute(
                "UPDATE providers SET archived_at=now() WHERE id=%s",
                (seeded_provider.id,),
            )
    page.goto(app_server.url)
    expect(page.get_by_label("Simulated role", exact=True)).to_be_enabled()
    page.locator("#provider-state").select_option("archived")
    if populated:
        expect(page.locator("#requirements")).to_contain_text("Drug screening")
    else:
        expect(page.locator("#requirements")).to_be_empty()
    page.get_by_label("Simulated role", exact=True).select_option("manager")
    page.get_by_role("button", name="Add provider", exact=True).click()
    form = page.locator("#provider-form")
    fill_form(form, "New active provider from Archived", "")
    created = save_form(page, app_server, form)
    expect(page.locator("#provider-state")).to_have_value("active")
    expect(page.get_by_label("Provider", exact=True)).to_have_value(str(created["id"]))
    assert created["archived_at"] is None
    assert_new_counts(page)


def test_provider_view_transitions_clear_update_text_before_selecting_another_person(
    page, app_server, seeded_provider
):
    preview = page.request.get(app_server.url + "/provider-types").json()[0]
    kind = preview["id"]

    def create(name):
        response = page.request.post(
            app_server.url + "/providers",
            headers={"X-Demo-Role": "manager"},
            data={
                "creation_request_id": str(uuid4()),
                "name": name,
                "provider_type_id": kind,
                "checklist_template_id": preview["checklist_template_id"],
                "template_fingerprint": preview["template_fingerprint"],
            },
        )
        assert response.status == 201
        return response.json()

    other = create("ZZ Active Example")
    archived = create("Archived Example")
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "UPDATE providers SET archived_at=now() WHERE id=%s", (archived["id"],)
        )
    page.goto(app_server.url)
    expect(page.get_by_label("Simulated role", exact=True)).to_be_enabled()
    page.get_by_label("Provider", exact=True).select_option(str(other["id"]))
    expect(page.get_by_label("Provider", exact=True)).to_have_value(str(other["id"]))
    page.get_by_label("Original update", exact=True).fill(
        "Drug screening completed for ZZ Active Example."
    )
    page.locator("#provider-state").select_option("archived")
    expect(page.get_by_label("Provider", exact=True)).to_have_value(str(archived["id"]))
    expect(page.get_by_label("Original update", exact=True)).to_have_value("")
    page.get_by_label("Original update", exact=True).fill(
        "An unsent archived-provider draft."
    )
    page.locator("#provider-state").select_option("active")
    expect(page.get_by_label("Provider", exact=True)).to_have_value(
        str(seeded_provider.id)
    )
    expect(page.get_by_label("Original update", exact=True)).to_have_value("")
    for identity in [seeded_provider.id, other["id"], archived["id"]]:
        assert (
            page.request.get(app_server.url + f"/providers/{identity}/updates").json()
            == []
        )


def test_provider_view_cannot_change_while_analysis_is_in_flight(page, app_server):
    page.goto(app_server.url)
    analyze = page.get_by_role("button", name="Analyze update", exact=True)
    expect(analyze).to_be_enabled()
    held = []
    page.route("**/updates/analyze", lambda route: held.append(route))
    page.get_by_label("Original update", exact=True).fill("Drug screening completed.")
    with page.expect_request("**/updates/analyze"):
        analyze.click()
    try:
        expect(page.locator("#provider-state")).to_be_disabled()
    finally:
        for route in held:
            route.continue_()
