"""Compatibility CLI for the explicit synthetic database seed."""

import asyncio

from db.seed import INITIAL_STATUSES, KEKOA_CREATION_REQUEST_ID, main, seed_synthetic

__all__ = ["INITIAL_STATUSES", "KEKOA_CREATION_REQUEST_ID", "main", "seed_synthetic"]

if __name__ == "__main__":
    asyncio.run(main())
