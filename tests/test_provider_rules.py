"""Provider creation validates profile input and trusted initialization rules."""

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.provider_models import CreateProviderRequest
from app.rules.providers import (
    INITIAL_REQUIREMENT_STATUS,
    ProviderCreationConflict,
    ProviderCreationForbidden,
    require_creation_manager,
    require_same_creation,
    require_templates,
)


def profile(**changes):
    return CreateProviderRequest.model_validate(
        {
            "id": uuid4(),
            "name": "  Dr. Avery Example  ",
            "provider_type_id": uuid4(),
            **changes,
        }
    )


def test_creation_name_is_trimmed_and_start_date_is_optional():
    request = profile()
    assert request.name == "Dr. Avery Example"
    assert request.proposed_start_date is None
    assert INITIAL_REQUIREMENT_STATUS == "Outstanding"


@pytest.mark.parametrize(
    "changes",
    [
        {"name": " "},
        {"id": "bad"},
        {"provider_type_id": "bad"},
        {"proposed_start_date": "2026-02-30"},
        {"requirements": []},
        {"status": "Signed"},
    ],
)
def test_creation_rejects_invalid_or_client_supplied_checklist_fields(changes):
    with pytest.raises(ValidationError):
        profile(**changes)


@pytest.mark.parametrize("role", ["proposer", "manager"])
def test_only_managers_can_create_providers(role):
    if role == "manager":
        require_creation_manager(role)
    else:
        with pytest.raises(ProviderCreationForbidden):
            require_creation_manager(role)


def test_identical_creation_identity_is_accepted():
    request = profile()
    require_same_creation(request, request.model_copy())


@pytest.mark.parametrize(
    "change",
    [
        {"name": "Other Example"},
        {"provider_type_id": uuid4()},
        {"proposed_start_date": date(2027, 1, 15)},
    ],
)
def test_changed_creation_profile_conflicts(change):
    request = profile()
    with pytest.raises(ProviderCreationConflict):
        require_same_creation(request, request.model_copy(update=change))


def test_creation_requires_a_nonempty_template():
    require_templates(["Drug screening"])
    with pytest.raises(ProviderCreationConflict):
        require_templates([])
