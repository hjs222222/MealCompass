"""混合检索（T1.8 / PRD F-B3）：向量 Top50 + BM25 Top50 → RRF → Top-k。

管线::

    查询 ──embedding──▶ pgvector 余弦 Top50（recipe_embeddings）
       ├─rag.chunking 卡片文档──▶ CardCorpus(BM25+jieba) Top50
       └──────────── RRF 融合（k=60）──▶ Top-k 候选（RecipeCandidate，带真实 recipe_id）

- 两个通道都只返回**排名**进 RRF，不混合原始分数（量纲不同）。
- 硬约束先构造 SQL 允许 recipe-id universe，再约束两个召回通道。
- 可观测：整个检索记为一个 ``retriever`` 观察（`SpanName.RETRIEVE_RECIPES`），
  metadata 里带通道命中数与是否降级；embedding 降级状态从 ``last_provider`` 读取。
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.ingredients import IngredientDictionary, clean_name
from domain.models.retrieval import HardFilters, RecipeCandidate
from infra.db import get_engine
from infra.ingredient_dict import load_dictionary
from infra.observability import ObservationType, SpanName, traced
from infra.tables import ingredient_aliases, ingredients, recipe_embeddings, recipe_ingredients, recipes
from rag.corpus import CardCorpus
from rag.fusion import DEFAULT_RRF_K, reciprocal_rank_fusion
from rag.reranker import rerank_candidates

VECTOR_TOP_N = 50  # 向量通道召回数（PRD F-B3：Top 50）
BM25_TOP_N = 50  # 关键词通道召回数（PRD F-B3：Top 50）


@lru_cache(maxsize=1)
def _ingredient_dictionary() -> IngredientDictionary:
    return load_dictionary()


def _exclusion_patterns(excluded: str) -> tuple[str, ...]:
    """Expand a forbidden ingredient to its known names before SQL filtering."""
    name = clean_name(excluded).lower()
    if not name:
        return ()
    dictionary = _ingredient_dictionary()
    entry = dictionary.resolve(name)
    terms = [name]
    if entry:
        terms.append(entry.name)
        other_names = {
            clean_name(variant).lower()
            for other in dictionary.entries()
            if other.name != entry.name
            for variant in (other.name, *other.aliases)
        }
        # 「里脊」也在「牛里脊」中；不把这种有明确其他食材归属的短别名展开成包含匹配。
        terms.extend(
            alias for alias in entry.aliases if not any(clean_name(alias).lower() in other for other in other_names)
        )
    patterns = []
    for term in dict.fromkeys(terms):
        escaped = term.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        patterns.append(f"%{escaped}%")
    return tuple(patterns)


class HybridRetriever:
    """实现 `domain/ports.Retriever` 的混合检索器。

    ``reranker`` 可选（T1.9）：提供则 RRF Top10 后交给重排（失败降级回 RRF 顺序）；
    不提供则保持 RRF 顺序返回（纯 T1.8 行为）。
    """

    def __init__(
        self,
        embedder: Any,
        corpus: CardCorpus,
        *,
        reranker: Any | None = None,
        engine: AsyncEngine | None = None,
        vector_top_n: int = VECTOR_TOP_N,
        bm25_top_n: int = BM25_TOP_N,
        rrf_k: int = DEFAULT_RRF_K,
    ) -> None:
        self._embedder = embedder
        self._corpus = corpus
        self._reranker = reranker
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
        with traced(
            SpanName.RETRIEVE_RECIPES,
            as_type=ObservationType.RETRIEVER,
            input={
                "query": cleaned,
                "top_k": top_k,
                "has_hard_filters": filters is not None and not filters.is_empty(),
            },
        ) as span:
            allowed_ids = await self._allowed_recipe_ids(filters)
            if allowed_ids is not None and not allowed_ids:
                span.update(
                    output={"recipe_ids": [], "vector_hits": 0, "bm25_hits": 0, "reranked": False, "degraded": False}
                )
                return []

            query_vector = (await self._embedder.embed([cleaned]))[0]

            vector_hits = await self._vector_search(query_vector, allowed_ids)
            # BM25 scores the small in-memory corpus first, then applies the SQL-derived
            # allowed universe; it must not inherit the vector channel's Top-N boundary.
            bm25_hits = self._corpus.search(cleaned, self._bm25_top_n, allowed_ids)

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

            reranked = self._reranker is not None
            if reranked and candidates:
                candidates = await rerank_candidates(cleaned, candidates, self._reranker, corpus=self._corpus)

            degraded = (
                any(candidate.degraded for candidate in candidates)
                or getattr(self._embedder, "last_provider", None) == "local"
            )

            span.update(
                output={
                    "recipe_ids": [candidate.recipe_id for candidate in candidates],
                    "vector_hits": len(vector_hits),
                    "bm25_hits": len(bm25_hits),
                    "reranked": reranked,
                    "degraded": degraded,
                }
            )
            return candidates

    def _allowed_recipe_statement(self, filters: HardFilters | None) -> sa.Select | None:
        """Build the SQL statement defining the complete hard-filter recipe universe."""
        if filters is None or filters.is_empty():
            return None
        conditions: list[Any] = []
        if filters.max_time_minutes is not None:
            # Strict safety: a time cap only admits recipes with known duration within the cap.
            conditions.extend(
                [
                    recipes.c.time_minutes.is_not(None),
                    recipes.c.time_minutes <= filters.max_time_minutes,
                ]
            )
        if filters.category:
            conditions.append(recipes.c.category == filters.category)
        if filters.tools_available:
            available = sa.cast(filters.tools_available, JSONB)
            conditions.append(recipes.c.tools.op("<@")(available))
        for excluded in filters.excluded_ingredients:
            patterns = _exclusion_patterns(excluded)
            if not patterns:
                continue
            # 菜名兜住缺失/未映射的原料行；原料原文及标准名兜住名称不同的衍生产物。
            title_match = sa.or_(*(sa.func.lower(recipes.c.name).like(pattern, escape="\\") for pattern in patterns))
            match = sa.or_(
                *(
                    sa.func.lower(column).like(pattern, escape="\\")
                    for column in (ingredients.c.name, recipe_ingredients.c.name_raw, ingredient_aliases.c.alias)
                    for pattern in patterns
                )
            )
            exists = (
                sa.select(1)
                .select_from(
                    recipe_ingredients.join(
                        ingredients, recipe_ingredients.c.ingredient_id == ingredients.c.id, isouter=True
                    ).join(ingredient_aliases, ingredient_aliases.c.ingredient_id == ingredients.c.id, isouter=True)
                )
                .where(recipe_ingredients.c.recipe_id == recipes.c.id, match)
                .exists()
            )
            conditions.append(~sa.or_(title_match, exists))
        return sa.select(recipes.c.id).where(*conditions)

    async def _allowed_recipe_ids(self, filters: HardFilters | None) -> set[str] | None:
        """Build the SQL hard-filter universe; None preserves the legacy unfiltered path."""
        statement = self._allowed_recipe_statement(filters)
        if statement is None:
            return None
        async with self._engine.connect() as conn:
            rows = (await conn.execute(statement)).all()
        return {str(row.id) for row in rows}

    async def _vector_search(
        self, query_vector: Sequence[float], allowed_ids: set[str] | None = None
    ) -> list[tuple[str, float]]:
        """pgvector cosine Top-N, optionally restricted to the SQL-derived universe."""
        statement = (
            sa.select(recipes.c.id, recipe_embeddings.c.embedding.cosine_distance(query_vector).label("distance"))
            .join(recipes, recipes.c.id == recipe_embeddings.c.recipe_id)
            .order_by("distance")
            .limit(self._vector_top_n)
        )
        if allowed_ids is not None:
            statement = statement.where(recipes.c.id.in_(list(allowed_ids)))
        async with self._engine.connect() as conn:
            rows = (await conn.execute(statement)).all()
        return [(str(row.id), float(row.distance)) for row in rows]
