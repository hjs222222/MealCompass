import json

from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from core.exceptions import AppError, ErrorResponse, request_id_context
from main import create_app


def test_error_response_has_stable_json_contract() -> None:
    response = ErrorResponse(code="example_error", message="示例错误", status=418, request_id="req-1")

    assert response.model_dump() == {
        "code": "example_error",
        "message": "示例错误",
        "status": 418,
        "request_id": "req-1",
    }
    assert json.loads(response.model_dump_json()) == response.model_dump()


def test_app_error_exposes_error_response() -> None:
    error = AppError(code="conflict", message="冲突", status=409)

    assert error.code == "conflict"
    assert error.message == "冲突"
    assert error.status == 409


def test_app_error_rejects_status_outside_http_error_range() -> None:
    import pytest

    with pytest.raises(ValueError):
        AppError("bad", "bad", 399)
    with pytest.raises(ValueError):
        AppError("bad", "bad", 600)

    client = TestClient(create_app(include_test_routes=True))

    response = client.get("/test-error", headers={"X-Request-ID": "req-app"})

    assert response.status_code == 400
    assert response.headers["X-Request-ID"] == "req-app"
    assert response.json() == {
        "code": "test_error",
        "message": "test error",
        "status": 400,
        "request_id": "req-app",
    }


def test_validation_error_is_rendered_without_internal_details() -> None:
    from fastapi import APIRouter
    from pydantic import BaseModel

    class Payload(BaseModel):
        value: int

    router = APIRouter()

    @router.post("/validate")
    async def validate(payload: Payload) -> dict[str, int]:
        return payload.model_dump()

    app = create_app()
    app.include_router(router)
    response = TestClient(app).post("/validate", json={"value": "invalid"})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert response.json()["status"] == 422
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    assert "traceback" not in response.text.lower()


def test_request_id_context_is_isolated() -> None:
    token = request_id_context.set("req-context")
    try:
        assert request_id_context.get() == "req-context"
    finally:
        request_id_context.reset(token)
    assert request_id_context.get() is None


def test_request_validation_error_type_is_supported() -> None:
    assert issubclass(RequestValidationError, Exception)
