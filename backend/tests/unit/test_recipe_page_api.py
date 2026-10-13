"""Direct recipe URLs return source-backed details without rerunning recommendation."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.deps import get_recipe_page_service
from core.config import Settings
from domain.models.recipe_details import RecipeDetails, RecipePage
from infra.recipe_details import SqlRecipeDetailsReader
from main import create_app
from services.recipe_page_service import RecipePageService

RECIPE_ID = "00000000-0000-0000-0000-000000000001"


class StubReader:
    def __init__(self, page: RecipePage | None) -> None:
        self.page = page
        self.requested: list[str] = []

    async def get_page(self, recipe_id: str) -> RecipePage | None:
        self.requested.append(recipe_id)
        return self.page


def test_recipe_page_route_is_available() -> None:
    client = TestClient(create_app(Settings(_env_file=None)))
    paths = client.get("/openapi.json").json()["paths"]
    assert "/recipes/{recipe_id}" in paths


def test_recipe_page_returns_complete_recipe() -> None:
    reader = StubReader(
        RecipePage(
            recipe_id=RECIPE_ID,
            name="番茄意面",
            details=RecipeDetails(ingredients=[], steps=["煮面", "炒酱"], time_text="约 20 分钟"),
        )
    )
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[get_recipe_page_service] = lambda: RecipePageService(reader)

    response = TestClient(app).get(f"/recipes/{RECIPE_ID}")

    assert response.status_code == 200
    assert response.json()["name"] == "番茄意面"
    assert response.json()["details"]["steps"] == ["煮面", "炒酱"]
    assert reader.requested == [RECIPE_ID]


def test_recipe_page_missing_and_invalid_ids() -> None:
    reader = StubReader(None)
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[get_recipe_page_service] = lambda: RecipePageService(reader)
    client = TestClient(app)

    assert client.get(f"/recipes/{RECIPE_ID}").status_code == 404
    assert client.get("/recipes/not-a-uuid").status_code == 422
    assert reader.requested == [RECIPE_ID]


class FakeResult:
    def __init__(self, name: str | None) -> None:
        self.name = name

    def first(self) -> Any | None:
        return None if self.name is None else type("Row", (), {"name": self.name})()


class FakeConnection:
    def __init__(self, name: str | None) -> None:
        self.name = name

    async def __aenter__(self) -> FakeConnection:
        return self

    async def __aexit__(self, *_: Any) -> bool:
        return False

    async def execute(self, _: Any) -> FakeResult:
        return FakeResult(self.name)


class FakeEngine:
    def __init__(self, name: str | None) -> None:
        self.name = name

    def connect(self) -> FakeConnection:
        return FakeConnection(self.name)


async def test_page_reader_combines_name_with_authoritative_details(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = SqlRecipeDetailsReader(FakeEngine("番茄意面"))

    async def fake_details(recipe_ids: list[str]) -> dict[str, RecipeDetails]:
        assert recipe_ids == [RECIPE_ID]
        return {RECIPE_ID: RecipeDetails(steps=["煮面"])}

    monkeypatch.setattr(reader, "get_details", fake_details)
    page = await reader.get_page(RECIPE_ID)
    assert page is not None
    assert page.name == "番茄意面"
    assert page.details.steps == ["煮面"]


async def test_page_reader_returns_none_for_missing_recipe() -> None:
    reader = SqlRecipeDetailsReader(FakeEngine(None))
    assert await reader.get_page(RECIPE_ID) is None
