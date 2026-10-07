"""混合检索（T1.8 / PRD F-B3）：向量 Top50 + BM25 Top50 → RRF → Top-k。

管线::

    查询 ──embedding──▶ pgvector 余弦 Top50（recipe_embeddings）
       ├─rag.chunking 卡片文档──▶ CardCorpus(BM25+jieba) Top50
       └──────────── RRF 融合（k=60）──▶ Top-k 候选（RecipeCandidate，带真实 recipe_id）

- 两个通道都只返回**排名**进 RRF，不混合原始分数（量纲不同）。
- 硬约束下推（T1.10）尚未实现：传入非空 ``filters`` 会抛 ``NotImplementedError``，
  契约先行（`domain/ports.py` 的 `Retriever`）。
- 可观测：整个检索记为一个 ``retriever`` 观察（`SpanName.RETRIEVE_RECIPES`），
  metadata 里带通道命中数与是否降级；embedding 降级状态从 ``last_provider`` 读取。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.models.retrieval import HardFilters, RecipeCandidate
from infra.db import get_engine
from infra.observability import ObservationType, SpanName, traced
from infra.tables import recipe_embeddings, recipes
from rag.corpus import CardCorpus
from rag.fusion import DEFAULT_RRF_K, reciprocal_rank_fusion

VECTOR_TOP_N = 50  # 向量通道召回数（PRD F-B3：Top 50）
BM25_TOP_N = 50  # 关键词通道召回数（PRD F-B3：Top 50）


class HybridRetriever:
    """实现 `domain/ports.Retriever` 的混合检索器。"""

    def __init__(
        self,
        embedder: Any,
        corpus: CardCorpus,
        *,
        engine: AsyncEngine | None = None,
        vector_top_n: int = VECTOR_TOP_N,
        bm25_top_n: int = BM25_TOP_N,
        rrf_k: int = DEFAULT_RRF_K,
    ) -> None:
        self._embedder = embedder
        self._corpus = corpus
        self._engine = engine or get_engine()
        self._vector_top_n = max(1, vector_top_n)
        self._bm25_top_n = max(1, bm25_top_n)
        self._rrf_k = max(1, rrf_k)

    async def search(
        self,
        query: str,
        filters: HardFilters | None = None,
        top_k: int = 10,
    ) -> list[RecipeCandidate]:
        """混合检索主入口；``top_k`` 默认 10（PRD F-B3：Top 10 进入重排）。"""
        cleaned = (query or "").strip()
        if not cleaned:
            return []
        if filters is not None and not filters.is_empty():
            raise NotImplementedError("硬约束下推属 T1.10，尚未实现")

        with traced(
            SpanName.RETRIEVE_RECIPES,
            as_type=ObservationType.RETRIEVER,
            input={"query": cleaned, "top_k": top_k},
        ) as span:
            query_vector = (await self._embedder.embed([cleaned]))[0]

            vector_hits = await self._vector_search(query_vector)
            bm25_hits = self._corpus.search(cleaned, self._bm25_top_n)

            fused = reciprocal_rank_fusion(
                {
                    "vector": [recipe_id for recipe_id, _ in vector_hits],
                    "bm25": [recipe_id for recipe_id, _ in bm25_hits],
                },
                k=self._rrf_k,
                top_n=top_k,
            )
            candidates = [
                RecipeCandidate(
                    recipe_id=recipe_id,
                    name=self._corpus.name_of(recipe_id) or "",
                    score=score,
                    rank=rank,
                    sources=channels,
                )
                for rank, (recipe_id, score, channels) in enumerate(fused, start=1)
            ]

            span.update(
                output={
                    "recipe_ids": [candidate.recipe_id for candidate in candidates],
                    "vector_hits": len(vector_hits),
                    "bm25_hits": len(bm25_hits),
                    "degraded": getattr(self._embedder, "last_provider", None) == "local",
                }
            )
            return candidates

    async def _vector_search(self, query_vector: Sequence[float]) -> list[tuple[str, float]]:
        """pgvector 余弦 Top-N（HNSW `vector_cosine_ops` 索引生效）。"""
        statement = (
            sa.select(recipes.c.id, recipe_embeddings.c.embedding.cosine_distance(query_vector).label("distance"))
            .join(recipes, recipes.c.id == recipe_embeddings.c.recipe_id)
            .order_by("distance")
            .limit(self._vector_top_n)
        )
        async with self._engine.connect() as conn:
            rows = (await conn.execute(statement)).all()
        return [(str(row.id), float(row.distance)) for row in rows]
