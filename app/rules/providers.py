"""Pure creation authorization, defaults, and request-identity rules."""

from collections.abc import Sequence

from app.models import DemoRole
from app.provider_models import (
    AdditionalRequirementInput,
    CreateProviderRequest,
    ProviderTypeTemplate,
)
from app.rules.catalog import normalize_name
from app.rules.statuses import status_choices

INITIAL_REQUIREMENT_STATUS = "Outstanding"


class ProviderCreationForbidden(ValueError):
    """Only the simulated Manager can initialize a provider."""


class ProviderCreationConflict(ValueError):
    """The creation identity or selected template cannot be used."""


class ProviderTemplateConflict(ProviderCreationConflict):
    """The checklist preview changed before final submission."""


class ProviderCreationInvalid(ValueError):
    """An initial additional requirement is invalid."""


def require_creation_manager(role: DemoRole) -> None:
    if role != "manager":
        raise ProviderCreationForbidden("Manager mode is required to add providers.")


def require_same_creation(
    existing: CreateProviderRequest, requested: CreateProviderRequest
) -> None:
    if existing.model_dump(exclude={"additional_requirements"}) != requested.model_dump(
        exclude={"additional_requirements"}
    ) or addition_identity(existing.additional_requirements) != addition_identity(
        requested.additional_requirements
    ):
        raise ProviderCreationConflict(
            "This creation attempt already saved different provider details. "
            "Refresh data before adding another provider."
        )


def addition_identity(additions: Sequence[AdditionalRequirementInput]) -> list[tuple]:
    return sorted(
        [
            (normalize_name(a.name), a.status, a.scheduled_date, a.deadline)
            for a in additions
        ],
        key=lambda item: item[0],
    )


def require_reviewed_template(
    request: CreateProviderRequest, template: ProviderTypeTemplate
) -> None:
    if (
        request.checklist_template_id != template.checklist_template_id
        or request.template_fingerprint != template.template_fingerprint
    ):
        raise ProviderTemplateConflict(
            "The standard checklist changed. Review its current requirements before adding this provider."
        )


def require_additions(
    template: ProviderTypeTemplate, additions: Sequence[AdditionalRequirementInput]
) -> None:
    names = {normalize_name(name) for name in template.requirements}
    for addition in additions:
        key = normalize_name(addition.name)
        if key in names:
            raise ProviderCreationInvalid(
                "Requirement names must be unique within this provider's checklist."
            )
        names.add(key)
        if addition.status not in status_choices(
            template.name, addition.name, is_additional=True
        ):
            raise ProviderCreationInvalid(
                "Choose a status available for this additional requirement."
            )


def require_templates(names: Sequence[str]) -> None:
    if not names:
        raise ProviderCreationConflict(
            "The selected provider type has no configured requirements."
        )
