"""Typed stored records must not expose SQL metadata to extraction."""

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError


def test_update_contract_accepts_integer_resource_and_uuid_retry_key():
    from app.models import SubmitUpdateRequest

    key = uuid4()
    request = SubmitUpdateRequest(
        provider_id=17, request_id=key, update_text="Synthetic"
    )
    assert request.provider_id == 17
    assert request.request_id == key


@pytest.mark.parametrize("value", [True, 1.0, 0, -1, "17", str(uuid4())])
def test_update_contract_rejects_non_integer_or_nonpositive_resource_ids(value):
    from app.models import SubmitUpdateRequest

    with pytest.raises(ValidationError):
        SubmitUpdateRequest(
            provider_id=value, request_id=uuid4(), update_text="Synthetic"
        )


def test_stored_provider_converts_to_model_context_without_database_fields():
    from app.models import StoredProvider, to_provider_context

    provider_id = 17
    provider = StoredProvider.model_validate(
        {
            "id": provider_id,
            "creation_request_id": str(uuid4()),
            "checklist_template_id": 8,
            "template_version": 1,
            "name": "Synthetic provider",
            "provider_type": "Dentist",
            "proposed_start_date": "2026-12-01",
            "requirements": [
                {
                    "id": 18,
                    "provider_id": provider_id,
                    "checklist_template_id": 8,
                    "requirement_definition_id": 9,
                    "name": "Synthetic requirement",
                    "status": "Outstanding",
                    "deadline": None,
                    "scheduled_date": None,
                    "version": 0,
                }
            ],
        }
    )
    context = to_provider_context(provider)
    assert context.provider_id == str(provider_id)
    assert context.proposed_start_date == date(2026, 12, 1)
    assert context.requirements[0].model_dump() == {
        "name": "Synthetic requirement",
        "status": "Outstanding",
        "deadline": None,
    }


def test_stored_requirement_rejects_negative_version():
    from app.models import StoredRequirement

    with pytest.raises(ValidationError):
        StoredRequirement(
            id=18,
            provider_id=17,
            checklist_template_id=8,
            requirement_definition_id=9,
            name="Test",
            status="Outstanding",
            scheduled_date=None,
            version=-1,
        )
