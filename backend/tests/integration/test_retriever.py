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
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from core.config import get_settings
from domain.models.retrieval import HardFilters
from infra.tables import ingredients, recipes
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
async def test_hard_filter_sql_semantics_against_postgres() -> None:
    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.begin() as conn:
            ingredient_id = await conn.scalar(
                sa.select(ingredients.c.id).where(sa.func.lower(ingredients.c.name) == "虾").limit(1)
            )
            if ingredient_id is None:
                pytest.skip("测试数据库缺少虾标准食材")
            rows = (
                await conn.execute(
                    sa.select(recipes.c.id, recipes.c.time_minutes, recipes.c.tools)
                    .where(recipes.c.time_minutes.is_(None))
                    .limit(1)
                )
            ).all()
            assert rows, "time_minutes=NULL fixture row is required"
            null_id = str(rows[0].id)
            allowed_tools = await conn.scalar(
                sa.select(recipes.c.id).where(recipes.c.tools.op("<@")(["炒锅"])).limit(1)
            )
            assert allowed_tools is not None
            corpus = CardCorpus(await load_card_documents(conn))
            if not corpus.doc_ids:
                pytest.skip("测试数据库没有可用菜谱语料")
            retriever = HybridRetriever(embedder=FixedVectorEmbedder([0.0] * 1024), corpus=corpus, engine=engine)
            assert null_id not in await retriever._allowed_recipe_ids(HardFilters(max_time_minutes=30))
            tools_statement = retriever._allowed_recipe_statement(HardFilters(tools_available=["炒锅"]))
            tool_ids = {str(row.id) for row in (await conn.execute(tools_statement)).all()}
            assert str(allowed_tools) in tool_ids
    finally:
        await engine.dispose()


@requires_db
async def test_retriever_applies_hard_filters_to_sql_universe() -> None:
    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.connect() as conn:
            corpus = CardCorpus(await load_card_documents(conn))
        if not corpus.doc_ids:
            pytest.skip("测试数据库没有可用菜谱语料")
        retriever = HybridRetriever(embedder=FixedVectorEmbedder([0.0] * 1024), corpus=corpus, engine=engine)
        filters = HardFilters(excluded_ingredients=["虾"])
        allowed_ids = await retriever._allowed_recipe_ids(filters)
        assert allowed_ids is not None
        assert allowed_ids
        candidates = await retriever.search("西红柿炒鸡蛋", filters=filters)
        assert all(candidate.recipe_id in allowed_ids for candidate in candidates)
        assert all(candidate.recipe_id in corpus.doc_ids for candidate in candidates)
    finally:
        await engine.dispose()


@requires_db
async def test_exclusions_reject_reported_pork_pumpkin_and_tomato_recipes() -> None:
    engine = create_async_engine(get_settings().database_url)
    cases = {
        "猪肉": {"香煎五花肉", "咕噜肉", "回锅肉", "白菜猪肉炖粉条", "猪肉烩酸菜"},
        "南瓜": {"山药南瓜炖鸡汤"},
        "番茄": {"番茄红酱"},
        "西红柿": {"番茄红酱"},
        "土豆": {"炸薯条"},
    }
    try:
        async with engine.connect() as conn:
            rows = (await conn.execute(sa.select(recipes.c.id, recipes.c.name))).all()
        by_name = {row.name: str(row.id) for row in rows}
        if any(name not in by_name for names in cases.values() for name in names):
            pytest.skip("测试数据库缺少事故菜谱")
        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever._engine = engine
        for excluded, forbidden_names in cases.items():
            allowed = await retriever._allowed_recipe_ids(HardFilters(excluded_ingredients=[excluded]))
            assert allowed is not None
            assert not {by_name[name] for name in forbidden_names} & allowed, excluded
            if excluded == "猪肉" and "小炒黄牛肉" in by_name:
                assert by_name["小炒黄牛肉"] in allowed
    finally:
        await engine.dispose()


async def test_retriever_empty_query_returns_empty() -> None:
    retriever = HybridRetriever(embedder=FixedVectorEmbedder([0.0] * 1024), corpus=CardCorpus([]))
    assert await retriever.search("   ") == []


class ReversingRerank:
    """把候选顺序倒过来，并记一次调用（验证重排步骤真实生效）。"""

    def __init__(self) -> None:
        self.last_provider = "remote"
        self.calls = 0

    async def rerank(self, query: str, documents: list[str], top_k: int = 10) -> list[tuple[int, float]]:
        self.calls += 1
        total = min(top_k, len(documents))
        # 反序降序给分：原最后一个文档分最高 → 返回下标逆序、分数递减
        return [(index, float(index + 1)) for index in range(total - 1, -1, -1)]


@requires_db
async def test_reranker_step_reorders_retrieval_results() -> None:
    import sqlalchemy as sa

    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            try:
                recipe_id, name, raw_embedding = (
                    await conn.execute(
                        sa.text(
                            "select r.id, r.name, e.embedding from recipes r "
                            "join recipe_embeddings e on e.recipe_id = r.id "
                            "order by length(r.name) desc limit 1"
                        )
                    )
                ).one()
                embedding = json.loads(raw_embedding) if isinstance(raw_embedding, str) else list(raw_embedding)

                corpus = CardCorpus(await load_card_documents(conn))
                reranker = ReversingRerank()
                retriever = HybridRetriever(
                    embedder=FixedVectorEmbedder(embedding),
                    corpus=corpus,
                    reranker=reranker,
                    engine=engine,
                )

                candidates = await retriever.search(name, top_k=10)

                assert reranker.calls == 1
                assert 1 <= len(candidates) <= 10
                # 重排后 rerank_score 已填、rank 严格 1..n
                assert all(candidate.rerank_score is not None for candidate in candidates)
                assert [candidate.rank for candidate in candidates] == list(range(1, len(candidates) + 1))
                # ReversingRerank 按文档逆序给分：原最后一个候选被重排到第一位
                assert candidates[0].rank == 1
                assert candidates[0].rerank_score == max(candidate.rerank_score or 0 for candidate in candidates)
                # provider=remote，未标记降级
                assert not any(candidate.degraded for candidate in candidates)
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@requires_db
async def test_reranker_failure_falls_back_to_rrf_order() -> None:
    import sqlalchemy as sa

    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            try:
                recipe_id, name, raw_embedding = (
                    await conn.execute(
                        sa.text(
                            "select r.id, r.name, e.embedding from recipes r "
                            "join recipe_embeddings e on e.recipe_id = r.id "
                            "order by length(r.name) desc limit 1"
                        )
                    )
                ).one()
                embedding = json.loads(raw_embedding) if isinstance(raw_embedding, str) else list(raw_embedding)

                corpus = CardCorpus(await load_card_documents(conn))

                class BrokenRerank:
                    last_provider = "remote"

                    async def rerank(self, query: str, documents: list[str], top_k: int = 10):
                        raise RuntimeError("remote down")

                retriever = HybridRetriever(
                    embedder=FixedVectorEmbedder(embedding),
                    corpus=corpus,
                    reranker=BrokenRerank(),
                    engine=engine,
                )
                candidates = await retriever.search(name, top_k=10)

                # 降级：候选按 RRF 原顺序返回，全部标记 degraded，rerank_score 为空
                assert 1 <= len(candidates) <= 10
                assert all(candidate.degraded for candidate in candidates)
                assert all(candidate.rerank_score is None for candidate in candidates)
                assert [candidate.rank for candidate in candidates] == list(range(1, len(candidates) + 1))
                # 目标菜仍应在 Top5（RRF 原顺序，向量通道 Top1）
                assert str(recipe_id) in [candidate.recipe_id for candidate in candidates[:5]]
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
