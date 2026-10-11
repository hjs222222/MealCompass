"""C1 共享契约：LLM 客户端 + 推荐/检索请求响应模型（TDD，先红后绿）。

覆盖：
1. `RemoteLLM` 的请求构造（endpoint / Authorization / response_format）与响应解析
2. `strip_code_fence`：剥掉 ```` ```json ... ``` ```` 围栏与首尾空白
3. 429 / 5xx 的指数退避重试；重试耗尽后抛 `httpx.HTTPStatusError`
4. `LLMClient` Protocol 的 runtime 语义与连接池归属（`_owns_client`）
5. 共享契约模型 `domain.models.recommend` 的边界与嵌套复用

> 说明：契约模型的用例放在本文件，是因为本次任务的文件边界只允许新增这一个测试文件。
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable

import httpx
import pytest
from pydantic import ValidationError

from core.config import Settings
from domain.models.recommend import RecommendRequest, RecommendResponse, SearchRequest, SearchResponse
from domain.models.recommendation import Recommendation
from domain.models.retrieval import RecipeCandidate
from domain.ports import LLMClient
from infra.llm_client import RemoteLLM, build_llm_client, strip_code_fence

MESSAGES: list[dict[str, str]] = [{"role": "user", "content": "推荐一道 20 分钟内能做的家常菜"}]


def _chat_response(content: str, *, usage: dict[str, int] | None = None) -> dict[str, object]:
    body: dict[str, object] = {"choices": [{"message": {"role": "assistant", "content": content}}]}
    if usage is not None:
        body["usage"] = usage
    return body


def make_llm(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    max_retries: int = 3,
    retry_base_delay: float = 0.0,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> RemoteLLM:
    """构造注入 `MockTransport` 的 `RemoteLLM`（退避基数默认 0，测试不真等）。"""
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return RemoteLLM(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="deepseek-chat",
        client=client,
        max_retries=max_retries,
        retry_base_delay=retry_base_delay,
        sleep=sleep,
    )


# ------------------------------------------------------------------ strip_code_fence


def test_strip_code_fence_removes_json_fence() -> None:
    assert strip_code_fence('```json\n{"recipe_id": "r1"}\n```') == '{"recipe_id": "r1"}'


def test_strip_code_fence_removes_bare_fence() -> None:
    assert strip_code_fence('```\n{"recipe_id": "r1"}\n```') == '{"recipe_id": "r1"}'


def test_strip_code_fence_handles_single_line_fence() -> None:
    assert strip_code_fence('```json {"recipe_id": "r1"}```') == '{"recipe_id": "r1"}'


def test_strip_code_fence_handles_missing_closing_fence() -> None:
    assert strip_code_fence('```json\n{"recipe_id": "r1"}') == '{"recipe_id": "r1"}'


def test_strip_code_fence_keeps_plain_text_and_only_trims_whitespace() -> None:
    assert strip_code_fence("  \n 红烧肉 \n\n") == "红烧肉"


def test_strip_code_fence_does_not_eat_text_starting_with_a_word() -> None:
    """围栏内是普通文本时，首行的普通单词不能被误当成语言标识删掉。"""
    assert strip_code_fence("```\n红烧肉 是一道家常菜\n```") == "红烧肉 是一道家常菜"


# ------------------------------------------------------------------ 请求构造与响应解析


async def test_complete_posts_openai_chat_payload() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=_chat_response("红烧肉"))

    text = await make_llm(handler).complete(MESSAGES)

    assert text == "红烧肉"
    assert seen["url"] == "https://example.test/v1/chat/completions"
    assert seen["auth"] == "Bearer test-key"
    body = seen["body"]
    assert body["model"] == "deepseek-chat"
    assert body["messages"] == MESSAGES
    assert body["temperature"] == 0.1


async def test_complete_omits_response_format_by_default() -> None:
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=_chat_response("ok"))

    await make_llm(handler).complete(MESSAGES)

    assert "response_format" not in bodies[0]


async def test_complete_sends_response_format_when_json_requested() -> None:
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=_chat_response("{}"))

    await make_llm(handler).complete(MESSAGES, temperature=0.2, response_format="json_object")

    assert bodies[0]["response_format"] == {"type": "json_object"}
    assert bodies[0]["temperature"] == 0.2


async def test_complete_strips_code_fence_from_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_chat_response('```json\n{"recipe_id": "r1"}\n```'))

    assert await make_llm(handler).complete(MESSAGES) == '{"recipe_id": "r1"}'


async def test_complete_with_usage_parses_token_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_chat_response(
                "ok",
                usage={"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19},
            ),
        )

    content, usage = await make_llm(handler).complete_with_usage(MESSAGES)

    assert content == "ok"
    assert usage == {"input_tokens": 12, "output_tokens": 7}


async def test_complete_with_usage_tolerates_missing_usage_block() -> None:
    """服务端漏了 usage 也不能让推荐崩掉；记 0 保证 trace 结构稳定。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_chat_response("ok"))

    _, usage = await make_llm(handler).complete_with_usage(MESSAGES)

    assert usage == {"input_tokens": 0, "output_tokens": 0}


# ------------------------------------------------------------------ 重试


async def test_complete_retries_after_429_then_succeeds_quickly() -> None:
    attempts = {"n": 0}
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(200, json=_chat_response("ok"))

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    started = time.perf_counter()
    text = await make_llm(handler, sleep=fake_sleep).complete(MESSAGES)
    elapsed = time.perf_counter() - started

    assert text == "ok"
    assert attempts["n"] == 2
    assert sleeps == [0.0]
    assert elapsed < 1.0


async def test_retry_backoff_is_exponential() -> None:
    attempts = {"n": 0}
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(503, json={"error": "busy"})

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    with pytest.raises(httpx.HTTPStatusError):
        await make_llm(handler, max_retries=3, retry_base_delay=0.5, sleep=fake_sleep).complete(MESSAGES)

    assert attempts["n"] == 4  # 1 次原始请求 + 3 次重试
    assert sleeps == [0.5, 1.0, 2.0]


async def test_complete_raises_after_exhausting_retries() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(500, json={"error": "boom"})

    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        await make_llm(handler).complete(MESSAGES)

    assert attempts["n"] == 4
    assert excinfo.value.response.status_code == 500


async def test_client_error_is_not_retried() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(401, json={"error": "bad key"})

    with pytest.raises(httpx.HTTPStatusError):
        await make_llm(handler).complete(MESSAGES)

    assert attempts["n"] == 1


# ------------------------------------------------------------------ Protocol 与连接池


def test_remote_llm_satisfies_llm_client_port() -> None:
    llm = RemoteLLM(api_key="k", base_url="https://example.test/v1", model="deepseek-chat")

    assert isinstance(llm, LLMClient)
    assert llm.model == "deepseek-chat"


async def test_aclose_does_not_close_injected_client() -> None:
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200)))

    try:
        llm = RemoteLLM(api_key="k", base_url="https://example.test/v1", model="m", client=client)
        await llm.aclose()

        assert client.is_closed is False
    finally:
        await client.aclose()


async def test_aclose_is_idempotent_when_no_client_was_created() -> None:
    llm = RemoteLLM(api_key="k", base_url="https://example.test/v1", model="m")

    await llm.aclose()
    await llm.aclose()


# ------------------------------------------------------------------ 装配与配置


def test_build_llm_client_uses_settings() -> None:
    settings = Settings(
        _env_file=None,
        llm_api_key="key",
        llm_base_url="https://llm.test/v1",
        llm_model="qwen-max",
        llm_timeout_seconds=12.5,
        llm_max_retries=1,
    )

    llm = build_llm_client(settings)

    assert isinstance(llm, RemoteLLM)
    assert llm.model == "qwen-max"
    # 超时 / 重试次数没有对外暴露，直接断言内部装配结果，防止配置项变成死配置
    assert llm._timeout == 12.5
    assert llm._max_retries == 1


def test_settings_expose_llm_retry_knobs_with_safe_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.llm_timeout_seconds == 60.0
    assert settings.llm_max_retries == 3


# ------------------------------------------------------------------ 契约模型


def test_recommend_request_defaults() -> None:
    request = RecommendRequest(query="红烧肉")

    assert request.max_time_minutes is None
    assert request.tools_available == []
    assert request.excluded_ingredients == []
    assert request.top_k == 3


def test_recommend_request_rejects_blank_query_and_bad_bounds() -> None:
    with pytest.raises(ValidationError):
        RecommendRequest(query="")
    with pytest.raises(ValidationError):
        RecommendRequest(query="x", top_k=6)
    with pytest.raises(ValidationError):
        RecommendRequest(query="x", max_time_minutes=0)


def test_search_request_allows_a_larger_top_k() -> None:
    assert SearchRequest(query="红烧肉", top_k=50).top_k == 50

    with pytest.raises(ValidationError):
        SearchRequest(query="红烧肉", top_k=51)


def test_search_response_carries_real_candidates() -> None:
    candidate = RecipeCandidate(recipe_id="r1", name="红烧肉", score=0.9, rank=1, sources=["vector", "bm25"])

    response = SearchResponse(query="红烧肉", candidates=[candidate], degraded=False)

    assert response.candidates[0].recipe_id == "r1"
    assert response.degradations == []
    assert response.model_dump()["candidates"][0]["recipe_id"] == "r1"


def test_recommend_response_round_trips_nested_models() -> None:
    response = RecommendResponse(
        query="红烧肉",
        recommendations=[Recommendation(recipe_id="r1", name="红烧肉", reason="命中硬约束")],
        candidates_considered=3,
        node_path=["parse_intent", "retrieve_recipes", "generate_recommendations"],
    )

    dumped = response.model_dump()

    assert dumped["no_solution_reason"] is None
    assert dumped["degraded"] is False
    assert dumped["degradations"] == []
    assert dumped["trace_id"] is None
    assert RecommendResponse.model_validate(dumped) == response
