"""Provider deletion cascades only owned records and preserves shared catalogs."""

import os
import shutil
import subprocess
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.errors import ForeignKeyViolation, RaiseException, RestrictViolation

from tests.database import ROOT, disposable_database, migrate_test_database

TABLES = (
    "providers",
    "requirements",
    "updates",
    "suggestions",
    "review_decisions",
    "checklist_edits",
)


def add_provider_history(conn, type_id, template_id):
    keys = {table: uuid4() for table in TABLES}
    conn.execute(
        "INSERT INTO providers(id,provider_type_id,name) VALUES (%s,%s,'Synthetic deletion example')",
        (keys["providers"], type_id),
    )
    conn.execute(
        "INSERT INTO requirements(id,provider_id,provider_type_id,source_template_id,name,status,version) VALUES (%s,%s,%s,%s,'Synthetic requirement','Pending',1)",
        (keys["requirements"], keys["providers"], type_id, template_id),
    )
    conn.execute(
        "INSERT INTO updates(id,request_id,provider_id,original_text,provider_snapshot,processing_state,message,completed_at) VALUES (%s,%s,%s,'Synthetic administrative update','{}','completed','Synthetic analysis',now())",
        (keys["updates"], uuid4(), keys["providers"]),
    )
    conn.execute(
        "INSERT INTO suggestions(id,update_id,requirement_id,provider_id,requirement_version,proposed_status,supporting_text) VALUES (%s,%s,%s,%s,0,'Received','Synthetic evidence')",
        (keys["suggestions"], keys["updates"], keys["requirements"], keys["providers"]),
    )
    conn.execute(
        "INSERT INTO review_decisions(id,suggestion_id,outcome,previous_status,reviewer_role) VALUES (%s,%s,'rejected','Outstanding','manager')",
        (keys["review_decisions"], keys["suggestions"]),
    )
    conn.execute(
        "INSERT INTO checklist_edits(id,provider_id,requirement_id,requirement_name,expected_version,resulting_version,previous_status,applied_status,reviewer_role) VALUES (%s,%s,%s,'Synthetic requirement',0,1,'Outstanding','Pending','manager')",
        (keys["checklist_edits"], keys["providers"], keys["requirements"]),
    )
    return keys


def add_shared_histories(conn):
    type_id, template_id = uuid4(), uuid4()
    conn.execute("INSERT INTO provider_types VALUES (%s,%s)", (type_id, str(type_id)))
    conn.execute(
        "INSERT INTO requirement_templates VALUES (%s,%s,'Synthetic requirement')",
        (template_id, type_id),
    )
    return {
        "type": type_id,
        "template": template_id,
        "first": add_provider_history(conn, type_id, template_id),
        "second": add_provider_history(conn, type_id, template_id),
    }


def assert_provider_cascade(conn, records):
    conn.execute("DELETE FROM providers WHERE id=%s", (records["first"]["providers"],))
    for table in TABLES:
        query = sql.SQL("SELECT count(*) FROM {} WHERE id=%s").format(
            sql.Identifier(table)
        )
        assert conn.execute(query, (records["first"][table],)).fetchone() == (0,)
        assert conn.execute(query, (records["second"][table],)).fetchone() == (1,)
    assert conn.execute(
        "SELECT count(*) FROM provider_types WHERE id=%s", (records["type"],)
    ).fetchone() == (1,)
    assert conn.execute(
        "SELECT count(*) FROM requirement_templates WHERE id=%s", (records["template"],)
    ).fetchone() == (1,)


@pytest.fixture
def history(db_url):
    with psycopg.connect(db_url) as conn:
        yield conn, add_shared_histories(conn)
        conn.rollback()


def test_provider_delete_removes_owned_history_and_preserves_shared_records(history):
    conn, records = history
    assert_provider_cascade(conn, records)


@pytest.mark.parametrize(
    "table,key", [("provider_types", "type"), ("requirement_templates", "template")]
)
def test_referenced_shared_catalog_cannot_be_deleted(history, table, key):
    conn, records = history
    with pytest.raises(RestrictViolation):
        conn.execute(
            sql.SQL("DELETE FROM {} WHERE id=%s").format(sql.Identifier(table)),
            (records[key],),
        )


def test_requirement_delete_cannot_bypass_manual_history_protection(history):
    conn, records = history
    with pytest.raises(RaiseException, match="history is immutable"):
        conn.execute(
            "DELETE FROM requirements WHERE id=%s", (records["first"]["requirements"],)
        )


def database_rows(conn):
    return {
        table: conn.execute(
            sql.SQL("SELECT * FROM {} ORDER BY id").format(sql.Identifier(table))
        ).fetchall()
        for table in ("provider_types", "requirement_templates", *TABLES)
    }


def test_populated_upgrade_rollback_and_reapply_preserve_data(tmp_path):
    previous = tmp_path / "migrations"
    previous.mkdir()
    for name in (
        "20261111000100_create_onboarding_records.sql",
        "20261112000100_add_checklist_edits.sql",
    ):
        shutil.copyfile(ROOT / "db/migrations" / name, previous / name)
    with disposable_database() as url:
        subprocess.run(
            [
                str(ROOT / ".superpowers/bin/dbmate"),
                "--env-file",
                "/dev/null",
                "--no-dump-schema",
                "--migrations-dir",
                str(previous),
                "migrate",
            ],
            env={**os.environ, "DATABASE_URL": url},
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        with psycopg.connect(url) as conn:
            records = add_shared_histories(conn)
            before = database_rows(conn)
        migrate_test_database(url)
        with psycopg.connect(url) as conn:
            assert database_rows(conn) == before
        subprocess.run(
            [
                str(ROOT / ".superpowers/bin/dbmate"),
                "--env-file",
                "/dev/null",
                "--no-dump-schema",
                "rollback",
            ],
            env={**os.environ, "DATABASE_URL": url},
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        with psycopg.connect(url) as conn:
            assert database_rows(conn) == before
            with pytest.raises(ForeignKeyViolation), conn.transaction():
                conn.execute(
                    "DELETE FROM providers WHERE id=%s",
                    (records["first"]["providers"],),
                )
        migrate_test_database(url)
        with psycopg.connect(url) as conn:
            assert database_rows(conn) == before
            assert_provider_cascade(conn, records)
