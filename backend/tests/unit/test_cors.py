"""Browser CORS regression tests; no database or external model calls."""

import pytest
from fastapi.testclient import TestClient

from api.deps import get_recommend_service
from core.config import Settings
from main import create_app


@pytest.mark.parametrize("origin", ["http://localhost:3000", "http://127.0.0.1:3000"])
@pytest.mark.parametrize("path", ["/recommend", "/recipes/search"])
def test_json_post_preflight_is_allowed(origin: str, path: str) -> None:
    client = TestClient(create_app(Settings(_env_file=None)))
    response = client.options(
        path,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-request-id",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "POST" in response.headers["access-control-allow-methods"]


@pytest.mark.parametrize("path", ["/health", "/version"])
def test_status_response_can_be_read_by_browser(path: str) -> None:
    response = TestClient(create_app(Settings(_env_file=None))).get(path, headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "X-Request-ID" in response.headers["access-control-expose-headers"]


@pytest.mark.parametrize("kind,status", [("app", 400), ("generic", 500)])
def test_error_response_can_be_read_by_browser(kind: str, status: int) -> None:
    client = TestClient(create_app(Settings(_env_file=None), include_test_routes=True), raise_server_exceptions=False)
    response = client.get(f"/test-error?kind={kind}", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == status
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_unknown_origin_preflight_is_rejected() -> None:
    response = TestClient(create_app(Settings(_env_file=None))).options(
        "/recommend",
        headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_origins_can_be_configured_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", '["https://meal.example"]')
    client = TestClient(create_app(Settings(_env_file=None)))
    allowed = client.get("/health", headers={"Origin": "https://meal.example"})
    denied = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert allowed.headers["access-control-allow-origin"] == "https://meal.example"
    assert "access-control-allow-origin" not in denied.headers


def test_empty_allowlist_disables_cross_origin_access() -> None:
    client = TestClient(create_app(Settings(_env_file=None, cors_allow_origins=[])))
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert "access-control-allow-origin" not in response.headers


def test_validation_error_can_be_read_by_browser() -> None:
    application = create_app(Settings(_env_file=None))
    # FastAPI resolves dependencies before returning body validation errors.
    application.dependency_overrides[get_recommend_service] = lambda: None
    response = TestClient(application).post(
        "/recommend", json={"query": ""}, headers={"Origin": "http://localhost:3000"}
    )
    assert response.status_code == 422
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
