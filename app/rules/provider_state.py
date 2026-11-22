"""Pure archived-state write rule."""

from app.models import ProviderSummary


class ProviderArchivedConflict(ValueError):
    """Archived records can be viewed but cannot receive new changes."""


def require_active(provider: ProviderSummary) -> None:
    if provider.archived_at is not None:
        raise ProviderArchivedConflict(
            "This provider is archived and available for viewing only."
        )
