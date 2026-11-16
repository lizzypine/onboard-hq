"""An archived provider must reject mutations while an active provider remains writable."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.models import ProviderSummary


def test_archive_guard_rejects_archived_and_accepts_active():
    from app.rules.provider_state import ProviderArchivedConflict, require_active

    provider = ProviderSummary(
        id=19,
        creation_request_id=uuid4(),
        checklist_template_id=8,
        template_version=2,
        name="Synthetic",
        provider_type="Dentist",
    )
    assert require_active(provider) is None
    archived = provider.model_copy(
        update={"archived_at": datetime(2026, 11, 15, tzinfo=UTC)}
    )
    with pytest.raises(ProviderArchivedConflict):
        require_active(archived)
