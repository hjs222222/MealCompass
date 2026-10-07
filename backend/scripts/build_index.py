"""双层向量索引构建（T1.6 / T1.12）：卡片级 + 步骤级 embedding 与 tsv 入库。

管线（幂等，可重复跑，全量重算）::

    PostgreSQL ──读取──▶ rag.chunking 构造文档 ──▶ EmbeddingClient（远程优先/本地兜底）
             ──写回──▶ recipe_embeddings(embedding, tsv) / recipe_steps(embedding)

- 卡片文档：菜名 + 简介 + 食材原文（`rag.chunking.build_card_document`）。
- 步骤文档：步骤原文（`rag.chunking.build_step_document`）。
- ``tsv``：jieba 分词后空格拼接，用 ``to_tsvector('simple', ...)`` 生成
  （官方 pgvector 镜像没有 zhparser；与 BM25 共用 `rag.tokenization`，词项一致）。

用法（在 ``backend/`` 下）::

    .venv\\Scripts\\python.exe -m scripts.build_index                # 两层全量
    .venv\\Scripts\\python.exe -m scripts.build_index --layer card   # 只建卡片
    .venv\\Scripts\\python.exe -m scripts.build_index --limit 5      # 冒烟
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# 允许 `python scripts/build_index.py` 直接运行
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sqlalchemy as sa  # noqa: E402
from pgvector.sqlalchemy import Vector  # noqa: E402
from sqlalchemy.dialects.postgresql import REGCONFIG  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncConnection  # noqa: E402

from infra.db import get_engine  # noqa: E402
from infra.embedding_client import build_embedding_client  # noqa: E402
from infra.tables import (  # noqa: E402
    EMBEDDING_DIM,
    recipe_embeddings,
    recipe_ingredients,
    recipe_steps,
    recipes,
)
from rag.chunking import build_card_document, build_step_document  # noqa: E402
from rag.tokenization import tokenize_joined  # noqa: E402

DEFAULT_BATCH_SIZE = 64  # 每块送 embedding 的文档数；RemoteEmbedding 内部还会再拆 HTTP 批次


@dataclass(frozen=True)
class IndexRecord:
    """一条待入库文档：``key`` 是写回时的主键（卡片=recipe_id，步骤=step_id）。"""

    key: uuid.UUID
    text: str


# --------------------------------------------------------------------- 读取


async def load_card_records(conn: AsyncConnection, limit: int | None = None) -> list[IndexRecord]:
    """从库中拼卡片文档。食材取 ``recipe_ingredients.name_raw``（关联表里只有食材，厨具已在 seed 时排除）。"""
    statement = (
        sa.select(
            recipes.c.id,
            recipes.c.name,
            recipes.c.description,
            sa.func.coalesce(sa.func.array_agg(recipe_ingredients.c.name_raw), sa.text("ARRAY[]::text[]")),
        )
        .select_from(recipes.outerjoin(recipe_ingredients, recipe_ingredients.c.recipe_id == recipes.c.id))
        .group_by(recipes.c.id)
        .order_by(recipes.c.id)
    )
    if limit is not None:
        statement = statement.limit(limit)

    records: list[IndexRecord] = []
    for recipe_id, name, description, ingredient_names in (await conn.execute(statement)).all():
        document = build_card_document(
            name=name,
            description=description,
            ingredients=[raw for raw in (ingredient_names or []) if raw],
        )
        records.append(IndexRecord(key=recipe_id, text=document))
    return records


async def load_step_records(conn: AsyncConnection, limit: int | None = None) -> list[IndexRecord]:
    statement = sa.select(recipe_steps.c.id, recipe_steps.c.content).order_by(
        recipe_steps.c.recipe_id, recipe_steps.c.step_no
    )
    if limit is not None:
        statement = statement.limit(limit)
    return [
        IndexRecord(key=step_id, text=build_step_document(content))
        for step_id, content in (await conn.execute(statement)).all()
    ]


# --------------------------------------------------------------------- 嵌入


def _assert_dimension(vectors: Sequence[Sequence[float]]) -> None:
    if vectors and len(vectors[0]) != EMBEDDING_DIM:
        raise ValueError(
            f"embedding 维度是 {len(vectors[0])}，与 schema 的 vector({EMBEDDING_DIM}) 不匹配；"
            "换模型必须全量重建索引（见 docs/CONVENTIONS.md §4.3）"
        )


async def embed_in_chunks(
    embedder: Any,
    records: Sequence[IndexRecord],
    *,
    batch_size: int,
    label: str,
) -> list[list[float]]:
    """分批调用 embedding，返回与 records 顺序严格对应的向量；每批打印进度。"""
    vectors: list[list[float]] = []
    total = len(records)
    for start in range(0, total, batch_size):
        chunk = records[start : start + batch_size]
        chunk_vectors = list(await embedder.embed([record.text for record in chunk]))
        _assert_dimension(chunk_vectors)
        vectors.extend(chunk_vectors)
        print(f"  {label}: {min(start + batch_size, total)}/{total}", flush=True)
    return vectors


# --------------------------------------------------------------------- 写回


async def upsert_cards(
    conn: AsyncConnection, records: Sequence[IndexRecord], vectors: Sequence[Sequence[float]]
) -> None:
    """``recipe_embeddings``：upsert embedding + tsv（tsv 与向量来自同一文档）。"""
    # to_tsvector 的配置名必须是 regconfig，直接传 varchar 会报 function does not exist
    simple_config = sa.cast(sa.literal("simple"), REGCONFIG)
    rows = [
        {
            "recipe_id": record.key,
            "embedding": list(vector),
            "tsv": sa.func.to_tsvector(simple_config, tokenize_joined(record.text)),
        }
        for record, vector in zip(records, vectors, strict=True)
    ]
    for start in range(0, len(rows), DEFAULT_BATCH_SIZE):
        statement = pg_insert(recipe_embeddings).values(rows[start : start + DEFAULT_BATCH_SIZE])
        statement = statement.on_conflict_do_update(
            index_elements=["recipe_id"],
            set_={"embedding": statement.excluded.embedding, "tsv": statement.excluded.tsv},
        )
        await conn.execute(statement)


async def update_steps(
    conn: AsyncConnection, records: Sequence[IndexRecord], vectors: Sequence[Sequence[float]]
) -> None:
    """``recipe_steps.embedding``：按步骤主键回填（全量重算，天然幂等）。

    executemany 的 WHERE 绑定名不能撞列名 ``id``（SQLAlchemy 保留），所以用 ``step_id``；
    SET 值显式标成 ``Vector(1024)``，走 pgvector 的绑定适配。
    """
    statement = (
        recipe_steps.update()
        .where(recipe_steps.c.id == sa.bindparam("step_id"))
        .values(embedding=sa.bindparam("embedding", type_=Vector(EMBEDDING_DIM)))
    )
    rows = [{"step_id": record.key, "embedding": list(vector)} for record, vector in zip(records, vectors, strict=True)]
    for start in range(0, len(rows), DEFAULT_BATCH_SIZE):
        await conn.execute(statement, rows[start : start + DEFAULT_BATCH_SIZE])


# --------------------------------------------------------------------- 编排


async def build_all(
    *,
    layer: str = "all",
    limit: int | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    embedder: Any | None = None,
) -> dict[str, int]:
    """建两层索引，返回各层文档数。``embedder`` 可注入（测试用假客户端）。"""
    if layer not in {"all", "card", "step"}:
        raise ValueError(f"未知 layer：{layer}")
    embedder = embedder or build_embedding_client()
    counts: dict[str, int] = {}

    try:
        async with get_engine().begin() as conn:
            if layer in {"all", "card"}:
                print("卡片级：菜名 + 简介 + 食材 → recipe_embeddings", flush=True)
                cards = await load_card_records(conn, limit)
                card_vectors = await embed_in_chunks(embedder, cards, batch_size=batch_size, label="card")
                await upsert_cards(conn, cards, card_vectors)
                counts["cards"] = len(cards)

            if layer in {"all", "step"}:
                print("步骤级：步骤原文 → recipe_steps.embedding", flush=True)
                steps = await load_step_records(conn, limit)
                step_vectors = await embed_in_chunks(embedder, steps, batch_size=batch_size, label="step")
                await update_steps(conn, steps, step_vectors)
                counts["steps"] = len(steps)
    finally:
        closer = getattr(embedder, "aclose", None)
        if closer is not None:
            await closer()

    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="构建菜谱双层向量索引（T1.6）")
    parser.add_argument("--layer", choices=["all", "card", "step"], default="all", help="建哪一层")
    parser.add_argument("--limit", type=int, default=None, help="每层只处理前 N 条（冒烟用）")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="单次 embedding 文档数")
    args = parser.parse_args(argv)

    counts = asyncio.run(build_all(layer=args.layer, limit=args.limit, batch_size=args.batch_size))
    print("索引构建完成（幂等，可重复执行）：")
    for layer_name, count in counts.items():
        print(f"  {layer_name:<8} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
