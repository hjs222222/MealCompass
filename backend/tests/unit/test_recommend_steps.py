"""Recipe steps must come from the database after citation validation."""

from collections.abc import Sequence

from domain.models.recommend import RecommendRequest
from services.recommend_service import RecommendService
from tests.unit.test_recommend_api import CANDIDATES, GENERATE_JSON, PARSE_JSON, SETTINGS, FakeLLM, FakeRetriever


class StepsReader:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[list[str]] = []
        self.fail = fail

    async def get_steps(self, recipe_ids: Sequence[str]) -> dict[str, list[str]]:
        self.calls.append(list(recipe_ids))
        if self.fail:
            raise RuntimeError("database unavailable")
        return {"r1": ["切好番茄。", "炒熟鸡蛋。"], "r2": ["炖熟牛腩。"]}


async def test_service_attaches_authoritative_steps_after_validation() -> None:
    reader = StepsReader()
    service = RecommendService(
        retriever=FakeRetriever(CANDIDATES),
        llm=FakeLLM([PARSE_JSON, GENERATE_JSON]),
        settings=SETTINGS,
        steps_reader=reader,
    )
    response = await service.recommend(RecommendRequest(query="番茄"))
    assert reader.calls == [["r1", "r2"]]
    assert response.recommendations[0].steps == ["切好番茄。", "炒熟鸡蛋。"]
    assert response.recommendations[1].steps == ["炖熟牛腩。"]


async def test_no_solution_does_not_read_steps() -> None:
    reader = StepsReader()
    service = RecommendService(
        retriever=FakeRetriever([]),
        llm=FakeLLM([PARSE_JSON]),
        settings=SETTINGS,
        steps_reader=reader,
    )
    response = await service.recommend(RecommendRequest(query="番茄"))
    assert response.recommendations == []
    assert reader.calls == []


async def test_steps_failure_preserves_recommendations_and_reports_degradation() -> None:
    service = RecommendService(
        retriever=FakeRetriever(CANDIDATES),
        llm=FakeLLM([PARSE_JSON, GENERATE_JSON]),
        settings=SETTINGS,
        steps_reader=StepsReader(fail=True),
    )
    response = await service.recommend(RecommendRequest(query="番茄"))
    assert len(response.recommendations) == 2
    assert response.recommendations[0].steps == []
    assert response.degraded
    assert "recipe_steps_unavailable" in response.degradations
