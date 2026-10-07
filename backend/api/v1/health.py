"""Health and runtime metadata endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_app_settings, tracing_degraded
from core.config import Settings

router = APIRouter()
AppSettings = Annotated[Settings, Depends(get_app_settings)]


class HealthResponse(BaseModel):
    status: str
    environment: str
    tracing_enabled: bool
    tracing_degraded: bool


class VersionResponse(BaseModel):
    name: str
    version: str
    environment: str


@router.get("/health", response_model=HealthResponse)
def health(settings: AppSettings) -> HealthResponse:
    return HealthResponse(
        status="ok",
        environment=settings.app_env,
        tracing_enabled=settings.tracing_enabled,
        tracing_degraded=tracing_degraded(settings),
    )


@router.get("/version", response_model=VersionResponse)
def version(settings: AppSettings) -> VersionResponse:
    return VersionResponse(name="mealcompass-backend", version=settings.app_version, environment=settings.app_env)
