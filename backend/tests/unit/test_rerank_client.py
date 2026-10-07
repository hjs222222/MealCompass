"""T1.7 Rerank 双通道：先写测试。"""

from __future__ import annotations

import json

import httpx
import pytest

from domain.ports import RerankClient
from infra.rerank_client import FallbackRerank, LocalRerank, RemoteRerank


class FakeRerank:
    def __init__(self, *, fail: bool = False, model: str = "fake") -> None:
        self.model = model
        self.calls: list[tuple[str, list[str], int]] = []
        self._fail = fail

    async def rerank(self, query: str, documents: list[str], top_k: int = 10) -> list[tuple[int, float]]:
        self.calls.append((query, list(documents), top_k))
        if self._fail:
            raise RuntimeError("remote down")
        return [(index, 1.0 - index / 10) for index in range(min(top_k, len(documents)))]


def make_remote(handler, **kwargs) -> RemoteRerank:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return RemoteRerank(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="BAAI/bge-reranker-v2-m3",
        client=client,
        **kwargs,
    )


# ------------------------------------------------------------------ 远程客户端


async def test_remote_rerank_sends_expected_body_and_parses_scores() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/rerank")
        body = json.loads(request.content)
        assert body["model"] == "BAAI/bge-reranker-v2-m3"
        assert body["query"] == "番茄炒蛋"
        assert body["top_n"] == 2
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 2, "relevance_score": 0.99},
                    {"index": 0, "relevance_score": 0.01},
                ]
            },
        )

    hits = await make_remote(handler).rerank("番茄炒蛋", ["红烧肉", "番茄汤", "西红柿炒鸡蛋"], top_k=2)

    assert hits == [(2, 0.99), (0, 0.01)]


async def test_remote_rerank_sorts_by_score_descending() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.10},
                    {"index": 2, "relevance_score": 0.90},
                ]
            },
        )

    hits = await make_remote(handler).rerank("q", ["a", "b", "c"], top_k=2)

    assert [index for index, _ in hits] == [2, 1]


async def test_remote_rerank_raises_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "rate limited"})

    with pytest.raises(httpx.HTTPStatusError):
        await make_remote(handler).rerank("q", ["a"])


async def test_remote_rerank_without_documents_short_circuits() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("空文档不应该发请求")

    assert await make_remote(handler).rerank("q", []) == []


def test_remote_rerank_satisfies_port() -> None:
    assert isinstance(
        RemoteRerank(api_key="k", base_url="https://example.test/v1", model="BAAI/bge-reranker-v2-m3"),
        RerankClient,
    )


# ------------------------------------------------------------------ 降级策略


async def test_fallback_uses_primary_when_healthy() -> None:
    primary = FakeRerank()
    local = FakeRerank(model="local")
    client = FallbackRerank(primary, local)

    hits = await client.rerank("q", ["a", "b"], top_k=2)

    assert hits == [(0, 1.0), (1, 0.9)]
    assert client.last_provider == "remote"
    assert client.degraded_count == 0
    assert local.calls == []


async def test_fallback_switches_to_local_on_failure() -> None:
    client = FallbackRerank(FakeRerank(fail=True), FakeRerank(model="local"))

    hits = await client.rerank("q", ["a", "b"], top_k=1)

    assert hits == [(0, 1.0)]
    assert client.last_provider == "local"
    assert client.degraded_count == 1
    assert client.last_error is not None and "remote down" in client.last_error


async def test_fallback_raises_when_local_unavailable() -> None:
    client = FallbackRerank(FakeRerank(fail=True), None)

    with pytest.raises(RuntimeError, match="remote down"):
        await client.rerank("q", ["a"])


# ------------------------------------------------------------------ 本地实现


async def test_local_rerank_uses_injected_encoder_and_keeps_original_indices() -> None:
    class FakeEncoder:
        def predict(self, pairs):  # noqa: ANN001
            assert pairs == [("q", "甲"), ("q", "乙"), ("q", "丙")]
            return [0.2, 0.9, 0.5]

    hits = await LocalRerank(model="fake", encoder_loader=FakeEncoder).rerank("q", ["甲", "乙", "丙"], top_k=2)

    assert hits == [(1, 0.9), (2, 0.5)]


def test_local_rerank_reports_missing_dependency_clearly() -> None:
    client = LocalRerank(model="BAAI/bge-reranker-v2-m3", encoder_loader=lambda: None)
    assert client.model == "BAAI/bge-reranker-v2-m3"


def test_build_rerank_client_prefers_remote() -> None:
    from core.config import get_settings
    from infra.rerank_client import build_rerank_client

    client = build_rerank_client()

    assert isinstance(client, FallbackRerank)
    assert client.model == get_settings().reranker_model
    assert client.last_provider is None
    assert client.degraded_count == 0
