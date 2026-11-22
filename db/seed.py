"""Explicit, repeatable synthetic development seed; never run at startup."""

import asyncio
from datetime import date
from uuid import NAMESPACE_URL, uuid5

from app.database import DatabasePool, create_pool, database_url
from app.models import Requirement, StoredProvider
from app.provider_models import CreateProviderRequest
from app.repository import connection
from app.repository.catalog import CatalogRepository
from app.repository.providers import ProviderRepository
from db.queries import fetch_provider

KEKOA_CREATION_REQUEST_ID = uuid5(NAMESPACE_URL, "onboard-hq:provider:kekoa-ejemplo")
INITIAL_STATUSES = {
    "Offer letter": "Signed",
    "Hawaii dental license": "Received",
    "Drug screening": "Scheduled",
    "State NED license": "Outstanding",
    "Insurance credentialing": "Pending",
}


async def seed_synthetic(pool: DatabasePool) -> StoredProvider:
    async with connection(pool) as conn:
        existing = await (
            await conn.execute(
                "SELECT id FROM providers WHERE creation_request_id=%s",
                (KEKOA_CREATION_REQUEST_ID,),
            )
        ).fetchone()
        if existing is not None:
            return await fetch_provider(conn, existing["id"])
        latest = await (
            await conn.execute("""SELECT c.template_version FROM checklist_templates c
            JOIN provider_types t ON t.id=c.provider_type_id WHERE lower(btrim(t.name))='dentist'
            ORDER BY c.template_version DESC LIMIT 1""")
        ).fetchone()
        if latest is not None and latest["template_version"] != 1:
            raise ValueError(
                "Existing Dentist catalog differs from the synthetic seed; no changes made."
            )
    template = await CatalogRepository(pool).ensure_version(
        "Dentist", list(INITIAL_STATUSES), template_version=1
    )
    return await ProviderRepository(pool).initialize_provider(
        CreateProviderRequest(
            creation_request_id=KEKOA_CREATION_REQUEST_ID,
            name="Dr. Kekoa Ejemplo",
            provider_type_id=template.id,
            checklist_template_id=template.checklist_template_id,
            template_fingerprint=template.template_fingerprint,
            proposed_start_date=date(2026, 12, 1),
        ),
        {
            name: Requirement(
                name=name,
                status={key.lower(): value for key, value in INITIAL_STATUSES.items()}[
                    name.strip(" ").lower()
                ],
            )
            for name in template.requirements
        },
    )


async def main() -> None:
    async with create_pool(database_url()) as pool:
        await seed_synthetic(pool)
    print("Synthetic provider seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
