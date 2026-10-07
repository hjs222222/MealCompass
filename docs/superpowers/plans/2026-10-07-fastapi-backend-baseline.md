# FastAPI Backend Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable FastAPI backend baseline with thin routes, externalized configuration, unified errors, request IDs, and structured logs.

**Architecture:** `backend/main.py` creates the FastAPI application and registers middleware, handlers, and versioned routers. `api/v1` contains only HTTP adaptation and delegates configuration/status access through dependencies; `core` owns settings, exception contracts, and logging without business or database logic.

**Tech Stack:** Python 3.11+, FastAPI 0.115+, Pydantic v2, pydantic-settings, pytest/httpx, standard-library logging and contextvars.

## Global Constraints

- Follow `api → services → domain / agents / rag → infra`; API routes do not access infra directly.
- All IO operations are async; route functions remain thin and no longer than 10 lines where practical.
- `core/config.py` is the only application configuration entry point; business code must not read environment variables directly.
- Do not expose secrets, database URLs, stack traces, or full exception details through health/version responses.
- Use Pydantic v2 APIs, complete type annotations, and the existing Ruff configuration (`line-length=120`, `target-version=py311`, `select=["E","F","I","UP","B","SIM"]`).
- Preserve Langfuse no-op fallback when credentials are absent.
- New behavior requires failing tests before implementation and a final full backend verification.

---

### Task 1: T1.14 FastAPI Entry Point and Thin API Layer

**Files:**
- Create: `backend/main.py`
- Create: `backend/api/__init__.py`
- Create: `backend/api/deps.py`
- Create: `backend/api/v1/__init__.py`
- Create: `backend/api/v1/health.py`
- Test: `backend/tests/unit/test_main.py`

**Interfaces:**
- Produces `create_app() -> FastAPI` and module-level `app: FastAPI`.
- Produces `GET /health` with `{status, environment, tracing_enabled, tracing_degraded}`.
- Produces `GET /version` with `{name, version, environment}`.
- Every response includes `X-Request-ID`; caller-provided valid IDs are preserved and absent IDs are generated.

- [ ] **Step 1: Write failing endpoint tests**

```python
from fastapi.testclient import TestClient
from main import create_app


def test_health_reports_runtime_status() -> None:
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "tracing_enabled" in response.json()
    assert "LANGFUSE" not in response.text


def test_version_reports_application_identity() -> None:
    response = TestClient(create_app()).get("/version")
    assert response.status_code == 200
    assert response.json()["name"] == "mealcompass-backend"
    assert response.json()["version"] == "0.1.0"


def test_request_id_is_preserved_or_generated() -> None:
    client = TestClient(create_app())
    preserved = client.get("/health", headers={"X-Request-ID": "request-test-1"})
    generated = client.get("/health")
    assert preserved.headers["X-Request-ID"] == "request-test-1"
    assert generated.headers["X-Request-ID"]
```

- [ ] **Step 2: Run tests and verify failure**

Run from `backend/`: `.venv\Scripts\python.exe -m pytest tests/unit/test_main.py -q -p no:cacheprovider`
Expected: FAIL because `main.py` and the health router do not exist.

- [ ] **Step 3: Implement the app factory and thin routes**

Implement `create_app(settings: Settings | None = None) -> FastAPI`, include the `/health` and `/version` router, and add request-ID middleware. Define response models in `health.py`; route handlers should obtain settings through a dependency in `api/deps.py` and return models without touching database or model clients.

- [ ] **Step 4: Run focused tests and lint**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_main.py -q -p no:cacheprovider` and `.venv\Scripts\python.exe -m ruff check main.py api tests/unit/test_main.py`
Expected: all endpoint tests pass and Ruff exits 0.

- [ ] **Step 5: Commit T1.14**

```text
git add backend/main.py backend/api backend/tests/unit/test_main.py
git commit -m "feat: add fastapi application entrypoint"
```

---

### Task 2: T1.15 Externalized Configuration and Environment Safety

**Files:**
- Modify: `backend/core/config.py`
- Test: `backend/tests/unit/test_config.py`
- Modify: `.env.example` only if newly validated settings need documenting

**Interfaces:**
- `Settings.app_env` accepts only `dev`, `staging`, or `prod`.
- `Settings.app_version` defaults to the package version `0.1.0`.
- `Settings.validate_runtime()` raises a typed settings error in production when `jwt_secret` remains `change-me-in-dev-only`.
- Existing `get_settings()` cache remains available; tests clear it between cases.

- [ ] **Step 1: Write failing configuration tests**

```python
import pytest
from pydantic import ValidationError
from core.config import Settings


def test_settings_have_safe_defaults_for_development() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_env == "dev"
    assert settings.app_version == "0.1.0"


def test_invalid_environment_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production", _env_file=None)


def test_production_rejects_default_jwt_secret() -> None:
    settings = Settings(app_env="prod", _env_file=None)
    with pytest.raises(ValueError, match="JWT_SECRET"):
        settings.validate_runtime()
```

- [ ] **Step 2: Run tests and verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_config.py -q -p no:cacheprovider`
Expected: FAIL because `app_version`, environment validation, and `validate_runtime()` do not yet exist.

- [ ] **Step 3: Implement typed settings validation**

Use a Pydantic v2 `field_validator` or `model_validator` for the environment enum and a `validate_runtime()` method for environment-sensitive checks. Keep `.env` loading rooted at the repository path and keep `extra="ignore"` for forward-compatible variables. Do not log or return secret values.

- [ ] **Step 4: Wire validation into app startup and document variables**

Call `settings.validate_runtime()` in the app lifespan before serving requests. Add `APP_VERSION` to `.env.example` only if the implementation supports overriding it; otherwise keep the version in code and document that it is application metadata.

- [ ] **Step 5: Run focused tests and lint**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_config.py tests/unit/test_main.py -q -p no:cacheprovider` and `.venv\Scripts\python.exe -m ruff check core/config.py tests/unit/test_config.py`
Expected: all tests pass.

- [ ] **Step 6: Commit T1.15**

```text
git add backend/core/config.py backend/tests/unit/test_config.py .env.example
 git commit -m "feat: harden application configuration"
```

---

### Task 3: T1.16 Unified Exceptions and Structured Logging

**Files:**
- Create: `backend/core/exceptions.py`
- Create: `backend/core/logging.py`
- Modify: `backend/main.py`
- Modify: `backend/api/v1/health.py` if an intentional test error route is needed only under tests
- Test: `backend/tests/unit/test_exceptions.py`
- Test: `backend/tests/unit/test_logging.py`
- Test: `backend/tests/unit/test_main.py`

**Interfaces:**
- `AppError(code: str, message: str, status_code: int = 400)` is the typed application error.
- `ErrorResponse` serializes as `{code, message, request_id}`.
- `configure_logging(level: str) -> None` installs JSON line output with `timestamp`, `level`, `logger`, `message`, and optional `request_id`.
- `request_id_context: ContextVar[str]` is safe across concurrent requests.
- Unhandled exceptions return HTTP 500 with code `internal_error` and no traceback.

- [ ] **Step 1: Write failing exception and logging tests**

```python
import json
import logging

from fastapi.testclient import TestClient
from main import create_app
from core.exceptions import AppError
from core.logging import configure_logging, request_id_context


def test_app_error_has_stable_json_contract() -> None:
    error = AppError(code="bad_request", message="invalid input", status_code=422)
    assert error.code == "bad_request"
    assert error.status_code == 422


def test_request_id_context_is_isolated() -> None:
    token = request_id_context.set("req-1")
    try:
        assert request_id_context.get() == "req-1"
    finally:
        request_id_context.reset(token)


def test_unhandled_exception_does_not_expose_traceback() -> None:
    app = create_app()
    response = TestClient(app, raise_server_exceptions=False).get("/test-error")
    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "Traceback" not in response.text
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
```

- [ ] **Step 2: Run tests and verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/test_exceptions.py tests/unit/test_logging.py -q -p no:cacheprovider`
Expected: FAIL because the exception and logging modules do not exist.

- [ ] **Step 3: Implement exception contracts and handlers**

Create `AppError` and `ErrorResponse` as typed application contracts. Register handlers for `AppError`, `RequestValidationError`, and generic `Exception` in `create_app()`. Generate no traceback in responses; log the exception server-side with request ID. Add a test-only route or dependency override mechanism for `/test-error` so production does not expose a debugging endpoint.

- [ ] **Step 4: Implement JSON logging and request completion middleware**

Create a JSON `logging.Formatter` using UTC ISO timestamps. Add a context variable for request ID. Middleware sets/resets the context, measures `duration_ms` with `perf_counter`, logs method/path/status, and always returns the response header. `configure_logging` must be idempotent and must not duplicate handlers.

- [ ] **Step 5: Run complete backend verification**

From `backend/`, set `$env:TEMP='D:\Allcode\MealCompass\.tmp'`, then run:

```text
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

Expected: Ruff check and format pass; all tests pass. Any unavailable external service must be represented by an explicit skipped integration test, not a weakened assertion.

- [ ] **Step 6: Synchronize documentation and TODO**

Mark T1.14, T1.15, and T1.16 complete in `TODO.md` only after verification. Update `docs/ARCHITECTURE.md` with the app/core/API boundaries and append an iteration-log entry. Add a concise dated entry to `docs/mistakes.md` describing any failures or, if none occurred, a no-failure record. Keep `AGENTS.md`’s autonomous-delivery rule intact.

- [ ] **Step 7: Commit T1.16 and documentation**

```text
git add backend/main.py backend/core backend/api backend/tests .env.example TODO.md docs/ARCHITECTURE.md docs/mistakes.md
git commit -m "feat: add structured fastapi runtime baseline"
```
