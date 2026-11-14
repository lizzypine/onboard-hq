"""Real PostgreSQL migration effects and constraints on disposable data."""

import os
import subprocess
from uuid import uuid4

import psycopg
import pytest
from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation

from tests.database import (
    ROOT,
    configured_test_url,
    disposable_database,
    migrate_test_database,
)


@pytest.fixture
def connection():
    url = configured_test_url()
    migrate_test_database(url)
    with psycopg.connect(url) as conn:
        yield conn
        conn.rollback()


def test_migrations_create_eight_application_tables(connection):
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
    }
    assert {
        "provider_types",
        "requirement_templates",
        "providers",
        "requirements",
        "updates",
        "suggestions",
        "review_decisions",
        "checklist_edits",
    } <= tables


def test_second_migrate_preserves_application_records(connection):
    key = uuid4()
    connection.execute("INSERT INTO provider_types VALUES (%s, %s)", (key, str(key)))
    connection.commit()
    migrate_test_database(configured_test_url())
    assert connection.execute(
        "SELECT count(*) FROM provider_types WHERE id=%s", (key,)
    ).fetchone() == (1,)
    connection.execute("DELETE FROM provider_types WHERE id=%s", (key,))
    connection.commit()


@pytest.fixture
def links(connection):
    dentist, hygienist, provider, other_provider, template, requirement, update = [
        uuid4() for _ in range(7)
    ]
    connection.execute(
        "INSERT INTO provider_types VALUES (%s,%s),(%s,%s)",
        (dentist, str(dentist), hygienist, str(hygienist)),
    )
    connection.execute(
        "INSERT INTO requirement_templates VALUES (%s,%s,'Synthetic requirement')",
        (template, dentist),
    )
    connection.execute(
        "INSERT INTO providers(id,provider_type_id,name) VALUES (%s,%s,'A'),(%s,%s,'B')",
        (provider, dentist, other_provider, hygienist),
    )
    connection.execute(
        "INSERT INTO requirements(id,provider_id,provider_type_id,source_template_id,name,status) VALUES (%s,%s,%s,%s,'Synthetic requirement','Outstanding')",
        (requirement, provider, dentist, template),
    )
    connection.execute(
        "INSERT INTO updates(id,request_id,provider_id,original_text,provider_snapshot,processing_state,message) VALUES (%s,%s,%s,'Synthetic update','{}','processing','Processing')",
        (update, uuid4(), provider),
    )
    return {
        "dentist": dentist,
        "hygienist": hygienist,
        "provider": provider,
        "other_provider": other_provider,
        "template": template,
        "requirement": requirement,
        "update": update,
    }


def test_requirement_cannot_reference_another_type_template(connection, links):
    with pytest.raises(ForeignKeyViolation):
        connection.execute(
            "INSERT INTO requirements(id,provider_id,provider_type_id,source_template_id,name,status) VALUES (%s,%s,%s,%s,'Wrong template','Outstanding')",
            (uuid4(), links["other_provider"], links["hygienist"], links["template"]),
        )


def test_suggestion_cannot_cross_provider_boundary(connection, links):
    with pytest.raises(ForeignKeyViolation):
        connection.execute(
            "INSERT INTO suggestions(id,update_id,requirement_id,provider_id,requirement_version,proposed_status,supporting_text) VALUES (%s,%s,%s,%s,0,'Received','Synthetic')",
            (uuid4(), links["update"], links["requirement"], links["other_provider"]),
        )


def test_blank_requirement_status_is_rejected(connection, links):
    with pytest.raises(CheckViolation):
        connection.execute(
            "UPDATE requirements SET status='   ' WHERE id=%s", (links["requirement"],)
        )


def test_suggestion_has_only_one_terminal_decision(connection, links):
    suggestion = uuid4()
    connection.execute(
        "INSERT INTO suggestions(id,update_id,requirement_id,provider_id,requirement_version,proposed_status,supporting_text) VALUES (%s,%s,%s,%s,0,'Received','Synthetic')",
        (suggestion, links["update"], links["requirement"], links["provider"]),
    )
    sql = "INSERT INTO review_decisions(id,suggestion_id,outcome,previous_status,reviewer_role) VALUES (%s,%s,'rejected','Outstanding','manager')"
    connection.execute(sql, (uuid4(), suggestion))
    with pytest.raises(UniqueViolation):
        connection.execute(sql, (uuid4(), suggestion))


def test_rollback_and_reapply_on_separate_disposable_database():
    with disposable_database() as url:
        migrate_test_database(url)
        for remaining in ("providers", None):
            result = subprocess.run(
                [str(ROOT / ".superpowers/bin/dbmate"), "--no-dump-schema", "rollback"],
                cwd=ROOT,
                env={**os.environ, "DATABASE_URL": url},
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 0, (
                "Rollback must succeed on the disposable database"
            )
            with psycopg.connect(url) as conn:
                assert conn.execute(
                    "SELECT to_regclass('public.providers')"
                ).fetchone() == (remaining,)
                assert conn.execute(
                    "SELECT to_regclass('public.checklist_edits')"
                ).fetchone() == (None,)
        migrate_test_database(url)
        with psycopg.connect(url) as conn:
            assert conn.execute("SELECT count(*) FROM providers").fetchone() == (0,)
            assert conn.execute("SELECT count(*) FROM checklist_edits").fetchone() == (
                0,
            )
