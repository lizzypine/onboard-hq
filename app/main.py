"""Routes and the synthetic provider onboarding page."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from fastapi import Path as ApiPath
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.agent import build_agent
from app.checklist import edit_checklist
from app.checklist_models import ChecklistEdit, ChecklistEditRequest
from app.database import (
    DatabaseConfigurationError,
    DatabasePool,
    DatabaseUnavailable,
    create_pool,
    database_url,
)
from app.dependencies import get_pool
from app.embeddings import EmbeddingUnavailable
from app.knowledge_routes import router as knowledge_router
from app.models import (
    DemoRole,
    ProviderSummary,
    ReviewDecision,
    ReviewRequest,
    SavedUpdate,
    StoredProvider,
    SubmitUpdateRequest,
)
from app.monitoring import get_dashboard, get_monitoring_date
from app.monitoring_models import ProviderDashboard
from app.page import PAGE
from app.provider_lifecycle import change_archive_state
from app.provider_models import CreateProviderRequest, ProviderTypeTemplate
from app.providers import add_provider
from app.repository import RecordNotFound
from app.repository.checklist import ChecklistRepository
from app.repository.provider_lifecycle import ProviderLifecycleRepository
from app.repository.providers import ProviderRepository
from app.repository.reviews import ReviewRepository
from app.repository.updates import UpdateConflict, UpdateRepository
from app.reviews import AgentFactory, review_suggestion, submit_update
from app.rules.checklist import (
    ChecklistEditConflict,
    ChecklistEditForbidden,
    ChecklistEditInvalid,
)
from app.rules.knowledge import KnowledgeConflict, KnowledgeForbidden, KnowledgeInvalid
from app.rules.provider_state import (
    ProviderArchivedConflict,
    ProviderLifecycleForbidden,
)
from app.rules.providers import (
    ProviderCreationConflict,
    ProviderCreationForbidden,
    ProviderCreationInvalid,
    ProviderTemplateConflict,
)
from app.rules.review import ReviewConflict, ReviewForbidden, ReviewValidationError
from app.source_extraction import SourceError


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    pool: DatabasePool | None
    try:
        pool = create_pool(database_url())
    except DatabaseConfigurationError:
        pool = None
    application.state.pool = pool
    if pool is not None:
        await pool.open()
    try:
        yield
    finally:
        if pool is not None:
            await pool.close()


router = APIRouter()
ResourcePath = Annotated[int, ApiPath(gt=0)]


def get_repository(
    pool: Annotated[DatabasePool, Depends(get_pool)],
) -> ProviderRepository:
    return ProviderRepository(pool)


async def database_error(_request: Request, _error: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Database is unavailable. Check configuration and migrations."
        },
    )


async def missing_record(_request: Request, _error: Exception) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "Record not found."})


@router.get("/providers", response_model=list[ProviderSummary])
async def providers(
    repository: Annotated[ProviderRepository, Depends(get_repository)],
    state: Literal["active", "archived", "all"] = "active",
) -> list[ProviderSummary]:
    return await repository.list_providers(state)


@router.get("/provider-types", response_model=list[ProviderTypeTemplate])
async def provider_types(
    repository: Annotated[ProviderRepository, Depends(get_repository)],
) -> list[ProviderTypeTemplate]:
    return await repository.list_provider_types()


@router.post("/providers", response_model=StoredProvider, status_code=201)
async def create_provider(
    request: CreateProviderRequest,
    repository: Annotated[ProviderRepository, Depends(get_repository)],
    role: Annotated[DemoRole, Header(alias="X-Demo-Role")] = "proposer",
) -> StoredProvider:
    return await add_provider(repository, request, role)


@router.get("/providers/{provider_id}", response_model=StoredProvider)
async def provider(
    provider_id: ResourcePath,
    repository: Annotated[ProviderRepository, Depends(get_repository)],
) -> StoredProvider:
    return await repository.get_provider(provider_id)


@router.post("/providers/{provider_id}/archive", response_model=StoredProvider)
async def archive_provider(
    provider_id: ResourcePath,
    pool: Annotated[DatabasePool, Depends(get_pool)],
    role: Annotated[DemoRole, Header(alias="X-Demo-Role")] = "proposer",
) -> StoredProvider:
    return await change_archive_state(
        ProviderLifecycleRepository(pool), provider_id, True, role
    )


@router.post("/providers/{provider_id}/restore", response_model=StoredProvider)
async def restore_provider(
    provider_id: ResourcePath,
    pool: Annotated[DatabasePool, Depends(get_pool)],
    role: Annotated[DemoRole, Header(alias="X-Demo-Role")] = "proposer",
) -> StoredProvider:
    return await change_archive_state(
        ProviderLifecycleRepository(pool), provider_id, False, role
    )


@router.get("/providers/{provider_id}/dashboard", response_model=ProviderDashboard)
async def provider_dashboard(
    provider_id: ResourcePath,
    repository: Annotated[ProviderRepository, Depends(get_repository)],
    as_of_date: Annotated[date, Depends(get_monitoring_date)],
) -> ProviderDashboard:
    return await get_dashboard(repository, provider_id, as_of_date=as_of_date)


@router.get("/", response_class=HTMLResponse)
async def index() -> str:
    """Display the synthetic provider dashboard and update form."""
    return PAGE


@router.get(
    "/providers/{provider_id}/checklist-edits", response_model=list[ChecklistEdit]
)
async def checklist_history(
    provider_id: ResourcePath, pool: Annotated[DatabasePool, Depends(get_pool)]
) -> list[ChecklistEdit]:
    return await ChecklistRepository(pool).list_for_provider(provider_id)


@router.post(
    "/providers/{provider_id}/requirements/{requirement_id}/edits",
    response_model=ChecklistEdit,
    status_code=201,
)
async def save_checklist_edit(
    provider_id: ResourcePath,
    requirement_id: ResourcePath,
    request: ChecklistEditRequest,
    pool: Annotated[DatabasePool, Depends(get_pool)],
    role: Annotated[DemoRole, Header(alias="X-Demo-Role")] = "proposer",
) -> ChecklistEdit:
    return await edit_checklist(
        ChecklistRepository(pool), provider_id, requirement_id, request, role
    )


def get_agent_factory() -> AgentFactory:
    """Construct the configured agent only after persisting a claimed update."""
    return build_agent


@router.post("/updates/analyze", response_model=SavedUpdate)
async def analyze_update(
    request: SubmitUpdateRequest,
    factory: Annotated[AgentFactory, Depends(get_agent_factory)],
    pool: Annotated[DatabasePool, Depends(get_pool)],
) -> SavedUpdate:
    saved = await submit_update(UpdateRepository(pool), request, factory)
    if saved.failure_category is not None:
        code = {"configuration": 503, "timeout": 504, "model": 502}[
            saved.failure_category
        ]
        raise HTTPException(code, {"message": saved.message, "update_id": saved.id})
    return saved


@router.get("/updates/{update_id}", response_model=SavedUpdate)
async def saved_update(
    update_id: ResourcePath, pool: Annotated[DatabasePool, Depends(get_pool)]
) -> SavedUpdate:
    return await UpdateRepository(pool).get(update_id)


@router.get("/providers/{provider_id}/updates", response_model=list[SavedUpdate])
async def saved_updates(
    provider_id: ResourcePath, pool: Annotated[DatabasePool, Depends(get_pool)]
) -> list[SavedUpdate]:
    return await UpdateRepository(pool).list_for_provider(provider_id)


async def update_conflict(_request: Request, _error: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "detail": "Request is already processing or its input has changed. Refresh saved history."
        },
    )


@router.post("/suggestions/{suggestion_id}/review", response_model=ReviewDecision)
async def record_review(
    suggestion_id: ResourcePath,
    request: ReviewRequest,
    pool: Annotated[DatabasePool, Depends(get_pool)],
    role: Annotated[DemoRole, Header(alias="X-Demo-Role")] = "proposer",
) -> ReviewDecision:
    return await review_suggestion(ReviewRepository(pool), suggestion_id, request, role)


async def review_forbidden(_request: Request, error: Exception) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(error)})


async def review_conflict(_request: Request, error: Exception) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(error)})


async def review_invalid(_request: Request, error: Exception) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(error)})


async def template_conflict(_request: Request, error: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=409, content={"detail": str(error), "code": "template_changed"}
    )


async def embedding_error(_request: Request, error: Exception) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(error)})


def create_app() -> FastAPI:
    application = FastAPI(title="Onboard HQ", lifespan=lifespan)
    application.include_router(router)
    application.include_router(knowledge_router)
    application.add_exception_handler(KnowledgeForbidden, review_forbidden)
    application.add_exception_handler(KnowledgeConflict, review_conflict)
    application.add_exception_handler(KnowledgeInvalid, review_invalid)
    application.add_exception_handler(SourceError, review_invalid)
    application.add_exception_handler(EmbeddingUnavailable, embedding_error)
    application.mount(
        "/static",
        StaticFiles(directory=Path(__file__).parent / "static"),
        name="static",
    )
    application.add_exception_handler(DatabaseUnavailable, database_error)
    application.add_exception_handler(RecordNotFound, missing_record)
    application.add_exception_handler(UpdateConflict, update_conflict)
    application.add_exception_handler(ReviewForbidden, review_forbidden)
    application.add_exception_handler(ProviderCreationForbidden, review_forbidden)
    application.add_exception_handler(ProviderCreationConflict, review_conflict)
    application.add_exception_handler(ProviderTemplateConflict, template_conflict)
    application.add_exception_handler(ProviderCreationInvalid, review_invalid)
    application.add_exception_handler(ReviewConflict, review_conflict)
    application.add_exception_handler(ReviewValidationError, review_invalid)
    application.add_exception_handler(ChecklistEditForbidden, review_forbidden)
    application.add_exception_handler(ChecklistEditConflict, review_conflict)
    application.add_exception_handler(ChecklistEditInvalid, review_invalid)
    application.add_exception_handler(ProviderArchivedConflict, review_conflict)
    application.add_exception_handler(ProviderLifecycleForbidden, review_forbidden)
    return application


app = create_app()
