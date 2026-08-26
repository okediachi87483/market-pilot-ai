from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    environment: str


class LivenessResponse(BaseModel):
    status: str


class DependencyStatus(BaseModel):
    status: str  # "ok" | "down"


class ReadinessResponse(BaseModel):
    status: str  # "ok" | "degraded"
    dependencies: dict[str, DependencyStatus]
