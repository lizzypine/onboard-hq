"""Manager-only direct edit orchestration; no model or HTTP dependencies."""

from uuid import UUID

from app.checklist_models import ChecklistEdit, ChecklistEditRequest
from app.models import DemoRole
from app.repository.checklist import ChecklistRepository
from app.rules.checklist import require_edit_manager


async def edit_checklist(
    repository: ChecklistRepository,
    provider_id: UUID,
    requirement_id: UUID,
    request: ChecklistEditRequest,
    role: DemoRole,
) -> ChecklistEdit:
    require_edit_manager(role)
    return await repository.edit(provider_id, requirement_id, request)
