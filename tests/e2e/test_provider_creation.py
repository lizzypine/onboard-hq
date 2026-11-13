"""Real browser creation, provider isolation, and recovery with TestModel only."""

from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
import pytest
from playwright.sync_api import expect

from tests.database import configured_test_url
from tests.e2e.test_review_workflow import open_history


def providers(page, app_server):
    return page.request.get(app_server.url + "/providers").json()


def open_form(page, app_server):
    page.goto(app_server.url)
    role = page.get_by_label("Simulated role", exact=True)
    expect(role).to_be_enabled()
    expect(page.get_by_role("button", name="Add provider", exact=True)).to_have_count(0)
    role.select_option("manager")
    button = page.get_by_role("button", name="Add provider", exact=True)
    expect(button).to_be_visible()
    button.click()
    form = page.locator("#provider-form")
    expect(form).to_be_visible()
    expect(form.get_by_label("Provider name", exact=True)).to_be_enabled()
    return form


def fill_form(form, name="Dr. Avery Example", start="2027-01-15"):
    form.get_by_label("Provider name", exact=True).fill(name)
    form.get_by_label("Proposed start date", exact=False).fill(start)


def save_form(page, app_server, form):
    with page.expect_response(
        lambda r: r.request.method == "POST" and r.url == app_server.url + "/providers"
    ) as response:
        form.get_by_role("button", name="Add provider", exact=True).click()
    assert response.value.status == 201
    created = response.value.json()
    expect(page.get_by_label("Provider", exact=True)).to_have_value(created["id"])
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
    form = open_form(page, app_server)
    expect(
        form.get_by_role("combobox", name="Provider type", exact=True)
    ).to_have_count(0)
    expect(form.locator("#provider-type-name")).to_have_text("Dentist")
    expect(form.get_by_label("Proposed start date", exact=False)).to_have_value("")
    preview = form.get_by_role(
        "table", name="New provider checklist preview", exact=True
    )
    expect(preview.locator("tbody tr")).to_have_count(5)
    expect(preview.get_by_role("cell", name="Outstanding", exact=True)).to_have_count(5)
    page.get_by_label("Original update", exact=True).fill("Old provider draft")
    fill_form(form)
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
    page.get_by_label("Provider", exact=True).select_option(created["id"])
    assert_new_counts(page)


def test_invalid_form_cancel_and_role_switch_do_not_create_records(page, app_server):
    form = open_form(page, app_server)
    submit = form.get_by_role("button", name="Add provider", exact=True)
    expect(submit).to_be_disabled()
    form.get_by_label("Provider name", exact=True).fill(" ")
    expect(submit).to_be_disabled()
    fill_form(form)
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
    page.get_by_label("Simulated role", exact=True).select_option("proposer")
    expect(form).to_be_hidden()
    expect(page.get_by_role("button", name="Add provider", exact=True)).to_have_count(0)
    assert len(providers(page, app_server)) == 1


def test_configured_type_preview_and_names_are_safe(page, app_server):
    type_id, template_id = uuid4(), uuid4()
    requirement = '<img src=x onerror="window.providerInjected=true">'
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "INSERT INTO provider_types VALUES (%s,'Synthetic Other')", (type_id,)
        )
        conn.execute(
            "INSERT INTO requirement_templates VALUES (%s,%s,%s)",
            (template_id, type_id, requirement),
        )
    form = open_form(page, app_server)
    form.get_by_label("Provider type", exact=True).select_option(str(type_id))
    expect(
        form.get_by_role("table", name="New provider checklist preview")
    ).to_contain_text(requirement)
    name = "<script>window.providerInjected=true</script>"
    fill_form(form, name, "")
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
    page.get_by_label("Provider", exact=True).select_option(created["id"])
    assert_new_counts(page)


def test_manager_can_create_first_provider_when_templates_exist(page, app_server):
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute("DELETE FROM requirements")
        conn.execute("DELETE FROM providers")
    form = open_form(page, app_server)
    expect(
        page.get_by_role("button", name="Analyze update", exact=True)
    ).to_be_disabled()
    fill_form(form, "First Fictional Provider", "")
    save_form(page, app_server, form)
    assert_new_counts(page)
    assert len(providers(page, app_server)) == 1


def test_missing_templates_disable_creation_without_fabricated_preview(
    page, app_server
):
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute("UPDATE requirements SET source_template_id=NULL")
        conn.execute("DELETE FROM requirement_templates")
    form = open_form(page, app_server)
    expect(page.locator("#provider-creation-status")).to_contain_text(
        "No configured requirements"
    )
    fill_form(form)
    expect(form.get_by_role("button", name="Add provider", exact=True)).to_be_disabled()
    expect(
        form.get_by_role("table", name="New provider checklist preview")
    ).to_be_hidden()
    assert len(providers(page, app_server)) == 1


@pytest.mark.parametrize("change_name", [False, True])
def test_lost_creation_response_reuses_identity(page, app_server, change_name):
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
    if change_name:
        form.get_by_label("Provider name", exact=True).fill("Changed Example")
        form.get_by_role("button", name="Add provider", exact=True).click()
        expect(page.locator("#provider-creation-status")).to_contain_text(
            "already saved different provider details"
        )
        assert all(p["name"] != "Changed Example" for p in providers(page, app_server))
    else:
        form.get_by_role("button", name="Add provider", exact=True).click()
        expect(form).to_be_hidden()
        expect(page.get_by_label("Provider", exact=True)).to_have_value(
            captured[0]["id"]
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
    expect(
        page.get_by_role("button", name="Analyze update", exact=True)
    ).to_be_disabled()
    page.unroute("**/providers**", intercept)
    page.get_by_role("button", name="Refresh data", exact=True).click()
    expect(page.get_by_label("Provider", exact=True)).to_have_value(saved_ids[0])
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
    page.get_by_label("Provider", exact=True).select_option(created["id"])
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
    page.get_by_label("Provider", exact=True).select_option(created["id"])
    expect(page.locator("#requirements")).to_contain_text("2026-12-18")


def test_creation_form_keyboard_and_narrow_layout(page, app_server, tmp_path):
    form = open_form(page, app_server)
    fill_form(form)
    form.screenshot(path=tmp_path / "provider-form-desktop.png")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    name = form.get_by_label("Provider name", exact=True)
    name.focus()
    page.keyboard.press("Tab")
    expect(form.get_by_label("Proposed start date", exact=False)).to_be_focused()
    save = form.get_by_role("button", name="Add provider", exact=True)
    for _ in range(8):
        page.keyboard.press("Tab")
        if save.evaluate("e => e === document.activeElement"):
            break
    expect(save).to_be_focused()
    form.screenshot(path=tmp_path / "provider-form-narrow.png")
