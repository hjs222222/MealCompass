"""T1.7 真连 SiliconFlow 的冒烟测试（没有 key 或网络不通时自动跳过）。

验证的是「协议真的对接上了」：维度对不对、排序对不对。
"""

from __future__ import annotations

import httpx
import pytest

from core.config import get_settings

settings = get_settings()
requires_key = pytest.mark.skipif(not settings.llm_api_key, reason=".env 里没有 LLM_API_KEY，跳过真实远程调用")


@requires_key
async def test_remote_embedding_returns_1024_dim_vectors() -> None:
    """维度必须与 schema 的 vector(1024) 对齐，否则索引直接建不起来。"""
    from infra.embedding_client import RemoteEmbedding

    client = RemoteEmbedding(
        api_key=settings.llm_api_key or "",
        base_url=settings.llm_base_url,
        model=settings.embedding_model,
    )
    try:
        vectors = await client.embed(["番茄炒蛋怎么做", "西红柿鸡蛋的做法"])
    finally:
        await client.aclose()

    assert len(vectors) == 2
    assert len(vectors[0]) == 1024


@requires_key
async def test_remote_rerank_puts_the_right_recipe_first() -> None:
    from infra.rerank_client import RemoteRerank

    client = RemoteRerank(
        api_key=settings.llm_api_key or "",
        base_url=settings.llm_base_url,
        model=settings.reranker_model,
    )
    try:
        hits = await client.rerank(
            "番茄炒蛋",
            ["红烧肉的家常做法", "西红柿炒鸡蛋", "番茄鸡蛋汤"],
            top_k=3,
        )
    finally:
        await client.aclose()

    assert hits[0][0] == 1  # 西红柿炒鸡蛋
    assert hits[0][1] > hits[-1][1]


@requires_key
async def test_fallback_client_survives_a_broken_remote_endpoint() -> None:
    """远程打不通时，没有本地模型就应该老实报错，而不是返回空向量糊弄上游。"""
    from infra.embedding_client import FallbackEmbedding, RemoteEmbedding

    broken = RemoteEmbedding(
        api_key=settings.llm_api_key or "",
        base_url="https://127.0.0.1:9/v1",  # 必然连不上
        model=settings.embedding_model,
        timeout=2.0,
    )
    client = FallbackEmbedding(broken, None)
    try:
        with pytest.raises(httpx.TransportError):  # 连不上就该抛连接类异常，而不是返回空向量
            await client.embed(["番茄炒蛋"])
    finally:
        await broken.aclose()
