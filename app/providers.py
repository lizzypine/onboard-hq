"""Manager-only creation orchestration, without HTTP or model calls."""

from app.models import DemoRole, StoredProvider
from app.provider_models import CreateProviderRequest
from app.repository.providers import ProviderRepository
from app.rules.providers import INITIAL_REQUIREMENT_STATUS, require_creation_manager


async def add_provider(
    repository: ProviderRepository, request: CreateProviderRequest, role: DemoRole
) -> StoredProvider:
    require_creation_manager(role)
    return await repository.create_from_template(
        request, initial_status=INITIAL_REQUIREMENT_STATUS
    )
