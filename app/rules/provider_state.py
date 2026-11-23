"""Pure archived-state write rule."""

from app.models import DemoRole, ProviderSummary


class ProviderLifecycleForbidden(ValueError):
    """Only the simulated Manager can archive or restore a provider."""


def require_lifecycle_manager(role: DemoRole) -> None:
    if role != "manager":
        raise ProviderLifecycleForbidden(
            "Manager mode is required to archive or restore providers."
        )


class ProviderArchivedConflict(ValueError):
    """Archived records can be viewed but cannot receive new changes."""


def require_active(provider: ProviderSummary) -> None:
    if provider.archived_at is not None:
        raise ProviderArchivedConflict(
            "This provider is archived and available for viewing only."
        )
