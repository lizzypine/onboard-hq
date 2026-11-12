"""Saved analysis/review workflow; model work never holds a database transaction."""

from collections.abc import Callable

from pydantic import ValidationError
from pydantic_ai import Agent
from pydantic_ai.exceptions import (
    ModelAPIError,
    ModelTimeoutError,
    UnexpectedModelBehavior,
)

from app.agent import AgentConfigurationError, ExtractionResult
from app.models import (
    AnalyzeUpdateRequest,
    SavedUpdate,
    SubmitUpdateRequest,
    to_provider_context,
)
from app.repository.updates import UpdateConflict, UpdateRepository
from app.updates import process_update

AgentFactory = Callable[[], Agent[None, ExtractionResult]]


async def submit_update(
    repository: UpdateRepository,
    request: SubmitUpdateRequest,
    agent_factory: AgentFactory,
) -> SavedUpdate:
    claim = await repository.claim(request)
    if not claim.created:
        if claim.update.processing_state == "processing":
            raise UpdateConflict("Analysis is still processing. Refresh saved history.")
        return claim.update
    saved = claim.update
    context = AnalyzeUpdateRequest(
        provider=to_provider_context(saved.provider_snapshot),
        update_text=saved.update_text,
    )
    try:
        result = await process_update(context, agent_factory())
    except AgentConfigurationError:
        return await repository.fail(saved.id, "configuration")
    except (TimeoutError, ModelTimeoutError):
        return await repository.fail(saved.id, "timeout")
    except (ModelAPIError, UnexpectedModelBehavior, ValidationError):
        return await repository.fail(saved.id, "model")
    return await repository.complete(saved.id, result)
