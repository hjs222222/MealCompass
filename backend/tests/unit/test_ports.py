"""T1.13 Protocol conformance tests: write these before the ports."""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from typing import get_type_hints

from domain.models.recipe import Recipe
from domain.models.retrieval import HardFilters
from domain.ports import LLMClient, RecipeRepository


class FakeRecipeRepository:
    async def get_by_id(self, recipe_id: str) -> Recipe | None:
        return None

    async def search(self, filters: HardFilters | None = None, limit: int = 50) -> list[Recipe]:
        return []


class FakeLLMClient:
    model = "test-model"

    async def complete(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float = 0.1,
        response_format: str | None = None,
    ) -> str:
        return ""


def test_recipe_repository_is_runtime_checkable_and_has_expected_contract() -> None:
    assert isinstance(FakeRecipeRepository(), RecipeRepository)

    assert inspect.iscoroutinefunction(RecipeRepository.get_by_id)
    assert inspect.iscoroutinefunction(FakeRecipeRepository.get_by_id)
    get_by_id = inspect.signature(RecipeRepository.get_by_id)
    assert list(get_by_id.parameters) == ["self", "recipe_id"]
    get_by_id_hints = get_type_hints(RecipeRepository.get_by_id)
    assert get_by_id_hints["recipe_id"] is str
    assert get_by_id_hints["return"] == Recipe | None

    assert inspect.iscoroutinefunction(RecipeRepository.search)
    assert inspect.iscoroutinefunction(FakeRecipeRepository.search)
    search = inspect.signature(RecipeRepository.search)
    assert list(search.parameters) == ["self", "filters", "limit"]
    assert search.parameters["filters"].default is None
    assert search.parameters["limit"].default == 50
    search_hints = get_type_hints(RecipeRepository.search)
    assert search_hints["filters"] == HardFilters | None
    assert search_hints["limit"] is int
    assert search_hints["return"] == list[Recipe]


def test_llm_client_is_runtime_checkable_and_has_expected_contract() -> None:
    client = FakeLLMClient()
    assert isinstance(client, LLMClient)
    assert client.model == "test-model"

    assert inspect.iscoroutinefunction(LLMClient.complete)
    assert inspect.iscoroutinefunction(FakeLLMClient.complete)
    complete = inspect.signature(LLMClient.complete)
    assert list(complete.parameters) == ["self", "messages", "temperature", "response_format"]
    assert complete.parameters["temperature"].kind is inspect.Parameter.KEYWORD_ONLY
    assert complete.parameters["temperature"].default == 0.1
    assert complete.parameters["response_format"].kind is inspect.Parameter.KEYWORD_ONLY
    assert complete.parameters["response_format"].default is None
    complete_hints = get_type_hints(LLMClient.complete)
    assert complete_hints["messages"] == Sequence[dict[str, str]]
    assert complete_hints["temperature"] is float
    assert complete_hints["response_format"] == str | None
    assert complete_hints["return"] is str
