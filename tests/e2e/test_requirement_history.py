"""Item history uses retained evidence without replacing checklist review drafts."""

from uuid import uuid4

import psycopg
import pytest
from playwright.sync_api import expect

from app.database import create_pool
from app.models import SubmitUpdateRequest
from app.repository.updates import UpdateRepository
from tests.e2e.test_checklist_edits import (
    MANAGER,
    editor,
    load,
    open_editor,
    row,
    save_editor,
    second_provider,
)
from tests.e2e.test_inline_suggestions import analyze, pending
from tests.fixtures.current_database import run_async


def submit(page, server, provider_id, message="Drug screening completed."):
    response = page.request.post(
        server.url + "/updates/analyze",
        data={
            "request_id": str(uuid4()),
            "provider_id": provider_id,
            "update_text": message,
        },
    )
    assert response.status == 200, response.text()
    return response.json()


def decide(page, server, suggestion, **decision):
    response = page.request.post(
        server.url + f"/suggestions/{suggestion['id']}/review",
        data=decision,
        headers=MANAGER,
    )
    assert response.status == 200, response.text()


def history_dialog(page):
    return page.get_by_role("dialog", name="Update history", exact=True)


def open_item_history(page, name="Drug screening"):
    row(page, name).get_by_role("button", name=name, exact=True).click()
    dialog = history_dialog(page)
    expect(dialog).to_be_visible()
    return dialog


def test_item_history_shows_saved_before_after_actor_and_empty_filter(
    page, app_server, seeded_provider
):
    group = open_editor(page, app_server, "Hawaii dental license")
    group.get_by_role("combobox", name="Checklist status").select_option("Pending")
    group.get_by_label("Expected completion date", exact=True).fill("2026-12-01")
    group.get_by_label("Deadline", exact=True).fill("2026-12-02")
    save_editor(page, group)
    writes = []
    page.on(
        "request", lambda req: writes.append(req.url) if req.method == "POST" else None
    )
    dialog = open_item_history(page, "Hawaii dental license")
    expect(dialog).to_contain_text("Dr. Kekoa Ejemplo")
    card = dialog.get_by_role(
        "article", name="Manager checklist edit: Hawaii dental license"
    )
    expect(card).to_contain_text("Received → Pending")
    expect(card).to_contain_text("Not set → 2026-12-01")
    expect(card).to_contain_text("Not set → 2026-12-02")
    expect(card).to_contain_text("Saved by simulated Manager")
    expect(dialog.get_by_role("region", name="Current saved values")).to_contain_text(
        "Pending"
    )
    drug = next(
        item for item in seeded_provider.requirements if item.name == "Drug screening"
    )
    dialog.get_by_label("Requirement", exact=True).select_option(str(drug.id))
    expect(dialog).to_contain_text("No saved activity for this requirement.")
    expect(dialog.get_by_role("article")).to_have_count(0)
    dialog.get_by_label("Requirement", exact=True).select_option("")
    expect(card).to_be_visible()
    dialog.get_by_role("button", name="Close history", exact=True).click()
    expect(
        row(page, "Hawaii dental license").get_by_role(
            "button", name="Hawaii dental license", exact=True
        )
    ).to_be_focused()
    assert writes == []
    expect(page.get_by_role("heading", name="4. Review history")).to_have_count(0)


def test_multi_item_review_history_filters_exactly_and_retains_rejected_evidence(
    page, app_server, seeded_provider
):
    app_server.restart("multiple")
    update = submit(
        page,
        app_server,
        seeded_provider.id,
        "Drug screening completed. Credentialing returned for missing info.",
    )
    drug, insurance = update["suggestions"]
    decide(
        page,
        app_server,
        drug,
        action="correct",
        corrected_status="Incomplete",
        date_action="clear",
    )
    decide(page, app_server, insurance, action="reject")
    load(page, app_server)
    dialog = open_item_history(page)
    card = dialog.get_by_role("article", name="Review: Drug screening", exact=True)
    expect(card).to_contain_text("Approved with corrections")
    expect(card).to_contain_text("Scheduled → Incomplete")
    expect(card).to_contain_text("Reviewed by simulated Manager")
    expect(card).to_contain_text(update["update_text"])
    expect(
        dialog.get_by_role("article", name="Review: Insurance credentialing")
    ).to_have_count(0)
    dialog.get_by_label("Requirement", exact=True).select_option(
        str(insurance["requirement_id"])
    )
    rejected = dialog.get_by_role("article", name="Review: Insurance credentialing")
    expect(rejected).to_contain_text("Rejected")
    expect(rejected).to_contain_text("No checklist change was applied.")
    expect(rejected).to_contain_text("Credentialing returned for missing info.")
    expect(dialog.get_by_role("article", name="Review: Drug screening")).to_have_count(
        0
    )
    page.keyboard.press("Escape")
    expect(row(page, "Insurance credentialing").locator(".status-badge")).to_have_text(
        "Pending"
    )


def test_late_review_sorts_before_newer_submission_and_manual_edit(
    page, app_server, seeded_provider
):
    older = submit(
        page,
        app_server,
        seeded_provider.id,
        "Older synthetic update: Drug screening completed.",
    )
    group = open_editor(page, app_server, "Hawaii dental license")
    group.get_by_label("Deadline", exact=True).fill("2026-12-02")
    save_editor(page, group)
    submit(
        page,
        app_server,
        seeded_provider.id,
        "Newer synthetic update: Drug screening completed.",
    )
    decide(page, app_server, older["suggestions"][0], action="reject")
    page.reload()
    page.get_by_role("button", name="All update history", exact=True).click()
    entries = history_dialog(page).get_by_role("article")
    expect(entries).to_have_count(3)
    expect(entries.nth(0)).to_contain_text("Older synthetic update")
    expect(entries.nth(0)).to_contain_text("Rejected")
    expect(entries.nth(1)).to_contain_text("Newer synthetic update")
    expect(entries.nth(1)).to_contain_text("Awaiting manager review")
    expect(entries.nth(2)).to_contain_text("Manager checklist edit")


@pytest.mark.parametrize("scenario", ["completed", "inferred"])
def test_open_close_history_preserves_review_edit_and_update_drafts_and_keyboard(
    page, app_server, tmp_path, scenario
):
    app_server.restart(scenario)
    load(page, app_server)
    analyze(
        page,
        "Drug screening on the 18th."
        if scenario == "inferred"
        else "Drug screening completed.",
    )
    page.get_by_label("Simulated role").select_option("manager")
    pending(page).get_by_label("Reviewed status", exact=True).select_option(
        "Incomplete"
    )
    if scenario == "inferred":
        pending(page).get_by_label("Confirm inferred date").check()
    row(page).get_by_role("button", name="Edit", exact=True).click()
    editor(page).get_by_label("Deadline", exact=True).fill("2026-12-05")
    page.get_by_label("Original update", exact=True).fill("Unsubmitted synthetic draft")
    opener = row(page).get_by_role("button", name="Drug screening", exact=True)
    opener.focus()
    page.keyboard.press("Enter")
    dialog = history_dialog(page)
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text("Awaiting manager review")
    expect(dialog.get_by_role("button", name="Approve", exact=True)).to_have_count(0)
    for _ in range(6):
        page.keyboard.press("Tab")
        assert dialog.evaluate("node => node.contains(document.activeElement)")
    dialog.screenshot(path=tmp_path / "requirement-history-desktop.png")
    page.set_viewport_size({"width": 390, "height": 680})
    dialog.screenshot(path=tmp_path / "requirement-history-mobile.png")
    assert dialog.evaluate("node => node.scrollWidth === node.clientWidth")
    assert dialog.bounding_box()["width"] < 390
    dialog.get_by_role("button", name="Refresh history", exact=True).click()
    expect(dialog).to_contain_text("History is up to date.")
    page.keyboard.press("Escape")
    expect(opener).to_be_focused()
    expect(editor(page).get_by_label("Deadline", exact=True)).to_have_value(
        "2026-12-05"
    )
    expect(pending(page).get_by_label("Reviewed status", exact=True)).to_have_value(
        "Incomplete"
    )
    expect(page.get_by_label("Original update", exact=True)).to_have_value(
        "Unsubmitted synthetic draft"
    )
    if scenario == "inferred":
        expect(pending(page).get_by_label("Confirm inferred date")).to_be_checked()


@pytest.mark.parametrize("scenario", ["empty", "failure", "processing"])
def test_unassigned_updates_remain_in_all_history_without_guessed_item(
    page, app_server, seeded_provider, scenario
):
    message = "Unassigned synthetic <script>window.injected=true</script> update"
    if scenario == "processing":

        async def claim():
            async with create_pool(app_server.database_url) as pool:
                await UpdateRepository(pool).claim(
                    SubmitUpdateRequest(
                        provider_id=seeded_provider.id,
                        request_id=uuid4(),
                        update_text=message,
                    )
                )

        run_async(claim)
    else:
        app_server.restart(scenario)
        response = page.request.post(
            app_server.url + "/updates/analyze",
            data={
                "request_id": str(uuid4()),
                "provider_id": seeded_provider.id,
                "update_text": message,
            },
        )
        assert response.status == (502 if scenario == "failure" else 200)
    load(page, app_server)
    dialog = open_item_history(page)
    expect(dialog).to_contain_text("No saved activity for this requirement.")
    dialog.get_by_label("Requirement", exact=True).select_option("")
    expect(dialog).to_contain_text(message)
    expect(dialog).to_contain_text(
        {
            "empty": "Insufficient information",
            "failure": "Unable to analyze update",
            "processing": "Analysis unfinished",
        }[scenario]
    )
    expect(dialog.locator("script")).to_have_count(0)
    assert page.evaluate("window.injected") is None


def test_history_refresh_retains_filter_and_previous_evidence_when_read_fails(
    page, app_server, seeded_provider
):
    submit(
        page,
        app_server,
        seeded_provider.id,
        "First synthetic update: Drug screening completed.",
    )
    load(page, app_server)
    dialog = open_item_history(page)
    chosen = dialog.get_by_label("Requirement", exact=True).input_value()
    submit(
        page,
        app_server,
        seeded_provider.id,
        "Second synthetic update: Drug screening completed.",
    )
    page.route("**/providers/*/updates", lambda route: route.abort("failed"))
    dialog.get_by_role("button", name="Refresh history", exact=True).click()
    expect(dialog).to_contain_text("History could not refresh")
    expect(dialog).to_contain_text("First synthetic update")
    expect(dialog.get_by_label("Requirement", exact=True)).to_have_value(chosen)
    page.unroute("**/providers/*/updates")
    dialog.get_by_role("button", name="Refresh history", exact=True).click()
    expect(dialog).to_contain_text("Second synthetic update")
    expect(dialog.get_by_label("Requirement", exact=True)).to_have_value(chosen)
    expect(dialog.get_by_role("article")).to_have_count(2)


def test_history_closes_on_provider_change_and_archived_history_is_read_only(
    page, app_server, seeded_provider
):
    saved = submit(page, app_server, seeded_provider.id)
    decide(page, app_server, saved["suggestions"][0], action="approve")
    other = second_provider(page, app_server)
    load(page, app_server)
    page.get_by_label("Provider", exact=True).select_option(str(seeded_provider.id))
    dialog = open_item_history(page)
    expect(dialog).to_contain_text("Approved")
    page.get_by_label("Provider", exact=True).evaluate(
        "(node, id) => { node.value = id; node.dispatchEvent(new Event('change')); }",
        str(other["id"]),
    )
    expect(dialog).to_be_hidden()
    expect(page.get_by_label("Simulated role")).to_be_enabled()
    dialog = open_item_history(page)
    expect(dialog).to_contain_text("No saved activity for this requirement.")
    expect(dialog).not_to_contain_text("Approved")
    page.keyboard.press("Escape")
    with psycopg.connect(app_server.database_url) as connection:
        connection.execute(
            "UPDATE providers SET archived_at=now() WHERE id=%s", (seeded_provider.id,)
        )
    page.get_by_label("Provider view").select_option("archived")
    dialog = open_item_history(page)
    expect(dialog).to_contain_text("Approved")
    expect(dialog.get_by_role("button", name="Approve", exact=True)).to_have_count(0)


def direct_edit(page, server, provider_id, name="Drug screening", **changes):
    provider = page.request.get(server.url + f"/providers/{provider_id}").json()
    requirement = next(
        item for item in provider["requirements"] if item["name"] == name
    )
    response = page.request.post(
        server.url + f"/providers/{provider_id}/requirements/{requirement['id']}/edits",
        headers=MANAGER,
        data={
            "operation_id": str(uuid4()),
            "expected_version": requirement["version"],
            "status": requirement["status"],
            "scheduled_date": requirement["scheduled_date"],
            "deadline": requirement["deadline"],
            **changes,
        },
    )
    assert response.status == 201, response.text()
    return response.json()


def test_rejection_keeps_decision_time_values_after_a_later_edit(
    page, app_server, seeded_provider
):
    update = submit(page, app_server, seeded_provider.id)
    decide(page, app_server, update["suggestions"][0], action="reject")
    direct_edit(
        page,
        app_server,
        seeded_provider.id,
        status="Incomplete",
        scheduled_date="2026-12-04",
        deadline="2026-12-05",
    )
    load(page, app_server)
    dialog = open_item_history(page)
    expect(dialog.get_by_role("region", name="Current saved values")).to_contain_text(
        "Incomplete"
    )
    rejected = dialog.get_by_role("article", name="Review: Drug screening")
    expect(rejected).to_contain_text("No checklist change was applied.")
    expect(rejected).to_contain_text("Status: Scheduled → Scheduled")
    expect(rejected).to_contain_text("Expected completion date: Not set → Not set")


@pytest.mark.parametrize("move_focus", [False, True])
def test_closing_during_refresh_restores_focus_without_stealing_it(
    page, app_server, move_focus
):
    load(page, app_server)
    dialog = open_item_history(page)
    held = []
    page.route("**/providers/*/updates", lambda route: held.append(route))
    with page.expect_request("**/providers/*/updates"):
        dialog.get_by_role("button", name="Refresh history", exact=True).click()
    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden()
    if move_focus:
        page.get_by_label("Original update", exact=True).focus()
    with page.expect_response("**/providers/*/updates"):
        held[0].continue_()
    opener = row(page).get_by_role("button", name="Drug screening", exact=True)
    expect(opener).to_be_enabled()
    expect(
        page.get_by_label("Original update", exact=True) if move_focus else opener
    ).to_be_focused()


def test_activity_order_keeps_saved_submillisecond_precision(
    page, app_server, seeded_provider
):
    update = submit(page, app_server, seeded_provider.id)
    decide(page, app_server, update["suggestions"][0], action="reject")
    update = page.request.get(app_server.url + f"/updates/{update['id']}").json()
    edit = direct_edit(page, app_server, seeded_provider.id, deadline="2026-12-05")
    update["suggestions"][0]["decision"]["reviewed_at"] = (
        "2026-11-25T10:00:00.123900+00:00"
    )
    edit["created_at"] = "2026-11-25T10:00:00.123100+00:00"
    load(page, app_server)
    order = page.evaluate(
        """async ({id, update, edit}) => {
        const {historyEvents} = await import('/static/history-events.js');
        return historyEvents(id, [update], [edit]).map(entry => entry.kind);
    }""",
        {"id": seeded_provider.id, "update": update, "edit": edit},
    )
    assert order == ["suggestion", "edit"]
