"""Ask AI stays scoped, read-only and usable while retaining cited answers."""

from html import escape
from urllib.parse import urlsplit

import psycopg
import pytest
from playwright.sync_api import expect

from tests.e2e.knowledge_data import (
    QUOTE,
    create_source,
    import_official,
    publish_source,
)
from tests.e2e.test_provider_creation import fill_form, save_form

RENEWAL_QUESTION = "When does renewal apply?"
ASK = "Ask about the documentation"


def load_dashboard(page, server):
    page.goto(server.url)
    expect(page.get_by_role("button", name="Analyze update")).to_be_enabled()
    button = page.get_by_role("button", name="Ask AI", exact=True)
    assert button.count() == 1, "Checklist heading needs a compact Ask AI button."
    return button


def open_ask(page, server):
    button = load_dashboard(page, server)
    button.click()
    dialog = page.get_by_role("dialog", name="Ask AI", exact=True)
    expect(dialog).to_be_visible()
    return dialog


def send(dialog, question):
    dialog.get_by_label("What would you like to know?").fill(question)
    dialog.get_by_role("button", name=ASK).click()


def test_ask_modal_keyboard_focus_and_suggestions(page, app_server):
    button = load_dashboard(page, app_server)
    expect(page.locator("#ask-dialog")).not_to_have_attribute("open", "")
    button.focus()
    page.keyboard.press("Enter")
    dialog = page.get_by_role("dialog", name="Ask AI", exact=True)
    question = dialog.get_by_label("What would you like to know?")
    expect(question).to_be_focused()
    expect(dialog).to_contain_text("Dentist")
    expect(dialog).to_contain_text("Hawaii")
    posts = []
    page.on("request", lambda req: posts.append(req) if req.method == "POST" else None)
    dialog.get_by_role("button", name="Which DEA forms are used?").click()
    expect(question).to_have_value("Which DEA forms are used?")
    expect(question).to_be_focused()
    for _ in range(8):
        page.keyboard.press("Tab")
        assert page.evaluate(
            "document.querySelector('#ask-dialog').contains(document.activeElement) || document.activeElement === document.body"
        )
    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden()
    expect(button).to_be_focused()
    button.click()
    dialog.get_by_role("button", name="Close Ask AI").click()
    expect(button).to_be_focused()
    assert posts == []


def test_both_roles_can_ask_for_archived_providers(page, app_server, seeded_provider):
    dialog = open_ask(page, app_server)
    page.keyboard.press("Escape")
    with psycopg.connect(app_server.database_url) as connection:
        connection.execute(
            "UPDATE providers SET archived_at=now() WHERE id=%s", (seeded_provider.id,)
        )
    page.get_by_label("Provider view").select_option("archived")
    expect(page.locator("#provider-description")).to_contain_text("Archived")
    expect(page.get_by_label("Original update")).to_be_visible()
    expect(page.get_by_role("button", name="Analyze update")).to_be_disabled()
    for role in ("proposer", "manager"):
        page.get_by_label("Simulated role").select_option(role)
        page.get_by_role("button", name="Ask AI", exact=True).click()
        send(dialog, "When can I apply for DEA?")
        expect(
            dialog.get_by_text("Cannot answer from the available information")
        ).to_be_visible()
        page.keyboard.press("Escape")
    answers = page.request.get(
        app_server.url + f"/providers/{seeded_provider.id}/answers"
    ).json()
    assert len(answers) == 2
    assert all(answer["requirement_id"] is None for answer in answers)


def test_unlabelled_official_citation_identifies_its_retained_version(page, app_server):
    raw = ("<h2>Board rules review</h2><p>" + escape(QUOTE) + "</p>").encode()
    version = import_official(app_server, raw)
    publish_source(page, app_server, version)
    dialog = open_ask(page, app_server)
    send(dialog, RENEWAL_QUESTION)
    dialog.get_by_text("[1] Board of Dentistry laws and rules", exact=True).click()
    expect(dialog.get_by_text("Official guidance", exact=True)).to_be_visible()
    expect(dialog.get_by_text(f"Version {version}", exact=True)).to_be_visible()
    dialog.get_by_role("button", name="View retained source").click()
    retained = dialog.get_by_role("region", name="Retained source")
    expect(retained).to_contain_text(f"Version {version}")
    expect(retained).to_contain_text(QUOTE)
    expect(retained.get_by_role("link", name="Official source")).to_be_visible()


def test_exact_citation_retained_after_withdrawal_and_reload(
    page, app_server, seeded_provider
):
    version = create_source(page, app_server, stated_revision="Synthetic edition 2")
    publish_source(page, app_server, version)
    before = page.request.get(
        app_server.url + f"/providers/{seeded_provider.id}"
    ).json()
    dialog = open_ask(page, app_server)
    send(dialog, RENEWAL_QUESTION)
    expect(dialog.get_by_text("Supported answer", exact=True)).to_be_visible()
    dialog.get_by_text("[1] Internal licensing guide", exact=True).click()
    expect(dialog.locator("blockquote")).to_have_text(QUOTE)
    expect(dialog.get_by_text("Internal procedure")).to_be_visible()
    expect(dialog.get_by_text("Synthetic edition 2")).to_be_visible()
    expect(dialog.get_by_text("Renewal review", exact=True)).to_be_visible()
    expect(dialog.get_by_text("Effective from")).to_be_visible()
    expect(dialog.get_by_text("Unknown", exact=True).first).to_be_visible()
    dialog.get_by_role("button", name="View retained source").click()
    retained = dialog.get_by_role("region", name="Retained source")
    expect(retained).to_contain_text(QUOTE)
    with page.expect_download() as matched:
        retained.get_by_role("link", name="Download original").click()
    assert QUOTE in matched.value.path().read_text()
    assert dialog.locator("img").count() == 0
    assert page.evaluate("window.injected") is None

    details = page.request.get(app_server.url + f"/knowledge/versions/{version}").json()
    from uuid import uuid4

    response = page.request.post(
        app_server.url + f"/knowledge/versions/{version}/withdraw",
        data={
            "operation_id": str(uuid4()),
            "expected_revision": details["draft_revision"],
        },
        headers={"X-Demo-Role": "manager"},
    )
    assert response.ok, response.text()
    dialog = open_ask(page, app_server)
    history = dialog.locator("summary").filter(has_text="Question history")
    history.click()
    dialog.get_by_role("button", name=RENEWAL_QUESTION, exact=True).click()
    expect(dialog.get_by_text("Historical answer", exact=True)).to_be_visible()
    expect(dialog.get_by_text("Outdated guidance", exact=True)).to_be_visible()
    dialog.get_by_text("[1] Internal licensing guide", exact=True).click()
    expect(dialog.locator("blockquote")).to_have_text(QUOTE)
    page.keyboard.press("Escape")
    page.get_by_text("Review history", exact=False).last.click()
    expect(page.locator("#review-results")).to_have_text("No saved updates yet.")
    assert (
        page.request.get(app_server.url + f"/providers/{seeded_provider.id}").json()
        == before
    )


@pytest.mark.parametrize(
    ("question", "outcome", "detail"),
    [
        (
            "How much CE do I personally have left?",
            "More information needed",
            "Initial licensure date",
        ),
        (
            "Are these renewal instructions in conflict?",
            "Conflicting guidance",
            "Ask a Manager",
        ),
        (
            "Is renewal temporarily unavailable?",
            "Service unavailable",
            "temporarily unavailable",
        ),
        (
            "What is the approval date? <img src=x onerror=window.injected=true>",
            "Cannot answer from the available information",
            "Individual approval",
        ),
    ],
)
def test_answer_outcomes_and_untrusted_questions(
    page, app_server, question, outcome, detail
):
    publish_source(page, app_server, create_source(page, app_server))
    dialog = open_ask(page, app_server)
    send(dialog, question)
    expect(dialog.get_by_text(outcome, exact=True)).to_be_visible()
    expect(dialog.get_by_text(detail, exact=False).first).to_be_visible()
    assert dialog.locator("img").count() == 0
    assert page.evaluate("window.injected") is None


def test_close_reopen_reconciles_once_and_changed_input_gets_new_uuid(
    page, app_server, seeded_provider
):
    publish_source(page, app_server, create_source(page, app_server))
    dialog = open_ask(page, app_server)
    posted = []
    checked = []
    page.on(
        "request",
        lambda req: (
            posted.append(req.post_data_json)
            if req.method == "POST" and req.url.endswith("/qa/ask")
            else None
        ),
    )
    page.on(
        "request",
        lambda req: checked.append(req.url) if "/qa/requests/" in req.url else None,
    )
    held = []

    def delay_response(route):
        held.append((route, route.fetch()))

    page.route("**/qa/ask", delay_response)
    send(dialog, RENEWAL_QUESTION)
    expect(dialog.get_by_text("Asking…", exact=True)).to_be_visible()
    page.keyboard.press("Escape")
    page.get_by_role("button", name="Ask AI", exact=True).click()
    expect(dialog.get_by_text("Supported answer", exact=True)).to_be_visible()
    assert len(posted) == 1
    assert checked == [app_server.url + f"/qa/requests/{posted[0]['request_id']}"]
    for route, response in held:
        route.fulfill(response=response)
    page.unroute("**/qa/ask", delay_response)
    send(dialog, "How much CE do I personally have left?")
    expect(dialog.get_by_text("More information needed", exact=True)).to_be_visible()
    assert len(posted) == 2
    assert posted[0]["request_id"] != posted[1]["request_id"]
    assert all(body["provider_id"] == seeded_provider.id for body in posted)


def test_provider_switch_during_answer_does_not_show_previous_provider(
    page, app_server, seeded_provider
):
    publish_source(page, app_server, create_source(page, app_server))
    open_ask(page, app_server)
    page.keyboard.press("Escape")
    page.get_by_label("Simulated role").select_option("manager")
    page.get_by_role("button", name="Add provider", exact=True).click()
    form = page.get_by_role("form", name="Add provider")
    fill_form(form, name="Dr. Other Synthetic")
    created = save_form(page, app_server, form)
    provider = page.get_by_label("Provider", exact=True)
    provider.select_option(str(seeded_provider.id))
    trigger = page.get_by_role("button", name="Ask AI", exact=True)
    trigger.click()
    dialog = page.get_by_role("dialog", name="Ask AI", exact=True)
    page.get_by_label("What would you like to know?").fill(RENEWAL_QUESTION)
    held = []

    def delay_response(route):
        held.append((route, route.fetch()))

    page.route("**/qa/ask", delay_response)
    dialog.get_by_role("button", name=ASK).click()
    page.keyboard.press("Escape")
    provider.select_option(str(created["id"]))
    expect(trigger).to_be_enabled()
    trigger.click()
    for route, response in held:
        route.fulfill(response=response)
    expect(dialog.get_by_label("What would you like to know?")).to_have_value("")
    expect(dialog.get_by_text("Supported answer", exact=True)).to_have_count(0)
    dialog.get_by_text("Question history", exact=False).click()
    expect(dialog.get_by_text("No saved questions yet.")).to_be_visible()
    page.keyboard.press("Escape")
    provider.select_option(str(seeded_provider.id))
    trigger.click()
    expect(dialog.get_by_label("What would you like to know?")).to_have_value("")
    if not dialog.get_by_role("button", name=RENEWAL_QUESTION, exact=True).is_visible():
        dialog.get_by_text("Question history", exact=False).click()
    expect(
        dialog.get_by_role("button", name=RENEWAL_QUESTION, exact=True)
    ).to_be_visible()


def test_requirement_context_preserves_update_review_and_edit_drafts(
    page, app_server, seeded_provider
):
    load_dashboard(page, app_server)
    update = page.get_by_label("Original update", exact=True)
    update.fill("Drug screening completed.")
    page.get_by_role("button", name="Analyze update").click()
    expect(page.get_by_text("1 pending suggestion", exact=True)).to_be_visible()
    page.get_by_label("Simulated role").select_option("manager")
    drug = page.get_by_role("row").filter(has_text="Drug screening").first
    drug.get_by_role("button", name="Edit", exact=True).click()
    schedule = page.locator("#checklist-scheduled-date")
    schedule.fill("2026-11-20")
    update.fill("Unsubmitted synthetic update")
    action = page.get_by_role(
        "button", name="Ask about this requirement", exact=True
    ).first
    expect(action).to_be_visible()
    action.click()
    dialog = page.get_by_role("dialog", name="Ask AI", exact=True)
    expect(dialog.get_by_text("Hawaii dental license", exact=False)).to_be_visible()
    with page.expect_request(lambda req: urlsplit(req.url).path == "/qa/ask") as sent:
        send(dialog, "Which DEA forms are used?")
    dental = next(
        req
        for req in seeded_provider.requirements
        if req.name == "Hawaii dental license"
    )
    assert sent.value.post_data_json["requirement_id"] == dental.id
    page.keyboard.press("Escape")
    expect(action).to_be_focused()
    expect(schedule).to_have_value("2026-11-20")
    expect(update).to_have_value("Unsubmitted synthetic update")
    expect(page.get_by_role("article", name="Drug screening")).to_contain_text(
        "Drug screening completed."
    )
    expect(page.get_by_role("button", name="Add provider", exact=True)).to_be_visible()


def test_phone_dialog_contained_scroll_and_safe_quote(page, app_server):
    page.set_viewport_size({"width": 390, "height": 680})
    publish_source(page, app_server, create_source(page, app_server))
    dialog = open_ask(page, app_server)
    send(dialog, RENEWAL_QUESTION)
    expect(dialog.get_by_text("Supported answer", exact=True)).to_be_visible()
    dialog.get_by_text("[1] Internal licensing guide", exact=True).click()
    dialog.get_by_role("button", name="View retained source").click()
    expect(dialog.get_by_role("region", name="Retained source")).to_be_visible()
    geometry = dialog.evaluate("""node => {
      const box = node.getBoundingClientRect();
      return [box.left, box.right, box.height, node.scrollHeight, node.clientHeight,
        node.scrollWidth, node.clientWidth, document.documentElement.scrollWidth];
    }""")
    (
        left,
        right,
        height,
        scroll_height,
        client_height,
        scroll_width,
        client_width,
        page_width,
    ) = geometry
    assert 0 <= left < right <= 390 and height < 680
    assert (
        scroll_height > client_height
        and scroll_width == client_width
        and page_width == 390
    )


def test_delayed_guide_bindings_preserve_editor_focus_and_pending_draft(
    page, app_server
):
    held = []
    page.route("**/requirement-topics", lambda route: held.append(route))
    with page.expect_request("**/requirement-topics"):
        load_dashboard(page, app_server)
    update = page.get_by_label("Original update", exact=True)
    update.fill("Drug screening completed.")
    page.get_by_role("button", name="Analyze update").click()
    expect(page.get_by_text("1 pending suggestion", exact=True)).to_be_visible()
    page.get_by_label("Simulated role").select_option("manager")
    correction = page.get_by_role("article", name="Drug screening").get_by_label(
        "Reviewed status"
    )
    correction.select_option("Incomplete")
    row = page.locator(".requirement-row").filter(has_text="Drug screening")
    row.get_by_role("button", name="Edit", exact=True).click()
    input_date = page.locator("#checklist-scheduled-date")
    input_date.fill("2026-11-20")
    input_date.focus()
    with page.expect_response("**/requirement-topics"):
        held[0].continue_()
    expect(
        page.get_by_role("button", name="Ask about this requirement", exact=True)
    ).to_have_count(2)
    expect(input_date).to_have_value("2026-11-20")
    expect(input_date).to_be_focused()
    expect(correction).to_have_value("Incomplete")


def test_processing_question_after_reload_can_stay_in_history_during_a_new_ask(
    page, app_server, seeded_provider
):
    from app.database import create_pool
    from app.qa_models import AskRequest
    from app.repository.qa import QARepository
    from tests.fixtures.current_database import run_async

    posted = []
    page.on(
        "request",
        lambda req: (
            posted.append(req.post_data_json)
            if req.method == "POST" and req.url.endswith("/qa/ask")
            else None
        ),
    )

    def interrupt_after_claim(route):
        request = AskRequest.model_validate(route.request.post_data_json)

        async def claim():
            async with create_pool(app_server.database_url) as pool:
                await QARepository(pool).claim(request, app_server.as_of)

        run_async(claim)
        route.abort()

    dialog = open_ask(page, app_server)
    page.route("**/qa/ask", interrupt_after_claim, times=1)
    send(dialog, RENEWAL_QUESTION)
    check = dialog.get_by_role("button", name="Check for answer")
    expect(check).to_be_visible()
    request_url = app_server.url + "/qa/requests/" + posted[0]["request_id"]
    with page.expect_response(request_url) as checked:
        check.click()
    original = checked.value.json()
    assert original["state"] == "processing"
    page.reload()
    with page.expect_response(request_url) as restored:
        page.get_by_role("button", name="Ask AI", exact=True).click()
    assert restored.value.json() == original

    dialog.get_by_role("button", name="Start a new question").click(timeout=3000)
    expect(dialog.get_by_label("What would you like to know?")).to_be_focused()
    expect(dialog.get_by_role("button", name=ASK)).to_be_disabled()
    assert len(posted) == 1
    send(dialog, "Which DEA forms are used?")
    expect(
        dialog.get_by_text("Cannot answer from the available information")
    ).to_be_visible()
    assert len(posted) == 2
    assert posted[1]["request_id"] != original["request_id"]
    assert posted[1]["provider_id"] == seeded_provider.id
    dialog.get_by_text("Question history", exact=True).click()
    with page.expect_response(app_server.url + f"/qa/{original['id']}") as historical:
        dialog.get_by_role("button", name=RENEWAL_QUESTION, exact=True).click()
    assert historical.value.json() == original
    expect(dialog.locator("#ask-answer")).to_contain_text("still processing")
    assert page.request.get(request_url).json() == original
    assert len(posted) == 2


def test_knowledge_metadata_uses_hawaii_day_and_preserves_effective_dates(
    page, app_server
):
    page.goto(app_server.url)
    dates = page.evaluate("""async () => {
        const {dateOrUnknown} = await import('/static/knowledge-ui.js');
        return [dateOrUnknown('2026-11-24T04:00:00Z'), dateOrUnknown('2026-11-24')];
    }""")
    assert dates == ["2026-11-23", "2026-11-24"]
