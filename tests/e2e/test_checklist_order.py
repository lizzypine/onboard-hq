"""Deadline order stays consistent from the creation draft to the saved checklist."""

import re

import psycopg
from playwright.sync_api import expect

from tests.e2e.test_checklist_edits import editor, load, row, save_editor
from tests.e2e.test_provider_wizard import (
    edit_addition,
    requirements_step,
    save_provider,
)


def expect_names(rows, names):
    expect(rows.locator("td:first-child")).to_have_text(
        [re.compile("^" + re.escape(name)) for name in names]
    )


def test_creation_preview_review_and_saved_list_share_deadline_order(
    page, app_server, tmp_path
):
    dialog = requirements_step(page, app_server)
    table = dialog.get_by_role("table", name="New provider checklist preview")
    for name, deadline, scheduled, status in (
        ("Zulu orientation", "2026-12-01", "2026-01-01", "Completed"),
        ("Bravo training", "2026-10-01", "2026-12-01", "Outstanding"),
        ("Alpha training", "2026-10-01", "2026-12-01", "Completed"),
        ("Clinic tour", "", "2026-01-01", "Outstanding"),
    ):
        group = edit_addition(dialog, name, status, scheduled)
        group.get_by_label("Deadline", exact=True).fill(deadline)
        group.get_by_role("button", name="Save requirement", exact=True).click()
    names = [
        "Alpha training",
        "Bravo training",
        "Zulu orientation",
        "Clinic tour",
        "Drug screening",
        "Hawaii dental license",
        "Insurance credentialing",
        "Offer letter",
        "State NED license",
    ]
    expect_names(table.locator("tbody tr"), names)
    dialog.get_by_role("button", name="Edit Zulu orientation", exact=True).click()
    group = dialog.get_by_role("group", name="Edit additional requirement")
    group.get_by_label("Deadline", exact=True).fill("2026-09-01")
    expect_names(table.locator("tbody tr"), names)
    group.get_by_role("button", name="Save requirement", exact=True).click()
    names = ["Zulu orientation", "Alpha training", "Bravo training", *names[3:]]
    expect_names(table.locator("tbody tr"), names)
    dialog.locator("#provider-scroll").evaluate("node => { node.scrollTop = 0; }")
    dialog.screenshot(path=tmp_path / "deadline-order-wizard.png")
    dialog.locator("#save-provider").click()
    review = dialog.get_by_role("table", name="Review all requirements")
    expect_names(review.locator("tbody tr"), names)
    dialog.get_by_role("button", name="Edit checklist", exact=True).click()
    saved = save_provider(page, app_server, dialog)
    expect_names(page.locator("#requirements > .requirement-row"), names)
    page.screenshot(path=tmp_path / "deadline-order-saved.png", full_page=True)
    page.reload()
    page.get_by_label("Provider", exact=True).select_option(str(saved["id"]))
    expect_names(page.locator("#requirements > .requirement-row"), names)


def test_saved_deadlines_reorder_after_save_and_clearing_joins_undated_items(
    page, app_server, seeded_provider
):
    requirements = {item.name: item for item in seeded_provider.requirements}
    with psycopg.connect(app_server.database_url) as connection:
        for name, deadline in (
            ("Offer letter", "2026-10-01"),
            ("State NED license", "2026-11-20"),
            ("Hawaii dental license", "2026-11-20"),
        ):
            connection.execute(
                "UPDATE requirements SET deadline=%s WHERE id=%s",
                (deadline, requirements[name].id),
            )
        connection.execute(
            "UPDATE requirements SET scheduled_date='2026-01-01' WHERE id=%s",
            (requirements["Drug screening"].id,),
        )
    load(page, app_server)
    rows = page.locator("#requirements > .requirement-row")
    names = [
        "Offer letter",
        "Hawaii dental license",
        "State NED license",
        "Drug screening",
        "Insurance credentialing",
    ]
    expect_names(rows, names)
    page.get_by_label("Simulated role", exact=True).select_option("manager")
    row(page).get_by_role("button", name="Edit", exact=True).click()
    group = editor(page)
    group.get_by_label("Deadline", exact=True).fill("2026-09-01")
    expect_names(rows, names)
    save_editor(page, group)
    expect_names(rows, ["Drug screening", *names[:3], "Insurance credentialing"])
    row(page).get_by_role("button", name="Edit", exact=True).click()
    group = editor(page)
    group.get_by_label("Deadline", exact=True).fill("")
    save_editor(page, group)
    expect_names(rows, names)
    page.reload()
    expect_names(rows, names)
