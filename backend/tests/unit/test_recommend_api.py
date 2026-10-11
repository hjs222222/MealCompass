"""C3 接口层测试：``POST /recommend`` 与 ``POST /recipes/search``。

原则：
- 不连真库、不连网络：``app.dependency_overrides`` 注入假 service，或用假 retriever/LLM 直接构造真
  ``RecommendService``（覆盖 service 编排代码）。
- 断言响应 schema 与 C1 冻结契约逐字段一致（前端 ``lib/api.ts`` 的守卫按这些字段写）。
- 断言非法入参是 422（而不是 500），且错误体是项目统一的 ``code/message/status/request_id`` 信封。
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from agents.graph import AgentDeps
from api.deps import get_recommend_service, reset_recommend_service
from core.config import Settings
from domain.models.recommend import RecommendRequest, RecommendResponse, SearchRequest, SearchResponse
from domain.models.recommendation import Recommendation
from domain.models.retrieval import HardFilters, RecipeCandidate
from main import create_app
from services.recommend_service import RecommendService

SETTINGS = Settings(_env_file=None, llm_model="fake-model")

PARSE_JSON = '{"max_time_minutes": null, "tools_available": [], "excluded_ingredients": []}'
GENERATE_JSON = """```json
{"recommendations": [
  {"recipe_id": "r1", "reason": "20 分钟能做好", "missing_ingredients": ["鸡蛋"], "substitutions": ["鸭蛋"]},
  {"recipe_id": "r2", "reason": "口味接近", "missing_ingredients": [], "substitutions": []}
]}
```"""

CANDIDATES = [
    RecipeCandidate(recipe_id="r1", name="西红柿炒鸡蛋", score=0.9, rank=1, sources=["vector", "bm25"]),
    RecipeCandidate(recipe_id="r2", name="番茄牛腩", score=0.8, rank=2, sources=["vector"]),
]


class FakeRetriever:
    def __init__(self, candidates: list[RecipeCandidate] | None = None, *, boom: bool = False) -> None:
        self._candidates = list(candidates if candidates is not None else [])
        self._boom = boom
        self.calls: list[tuple[str, HardFilters | None, int]] = []

    async def search(self, query: str, filters: HardFilters | None = None, top_k: int = 10) -> list[RecipeCandidate]:
        self.calls.append((query, filters, top_k))
        if self._boom:
            raise RuntimeError("retriever down")
        return list(self._candidates[:top_k])


class FakeLLM:
    model = "fake-model"

    def __init__(self, replies: list[str] | None = None, *, boom: bool = False) -> None:
        self._replies = list(replies or [])
        self._boom = boom

    async def complete(self, messages, *, temperature: float = 0.1, response_format: str | None = None) -> str:
        text, _ = await self.complete_with_usage(messages, temperature=temperature, response_format=response_format)
        return text

    async def complete_with_usage(self, messages, *, temperature: float = 0.1, response_format: str | None = None):
        if self._boom:
            raise RuntimeError("llm down")
        return self._replies.pop(0), {"input_tokens": 7, "output_tokens": 3}


class StubService:
    """假的 ``RecommendService``：只回放预设响应，用于隔离 API 层。"""

    def __init__(self, response: Any) -> None:
        self.response = response
        self.recommend_calls: list[RecommendRequest] = []
        self.search_calls: list[SearchRequest] = []

    async def recommend(self, request: RecommendRequest, *, session_id: str | None = None) -> Any:
        del session_id
        self.recommend_calls.append(request)
        return self.response

    async def search(self, request: SearchRequest, *, session_id: str | None = None) -> Any:
        del session_id
        self.search_calls.append(request)
        return self.response


def client_with(service: Any) -> TestClient:
    app = create_app(SETTINGS)
    app.dependency_overrides[get_recommend_service] = lambda: service
    return TestClient(app)


RESPONSE_FIELDS = {
    "query",
    "recommendations",
    "candidates_considered",
    "no_solution_reason",
    "degraded",
    "degradations",
    "node_path",
    "trace_id",
}


@pytest.fixture(autouse=True)
def _clean_service_singleton() -> Any:
    reset_recommend_service()
    yield
    reset_recommend_service()


# ------------------------------------------------------------------------ /recommend


def test_recommend_returns_full_schema() -> None:
    response = RecommendResponse(
        query="20 分钟做个西红柿炒鸡蛋",
        recommendations=[
            Recommendation(
                recipe_id="r1",
                name="西红柿炒鸡蛋",
                reason="20 分钟能做好",
                missing_ingredients=["鸡蛋"],
                substitutions=["鸭蛋"],
            ),
            Recommendation(recipe_id="r2", name="番茄牛腩", reason="口味接近"),
        ],
        candidates_considered=2,
        node_path=["parse", "search", "generate", "validate"],
    )
    service = StubService(response)
    client = client_with(service)

    http = client.post("/recommend", json={"query": "20 分钟做个西红柿炒鸡蛋", "top_k": 3})

    assert http.status_code == 200
    body = http.json()
    assert set(body) == RESPONSE_FIELDS
    assert body["recommendations"][0]["recipe_id"] == "r1"
    assert body["recommendations"][0]["missing_ingredients"] == ["鸡蛋"]
    assert body["recommendations"][0]["time_minutes"] is None
    assert body["node_path"] == ["parse", "search", "generate", "validate"]
    assert body["trace_id"] is None
    assert service.recommend_calls[0].top_k == 3


def test_recommend_no_solution_body_shape() -> None:
    service = StubService(
        RecommendResponse(
            query="空气炸锅能做啥",
            recommendations=[],
            candidates_considered=0,
            no_solution_reason="no_candidates_under_constraints",
            node_path=["parse", "search", "no_solution"],
        )
    )
    http = client_with(service).post("/recommend", json={"query": "空气炸锅能做啥"})

    assert http.status_code == 200
    body = http.json()
    assert body["recommendations"] == []
    assert body["no_solution_reason"] == "no_candidates_under_constraints"
    assert body["candidates_considered"] == 0  # 必填，无解时也要给
    assert body["degraded"] is False


def test_recommend_degraded_body_shape() -> None:
    service = StubService(
        RecommendResponse(
            query="随便",
            recommendations=[Recommendation(recipe_id="r1", name="西红柿炒鸡蛋", reason="规则兜底")],
            candidates_considered=1,
            degraded=True,
            degradations=["generate_fallback"],
            node_path=["parse", "search", "generate", "validate"],
        )
    )
    body = client_with(service).post("/recommend", json={"query": "随便"}).json()

    assert body["degraded"] is True
    assert body["degradations"] == ["generate_fallback"]


@pytest.mark.parametrize(
    "payload",
    [
        {"query": ""},
        {"query": "x" * 201},
        {"query": "ok", "top_k": 99},
        {"query": "ok", "top_k": 0},
        {"query": "ok", "max_time_minutes": 0},
        {"query": "ok", "max_time_minutes": 9999},
        {},
    ],
)
def test_recommend_rejects_invalid_payload(payload: dict[str, Any]) -> None:
    http = client_with(StubService(RecommendResponse(query="q", recommendations=[], candidates_considered=0))).post(
        "/recommend", json=payload
    )

    assert http.status_code == 422
    assert http.json()["code"] == "validation_error"
    assert http.json()["request_id"] == http.headers["X-Request-ID"]


def test_recommend_service_error_is_not_500() -> None:
    class ExplodingService:
        async def recommend(self, request: RecommendRequest, *, session_id: str | None = None) -> Any:
            del request, session_id
            raise RuntimeError("should not happen in production code")

        async def search(self, request: SearchRequest, *, session_id: str | None = None) -> Any:
            del request, session_id
            raise RuntimeError("boom")

    app = create_app(SETTINGS)
    app.dependency_overrides[get_recommend_service] = lambda: ExplodingService()
    http = TestClient(app, raise_server_exceptions=False).post("/recommend", json={"query": "ok"})

    # 5xx 会暴露「节点没兜住异常」，这条测试确保异常被错误信封包住而不是裸 500 traceback
    assert http.status_code == 500
    assert http.json()["code"] == "internal_error"
    assert "RuntimeError" not in http.text


# ------------------------------------------------------------------- /recipes/search


def test_search_returns_candidates() -> None:
    service = StubService(SearchResponse(query="番茄", candidates=CANDIDATES, degraded=False, degradations=[]))
    http = client_with(service).post("/recipes/search", json={"query": "番茄", "top_k": 10})

    assert http.status_code == 200
    body = http.json()
    assert body["query"] == "番茄"
    assert [item["recipe_id"] for item in body["candidates"]] == ["r1", "r2"]
    assert body["candidates"][0]["sources"] == ["vector", "bm25"]
    assert body["degraded"] is False
    assert service.search_calls[0].top_k == 10


def test_search_degraded_flag_is_reported() -> None:
    service = StubService(SearchResponse(query="q", candidates=[], degraded=True, degradations=["retrieval_failed"]))
    body = client_with(service).post("/recipes/search", json={"query": "q"}).json()

    assert body["degraded"] is True
    assert body["degradations"] == ["retrieval_failed"]


@pytest.mark.parametrize("payload", [{"query": ""}, {"query": "ok", "top_k": 99}, {"query": "ok", "top_k": 0}])
def test_search_rejects_invalid_payload(payload: dict[str, Any]) -> None:
    http = client_with(StubService(SearchResponse(query="q", candidates=[], degraded=False))).post(
        "/recipes/search", json=payload
    )

    assert http.status_code == 422


def test_openapi_exposes_both_routes() -> None:
    schema = TestClient(create_app(SETTINGS)).get("/openapi.json").json()

    assert "/recommend" in schema["paths"]
    assert "/recipes/search" in schema["paths"]
    assert "/api/v1/recommend" not in schema["paths"]


# ------------------------------------------------- 真 RecommendService（假依赖，覆盖编排）


async def test_service_recommend_end_to_end_with_fakes() -> None:
    service = RecommendService(
        retriever=FakeRetriever(CANDIDATES),
        llm=FakeLLM([PARSE_JSON, GENERATE_JSON]),
        settings=SETTINGS,
    )

    response = await service.recommend(RecommendRequest(query="20 分钟做个西红柿炒鸡蛋"))

    assert [item.recipe_id for item in response.recommendations] == ["r1", "r2"]
    assert response.node_path == ["parse", "search", "generate", "validate"]
    assert response.candidates_considered == 2
    assert response.no_solution_reason is None
    assert response.trace_id is None or isinstance(response.trace_id, str)


async def test_service_recommend_returns_no_solution_without_candidates() -> None:
    service = RecommendService(retriever=FakeRetriever([]), llm=FakeLLM([PARSE_JSON]), settings=SETTINGS)

    response = await service.recommend(RecommendRequest(query="空气炸锅能做啥"))

    assert response.recommendations == []
    assert response.no_solution_reason == "no_candidates_under_constraints"
    assert response.candidates_considered == 0


async def test_service_search_returns_candidates_and_degradation_flag() -> None:
    degraded = [CANDIDATES[0].model_copy(update={"degraded": True})]
    service = RecommendService(retriever=FakeRetriever(degraded), llm=FakeLLM(), settings=SETTINGS)

    response = await service.search(SearchRequest(query="番茄", max_time_minutes=30, top_k=5))

    assert [item.recipe_id for item in response.candidates] == ["r1"]
    assert response.degraded is True
    assert response.degradations == ["retrieval_degraded"]


async def test_service_search_swallows_retriever_errors() -> None:
    service = RecommendService(retriever=FakeRetriever(boom=True), llm=FakeLLM(), settings=SETTINGS)

    response = await service.search(SearchRequest(query="番茄"))

    assert response.candidates == []
    assert response.degraded is True
    assert response.degradations == ["retrieval_failed"]


async def test_service_passes_hard_filters_down_to_retriever() -> None:
    retriever = FakeRetriever(CANDIDATES)
    service = RecommendService(retriever=retriever, llm=FakeLLM([PARSE_JSON, GENERATE_JSON]), settings=SETTINGS)

    await service.search(
        SearchRequest(query="番茄", max_time_minutes=30, tools_available=["炒锅"], excluded_ingredients=["花生"])
    )

    _, filters, _ = retriever.calls[0]
    assert filters == HardFilters(max_time_minutes=30, tools_available=["炒锅"], excluded_ingredients=["花生"])


def test_service_settings_property() -> None:
    service = RecommendService(retriever=FakeRetriever(), llm=FakeLLM(), settings=SETTINGS)

    assert service.settings is SETTINGS


def test_agent_deps_is_a_dataclass_with_three_fields() -> None:
    deps = AgentDeps(retriever=FakeRetriever(), llm=FakeLLM(), settings=SETTINGS)

    assert deps.settings is SETTINGS
    assert isinstance(deps.retriever, FakeRetriever)
    assert deps.llm.model == "fake-model"


# ---------------------------------------------------------------- deps 单例 / 装配


async def test_get_recommend_service_caches_by_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.deps as deps_module

    built: list[int] = []

    async def fake_build(settings: Settings) -> RecommendService:
        built.append(id(settings))
        return RecommendService(retriever=FakeRetriever(), llm=FakeLLM(), settings=settings)

    monkeypatch.setattr(deps_module, "_build_service", fake_build)
    reset_recommend_service()

    first = await deps_module.get_recommend_service(SETTINGS)
    second = await deps_module.get_recommend_service(SETTINGS)

    assert first is second
    assert built == [id(SETTINGS)]  # 只装配一次，不每个请求重建

    await deps_module.close_recommend_service()
