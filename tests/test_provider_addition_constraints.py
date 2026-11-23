"""Provider-only rows retain ownership, immutable receipts, and shared catalogs."""

import psycopg
import pytest
from psycopg.errors import (
    CheckViolation,
    ForeignKeyViolation,
    RaiseException,
    RestrictViolation,
    UniqueViolation,
)

from app.rules.statuses import classify_completion, status_choices


@pytest.fixture
def addition_data(db_url, seeded_provider):
    with psycopg.connect(db_url) as conn:
        definition = conn.execute(
            "INSERT INTO requirement_definitions(name) VALUES ('Orientation') RETURNING id"
        ).fetchone()[0]
    return db_url, seeded_provider, definition


def insert_addition(conn, provider, definition, initial="Outstanding"):
    return conn.execute(
        """INSERT INTO requirements
        (provider_id,requirement_definition_id,status,initial_status)
        VALUES (%s,%s,'Outstanding',%s) RETURNING id""",
        (provider, definition, initial),
    ).fetchone()[0]


def test_addition_requires_real_provider_and_definition(addition_data):
    url, provider, definition = addition_data
    with psycopg.connect(url) as conn:
        for owner, item in [(2147483647, definition), (provider.id, 2147483647)]:
            with pytest.raises(ForeignKeyViolation), conn.transaction():
                insert_addition(conn, owner, item)
        requirement = insert_addition(conn, provider.id, definition)
        assert requirement > 0
        with pytest.raises(UniqueViolation), conn.transaction():
            insert_addition(conn, provider.id, definition)


@pytest.mark.parametrize("initial", [None, "", "   "])
def test_addition_requires_nonblank_immutable_initial_status(addition_data, initial):
    url, provider, definition = addition_data
    with psycopg.connect(url) as conn, pytest.raises(CheckViolation):
        insert_addition(conn, provider.id, definition, initial)


def test_standard_row_cannot_have_additional_receipt(addition_data):
    url, provider, definition = addition_data
    with psycopg.connect(url) as conn, pytest.raises(CheckViolation):
        conn.execute(
            """INSERT INTO requirements(provider_id,checklist_template_id,
                requirement_definition_id,status,initial_status)
                VALUES (%s,%s,%s,'Outstanding','Outstanding')""",
            (provider.id, provider.checklist_template_id, definition),
        )


@pytest.mark.parametrize(
    "column,value",
    [
        ("initial_status", "Completed"),
        ("initial_scheduled_date", "2026-12-10"),
        ("initial_deadline", "2026-12-20"),
        ("checklist_template_id", 123456789),
    ],
)
def test_addition_receipt_and_origin_cannot_be_changed(addition_data, column, value):
    url, provider, definition = addition_data
    with psycopg.connect(url) as conn:
        requirement = insert_addition(conn, provider.id, definition)
        with pytest.raises(RaiseException), conn.transaction():
            conn.execute(
                psycopg.sql.SQL("UPDATE requirements SET {}=%s WHERE id=%s").format(
                    psycopg.sql.Identifier(column)
                ),
                (value, requirement),
            )
        conn.execute(
            "UPDATE requirements SET status='Completed',version=1 WHERE id=%s",
            (requirement,),
        )
        assert conn.execute(
            "SELECT initial_status FROM requirements WHERE id=%s", (requirement,)
        ).fetchone() == ("Outstanding",)


def test_provider_deletion_removes_additions_but_preserves_definitions(addition_data):
    url, provider, definition = addition_data
    with psycopg.connect(url) as conn:
        requirement = insert_addition(conn, provider.id, definition)
        with pytest.raises(RestrictViolation), conn.transaction():
            conn.execute(
                "DELETE FROM requirement_definitions WHERE id=%s", (definition,)
            )
        conn.execute("DELETE FROM providers WHERE id=%s", (provider.id,))
        assert (
            conn.execute(
                "SELECT id FROM requirements WHERE id=%s", (requirement,)
            ).fetchone()
            is None
        )
        assert conn.execute(
            "SELECT name FROM requirement_definitions WHERE id=%s", (definition,)
        ).fetchone() == ("Orientation",)


@pytest.mark.parametrize(
    "status,expected",
    [
        ("Completed", "finished"),
        ("Scheduled", "outstanding"),
        ("Pending", "outstanding"),
        ("Incomplete", "outstanding"),
        ("Outstanding", "outstanding"),
        ("Unfamiliar", "needs_review"),
    ],
)
def test_generic_completion_requires_additional_origin(status, expected):
    assert (
        classify_completion(
            "Synthetic Other", "Orientation", status, is_additional=True
        )
        == expected
    )
    assert (
        classify_completion("Synthetic Other", "Orientation", status) == "needs_review"
    )


def test_configured_addition_keeps_requirement_specific_statuses():
    choices = status_choices("Dentist", "Offer letter", is_additional=True)
    assert "Signed" in choices and "Completed" not in choices
    assert (
        classify_completion("Dentist", "Offer letter", "Signed", is_additional=True)
        == "finished"
    )
