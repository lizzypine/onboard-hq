"""Final-review regressions keep archived controls and recovery bound to their owner."""

from uuid import uuid4

import pytest
from playwright.sync_api import expect

from tests.e2e.test_checklist_edits import editor, row
from tests.e2e.test_provider_lifecycle import (
    MANAGER,
    assert_loaded,
    click_action,
    current,
    open_manager,
)
from tests.e2e.test_review_workflow import drug_card, reviewed_card


def test_pending_review_stays_disabled_when_archived_and_works_after_restore(
    page, app_server, seeded_provider
):
    identity = seeded_provider.id
    result = page.request.post(
        app_server.url + "/updates/analyze",
        data={
            "request_id": str(uuid4()),
            "provider_id": identity,
            "update_text": "Drug screening completed.",
        },
    )
    assert result.status == 200
    open_manager(page, app_server)
    click_action(page, "archive")
    assert_loaded(page, identity, True)
    card = drug_card(page)
    expect(card.get_by_label("Reviewed status", exact=True)).to_be_disabled()
    expect(card.get_by_label("Reviewed date", exact=True)).to_be_disabled()
    expect(card.get_by_role("button", name="Approve", exact=True)).to_be_disabled()
    expect(card.get_by_role("button", name="Reject", exact=True)).to_be_disabled()
    click_action(page, "restore")
    assert_loaded(page, identity, False)
    expect(card.get_by_label("Reviewed status", exact=True)).to_be_enabled()
    card.get_by_role("button", name="Approve", exact=True).click()
    expect(reviewed_card(page)).to_contain_text("Approved")
    expect(row(page)).to_contain_text("Completed")


def test_uncommitted_unreadable_restore_refreshes_its_owner_and_clears_unsent_text(
    page, app_server, seeded_provider
):
    identity = seeded_provider.id
    before = current(page, app_server, identity)
    kind = page.request.get(app_server.url + "/provider-types").json()[0]
    response = page.request.post(
        app_server.url + "/providers",
        headers=MANAGER,
        data={
            "creation_request_id": str(uuid4()),
            "name": "Dr. Other Active Example",
            "provider_type_id": kind["id"],
            "checklist_template_id": kind["checklist_template_id"],
            "template_fingerprint": kind["template_fingerprint"],
        },
    )
    assert response.status == 201
    other = response.json()
    assert (
        page.request.post(
            app_server.url + f"/providers/{identity}/archive", headers=MANAGER
        ).status
        == 200
    )
    open_manager(page, app_server, archived=True)
    page.get_by_label("Original update", exact=True).fill(
        "Drug screening completed for the archived provider."
    )
    page.route(
        app_server.url + f"/providers/{identity}/restore",
        lambda route: route.abort("failed"),
    )
    page.route(
        app_server.url + f"/providers/{identity}",
        lambda route: route.fulfill(status=503, json={"detail": "Unavailable"}),
    )
    click_action(page, "restore")
    expect(page.locator("#provider-lifecycle-status")).to_contain_text("Refresh data")
    page.unroute_all(behavior="wait")
    page.get_by_role("button", name="Refresh data", exact=True).click()
    expect(page.get_by_label("Provider", exact=True)).to_have_value(str(identity))
    expect(
        page.get_by_role("combobox", name="Provider view", exact=True)
    ).to_have_value("archived")
    expect(page.get_by_label("Original update", exact=True)).to_have_value("")
    expect(
        page.get_by_role("button", name="Analyze update", exact=True)
    ).to_be_disabled()
    assert current(page, app_server, other["id"]) == other
    assert current(page, app_server, identity)["requirements"] == before["requirements"]
    click_action(page, "restore")
    assert_loaded(page, identity, False)
    assert current(page, app_server, identity) == before


@pytest.mark.parametrize("committed", [False, True])
def test_frozen_manual_save_survives_archive_reload_and_restore(
    page, app_server, seeded_provider, committed
):
    identity = seeded_provider.id
    open_manager(page, app_server)
    row(page).get_by_role("button", name="Edit", exact=True).click()
    group = editor(page)
    group.get_by_role("combobox", name="Checklist status", exact=True).select_option(
        "Completed"
    )
    bodies = []

    def lose(route):
        bodies.append(route.request.post_data_json)
        if committed:
            assert route.fetch().status == 201
        route.abort("failed")

    page.route("**/requirements/*/edits", lose)
    group.get_by_role("button", name="Save changes", exact=True).click()
    expect(page.locator("#checklist-status")).to_contain_text("could not be confirmed")
    page.unroute("**/requirements/*/edits", lose)
    frozen = page.evaluate(
        'sessionStorage.getItem("onboard-hq:pending-checklist-edit:v2")'
    )
    assert frozen is not None
    click_action(page, "archive")
    assert_loaded(page, identity, True)
    page.reload()
    expect(page.get_by_label("Simulated role", exact=True)).to_be_enabled()
    page.get_by_role("combobox", name="Provider view", exact=True).select_option(
        "archived"
    )
    expect(page.get_by_label("Provider", exact=True)).to_be_enabled()
    page.get_by_label("Simulated role", exact=True).select_option("manager")
    expect(
        page.get_by_role("button", name="Retry checklist save", exact=True)
    ).to_be_hidden()
    posts = []
    page.on(
        "request",
        lambda request: posts.append(request.url) if request.method == "POST" else None,
    )
    page.locator("#retry-checklist").evaluate("button => button.click()")
    assert (
        page.evaluate('sessionStorage.getItem("onboard-hq:pending-checklist-edit:v2")')
        == frozen
    )
    assert posts == []
    click_action(page, "restore")
    assert_loaded(page, identity, False)
    with page.expect_request(
        lambda request: request.method == "POST" and request.url.endswith("/edits")
    ) as retry:
        page.get_by_role("button", name="Retry checklist save", exact=True).click()
    assert retry.value.post_data_json == bodies[0]
    expect(page.locator("#checklist-status")).to_contain_text("up to date")
    expect(row(page)).to_contain_text("Completed")
    assert (
        page.evaluate('sessionStorage.getItem("onboard-hq:pending-checklist-edit:v2")')
        is None
    )
    assert (
        len(
            page.request.get(
                app_server.url + f"/providers/{identity}/checklist-edits"
            ).json()
        )
        == 1
    )
