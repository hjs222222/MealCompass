"""Validated recommendations receive only authoritative recipe detail data."""

from collections.abc import Sequence

from domain.models.recipe import Ingredient
from domain.models.recipe_details import RecipeDetails
from domain.models.recommend import RecommendRequest
from services.recommend_service import RecommendService
from tests.unit.test_recommend_api import CANDIDATES, GENERATE_JSON, PARSE_JSON, SETTINGS, FakeLLM, FakeRetriever


class DetailsReader:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[list[str]] = []
        self.fail = fail

    async def get_details(self, recipe_ids: Sequence[str]) -> dict[str, RecipeDetails]:
        self.calls.append(list(recipe_ids))
        if self.fail:
            raise RuntimeError("db")
        return {
            "r1": RecipeDetails(
                time_text="从备料到完成约需 40 分钟。",
                difficulty=3,
                calories_kcal=524,
                ingredients=[Ingredient(name="鳊鱼", amount_text="550 克")],
                tools=["炒锅"],
                steps=["先洗鱼", "炖豆腐"],
                images=["aquatic/鳊鱼炖豆腐/鳊鱼炖豆腐.jpg"],
                extra="小火炖。",
            )
        }


async def test_enrichment_uses_final_validated_ids_and_authoritative_fields() -> None:
    reader = DetailsReader()
    service = RecommendService(
        retriever=FakeRetriever(CANDIDATES),
        llm=FakeLLM([PARSE_JSON, GENERATE_JSON]),
        settings=SETTINGS,
        details_reader=reader,
    )
    response = await service.recommend(RecommendRequest(query="鱼"))
    assert reader.calls == [["r1", "r2"]]
    assert response.recommendations[0].details.time_text == "从备料到完成约需 40 分钟。"
    assert response.recommendations[0].details.ingredients[0].amount_text == "550 克"
    assert response.recommendations[0].steps == ["先洗鱼", "炖豆腐"]
    assert response.recommendations[1].details is None


async def test_no_solution_does_not_read_details() -> None:
    reader = DetailsReader()
    service = RecommendService(
        retriever=FakeRetriever([]),
        llm=FakeLLM([PARSE_JSON]),
        settings=SETTINGS,
        details_reader=reader,
    )
    response = await service.recommend(RecommendRequest(query="无候选"))
    assert response.recommendations == []
    assert reader.calls == []


async def test_details_failure_preserves_valid_recommendations() -> None:
    service = RecommendService(
        retriever=FakeRetriever(CANDIDATES),
        llm=FakeLLM([PARSE_JSON, GENERATE_JSON]),
        settings=SETTINGS,
        details_reader=DetailsReader(fail=True),
    )
    response = await service.recommend(RecommendRequest(query="鱼"))
    assert [item.recipe_id for item in response.recommendations] == ["r1", "r2"]
    assert response.degraded and "recipe_details_unavailable" in response.degradations
