"""Manager-only archive/restore orchestration, without HTTP or model calls."""

from app.models import DemoRole, StoredProvider
from app.repository.provider_lifecycle import ProviderLifecycleRepository
from app.rules.provider_state import require_lifecycle_manager


async def change_archive_state(
    repository: ProviderLifecycleRepository,
    provider_id: int,
    archived: bool,
    role: DemoRole,
) -> StoredProvider:
    require_lifecycle_manager(role)
    return await repository.set_archived(provider_id, archived)
