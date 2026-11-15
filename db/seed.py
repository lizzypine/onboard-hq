"""Explicit, repeatable synthetic development seed; never run at startup."""

import asyncio
from datetime import date
from uuid import NAMESPACE_URL, uuid5

from app.database import DatabasePool, create_pool, database_url
from app.models import ProviderSummary, Requirement
from app.repository import connection
from app.repository.providers import ProviderRepository

KEKOA_ID = uuid5(NAMESPACE_URL, "onboard-hq:provider:kekoa-ejemplo")
DENTIST_ID = uuid5(NAMESPACE_URL, "onboard-hq:type:dentist")
INITIAL_STATUSES = {
    "Offer letter": "Signed",
    "Hawaii dental license": "Received",
    "Drug screening": "Scheduled",
    "State NED license": "Outstanding",
    "Insurance credentialing": "Pending",
}


async def seed_synthetic(pool: DatabasePool) -> None:
    async with connection(pool) as conn:
        await conn.execute(
            "INSERT INTO provider_types(id,name) VALUES (%s,'Dentist') ON CONFLICT(id) DO NOTHING",
            (DENTIST_ID,),
        )
        for name in INITIAL_STATUSES:
            key = uuid5(NAMESPACE_URL, "onboard-hq:template:dentist:" + name)
            await conn.execute(
                "INSERT INTO requirement_templates(id,provider_type_id,name) VALUES (%s,%s,%s) ON CONFLICT(id) DO NOTHING",
                (key, DENTIST_ID, name),
            )
    await ProviderRepository(pool).initialize_provider(
        ProviderSummary(
            id=KEKOA_ID,
            name="Dr. Kekoa Ejemplo",
            provider_type="Dentist",
            proposed_start_date=date(2026, 12, 1),
        ),
        DENTIST_ID,
        {
            name: Requirement(name=name, status=status)
            for name, status in INITIAL_STATUSES.items()
        },
    )


async def main() -> None:
    async with create_pool(database_url()) as pool:
        await seed_synthetic(pool)
    print("Synthetic provider seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
