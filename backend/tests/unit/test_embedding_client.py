"""T1.7 Embedding 双通道：先写测试。

覆盖三件事：
1. 远程（SiliconFlow OpenAI 兼容）客户端的请求构造与响应解析
2. 本地兜底的可插拔与惰性加载
3. 降级策略：远程失败 → 本地，且把 provider / 降级事实记录下来供 trace 使用
"""

from __future__ import annotations

import json

import httpx
import pytest

from domain.ports import EmbeddingClient
from infra.embedding_client import FallbackEmbedding, LocalEmbedding, RemoteEmbedding


class FakeEmbedding:
    """可编程的假客户端（记录调用、可指定失败）。"""

    def __init__(self, *, dim: int = 4, fail: bool = False, model: str = "fake") -> None:
        self.model = model
        self.calls: list[list[str]] = []
        self._dim = dim
        self._fail = fail

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self._fail:
            raise RuntimeError("remote down")
        return [[float(index)] * self._dim for index, _ in enumerate(texts)]


def make_remote(handler, **kwargs) -> RemoteEmbedding:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return RemoteEmbedding(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="BAAI/bge-m3",
        client=client,
        **kwargs,
    )


# ------------------------------------------------------------------ 远程客户端


async def test_remote_embedding_parses_response_in_index_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/embeddings")
        assert json.loads(request.content)["model"] == "BAAI/bge-m3"
        # 故意乱序返回，客户端必须按 index 还原顺序
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [2.0, 2.0]},
                    {"index": 0, "embedding": [1.0, 1.0]},
                ]
            },
        )

    vectors = await make_remote(handler).embed(["甲", "乙"])

    assert vectors == [[1.0, 1.0], [2.0, 2.0]]


async def test_remote_embedding_splits_into_batches() -> None:
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        batch = json.loads(request.content)["input"]
        seen.append(len(batch))
        return httpx.Response(200, json={"data": [{"index": i, "embedding": [0.0]} for i in range(len(batch))]})

    vectors = await make_remote(handler, batch_size=2).embed(["a", "b", "c", "d", "e"])

    assert seen == [2, 2, 1]
    assert len(vectors) == 5


async def test_remote_embedding_truncates_overlong_text() -> None:
    lengths: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        lengths.extend(len(text) for text in json.loads(request.content)["input"])
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.0]}]})

    await make_remote(handler, max_chars=5).embed(["一二三四五六七八九十"])

    assert lengths == [5]


async def test_remote_embedding_raises_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "bad key"})

    with pytest.raises(httpx.HTTPStatusError):
        await make_remote(handler).embed(["甲"])


async def test_remote_embedding_retries_once_on_server_error() -> None:
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(503, json={"message": "busy"})
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})

    vectors = await make_remote(handler).embed(["甲"])

    assert attempts["n"] == 2
    assert vectors == [[1.0]]


async def test_remote_embedding_empty_input_returns_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - 不该被调用
        raise AssertionError("空输入不应该发请求")

    assert await make_remote(handler).embed([]) == []


def test_remote_embedding_satisfies_port() -> None:
    assert isinstance(
        RemoteEmbedding(api_key="k", base_url="https://example.test/v1", model="BAAI/bge-m3"),
        EmbeddingClient,
    )


# ------------------------------------------------------------------ 降级策略


async def test_fallback_uses_primary_when_healthy() -> None:
    primary = FakeEmbedding(dim=2)
    local = FakeEmbedding(dim=9, model="local")
    client = FallbackEmbedding(primary, local)

    vectors = await client.embed(["甲"])

    assert vectors == [[0.0, 0.0]]
    assert client.last_provider == "remote"
    assert client.degraded_count == 0
    assert local.calls == []


async def test_fallback_switches_to_local_and_records_degradation() -> None:
    primary = FakeEmbedding(fail=True)
    local = FakeEmbedding(dim=3, model="local")
    events: list[object] = []
    client = FallbackEmbedding(primary, local, on_event=events.append)

    vectors = await client.embed(["甲"])

    assert vectors == [[0.0, 0.0, 0.0]]
    assert client.last_provider == "local"
    assert client.degraded_count == 1
    assert client.last_error is not None and "remote down" in client.last_error
    assert events and events[0].degraded is True


async def test_fallback_raises_original_error_when_local_unavailable() -> None:
    client = FallbackEmbedding(FakeEmbedding(fail=True), None)

    with pytest.raises(RuntimeError, match="remote down"):
        await client.embed(["甲"])


async def test_fallback_counts_successful_remote_calls() -> None:
    client = FallbackEmbedding(FakeEmbedding(), FakeEmbedding())

    await client.embed(["甲"])
    await client.embed(["乙"])

    assert client.degraded_count == 0
    assert client.remote_count == 2


def test_local_embedding_reports_missing_dependency_clearly() -> None:
    """没装 sentence-transformers 时，报错要说人话，而不是 ImportError 裸奔。"""
    client = LocalEmbedding(model="BAAI/bge-m3", encoder_loader=lambda: None)

    assert client.model == "BAAI/bge-m3"


async def test_local_embedding_uses_injected_encoder() -> None:
    class FakeEncoder:
        def encode(self, texts, normalize_embeddings=True):  # noqa: ANN001, ARG002
            return [[0.5] * 3 for _ in texts]

    vectors = await LocalEmbedding(model="fake-local", encoder_loader=FakeEncoder).embed(["甲", "乙"])

    assert vectors == [[0.5, 0.5, 0.5], [0.5, 0.5, 0.5]]


# ------------------------------------------------------------------ 装配与配置


def test_build_embedding_client_prefers_remote() -> None:
    from core.config import get_settings
    from infra.embedding_client import build_embedding_client

    client = build_embedding_client()

    assert isinstance(client, FallbackEmbedding)
    assert client.model == get_settings().embedding_model
    assert client.last_provider is None  # 还没调用过
    assert client.degraded_count == 0


def test_embedding_key_falls_back_to_llm_key() -> None:
    from core.config import Settings

    settings = Settings(
        llm_api_key="llm-key",
        llm_base_url="https://llm.test/v1",
        embedding_api_key=None,
        embedding_base_url=None,
    )

    assert settings.embedding_key == "llm-key"
    assert settings.embedding_url == "https://llm.test/v1"


def test_embedding_key_prefers_explicit_value() -> None:
    from core.config import Settings

    settings = Settings(
        llm_api_key="llm-key",
        llm_base_url="https://llm.test/v1",
        embedding_api_key="emb-key",
        embedding_base_url="https://emb.test/v1",
    )

    assert settings.embedding_key == "emb-key"
    assert settings.embedding_url == "https://emb.test/v1"
