"""Compatibility entry point for the explicit database seed in db.seed."""

import asyncio

from db.seed import DENTIST_ID, INITIAL_STATUSES, KEKOA_ID, main, seed_synthetic

__all__ = ["DENTIST_ID", "INITIAL_STATUSES", "KEKOA_ID", "main", "seed_synthetic"]

if __name__ == "__main__":
    asyncio.run(main())
