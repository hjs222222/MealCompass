"""Application errors and stable HTTP error responses."""

from __future__ import annotations

from contextvars import ContextVar

from pydantic import BaseModel, ConfigDict, Field

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)


class ErrorResponse(BaseModel):
    """Stable public error envelope."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    status: int = Field(ge=400, le=599)
    request_id: str = Field(min_length=1)


class AppError(Exception):
    """Expected application error safe to expose to clients."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        if not 400 <= status <= 599:
            raise ValueError("AppError status must be between 400 and 599")
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status

    def to_response(self, request_id: str) -> ErrorResponse:
        return ErrorResponse(code=self.code, message=self.message, status=self.status, request_id=request_id)
