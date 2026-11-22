"""Configure test catalogs without assigning database-generated IDs in fixtures."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

import psycopg

from app.database import create_pool
from app.repository.catalog import CatalogRepository
from tests.database import configured_test_url


def provider_type_id(name="Dentist", *, url=None):
    with psycopg.connect(url or configured_test_url()) as conn:
        row = conn.execute(
            "SELECT id FROM provider_types WHERE lower(btrim(name))=lower(btrim(%s))",
            (name,),
        ).fetchone()
        assert row is not None
        return row[0]


def configure_catalog(name, requirements, version=1, *, url=None):
    async def configure():
        async with create_pool(url or configured_test_url()) as pool:
            return await CatalogRepository(pool).ensure_version(
                name, requirements, template_version=version
            )

    return run_async(configure)


def run_async(factory):
    """Playwright sync tests already own a running loop; isolate async DB work."""
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(factory())).result()
