"""Typed stored records must not expose SQL metadata to extraction."""

from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError


def test_stored_provider_converts_to_model_context_without_database_fields():
    from app.models import StoredProvider, to_provider_context

    provider_id = uuid4()
    provider = StoredProvider.model_validate(
        {
            "id": str(provider_id),
            "name": "Synthetic provider",
            "provider_type": "Dentist",
            "proposed_start_date": "2026-12-01",
            "requirements": [
                {
                    "id": str(uuid4()),
                    "provider_id": str(provider_id),
                    "source_template_id": None,
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
            id=uuid4(),
            provider_id=uuid4(),
            source_template_id=None,
            name="Test",
            status="Outstanding",
            scheduled_date=None,
            version=-1,
        )
