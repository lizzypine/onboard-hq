"""Pure creation authorization, defaults, and request-identity rules."""

from collections.abc import Sequence

from app.models import DemoRole
from app.provider_models import CreateProviderRequest

INITIAL_REQUIREMENT_STATUS = "Outstanding"


class ProviderCreationForbidden(ValueError):
    """Only the simulated Manager can initialize a provider."""


class ProviderCreationConflict(ValueError):
    """The creation identity or selected template cannot be used."""


def require_creation_manager(role: DemoRole) -> None:
    if role != "manager":
        raise ProviderCreationForbidden("Manager mode is required to add providers.")


def require_same_creation(
    existing: CreateProviderRequest, requested: CreateProviderRequest
) -> None:
    if existing != requested:
        raise ProviderCreationConflict(
            "This creation attempt already saved different provider details. "
            "Refresh data before adding another provider."
        )


def require_templates(names: Sequence[str]) -> None:
    if not names:
        raise ProviderCreationConflict(
            "The selected provider type has no configured requirements."
        )
