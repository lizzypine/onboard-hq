"""Inline archive/restore preserves real saved checklists and reconciles failures."""

from uuid import uuid4

import pytest
from playwright.sync_api import expect

from tests.e2e.test_checklist_edits import row, save_editor

MANAGER = {"X-Demo-Role": "manager"}


def current(page, server, identity):
    return page.request.get(server.url + f"/providers/{identity}").json()


def open_manager(page, server, *, archived=False, identity=None):
    page.goto(server.url)
    role = page.get_by_label("Simulated role", exact=True)
    expect(role).to_be_enabled()
    role.select_option("manager")
    if archived:
        page.get_by_role("combobox", name="Provider view", exact=True).select_option(
            "archived"
        )
    if identity:
        picker = page.get_by_label("Provider", exact=True)
        expect(picker).to_be_enabled()
        picker.select_option(str(identity))
    expect(
        page.get_by_role(
            "button",
            name="Restore provider" if archived else "Archive provider",
            exact=True,
        )
    ).to_be_enabled()


def click_action(page, action):
    if action == "archive":
        page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role(
        "button",
        name="Archive provider" if action == "archive" else "Restore provider",
        exact=True,
    ).click()


def assert_loaded(page, identity, archived):
    expect(
        page.get_by_role("combobox", name="Provider view", exact=True)
    ).to_have_value("archived" if archived else "active")
    expect(page.get_by_label("Provider", exact=True)).to_have_value(str(identity))
    expect(page.locator("#provider-lifecycle-status")).to_contain_text(
        "Current checklist and history loaded."
    )
    expect(page.get_by_label("Simulated role", exact=True)).to_be_enabled()


def test_manager_visibility_and_archive_cancel_leave_provider_unchanged(
    page, app_server, seeded_provider
):
    page.goto(app_server.url)
    expect(page.get_by_label("Simulated role", exact=True)).to_be_enabled()
    expect(
        page.get_by_role("button", name="Archive provider", exact=True)
    ).to_have_count(0)
    before = current(page, app_server, seeded_provider.id)
    page.get_by_label("Simulated role", exact=True).select_option("manager")
    messages = []

    def cancel(dialog):
        messages.append(dialog.message)
        dialog.dismiss()

    page.once("dialog", cancel)
    page.get_by_role("button", name="Archive provider", exact=True).click()
    assert (
        before["name"] in messages[0]
        and "preserved" in messages[0]
        and "restore" in messages[0]
    )
    assert current(page, app_server, seeded_provider.id) == before
    page.get_by_label("Simulated role", exact=True).select_option("proposer")
    expect(
        page.get_by_role("button", name="Archive provider", exact=True)
    ).to_have_count(0)


def test_restore_returns_the_same_checklist_progress_and_history_after_restart(
    page, app_server, seeded_provider
):
    kind = page.request.get(app_server.url + "/provider-types").json()[0]
    original = current(page, app_server, seeded_provider.id)
    response = page.request.post(
        app_server.url + "/providers",
        headers=MANAGER,
        data={
            "creation_request_id": str(uuid4()),
            "name": "Dr. Archive Example",
            "provider_type_id": kind["id"],
            "checklist_template_id": kind["checklist_template_id"],
            "template_fingerprint": kind["template_fingerprint"],
            "proposed_start_date": "2027-01-15",
            "additional_requirements": [
                {
                    "name": "Orientation",
                    "status": "Scheduled",
                    "scheduled_date": "2026-12-10",
                    "deadline": "2026-12-15",
                }
            ],
        },
    )
    assert response.status == 201
    identity = response.json()["id"]
    open_manager(page, app_server, identity=identity)
    row(page, "Orientation").get_by_role("button", name="Edit", exact=True).click()
    group = page.get_by_role("group", name="Edit Orientation", exact=True)
    group.get_by_role("combobox", name="Checklist status", exact=True).select_option(
        "Completed"
    )
    save_editor(page, group)
    before = current(page, app_server, identity)
    history = page.request.get(
        app_server.url + f"/providers/{identity}/checklist-edits"
    ).json()
    assert len(history) == 1
    click_action(page, "archive")
    assert_loaded(page, identity, True)
    expect(page.locator("#provider-description")).to_contain_text("Archived")
    expect(row(page, "Orientation")).to_contain_text("Completed")
    expect(row(page, "Orientation")).to_contain_text("2026-12-10")
    expect(page.get_by_role("button", name="Edit", exact=True)).to_have_count(0)
    expect(
        page.get_by_role("button", name="Analyze update", exact=True)
    ).to_be_disabled()
    page.get_by_label("Simulated role", exact=True).select_option("proposer")
    expect(
        page.get_by_role("button", name="Restore provider", exact=True)
    ).to_have_count(0)
    page.get_by_label("Simulated role", exact=True).select_option("manager")
    click_action(page, "restore")
    assert_loaded(page, identity, False)
    assert current(page, app_server, identity) == before
    assert current(page, app_server, seeded_provider.id) == original
    assert (
        page.request.get(
            app_server.url + f"/providers/{identity}/checklist-edits"
        ).json()
        == history
    )
    expect(
        row(page, "Orientation").get_by_role("button", name="Edit", exact=True)
    ).to_be_enabled()
    app_server.restart()
    open_manager(page, app_server, identity=identity)
    expect(row(page, "Orientation")).to_contain_text("Completed")
    assert current(page, app_server, identity) == before


def test_last_provider_can_move_between_empty_active_and_archived_views(
    page, app_server, seeded_provider
):
    open_manager(page, app_server)
    click_action(page, "archive")
    assert_loaded(page, seeded_provider.id, True)
    page.get_by_role("combobox", name="Provider view", exact=True).select_option(
        "active"
    )
    expect(page.locator("#request-status")).to_contain_text("No active providers")
    expect(
        page.get_by_role("combobox", name="Provider view", exact=True)
    ).to_be_enabled()
    expect(
        page.get_by_role("button", name="Archive provider", exact=True)
    ).to_have_count(0)
    page.get_by_role("combobox", name="Provider view", exact=True).select_option(
        "archived"
    )
    click_action(page, "restore")
    assert_loaded(page, seeded_provider.id, False)
    page.get_by_role("combobox", name="Provider view", exact=True).select_option(
        "archived"
    )
    expect(page.locator("#request-status")).to_contain_text("No archived providers")
    expect(
        page.get_by_role("combobox", name="Provider view", exact=True)
    ).to_be_enabled()
    expect(
        page.get_by_role("button", name="Restore provider", exact=True)
    ).to_have_count(0)


@pytest.mark.parametrize("action", ["archive", "restore"])
@pytest.mark.parametrize("committed", [True, False])
def test_unconfirmed_response_reads_current_state_without_replaying_action(
    page, app_server, seeded_provider, action, committed
):
    identity = seeded_provider.id
    if action == "restore":
        assert (
            page.request.post(
                app_server.url + f"/providers/{identity}/archive", headers=MANAGER
            ).status
            == 200
        )
    open_manager(page, app_server, archived=action == "restore")
    posts = []
    path = app_server.url + f"/providers/{identity}/{action}"

    def lose_response(route):
        posts.append(route.request.url)
        if committed:
            assert route.fetch().status == 200
        route.abort("failed")

    page.route(path, lose_response)
    click_action(page, action)
    archived = (action == "archive") if committed else (action == "restore")
    assert_loaded(page, identity, archived)
    assert (current(page, app_server, identity)["archived_at"] is not None) == archived
    assert len(posts) == 1


@pytest.mark.parametrize("failure", ["saved_refresh", "lost_and_unreadable"])
def test_failed_refresh_clears_stale_writes_then_refresh_recovers(
    page, app_server, seeded_provider, failure
):
    identity = seeded_provider.id
    open_manager(page, app_server)
    before = current(page, app_server, identity)
    path = app_server.url + f"/providers/{identity}/archive"
    if failure == "saved_refresh":
        page.route(
            "**/providers?state=archived",
            lambda route: route.fulfill(status=503, json={"detail": "Unavailable"}),
        )
    else:

        def lose(route):
            assert route.fetch().status == 200
            route.abort("failed")

        page.route(path, lose)
        page.route(
            app_server.url + f"/providers/{identity}",
            lambda route: route.fulfill(status=503, json={"detail": "Unavailable"}),
        )
    click_action(page, "archive")
    expect(page.locator("#provider-lifecycle-status")).to_contain_text("Refresh data")
    expect(
        page.get_by_role("button", name="Analyze update", exact=True)
    ).to_be_disabled()
    expect(page.get_by_role("button", name="Edit", exact=True)).to_have_count(0)
    expect(
        page.get_by_role("button", name="Archive provider", exact=True)
    ).to_have_count(0)
    page.unroute_all(behavior="wait")
    page.get_by_role("button", name="Refresh data", exact=True).click()
    expect(
        page.get_by_role("button", name="Restore provider", exact=True)
    ).to_be_enabled()
    saved = current(page, app_server, identity)
    assert saved["archived_at"] is not None
    assert saved["requirements"] == before["requirements"]


def test_double_click_sends_only_one_archive_request(page, app_server, seeded_provider):
    open_manager(page, app_server)
    posts = []
    page.on(
        "request",
        lambda request: posts.append(request.url) if request.method == "POST" else None,
    )
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Archive provider", exact=True).evaluate(
        "button => { button.click(); button.click(); }"
    )
    assert_loaded(page, seeded_provider.id, True)
    assert len(posts) == 1
