"""The deliverable query reads the same typed checklist used by the app."""

import asyncio
import os
import subprocess
import sys
from uuid import uuid4

import psycopg
import pytest

from app.database import create_pool
from app.provider_models import CreateProviderRequest
from app.repository import RecordNotFound
from app.repository.providers import ProviderRepository
from db.queries import fetch_provider
from db.seed import KEKOA_ID, seed_synthetic
from tests.database import ROOT


def read(url, provider_id=KEKOA_ID):
    async def query():
        async with create_pool(url) as pool, pool.connection() as conn:
            return await fetch_provider(conn, provider_id)

    return asyncio.run(query())


def seed(url):
    async def load():
        async with create_pool(url) as pool:
            await seed_synthetic(pool)

    asyncio.run(load())


def test_query_returns_seeded_provider_identity_and_linked_checklist(db_url):
    seed(db_url)
    provider = read(db_url)
    assert provider.id == KEKOA_ID
    assert provider.name == "Dr. Kekoa Ejemplo"
    assert provider.provider_type == "Dentist"
    assert provider.proposed_start_date.isoformat() == "2026-12-01"
    assert [(r.name, r.status) for r in provider.requirements] == [
        ("Drug screening", "Scheduled"),
        ("Hawaii dental license", "Received"),
        ("Insurance credentialing", "Pending"),
        ("Offer letter", "Signed"),
        ("State NED license", "Outstanding"),
    ]
    assert all(
        r.provider_id == KEKOA_ID and r.source_template_id is not None
        for r in provider.requirements
    )
    assert all(
        r.deadline is None and r.scheduled_date is None for r in provider.requirements
    )


def test_query_keeps_other_provider_types_and_checklists_separate(db_url):
    seed(db_url)
    type_id, template_id, provider_id = uuid4(), uuid4(), uuid4()
    with psycopg.connect(db_url) as conn:
        conn.execute(
            "INSERT INTO provider_types VALUES (%s,'Synthetic Other')", (type_id,)
        )
        conn.execute(
            "INSERT INTO requirement_templates VALUES (%s,%s,'Other requirement')",
            (template_id, type_id),
        )

    async def create():
        async with create_pool(db_url) as pool:
            await ProviderRepository(pool).create_from_template(
                CreateProviderRequest(
                    id=provider_id,
                    name="Other Fictional Provider",
                    provider_type_id=type_id,
                ),
                initial_status="Outstanding",
            )

    asyncio.run(create())
    other = read(db_url, provider_id)
    assert other.provider_type == "Synthetic Other"
    assert [(r.name, r.status) for r in other.requirements] == [
        ("Other requirement", "Outstanding")
    ]
    assert all(r.provider_id == provider_id for r in other.requirements)
    assert len(read(db_url).requirements) == 5


def test_query_returns_an_empty_checklist_for_an_existing_provider(db_url):
    seed(db_url)
    with psycopg.connect(db_url) as conn:
        conn.execute("DELETE FROM requirements WHERE provider_id=%s", (KEKOA_ID,))
    assert read(db_url).requirements == []


def test_query_reports_missing_provider(db_url):
    with pytest.raises(RecordNotFound):
        read(db_url, uuid4())


def test_seed_cli_loads_empty_database_and_repeat_preserves_progress(db_url):
    environment = {
        "PATH": os.environ["PATH"],
        "DATABASE_URL": db_url,
        "PYTHONPATH": str(ROOT),
    }
    command = [sys.executable, "-m", "db.seed"]
    result = subprocess.run(
        command,
        check=False,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    before = read(db_url)
    assert len(before.requirements) == 5
    with psycopg.connect(db_url) as conn:
        conn.execute(
            "UPDATE requirements SET status='Completed',version=version+1 WHERE provider_id=%s AND name='Drug screening'",
            (KEKOA_ID,),
        )
        conn.execute(
            "INSERT INTO requirement_templates(id,provider_type_id,name) SELECT %s,provider_type_id,'Later requirement' FROM providers WHERE id=%s",
            (uuid4(), KEKOA_ID),
        )
    result = subprocess.run(
        command,
        check=False,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    after = read(db_url)
    assert len(after.requirements) == 5
    drug = next(r for r in after.requirements if r.name == "Drug screening")
    assert drug.status == "Completed" and drug.version == 1
    assert {r.id for r in after.requirements} == {r.id for r in before.requirements}
