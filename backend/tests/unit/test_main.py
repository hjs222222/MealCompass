import logging

from fastapi.testclient import TestClient

from core.config import Settings
from main import create_app


def test_health_reports_runtime_status() -> None:
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "environment" in response.json()
    assert "tracing_enabled" in response.json()
    assert "tracing_degraded" in response.json()
    assert "LANGFUSE" not in response.text


def test_version_reports_application_identity() -> None:
    response = TestClient(create_app()).get("/version")

    assert response.status_code == 200
    assert response.json() == {
        "name": "mealcompass-backend",
        "version": "0.1.0",
        "environment": "dev",
    }


def test_version_uses_custom_app_version() -> None:
    settings = Settings(_env_file=None, app_version="9.9.9")
    with TestClient(create_app(settings)) as client:
        response = client.get("/version")
    assert response.json()["version"] == "9.9.9"


def test_prod_default_secret_fails_on_client_context() -> None:
    settings = Settings(_env_file=None, app_env="prod")
    import pytest

    with pytest.raises(ValueError, match="JWT_SECRET"), TestClient(create_app(settings)):
        pass


def test_prod_valid_secret_starts_and_openapi_version_matches() -> None:
    settings = Settings(_env_file=None, app_env="prod", jwt_secret="secure-value", app_version="3.2.1")
    with TestClient(create_app(settings)) as client:
        assert client.get("/version").json()["version"] == "3.2.1"
        assert client.get("/openapi.json").json()["info"]["version"] == "3.2.1"

    client = TestClient(create_app())

    preserved = client.get("/health", headers={"X-Request-ID": "request-test-1"})
    generated = client.get("/health")

    assert preserved.headers["X-Request-ID"] == "request-test-1"
    assert generated.headers["X-Request-ID"]
    assert generated.headers["X-Request-ID"] != preserved.headers["X-Request-ID"]


def test_request_id_rejects_invalid_values() -> None:
    client = TestClient(create_app())
    for value in ("", "has space", "line\nfeed", "x" * 129):
        response = client.get("/health", headers={"X-Request-ID": value})
        generated = response.headers["X-Request-ID"]
        assert generated != value
        assert len(generated) == 36

    response = TestClient(create_app()).get("/test-error")

    assert response.status_code == 404


def test_test_error_route_can_be_enabled_explicitly() -> None:
    response = TestClient(create_app(include_test_routes=True)).get("/test-error")

    assert response.status_code == 400
    assert response.json()["code"] == "test_error"


def test_generic_exception_returns_safe_500_response() -> None:
    app = create_app(include_test_routes=True)
    response = TestClient(app, raise_server_exceptions=False).get("/test-error?kind=generic")

    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert response.json()["message"] == "Internal server error"
    assert "traceback" not in response.text.lower()
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_request_completion_log_contains_http_fields(caplog) -> None:
    caplog.set_level(logging.INFO, logger="mealcompass.http")
    response = TestClient(create_app()).get("/health", headers={"X-Request-ID": "req-complete"})

    assert response.status_code == 200
    completion = next(record for record in caplog.records if record.message == "request completed")
    assert completion.method == "GET"
    assert completion.path == "/health"
    assert completion.status_code == 200
    assert completion.request_id == "req-complete"
    assert completion.duration_ms >= 0
