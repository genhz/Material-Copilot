"""FastAPI routes for MatterGen generation jobs."""

from fastapi import APIRouter, HTTPException, status

from generation.exceptions import GenerationError
from generation.manager import get_generation_manager
from generation.schemas import (
    CampaignCandidateCollection,
    CampaignJob,
    CampaignRequest,
    CandidateCollection,
    GenerationJob,
    GenerationRequest,
    ModelInfo,
)


router = APIRouter(prefix="/api/generation", tags=["generation"])


def _raise_http(exc: GenerationError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    ) from exc


@router.post(
    "/jobs",
    response_model=GenerationJob,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_generation_job(request: GenerationRequest) -> GenerationJob:
    try:
        return await get_generation_manager().submit(request)
    except GenerationError as exc:
        _raise_http(exc)


@router.get("/jobs/{job_id}", response_model=GenerationJob)
async def get_generation_job(job_id: str) -> GenerationJob:
    manager = get_generation_manager()
    try:
        return await manager.get_job(job_id)
    except GenerationError as exc:
        _raise_http(exc)


@router.get(
    "/jobs/{job_id}/candidates",
    response_model=CandidateCollection,
)
async def get_generation_candidates(job_id: str) -> CandidateCollection:
    manager = get_generation_manager()
    try:
        return await manager.get_candidates(job_id)
    except GenerationError as exc:
        _raise_http(exc)


@router.post("/jobs/{job_id}/cancel", response_model=GenerationJob)
async def cancel_generation_job(job_id: str) -> GenerationJob:
    manager = get_generation_manager()
    try:
        return await manager.cancel(job_id)
    except GenerationError as exc:
        _raise_http(exc)


@router.get("/models", response_model=list[ModelInfo])
async def list_generation_models() -> list[ModelInfo]:
    return await get_generation_manager().available_models()


@router.post(
    "/campaigns",
    response_model=CampaignJob,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_generation_campaign(
    request: CampaignRequest,
) -> CampaignJob:
    try:
        return await get_generation_manager().submit_campaign(request)
    except GenerationError as exc:
        _raise_http(exc)


@router.get("/campaigns/{campaign_id}", response_model=CampaignJob)
async def get_generation_campaign(campaign_id: str) -> CampaignJob:
    try:
        return await get_generation_manager().get_campaign(campaign_id)
    except GenerationError as exc:
        _raise_http(exc)


@router.get(
    "/campaigns/{campaign_id}/candidates",
    response_model=CampaignCandidateCollection,
)
async def get_generation_campaign_candidates(
    campaign_id: str,
) -> CampaignCandidateCollection:
    try:
        return await get_generation_manager().get_campaign_candidates(
            campaign_id
        )
    except GenerationError as exc:
        _raise_http(exc)


@router.post("/campaigns/{campaign_id}/cancel", response_model=CampaignJob)
async def cancel_generation_campaign(campaign_id: str) -> CampaignJob:
    try:
        return await get_generation_manager().cancel_campaign(campaign_id)
    except GenerationError as exc:
        _raise_http(exc)
