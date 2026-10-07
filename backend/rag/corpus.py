"""卡片文档语料（T1.8）：BM25 关键词检索的内存语料与加载。

与向量通道共用**同一份卡片文档**（`rag.chunking.build_card_document`）：
库里 ``recipe_embeddings.embedding`` embed 的就是这份文本，BM25 检索的也是它，
两个通道召回结果才可解释、可融合。

- `load_card_documents(conn)`：从库中拼卡片文档（与 `scripts/build_index.py` 共用）。
- `CardCorpus`：持 doc_id → 菜名映射 + BM25 索引；纯同步，可离线单测。
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from infra.tables import recipe_ingredients, recipes
from rag.bm25_index import BM25Index
from rag.chunking import build_card_document
from rag.tokenization import tokenize


@dataclass(frozen=True)
class CardDocument:
    """一张卡片文档：``key`` 是 recipe_id，``text`` 是 embed/检索用的同一份文本。"""

    key: UUID
    name: str
    text: str


async def load_card_documents(conn: AsyncConnection, limit: int | None = None) -> list[CardDocument]:
    """从库中拼卡片文档（菜名 + 简介 + 食材原文，按序去重）。"""
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

    documents: list[CardDocument] = []
    for recipe_id, name, description, ingredient_names in (await conn.execute(statement)).all():
        text = build_card_document(
            name=name,
            description=description,
            ingredients=[raw for raw in (ingredient_names or []) if raw],
        )
        documents.append(CardDocument(key=recipe_id, name=name, text=text))
    return documents


class CardCorpus:
    """内存 BM25 语料：doc_id → 菜名 + 卡片文本（供重排取原文）。"""

    def __init__(self, documents: list[CardDocument]) -> None:
        self._doc_ids = [str(document.key) for document in documents]
        self._names = {str(document.key): document.name for document in documents}
        self._texts = {str(document.key): document.text for document in documents}
        self._bm25 = BM25Index(self._doc_ids, [tokenize(document.text) for document in documents])

    @property
    def doc_ids(self) -> list[str]:
        return list(self._doc_ids)

    def name_of(self, doc_id: str) -> str | None:
        return self._names.get(doc_id)

    def text_of(self, doc_id: str) -> str | None:
        """卡片索引文本（菜名+简介+食材），重排时作为 query 的配对文档。"""
        return self._texts.get(doc_id)

    def search(self, query: str, top_n: int, allowed_ids: set[str] | None = None) -> list[tuple[str, float]]:
        """返回 ``[(recipe_id, bm25分)]``，可限制在 SQL 产生的允许 ID 集合内。"""
        return self._bm25.search(tokenize(query), top_n, allowed_ids)
