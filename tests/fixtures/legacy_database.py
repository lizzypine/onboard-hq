"""Guarded UUID-era migrations and synthetic evidence, independent of new DTOs."""

import os
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from tests.database import ROOT, require_disposable_database

LEGACY_VERSIONS = ("20261111000100", "20261112000100", "20261114000100")


@dataclass(frozen=True)
class LegacyGraph:
    provider_key: UUID
    request_key: UUID
    operation_key: UUID
    update_id: UUID
    requirement_id: UUID
    type_id: UUID


def dbmate(url: str, command: str, *, migrations: Path | None = None):
    require_disposable_database(url, os.environ.get("DATABASE_URL"))
    args = [str(ROOT / ".superpowers/bin/dbmate"), "--no-dump-schema"]
    if migrations is not None:
        args.extend(["--migrations-dir", str(migrations)])
    return subprocess.run(
        [*args, command],
        cwd=ROOT,
        env={**os.environ, "DATABASE_URL": url, "DBMATE_NO_DUMP_SCHEMA": "true"},
        capture_output=True,
        text=True,
        check=False,
    )


def migrate_legacy(url: str) -> None:
    with TemporaryDirectory(prefix="onboard-legacy-") as directory:
        target = Path(directory)
        for version in LEGACY_VERSIONS:
            (source,) = (ROOT / "db/migrations").glob(version + "_*.sql")
            (target / source.name).write_bytes(source.read_bytes())
        result = dbmate(url, "up", migrations=target)
        assert result.returncode == 0, result.stderr


def seed_legacy_graph(url: str, scenario: str = "representative") -> LegacyGraph:
    require_disposable_database(url, os.environ.get("DATABASE_URL"))
    assert scenario == "representative"
    provider, request, operation, update, requirement, kind, template, suggestion = (
        uuid4() for _ in range(8)
    )
    snapshot = {
        "id": str(provider),
        "name": "Dr. Synthetic Upgrade",
        "provider_type": "Dentist",
        "proposed_start_date": "2026-12-01",
        "requirements": [
            {
                "id": str(requirement),
                "provider_id": str(provider),
                "source_template_id": str(template),
                "name": "Drug screening",
                "status": "Scheduled",
                "scheduled_date": "2026-10-22",
                "deadline": "2026-11-01",
                "version": 3,
            }
        ],
    }
    with psycopg.connect(url) as conn:
        conn.execute("INSERT INTO provider_types VALUES (%s,%s)", (kind, "Dentist"))
        conn.execute(
            "INSERT INTO requirement_templates VALUES (%s,%s,%s)",
            (template, kind, "Drug screening"),
        )
        conn.execute(
            "INSERT INTO providers VALUES (%s,%s,%s,%s)",
            (provider, kind, "Dr. Synthetic Upgrade", date(2026, 12, 1)),
        )
        conn.execute(
            """INSERT INTO requirements
            (id,provider_id,provider_type_id,source_template_id,name,status,
             scheduled_date,deadline,version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,7)""",
            (
                requirement,
                provider,
                kind,
                template,
                "Drug screening",
                "Completed",
                date(2026, 10, 29),
                date(2026, 11, 2),
            ),
        )
        conn.execute(
            """INSERT INTO updates
            (id,request_id,provider_id,original_text,provider_snapshot,
             processing_state,message,ambiguities,created_at,completed_at)
            VALUES (%s,%s,%s,'Drug screening completed',%s,'completed',
                    'Review the proposed change',%s,
                    '2026-10-20T12:00:00Z','2026-10-20T12:00:01Z')""",
            (update, request, provider, Jsonb(snapshot), Jsonb(["Confirm the date"])),
        )
        conn.execute(
            """INSERT INTO suggestions
            (id,update_id,requirement_id,provider_id,requirement_version,
             proposed_status,proposed_date,supporting_text,date_text,date_inferred,
             date_explanation,date_requires_confirmation,created_at)
            VALUES (%s,%s,%s,%s,3,'Completed','2026-10-29','screening completed',
             'the 29th',true,'Anchored to start date',true,'2026-10-20T12:00:01Z')""",
            (suggestion, update, requirement, provider),
        )
        conn.execute(
            """INSERT INTO review_decisions
            (id,suggestion_id,outcome,previous_status,previous_scheduled_date,
             applied_status,applied_scheduled_date,reviewer_role,reviewed_at)
            VALUES (%s,%s,'corrected','Scheduled','2026-10-22',
             'Completed','2026-10-29','manager','2026-10-21T12:00:00Z')""",
            (uuid4(), suggestion),
        )
        conn.execute(
            """INSERT INTO checklist_edits
            (id,provider_id,requirement_id,requirement_name,expected_version,
             resulting_version,previous_status,previous_scheduled_date,
             previous_deadline,applied_status,applied_scheduled_date,
             applied_deadline,reviewer_role,created_at)
            VALUES (%s,%s,%s,'Drug screening',6,7,'Completed','2026-10-29',
             '2026-11-01','Completed','2026-10-29','2026-11-02','manager',
             '2026-10-22T12:00:00Z')""",
            (operation, provider, requirement),
        )
    return LegacyGraph(provider, request, operation, update, requirement, kind)
