"""Browser review and publishing of controlled source versions."""

from uuid import uuid4

import psycopg
import pytest
from playwright.sync_api import expect

from tests.e2e.knowledge_data import (
    ISSUE,
    MANAGER,
    QUOTE,
    create_source,
    import_official,
)


def manager_section(page, server):
    page.goto(server.url)
    section = page.get_by_role("region", name="Manage licensing guidance")
    expect(section).to_be_hidden()
    page.get_by_label("Simulated role").select_option("manager")
    assert section.count() == 1, "Manager mode must expose the guidance catalog."
    expect(section).to_be_visible()
    return section


def open_editor(
    page, section, *, title="Internal licensing guide", action="Review draft"
):
    trigger = section.get_by_role("article", name=title).get_by_role(
        "button", name=action
    )
    trigger.click()
    dialog = page.get_by_role("dialog", name="Review licensing source")
    expect(dialog).to_be_visible()
    return dialog, trigger


def test_manager_reviews_edits_and_withdraws_internal_source(page, app_server):
    version = create_source(page, app_server, review_issues=[ISSUE])
    section = manager_section(page, app_server)
    expect(section.get_by_text("Available to Ask AI")).to_have_count(0)
    dialog, trigger = open_editor(page, section)
    text = dialog.get_by_label("Internal instructions")
    expect(text).to_be_editable()
    expect(dialog.get_by_text(ISSUE)).to_be_visible()
    expect(dialog.get_by_label("Scope 1 provider type")).to_have_value("Dentist")
    expect(dialog.get_by_label("Scope 1 topic")).to_have_value("renewal")
    publish = dialog.get_by_role("button", name="Publish reviewed version")
    expect(publish).to_be_disabled()
    text.fill("## Revised synthetic guide\n\n" + QUOTE)
    dialog.get_by_text("Preview instructions", exact=True).click()
    expect(
        dialog.get_by_role("heading", name="Revised synthetic guide")
    ).to_be_visible()
    expect(dialog.get_by_text(QUOTE, exact=True)).to_be_visible()
    assert dialog.locator("img").count() == 0
    dialog.get_by_label("Resolve: " + ISSUE).check()
    dialog.get_by_label("Stated source revision").fill("Synthetic revision")
    dialog.get_by_role("button", name="Save draft").click()
    expect(dialog.get_by_text("Draft saved.", exact=True)).to_be_visible()
    expect(publish).to_be_disabled()
    dialog.get_by_label(
        "I reviewed the source, applicability and unresolved issues."
    ).check()
    publish.click()
    expect(dialog.get_by_text("Version published.", exact=True)).to_be_visible()
    page.keyboard.press("Escape")
    expect(section.get_by_text("Published", exact=True)).to_be_visible()
    expect(trigger).to_have_count(0)
    dialog, _ = open_editor(page, section, action="View published version")
    dialog.get_by_role("button", name="Withdraw version").click()
    dialog.get_by_role("button", name="Confirm withdrawal").click()
    expect(dialog.get_by_text("Version withdrawn.", exact=True)).to_be_visible()
    expect(section.get_by_text("Withdrawn", exact=True)).to_be_visible()
    retained = page.request.get(
        app_server.url + f"/knowledge/versions/{version}"
    ).json()
    assert retained["text"] == "## Revised synthetic guide\n\n" + QUOTE
    assert retained["status"] == "withdrawn"
    assert retained["stated_revision"] == "Synthetic revision"


def test_official_review_is_read_only_and_surfaces_stale_edits(page, app_server):
    version = import_official(app_server)
    response = page.request.get(
        app_server.url + f"/knowledge/versions/{version}", headers=MANAGER
    )
    official = response.json()
    section = manager_section(page, app_server)
    dialog, trigger = open_editor(page, section, title=official["document"]["title"])
    extracted = dialog.get_by_label("Extracted official text")
    expect(extracted).not_to_be_editable()
    expect(extracted).to_have_value("Synthetic official guidance.")
    expect(dialog.get_by_role("link", name="Official source")).to_have_attribute(
        "href", official["document"]["original_url"]
    )
    dialog.get_by_label("Stated source revision").fill("Synthetic official revision")
    with page.expect_request(
        lambda request: (
            request.method == "PUT"
            and request.url.endswith(f"/knowledge/versions/{version}")
        )
    ) as metadata_edit:
        dialog.get_by_role("button", name="Save draft").click()
    assert metadata_edit.value.post_data_json["text"] == official["text"]
    expect(dialog.get_by_text("Draft saved.", exact=True)).to_be_visible()
    page.keyboard.press("Escape")
    expect(trigger).to_be_focused()
    dialog, _ = open_editor(page, section, title=official["document"]["title"])
    expect(dialog.get_by_label("Stated source revision")).to_have_value(
        "Synthetic official revision"
    )
    external_edit = page.request.put(
        app_server.url + f"/knowledge/versions/{version}",
        headers=MANAGER,
        data={
            "operation_id": str(uuid4()),
            "expected_revision": 2,
            "text": official["text"],
            "stated_revision": "Concurrent revision",
            "scopes": official["scopes"],
        },
    )
    assert external_edit.ok, external_edit.text()
    dialog.get_by_label("Stated source revision").fill("Stale draft")
    dialog.get_by_role("button", name="Save draft").click()
    expect(
        dialog.get_by_text("The source version changed. Load its saved state.")
    ).to_be_visible()
    expect(dialog.get_by_label("Stated source revision")).to_have_value("Stale draft")
    dialog.get_by_role("button", name="Reload saved version").click()
    expect(dialog.get_by_label("Stated source revision")).to_have_value(
        "Concurrent revision"
    )


def test_metadata_edit_preserves_internal_source_original_and_locators(
    page, app_server
):
    original_text = "# Synthetic section\r\n\r\nThis is line one.\rLine two.\r\n"
    version = create_source(page, app_server, text=original_text)
    path = app_server.url + f"/knowledge/versions/{version}"
    before = page.request.get(path, headers=MANAGER).json()
    assert before["text"] == original_text
    section = manager_section(page, app_server)
    dialog, _ = open_editor(page, section)
    expect(dialog.get_by_label("Internal instructions")).to_have_value(
        original_text.replace("\r\n", "\n").replace("\r", "\n")
    )
    dialog.get_by_label("Stated source revision").fill("Metadata revision")
    dialog.get_by_role("button", name="Save draft").click()
    expect(dialog.get_by_text("Draft saved.", exact=True)).to_be_visible()
    after = page.request.get(path, headers=MANAGER).json()
    assert after["stated_revision"] == "Metadata revision"
    assert after["text"] == original_text
    assert after["checksum"] == before["checksum"]
    assert after["chunks"] == before["chunks"]
    assert (
        page.request.get(path + "/original", headers=MANAGER).body()
        == original_text.encode()
    )


@pytest.mark.parametrize("reopen", ["same", "reload", "legacy", "different"])
def test_create_receipt_recovers_matching_reopened_editor(page, app_server, reopen):
    reload = reopen in {"reload", "legacy"}
    other_title = "Synthetic alternate internal guide"
    if reopen == "different":
        with psycopg.connect(app_server.database_url) as connection:
            connection.execute(
                """INSERT INTO knowledge_documents(source_key,title,source_kind,publisher)
                VALUES ('synthetic-alternate-guide',%s,'internal','Synthetic team')
                ON CONFLICT(source_key) DO NOTHING""",
                (other_title,),
            )
    section = manager_section(page, app_server)
    held = []
    path = "**/knowledge/documents/*/drafts"
    storage_key = "onboard-hq:pending-source-operation:v1"
    source = "Synthetic draft recovered in its original editor."

    def hold(route):
        response = route.fetch()
        assert response.status == 201
        held.append((route, response))
        if reload:
            route.abort()

    page.route(path, hold)
    dialog, _ = open_editor(page, section, action="Create internal draft")
    dialog.get_by_label("Internal instructions").fill(source)
    with page.expect_request(path) as created:
        dialog.get_by_role("button", name="Create draft", exact=True).click()
    operation_id = created.value.post_data_json["operation_id"]
    document_id = int(created.value.url.split("/")[-2])
    assert page.evaluate(
        "key => JSON.parse(sessionStorage.getItem(key))", storage_key
    ) == {"id": operation_id, "action": "create", "documentId": document_id}
    if reload:
        expect(
            dialog.get_by_text(
                "The source operation could not be confirmed.", exact=False
            )
        ).to_be_visible()
    if reopen == "legacy":
        page.evaluate(
            "([key, id]) => sessionStorage.setItem(key, JSON.stringify({id, action: 'create'}))",
            [storage_key, operation_id],
        )
    if reload:
        recovery = []
        page.route("**/knowledge/operations/*", lambda route: recovery.append(route))
        with page.expect_request("**/knowledge/operations/*") as receipt:
            section = manager_section(page, app_server)
        assert receipt.value.url.endswith(operation_id)
    else:
        page.keyboard.press("Escape")
    title = other_title if reopen == "different" else "Internal licensing guide"
    dialog, _ = open_editor(page, section, title=title, action="Create internal draft")
    if reopen == "different":
        expect(dialog.get_by_label("Internal instructions")).to_be_disabled()
    if reload:
        recovery[0].continue_()
    else:
        held[0][0].fulfill(response=held[0][1])
    if reopen == "different":
        expect(dialog.get_by_label("Internal instructions")).to_be_editable()
        expect(dialog.get_by_label("Internal instructions")).to_have_value("")
        expect(
            dialog.get_by_role("button", name="Create draft", exact=True)
        ).to_be_visible()
        expect(
            section.get_by_role("article", name="Internal licensing guide").get_by_role(
                "button", name="Review draft"
            )
        ).to_have_count(1)
    else:
        expect(dialog.get_by_label("Internal instructions")).to_have_value(source)
        expect(
            dialog.get_by_role("button", name="Save draft", exact=True)
        ).to_be_visible()
    expect(dialog.get_by_role("button", name="Check source operation")).to_be_hidden()
    assert page.evaluate("key => sessionStorage.getItem(key)", storage_key) is None
    assert len(held) == 1


def test_lost_create_keeps_uuid_until_catalog_and_matching_editor_refresh(
    page, app_server
):
    section = manager_section(page, app_server)
    dialog, _ = open_editor(page, section, action="Create internal draft")
    bodies = []
    versions = []
    storage_key = "onboard-hq:pending-source-operation:v1"
    source = "Synthetic instructions with a recoverable create receipt."

    def drop(route):
        bodies.append(route.request.post_data_json)
        saved = route.fetch()
        assert saved.status == 201
        versions.append(saved.json()["version_id"])
        route.abort()

    def unavailable(route):
        route.fulfill(status=503, json={"detail": "Unavailable."})

    page.route("**/knowledge/documents/*/drafts", drop)
    dialog.get_by_label("Internal instructions").fill(source)
    dialog.get_by_role("button", name="Create draft", exact=True).click()
    expect(
        dialog.get_by_text("The source operation could not be confirmed.", exact=False)
    ).to_be_visible()
    page.keyboard.press("Escape")
    catalog_path = "**/knowledge/documents"
    editor_path = f"**/knowledge/versions/{versions[0]}"
    page.route(catalog_path, unavailable)
    page.route(editor_path, unavailable)
    dialog, _ = open_editor(page, section, action="Create internal draft")
    expect(
        section.get_by_text("The source catalog could not refresh.", exact=False)
    ).to_have_count(1)
    assert (
        page.evaluate("key => JSON.parse(sessionStorage.getItem(key)).id", storage_key)
        == bodies[0]["operation_id"]
    )
    page.unroute(catalog_path, unavailable)
    check = dialog.get_by_role("button", name="Check source operation")
    check.click()
    expect(
        dialog.get_by_text("The saved version could not refresh.", exact=False)
    ).to_be_visible()
    assert (
        page.evaluate("key => JSON.parse(sessionStorage.getItem(key)).id", storage_key)
        == bodies[0]["operation_id"]
    )
    page.unroute(editor_path, unavailable)
    check.click()
    expect(dialog.get_by_label("Internal instructions")).to_have_value(source)
    expect(check).to_be_hidden()
    assert page.evaluate("key => sessionStorage.getItem(key)", storage_key) is None
    assert len(bodies) == 1


def test_lost_publish_response_recovers_saved_receipt_without_replay(page, app_server):
    version = create_source(page, app_server)
    section = manager_section(page, app_server)
    dialog, _ = open_editor(page, section)
    publication_path = f"**/knowledge/versions/{version}/publish"
    bodies = []

    def drop(route):
        bodies.append(route.request.post_data_json)
        assert route.fetch().status == 200
        route.abort()

    page.route(publication_path, drop)
    dialog.get_by_label(
        "I reviewed the source, applicability and unresolved issues."
    ).check()
    dialog.get_by_role("button", name="Publish reviewed version").click()
    expect(
        dialog.get_by_text("Publication could not be confirmed.", exact=False)
    ).to_be_visible()
    page.keyboard.press("Escape")
    with page.expect_request("**/knowledge/operations/*") as receipt:
        page.get_by_role("button", name="Check source operation").click()
    assert receipt.value.headers["x-demo-role"] == "manager"
    assert receipt.value.url.endswith(bodies[0]["operation_id"])
    expect(section.get_by_text("Published", exact=True)).to_be_visible()
    assert len(bodies) == 1


def test_source_receipt_survives_failed_catalog_refresh(page, app_server):
    version = create_source(page, app_server)
    section = manager_section(page, app_server)
    dialog, _ = open_editor(page, section)

    def unavailable(route):
        route.fulfill(status=503, json={"detail": "Unavailable."})

    page.route("**/knowledge/documents", unavailable)
    dialog.get_by_label(
        "I reviewed the source, applicability and unresolved issues."
    ).check()
    with page.expect_request(f"**/knowledge/versions/{version}/publish") as published:
        dialog.get_by_role("button", name="Publish reviewed version").click()
    expect(
        section.get_by_text("The source catalog could not refresh.", exact=False)
    ).to_have_count(1)
    page.keyboard.press("Escape")
    page.unroute("**/knowledge/documents", unavailable)
    with page.expect_request("**/knowledge/operations/*") as receipt:
        section.get_by_role("button", name="Check source operation").click(timeout=3000)
    assert receipt.value.url.endswith(published.value.post_data_json["operation_id"])
    expect(section.get_by_text("Published", exact=True)).to_be_visible()
    expect(section.get_by_role("button", name="Check source operation")).to_be_hidden()


def test_source_indexing_failure_keeps_draft_recoverable(page, app_server):
    version = create_source(
        page, app_server, text="Synthetic guide with an unavailable index."
    )
    section = manager_section(page, app_server)
    dialog, _ = open_editor(page, section)
    dialog.get_by_label(
        "I reviewed the source, applicability and unresolved issues."
    ).check()
    with page.expect_response(f"**/knowledge/versions/{version}/publish") as failed:
        dialog.get_by_role("button", name="Publish reviewed version").click()
    assert failed.value.status == 503
    expect(
        dialog.get_by_text("Publication could not be confirmed.", exact=False)
    ).to_be_visible()
    dialog.get_by_role("button", name="Check source operation").click()
    expect(
        dialog.get_by_text("There is no saved receipt yet.", exact=False)
    ).to_be_visible()
    dialog.get_by_role("button", name="Dismiss unconfirmed operation").click()
    expect(dialog.get_by_role("button", name="Reload saved version")).to_be_visible()
    dialog.get_by_role("button", name="Reload saved version").click()
    expect(dialog.get_by_label("Internal instructions")).to_have_value(
        "Synthetic guide with an unavailable index."
    )
    page.keyboard.press("Escape")
    expect(section.get_by_text("Draft", exact=True)).to_be_visible()


def test_scope_options_repair_unknown_label_and_phone_source_geometry(page, app_server):
    page.set_viewport_size({"width": 390, "height": 680})
    create_source(
        page,
        app_server,
        scopes=[
            {"provider_type": "Dentist", "jurisdiction": "HI", "topic": "unresolved"}
        ],
    )
    section = manager_section(page, app_server)
    row = section.get_by_role("article", name="Internal licensing guide")
    expect(row.get_by_text("Draft", exact=True)).to_be_visible()
    assert section.evaluate("node => getComputedStyle(node).padding") == "20px"
    first = section.get_by_role("article").first
    assert first.evaluate("node => getComputedStyle(node).borderTopWidth") == "0px"
    assert row.get_by_text("Draft", exact=True).bounding_box()["height"] < 32
    dialog, _ = open_editor(page, section)
    topic = dialog.get_by_label("Scope 1 topic")
    expect(topic).to_have_value("unresolved")
    topic.select_option("renewal")
    dialog.get_by_role("button", name="Save draft").click()
    expect(dialog.get_by_text("Draft saved.", exact=True)).to_be_visible()
    dimensions = dialog.evaluate(
        "node => [node.scrollWidth, node.clientWidth, innerWidth, document.documentElement.scrollWidth]"
    )
    assert dimensions[0] == dimensions[1] and dimensions[2:] == [390, 390]
