"""T1.6 建索引脚本：纯逻辑单测 + 真库集成测试（事务回滚，不留假向量）。

注意：集成测试**各自创建独立 engine**，不用 ``infra.db`` 的全局单例 ——
pytest-asyncio 每个测试一个事件循环，全局连接池里的连接绑死旧 loop 会报
「Event loop is closed」。
"""

from __future__ import annotations

import asyncio

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from core.config import get_settings
from infra.tables import EMBEDDING_DIM
from scripts.build_index import (
    IndexRecord,
    _assert_dimension,
    embed_in_chunks,
    load_card_records,
    load_step_records,
    update_steps,
    upsert_cards,
)


class FakeEmbedder:
    """按文档批内序号生成 1024 维向量（不用真模型，不联网）。"""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [[float(index)] * EMBEDDING_DIM for index, _ in enumerate(texts)]


# ------------------------------------------------------------------ 纯逻辑


async def test_embed_in_chunks_preserves_order_and_batches() -> None:
    embedder = FakeEmbedder()
    records = [IndexRecord(key=object(), text=f"d{i}") for i in range(5)]  # type: ignore[arg-type]

    vectors = await embed_in_chunks(embedder, records, batch_size=2, label="x")

    assert [len(call) for call in embedder.calls] == [2, 2, 1]
    assert len(vectors) == 5
    # 与 records 顺序严格对应：首批第 0 行、次批第 1 行
    assert vectors[0] == [0.0] * EMBEDDING_DIM
    assert vectors[3] == [1.0] * EMBEDDING_DIM


def test_assert_dimension_rejects_mismatch() -> None:
    with pytest.raises(ValueError):
        _assert_dimension([[1.0, 2.0]])


# ------------------------------------------------------------------ 集成


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
async def test_card_index_roundtrip_in_rolled_back_transaction() -> None:
    import sqlalchemy as sa

    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            try:
                cards = await load_card_records(conn, limit=3)
                assert len(cards) == 3
                # 卡片文档首行是菜名；食材段来自 recipe_ingredients.name_raw
                assert all(record.text.split("\n", 1)[0] for record in cards)

                embedder = FakeEmbedder()
                vectors = await embed_in_chunks(embedder, cards, batch_size=2, label="card")
                await upsert_cards(conn, cards, vectors)

                for record in cards:
                    dims, tsv_length = (
                        await conn.execute(
                            sa.text(
                                "select vector_dims(embedding), length(tsv::text) "
                                "from recipe_embeddings where recipe_id = :rid"
                            ),
                            {"rid": str(record.key)},
                        )
                    ).one()
                    assert dims == 1024
                    assert tsv_length > 0  # tsv 非空：分词确实写进去了
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()


@requires_db
async def test_step_index_roundtrip_in_rolled_back_transaction() -> None:
    import sqlalchemy as sa

    engine = create_async_engine(get_settings().database_url)
    try:
        async with engine.connect() as conn:
            transaction = await conn.begin()
            try:
                steps = await load_step_records(conn, limit=4)
                assert len(steps) == 4
                assert all(record.text for record in steps)

                embedder = FakeEmbedder()
                vectors = await embed_in_chunks(embedder, steps, batch_size=2, label="step")
                await update_steps(conn, steps, vectors)

                for record in steps:
                    dims = (
                        await conn.execute(
                            sa.text("select vector_dims(embedding) from recipe_steps where id = :sid"),
                            {"sid": str(record.key)},
                        )
                    ).scalar()
                    assert dims == 1024
            finally:
                await transaction.rollback()
    finally:
        await engine.dispose()
