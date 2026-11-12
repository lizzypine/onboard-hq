"""Hawaii clock boundary and coherent, read-only dashboard loading."""

from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from app.monitoring_models import ProviderDashboard
from app.repository.providers import ProviderRepository
from app.rules.monitoring import monitor_provider


def hawaii_date_at(instant: datetime) -> date:
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("Monitoring requires a timezone-aware instant.")
    return instant.astimezone(ZoneInfo("Pacific/Honolulu")).date()


def get_monitoring_date() -> date:
    return hawaii_date_at(datetime.now(UTC))


async def get_dashboard(
    repository: ProviderRepository, provider_id: UUID, *, as_of_date: date
) -> ProviderDashboard:
    provider = await repository.get_provider(provider_id)
    return ProviderDashboard(
        provider=provider,
        monitoring=monitor_provider(provider, as_of_date=as_of_date),
    )
