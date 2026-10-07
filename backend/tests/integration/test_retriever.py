"""T1.8 混合检索端到端：真库 + 注入已知向量 + 真 BM25 语料（回滚事务，不留数据）。

原理：从库中取某道菜的**真实 embedding** 作为「查询向量」，用假 embedder 返回它。
这样向量通道必然把这道菜排到最近；BM25 通道用真实卡片语料（jieba 分词）。
两个通道 Top50 → RRF → Top10，验证整条管线。
"""

from __future__ import annotations

import asyncio
import json

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from core.config import get_settings
from domain.models.retrieval import HardFilters
from rag.corpus import CardCorpus, load_card_documents
from rag.retriever import HybridRetriever


class FixedVectorEmbedder:
    """对任意查询都返回固定向量（此处为某道菜的真实 embedding）。"""

    def __init__(self, vector: list[float]) -> None:
        self._vector = vector

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector for _ in texts]


def _dsn() -> str:
    return get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")


async def _db_available() -> bool:
    try:
        connection = await asyncio.wait_for(asyncpg.connect(_dsn()), timeout=3)
    except Exception:
        return False
    await connection.close()
    return True


DB_UP = asyncio.run(_db_available())
requires_db = pytest.mark.skipif(not DB_UP, reason="Postgres 未启动（docker compose up -d）")


@requires_db
async def test_mixed_retrieval_roundtrip() -> None:
    import sqlalchemy as sa

    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            try:
                # 取一道菜 + 它的真实 embedding
                recipe_id, name, raw_embedding = (
                    await conn.execute(
                        sa.text(
                            "select r.id, r.name, e.embedding from recipes r "
                            "join recipe_embeddings e on e.recipe_id = r.id "
                            "where r.name like '%鸡蛋%' order by length(r.name) limit 1"
                        )
                    )
                ).one()
                target_id = str(recipe_id)
                # asyncpg 未注册 pgvector codec 时把向量以字符串返回，规范化成 float list
                embedding = json.loads(raw_embedding) if isinstance(raw_embedding, str) else list(raw_embedding)

                corpus = CardCorpus(await load_card_documents(conn))
                retriever = HybridRetriever(
                    embedder=FixedVectorEmbedder(list(embedding)),
                    corpus=corpus,
                    engine=engine,
                )

                candidates = await retriever.search(name, top_k=10)

                # RRF 融合后 Top10，全带真实 recipe_id 与菜名
                assert 1 <= len(candidates) <= 10
                assert all(candidate.recipe_id for candidate in candidates)
                assert all(candidate.name for candidate in candidates)
                # 向量通道必然命中目标 → 至少一个候选的 sources 含 vector
                assert any("vector" in candidate.sources for candidate in candidates)
                # rank 严格 1..n
                assert [candidate.rank for candidate in candidates] == list(range(1, len(candidates) + 1))
                # 分数降序
                scores = [candidate.score for candidate in candidates]
                assert scores == sorted(scores, reverse=True)

                # 目标菜应该在 Top5（向量 Top1 + BM25 命中菜名，RRF 后不会掉出前 5）
                assert target_id in [candidate.recipe_id for candidate in candidates[:5]]
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@requires_db
async def test_retriever_rejects_non_empty_filters_until_t1_10() -> None:
    engine = create_async_engine(get_settings().database_url)
    try:
        retriever = HybridRetriever(embedder=FixedVectorEmbedder([0.0] * 1024), corpus=CardCorpus([]), engine=engine)
        with pytest.raises(NotImplementedError):
            await retriever.search("西红柿炒鸡蛋", filters=HardFilters(excluded_ingredients=["虾"]))
    finally:
        await engine.dispose()


async def test_retriever_empty_query_returns_empty() -> None:
    retriever = HybridRetriever(embedder=FixedVectorEmbedder([0.0] * 1024), corpus=CardCorpus([]))
    assert await retriever.search("   ") == []
