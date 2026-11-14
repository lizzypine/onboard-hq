"""Real-browser Manager edits, disclosure behavior, and frozen save recovery."""

from uuid import uuid4

import psycopg
import pytest
from playwright.sync_api import expect

from app.seed import DENTIST_ID
from tests.database import configured_test_url
from tests.test_checklist_edits import edit_body, endpoint

MANAGER = {"X-Demo-Role": "manager"}


def load(page, server):
    page.goto(server.url)
    expect(page.get_by_label("Simulated role", exact=True)).to_be_enabled()


def row(page, name="Drug screening"):
    return page.locator("#requirements > .requirement-row").filter(has_text=name)


def editor(page, name="Drug screening"):
    return page.get_by_role("group", name="Edit " + name, exact=True)


def open_editor(page, server, name="Drug screening"):
    load(page, server)
    expect(page.get_by_role("button", name="Edit", exact=True)).to_have_count(0)
    page.get_by_label("Simulated role", exact=True).select_option("manager")
    row(page, name).get_by_role("button", name="Edit", exact=True).click()
    return editor(page, name)


def history(page):
    return page.locator("#review-disclosure")


def open_history(page):
    if not history(page).evaluate("e => e.open"):
        history(page).locator("summary").click()


def read_provider(page, server, provider_id):
    return page.request.get(server.url + f"/providers/{provider_id}").json()


def read_edits(page, server, provider_id):
    return page.request.get(
        server.url + f"/providers/{provider_id}/checklist-edits"
    ).json()


def save_editor(page, group):
    with page.expect_response(
        lambda r: r.request.method == "POST" and r.url.endswith("/edits")
    ) as response:
        group.get_by_role("button", name="Save changes", exact=True).click()
    assert response.value.status == 201
    expect(group).to_have_count(0)
    return response.value.json()


def second_provider(page, server):
    response = page.request.post(
        server.url + "/providers",
        headers=MANAGER,
        data={
            "id": str(uuid4()),
            "name": "Another Fictional Provider",
            "provider_type_id": str(DENTIST_ID),
        },
    )
    assert response.status == 201
    return response.json()


def test_disclosure_defaults_pending_counts_and_provider_switch(
    page, app_server, seeded_provider
):
    load(page, app_server)
    expect(page.get_by_role("heading", name="3. Updates", exact=True)).to_be_visible()
    assert not history(page).evaluate("e => e.open")
    page.get_by_label("Original update", exact=True).fill("Drug screening completed.")
    page.get_by_role("button", name="Analyze update", exact=True).click()
    expect(history(page).locator("summary")).to_contain_text("1 pending suggestion")
    assert not history(page).evaluate("e => e.open")
    expect(page.locator("#request-status")).to_contain_text(
        "Suggestions and review history"
    )
    summary = history(page).locator("summary")
    summary.focus()
    page.keyboard.press("Enter")
    expect(
        page.get_by_role("article", name="Drug screening", exact=True)
    ).to_be_visible()
    page.get_by_role("button", name="Refresh data", exact=True).click()
    expect(page.get_by_label("Simulated role", exact=True)).to_be_enabled()
    assert history(page).evaluate("e => e.open")
    page.get_by_label("Simulated role", exact=True).select_option("manager")
    page.get_by_role("button", name="Approve", exact=True).click()
    expect(history(page).locator("summary")).to_contain_text("0 pending suggestions")
    assert history(page).evaluate("e => e.open")
    other = second_provider(page, app_server)
    page.get_by_role("button", name="Refresh data", exact=True).click()
    page.get_by_label("Provider", exact=True).select_option(other["id"])
    expect(row(page)).to_contain_text("Outstanding")
    assert not history(page).evaluate("e => e.open")
    page.get_by_label("Provider", exact=True).select_option(str(seeded_provider.id))
    expect(row(page)).to_contain_text("Completed")
    assert not history(page).evaluate("e => e.open")


def test_manager_saves_three_fields_and_history_survives_restart(
    page, app_server, seeded_provider
):
    group = open_editor(page, app_server)
    status = group.get_by_role("combobox", name="Checklist status", exact=True)
    expect(status.get_by_role("option")).to_have_text(
        ["Outstanding", "Pending", "Scheduled", "Incomplete", "Completed"]
    )
    status.select_option("Completed")
    group.get_by_label("Requirement date", exact=True).fill("2026-11-12")
    group.get_by_label("Deadline", exact=True).fill("2026-11-20")
    saved = save_editor(page, group)
    expect(row(page).locator(".status-badge")).to_have_class(
        "status-badge status-finished"
    )
    expect(row(page)).to_contain_text("2026-11-12")
    expect(row(page)).to_contain_text("2026-11-20")
    expect(page.locator("#count-finished")).to_have_text("3")
    assert not history(page).evaluate("e => e.open")
    open_history(page)
    expect(history(page)).to_contain_text("Manager checklist edit")
    expect(history(page)).to_contain_text("Scheduled → Completed")
    assert read_edits(page, app_server, seeded_provider.id) == [saved]
    app_server.restart()
    page.reload()
    expect(row(page)).to_contain_text("2026-11-20")
    assert not history(page).evaluate("e => e.open")
    page.get_by_label("Simulated role", exact=True).select_option("manager")
    row(page).get_by_role("button", name="Edit", exact=True).click()
    group = editor(page)
    group.get_by_label("Requirement date", exact=True).fill("")
    group.get_by_label("Deadline", exact=True).fill("")
    save_editor(page, group)
    expect(row(page).get_by_role("cell").nth(2)).to_have_text("Not set")
    expect(row(page).get_by_role("cell").nth(3)).to_have_text("Not set")
    assert len(read_edits(page, app_server, seeded_provider.id)) == 2


def test_invalid_noop_cancel_role_change_and_row_stripes(
    page, app_server, seeded_provider
):
    group = open_editor(page, app_server)
    stripe_classes = page.locator("#requirements > .requirement-row").evaluate_all(
        "rows => rows.map(r => r.classList.contains('stripe-even'))"
    )
    assert stripe_classes == [False, True, False, True, False]
    save = group.get_by_role("button", name="Save changes", exact=True)
    expect(save).to_be_disabled()
    field = group.get_by_label("Requirement date", exact=True)
    field.fill("2026-11-12")
    field.focus()
    field.press("Home")
    field.press("Delete")
    assert field.evaluate("e => e.validity.badInput")
    expect(save).to_be_disabled()
    group.get_by_role("button", name="Cancel", exact=True).click()
    expect(group).to_have_count(0)
    assert (
        page.locator("#requirements > .requirement-row").evaluate_all(
            "rows => rows.map(r => r.classList.contains('stripe-even'))"
        )
        == stripe_classes
    )
    row(page).get_by_role("button", name="Edit", exact=True).click()
    editor(page).get_by_role(
        "combobox", name="Checklist status", exact=True
    ).select_option("Completed")
    page.get_by_label("Simulated role", exact=True).select_option("proposer")
    expect(editor(page)).to_have_count(0)
    assert read_edits(page, app_server, seeded_provider.id) == []


@pytest.mark.parametrize("later_progress", [False, True])
def test_lost_save_response_freezes_identity_across_role_and_provider_switch(
    page, app_server, seeded_provider, later_progress
):
    other = second_provider(page, app_server)
    group = open_editor(page, app_server)
    page.get_by_label("Provider", exact=True).select_option(str(seeded_provider.id))
    row(page).get_by_role("button", name="Edit", exact=True).click()
    group = editor(page)
    group.get_by_role("combobox", name="Checklist status", exact=True).select_option(
        "Completed"
    )
    captured = []

    def lose(route):
        captured.append(route.request.post_data_json)
        assert route.fetch().status == 201
        route.abort("failed")

    page.route("**/requirements/*/edits", lose)
    group.get_by_role("button", name="Save changes", exact=True).click()
    expect(page.locator("#checklist-status")).to_contain_text("could not be confirmed")
    expect(
        group.get_by_role("combobox", name="Checklist status", exact=True)
    ).to_be_disabled()
    page.unroute("**/requirements/*/edits", lose)
    if later_progress:
        page.reload()
        expect(page.get_by_label("Simulated role", exact=True)).to_be_enabled()
    page.get_by_label("Simulated role", exact=True).select_option("proposer")
    page.get_by_label("Provider", exact=True).select_option(other["id"])
    expect(
        page.get_by_role("button", name="Retry checklist save", exact=True)
    ).to_be_hidden()
    if later_progress:
        current = next(
            r
            for r in read_provider(page, app_server, seeded_provider.id)["requirements"]
            if r["name"] == "Drug screening"
        )
        response = page.request.post(
            app_server.url + endpoint(seeded_provider.id, current["id"]),
            headers=MANAGER,
            data=edit_body(current, status="Incomplete"),
        )
        assert response.status == 201
    page.get_by_label("Provider", exact=True).select_option(str(seeded_provider.id))
    page.get_by_label("Simulated role", exact=True).select_option("manager")
    with page.expect_request(
        lambda r: r.method == "POST" and r.url.endswith("/edits")
    ) as retry:
        page.get_by_role("button", name="Retry checklist save", exact=True).click()
    assert retry.value.post_data_json == captured[0]
    expect(
        page.get_by_role("button", name="Retry checklist save", exact=True)
    ).to_be_hidden()
    expect(row(page)).to_contain_text("Incomplete" if later_progress else "Completed")
    assert len(read_edits(page, app_server, seeded_provider.id)) == (
        2 if later_progress else 1
    )


@pytest.mark.parametrize("failed_read", ["dashboard", "updates", "checklist-edits"])
def test_saved_edit_failed_reload_is_honest_and_refresh_recovers(
    page, app_server, seeded_provider, failed_read
):
    group = open_editor(page, app_server)
    group.get_by_role("combobox", name="Checklist status", exact=True).select_option(
        "Completed"
    )

    def fail(route):
        route.fulfill(status=503, json={"detail": "Saved data is unavailable."})

    pattern = "**/providers/*/" + failed_read
    page.route(pattern, fail)
    group.get_by_role("button", name="Save changes", exact=True).click()
    expect(page.locator("#checklist-status")).to_contain_text("saved, but")
    expect(row(page)).to_contain_text("Scheduled")
    expect(page.locator("#count-finished")).to_have_text("2")
    page.unroute(pattern, fail)
    page.get_by_role("button", name="Refresh data", exact=True).click()
    expect(row(page)).to_contain_text("Completed")
    expect(page.locator("#count-finished")).to_have_text("3")
    expect(
        page.get_by_role("button", name="Retry checklist save", exact=True)
    ).to_be_hidden()
    assert len(read_edits(page, app_server, seeded_provider.id)) == 1


def test_stale_editor_refreshes_without_overwriting_other_manager(
    page, app_server, seeded_provider
):
    group = open_editor(page, app_server)
    group.get_by_role("combobox", name="Checklist status", exact=True).select_option(
        "Completed"
    )
    current = next(
        r
        for r in read_provider(page, app_server, seeded_provider.id)["requirements"]
        if r["name"] == "Drug screening"
    )
    response = page.request.post(
        app_server.url + endpoint(seeded_provider.id, current["id"]),
        headers=MANAGER,
        data=edit_body(current, status="Incomplete"),
    )
    assert response.status == 201
    group.get_by_role("button", name="Save changes", exact=True).click()
    expect(page.locator("#checklist-status")).to_contain_text("checklist changed")
    expect(row(page)).to_contain_text("Incomplete")
    assert len(read_edits(page, app_server, seeded_provider.id)) == 1


def test_deadline_only_save_stales_suggestion_and_updates_monitoring(page, app_server):
    load(page, app_server)
    page.get_by_label("Original update", exact=True).fill("Drug screening completed.")
    page.get_by_role("button", name="Analyze update", exact=True).click()
    expect(history(page).locator("summary")).to_contain_text("1 pending suggestion")
    page.get_by_label("Simulated role", exact=True).select_option("manager")
    row(page).get_by_role("button", name="Edit", exact=True).click()
    group = editor(page)
    group.get_by_label("Deadline", exact=True).fill("2026-11-10")
    save_editor(page, group)
    expect(row(page).get_by_role("cell").nth(4)).to_have_text("Overdue")
    open_history(page)
    card = page.get_by_role("article", name="Drug screening", exact=True)
    expect(card.get_by_role("button", name="Approve", exact=True)).to_be_disabled()
    expect(card).to_contain_text("checklist changed")
    expect(card.get_by_role("button", name="Reject", exact=True)).to_be_enabled()


def test_unfamiliar_current_and_proposed_values_are_safe_dropdown_options(
    page, app_server, seeded_provider
):
    raw = '<img src=x onerror="window.checklistInjected=true">'
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "UPDATE requirements SET status=%s WHERE provider_id=%s AND name='Drug screening'",
            (raw, seeded_provider.id),
        )
    group = open_editor(page, app_server)
    expect(
        group.get_by_role("combobox", name="Checklist status", exact=True)
    ).to_have_value(raw)
    group.get_by_label("Deadline", exact=True).fill("2026-11-20")
    save_editor(page, group)
    expect(row(page).locator(".status-badge")).to_have_text(raw)
    expect(row(page).locator(".status-badge")).to_have_class(
        "status-badge status-unknown"
    )
    page.get_by_label("Original update", exact=True).fill("Drug screening completed.")
    page.get_by_role("button", name="Analyze update", exact=True).click()
    expect(history(page).locator("summary")).to_contain_text("1 pending suggestion")
    with psycopg.connect(configured_test_url()) as conn:
        conn.execute(
            "UPDATE suggestions SET proposed_status=%s WHERE provider_id=%s",
            (raw + " proposed", seeded_provider.id),
        )
    page.get_by_role("button", name="Refresh data", exact=True).click()
    open_history(page)
    reviewed = page.get_by_role("combobox", name="Reviewed status", exact=True)
    expect(reviewed).to_have_value(raw + " proposed")
    expect(reviewed.get_by_role("option").last).to_have_text(raw + " proposed")
    assert page.evaluate("window.checklistInjected") is None
    expect(page.locator("#requirements img, #review-results img")).to_have_count(0)


def test_editor_keyboard_and_header_position_at_desktop_and_phone(
    page, app_server, tmp_path
):
    group = open_editor(page, app_server)
    heading = page.get_by_role(
        "heading", name="1. Select a provider", exact=True
    ).bounding_box()
    add = page.get_by_role("button", name="Add provider", exact=True).bounding_box()
    assert add["x"] > heading["x"] + heading["width"]
    assert abs(add["y"] - heading["y"]) < 20
    page.screenshot(path=tmp_path / "checklist-edit-desktop.png", full_page=True)
    status = group.get_by_role("combobox", name="Checklist status", exact=True)
    status.focus()
    page.keyboard.press("Tab")
    expect(group.get_by_label("Requirement date", exact=True)).to_be_focused()
    deadline = group.get_by_label("Deadline", exact=True)
    for _ in range(6):
        page.keyboard.press("Tab")
        if deadline.evaluate("e => e === document.activeElement"):
            break
        expect(group.get_by_label("Requirement date", exact=True)).to_be_focused()
    expect(deadline).to_be_focused()
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert page.get_by_role("button", name="Add provider", exact=True).is_visible()
    assert (
        row(page)
        .locator(".status-badge")
        .evaluate("e => e.getBoundingClientRect().height < 40")
    )
    page.screenshot(path=tmp_path / "checklist-edit-narrow.png", full_page=True)


@pytest.mark.parametrize("preserved_source", ["saved", "proposed"])
def test_review_saves_verbatim_status_options(
    page, app_server, seeded_provider, preserved_source
):
    saved_status, proposed_status = "  sChEdUlEd  ", "  cOmPlEtEd  "
    if preserved_source == "saved":
        with psycopg.connect(configured_test_url()) as conn:
            conn.execute(
                "UPDATE requirements SET status=%s WHERE provider_id=%s AND name='Drug screening'",
                (saved_status, seeded_provider.id),
            )
    load(page, app_server)
    page.get_by_label("Original update", exact=True).fill("Drug screening completed.")
    page.get_by_role("button", name="Analyze update", exact=True).click()
    expect(history(page).locator("summary")).to_contain_text("1 pending suggestion")
    if preserved_source == "proposed":
        with psycopg.connect(configured_test_url()) as conn:
            conn.execute(
                "UPDATE suggestions SET proposed_status=%s WHERE provider_id=%s",
                (proposed_status, seeded_provider.id),
            )
        page.get_by_role("button", name="Refresh data", exact=True).click()
    page.get_by_label("Simulated role", exact=True).select_option("manager")
    open_history(page)
    card = page.get_by_role("article", name="Drug screening", exact=True)
    reviewed = card.get_by_role("combobox", name="Reviewed status", exact=True)
    if preserved_source == "saved":
        reviewed.select_option(saved_status)
        expected, action = saved_status, "Approve with corrections"
    else:
        expect(reviewed).to_have_value(proposed_status)
        expect(card.get_by_role("button", name="Approve", exact=True)).to_be_enabled()
        expected, action = proposed_status, "Approve"
    with page.expect_request(
        lambda r: r.method == "POST" and r.url.endswith("/review")
    ) as request:
        card.get_by_role("button", name=action, exact=True).click()
    if preserved_source == "saved":
        assert request.value.post_data_json["corrected_status"] == expected
    expect(page.locator("#request-status")).to_contain_text("Manager decision saved")
    current = next(
        r
        for r in read_provider(page, app_server, seeded_provider.id)["requirements"]
        if r["name"] == "Drug screening"
    )
    assert current["status"] == expected
    updates = page.request.get(
        app_server.url + f"/providers/{seeded_provider.id}/updates"
    ).json()
    assert updates[0]["suggestions"][0]["decision"]["applied_status"] == expected


@pytest.mark.parametrize("scenario", ["completed", "failure"])
def test_analysis_preserves_unsaved_manual_editor_including_partial_date(
    page, app_server, scenario
):
    if scenario == "failure":
        app_server.restart("failure")
    group = open_editor(page, app_server)
    group.get_by_role("combobox", name="Checklist status", exact=True).select_option(
        "Incomplete"
    )
    group.get_by_label("Deadline", exact=True).fill("2026-12-01")
    partial = group.get_by_label("Requirement date", exact=True)
    partial.fill("2026-11-12")
    partial.press("Home")
    partial.press("Delete")
    assert partial.evaluate("e => e.validity.badInput")
    page.get_by_label("Original update", exact=True).fill("Drug screening completed.")
    page.get_by_role("button", name="Analyze update", exact=True).click()
    expect(page.get_by_label("Simulated role", exact=True)).to_be_enabled()
    expect(page.locator("#request-status")).not_to_have_text("Analyzing update…")
    expect(group).to_be_visible()
    expect(
        group.get_by_role("combobox", name="Checklist status", exact=True)
    ).to_have_value("Incomplete")
    expect(group.get_by_label("Deadline", exact=True)).to_have_value("2026-12-01")
    assert partial.evaluate("e => e.validity.badInput")
    expect(
        group.get_by_role("button", name="Save changes", exact=True)
    ).to_be_disabled()
    partial.fill("2026-11-12")
    save_editor(page, group)
    expect(row(page)).to_contain_text("Incomplete")
    expect(row(page)).to_contain_text("2026-12-01")
