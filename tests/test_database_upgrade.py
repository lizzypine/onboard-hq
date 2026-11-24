"""Actual historical-data conversion and failure atomicity."""

from datetime import UTC, date, datetime

import psycopg
import pytest
from psycopg.rows import dict_row

from tests.database import disposable_database
from tests.fixtures.legacy_database import dbmate, migrate_legacy, seed_legacy_graph


def test_populated_uuid_upgrade_preserves_history():
    with disposable_database() as url:
        migrate_legacy(url)
        graph = seed_legacy_graph(url)
        result = dbmate(url, "up")
        assert result.returncode == 0, result.stderr
        with psycopg.connect(url, row_factory=dict_row) as conn:
            provider = conn.execute(
                "SELECT * FROM providers WHERE creation_request_id=%s",
                (graph.provider_key,),
            ).fetchone()
            assert provider is not None
            assert type(provider["id"]) is int and provider["id"] > 0
            assert provider["archived_at"] is None
            drug = conn.execute(
                "SELECT * FROM requirements WHERE provider_id=%s", (provider["id"],)
            ).fetchone()
            assert (
                drug["status"],
                drug["scheduled_date"],
                drug["deadline"],
                drug["version"],
            ) == ("Completed", date(2026, 10, 29), date(2026, 11, 2), 7)
            captured = conn.execute(
                "SELECT * FROM update_requirement_snapshots"
            ).fetchone()
            assert (
                captured["status"],
                captured["scheduled_date"],
                captured["deadline"],
                captured["requirement_version"],
            ) == ("Scheduled", date(2026, 10, 22), date(2026, 11, 1), 3)
            update = conn.execute("SELECT * FROM updates").fetchone()
            assert update["request_id"] == graph.request_key
            assert update["original_text"] == "Drug screening completed"
            assert update["created_at"] == datetime(2026, 10, 20, 12, tzinfo=UTC)
            assert conn.execute(
                "SELECT message FROM update_ambiguities"
            ).fetchone() == {"message": "Confirm the date"}
            decision = conn.execute("SELECT * FROM review_decisions").fetchone()
            assert decision["outcome"] == "corrected"
            assert decision["applied_scheduled_date"] == date(2026, 10, 29)
            edit = conn.execute("SELECT * FROM checklist_edits").fetchone()
            assert edit["operation_id"] == graph.operation_key
            assert edit["previous_deadline"] == date(2026, 11, 1)
            assert edit["applied_deadline"] == date(2026, 11, 2)
            assert edit["resulting_version"] == 7
            assert (
                conn.execute(
                    "SELECT count(*) AS n FROM pg_constraint WHERE contype='f' AND connamespace='public'::regnamespace"
                ).fetchone()["n"]
                == 39
            )
            assert (
                conn.execute(
                    "SELECT count(*) AS n FROM pg_tables WHERE schemaname='public' AND tablename <> 'schema_migrations'"
                ).fetchone()["n"]
                == 27
            )


@pytest.mark.parametrize(
    "corruption",
    ["snapshot", "warning", "duplicate", "profile", "type_catalog", "missing_parent"],
)
def test_unrepresentable_legacy_data_aborts_atomically(corruption):
    with disposable_database() as url:
        migrate_legacy(url)
        graph = seed_legacy_graph(url)
        with psycopg.connect(url) as conn:
            if corruption == "snapshot":
                conn.execute("UPDATE updates SET provider_snapshot='{}'")
            elif corruption == "warning":
                conn.execute("""UPDATE updates SET ambiguities='[" "]' """)
            elif corruption == "profile":
                conn.execute(
                    "UPDATE updates SET provider_snapshot=jsonb_set(provider_snapshot,'{name}','\"Different name\"')"
                )
            elif corruption == "type_catalog":
                conn.execute(
                    "INSERT INTO provider_types VALUES (gen_random_uuid(),'dentist')"
                )
            elif corruption == "missing_parent":
                conn.execute(
                    "UPDATE updates SET provider_snapshot=jsonb_set(provider_snapshot,'{requirements,0,id}',to_jsonb(gen_random_uuid()::text))"
                )
            else:
                conn.execute(
                    """INSERT INTO requirements
                    (id,provider_id,provider_type_id,name,status)
                    VALUES (gen_random_uuid(),%s,%s,'drug screening','Outstanding')""",
                    (graph.provider_key, graph.type_id),
                )
        result = dbmate(url, "up")
        assert result.returncode != 0
        with psycopg.connect(url) as conn:
            assert conn.execute("SELECT id FROM providers").fetchone() == (
                graph.provider_key,
            )
            assert conn.execute(
                "SELECT count(*) FROM schema_migrations"
            ).fetchone() == (3,)
            assert conn.execute(
                "SELECT to_regclass('public.update_requirement_snapshots')"
            ).fetchone() == (None,)


def test_normalization_down_refuses_after_empty_additions_down_without_data_loss():
    with disposable_database() as url:
        migrate_legacy(url)
        graph = seed_legacy_graph(url)
        assert dbmate(url, "up").returncode == 0
        # Remove empty answers, sources, then provider-only additions.
        assert dbmate(url, "rollback").returncode == 0
        assert dbmate(url, "rollback").returncode == 0
        assert dbmate(url, "rollback").returncode == 0
        with psycopg.connect(url) as conn:
            assert conn.execute(
                "SELECT initial_status FROM requirements"
            ).fetchall() == [(None,)]
        result = dbmate(url, "rollback")
        assert result.returncode != 0
        assert "backup" in (result.stdout + result.stderr).lower()
        with psycopg.connect(url) as conn:
            assert conn.execute(
                "SELECT creation_request_id FROM providers"
            ).fetchone() == (graph.provider_key,)
            assert conn.execute(
                "SELECT count(*) FROM schema_migrations"
            ).fetchone() == (4,)


def test_target_constraints_and_catalogs_preserve_history_through_provider_delete():
    from psycopg.errors import GeneratedAlways, RaiseException

    with disposable_database() as url:
        migrate_legacy(url)
        first = seed_legacy_graph(url)
        with psycopg.connect(url) as conn:
            conn.execute(
                "UPDATE provider_types SET name='Synthetic First' WHERE id=%s",
                (first.type_id,),
            )
            conn.execute(
                """UPDATE updates SET provider_snapshot=jsonb_set(provider_snapshot,'{provider_type}','"Synthetic First"')"""
            )
        second = seed_legacy_graph(url)
        assert dbmate(url, "up").returncode == 0
        with psycopg.connect(url) as conn:
            identities = dict(
                conn.execute("SELECT creation_request_id,id FROM providers").fetchall()
            )
            assert set(identities) == {first.provider_key, second.provider_key}
            with pytest.raises(GeneratedAlways), conn.transaction():
                conn.execute(
                    "INSERT INTO provider_types(id,name) VALUES (999,'Explicit')"
                )
            for query in [
                "UPDATE checklist_edits SET applied_status='Changed'",
                "DELETE FROM checklist_edits",
                "DELETE FROM requirements WHERE provider_id=%s",
            ]:
                with pytest.raises(RaiseException), conn.transaction():
                    conn.execute(
                        query,
                        (identities[first.provider_key],) if "%s" in query else None,
                    )
            with pytest.raises(RaiseException), conn.transaction():
                conn.execute("DELETE FROM template_requirements")
            with pytest.raises(RaiseException), conn.transaction():
                conn.execute("UPDATE requirement_definitions SET name='Renamed'")
            catalog_before = [
                conn.execute("SELECT count(*) FROM " + table).fetchone()[0]
                for table in [
                    "provider_types",
                    "requirement_definitions",
                    "checklist_templates",
                    "template_requirements",
                ]
            ]
            conn.execute(
                "DELETE FROM providers WHERE id=%s", (identities[first.provider_key],)
            )
            for table in [
                "providers",
                "requirements",
                "updates",
                "suggestions",
                "review_decisions",
                "checklist_edits",
                "update_requirement_snapshots",
                "update_ambiguities",
            ]:
                assert conn.execute("SELECT count(*) FROM " + table).fetchone() == (1,)
            assert [
                conn.execute("SELECT count(*) FROM " + table).fetchone()[0]
                for table in [
                    "provider_types",
                    "requirement_definitions",
                    "checklist_templates",
                    "template_requirements",
                ]
            ] == catalog_before
            missing_indexes = conn.execute("""SELECT c.conrelid::regclass,a.attname
                FROM pg_constraint c CROSS JOIN LATERAL unnest(c.conkey) k(attnum)
                JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.attnum
                WHERE c.contype='f' AND c.connamespace='public'::regnamespace
                AND NOT EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid=c.conrelid
                    AND i.indisvalid AND i.indkey[0]=k.attnum)""").fetchall()
            assert missing_indexes == []
            assert conn.execute(
                "SELECT count(*) FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind='r' AND relname<>'schema_migrations' AND obj_description(oid) IS NULL"
            ).fetchone() == (0,)


def test_legacy_membership_versions_preserve_empty_and_old_checklists():
    from uuid import uuid4

    with disposable_database() as url:
        migrate_legacy(url)
        graph = seed_legacy_graph(url)
        empty, old = uuid4(), uuid4()
        with psycopg.connect(url) as conn:
            conn.execute(
                "INSERT INTO providers(id,provider_type_id,name) VALUES (%s,%s,'Empty'),(%s,%s,'Older checklist')",
                (empty, graph.type_id, old, graph.type_id),
            )
            conn.execute(
                "INSERT INTO requirement_templates VALUES (gen_random_uuid(),%s,'Offer letter')",
                (graph.type_id,),
            )
            conn.execute(
                "INSERT INTO requirements(id,provider_id,provider_type_id,name,status) VALUES (gen_random_uuid(),%s,%s,'Old requirement','Pending')",
                (old, graph.type_id),
            )
        result = dbmate(url, "up")
        assert result.returncode == 0, result.stderr
        with psycopg.connect(url) as conn:
            rows = conn.execute("""SELECT p.creation_request_id,c.template_version,
                ARRAY(SELECT d.name FROM requirements r JOIN requirement_definitions d
                    ON d.id=r.requirement_definition_id WHERE r.provider_id=p.id ORDER BY d.name)
                FROM providers p JOIN checklist_templates c ON c.id=p.checklist_template_id""").fetchall()
            members = {key: names for key, _, names in rows}
            assert members[empty] == []
            assert members[old] == ["Old requirement"]
            assert members[graph.provider_key] == ["Drug screening"]
            assert len({version for _, version, _ in rows}) == 3
            assert conn.execute(
                "SELECT max(template_version) FROM checklist_templates"
            ).fetchone() == (4,)
            assert conn.execute("""SELECT d.name FROM template_requirements m
                JOIN requirement_definitions d ON d.id=m.requirement_definition_id
                JOIN checklist_templates c ON c.id=m.checklist_template_id
                WHERE c.template_version=4 ORDER BY d.name""").fetchall() == [
                ("Drug screening",),
                ("Offer letter",),
            ]
