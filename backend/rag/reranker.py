"""重排编排（T1.9 / PRD F-B4）：对 RRF 融合后的候选做 bge-reranker 二次排序。

- 输入：`HybridRetriever.search` 产出的候选（RRF 顺序）。
- 文档文本用 `CardCorpus.text_of`（与向量/BM25 同一份卡片文本），缺失时用菜名兜底。
- **降级契约**：重排整体抛异常（远程挂了、本地也没兜底）→ 返回原 RRF 顺序，
  所有候选标记 `degraded=True`、`rerank_score=None`，绝不让检索主流程挂掉。
- provider 走了本地兜底（`last_provider == "local"`）也算降级路径，标记 degraded。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from domain.models.retrieval import RecipeCandidate
from rag.corpus import CardCorpus

logger = logging.getLogger(__name__)


async def rerank_candidates(
    query: str,
    candidates: Sequence[RecipeCandidate],
    reranker: Any,
    *,
    corpus: CardCorpus,
    top_k: int | None = None,
) -> list[RecipeCandidate]:
    """重排候选；失败时按原顺序降级返回。``top_k`` 不传则保留全部候选。"""
    if not candidates:
        return []
    effective_top_k = top_k if top_k is not None else len(candidates)
    if effective_top_k <= 0:
        return []

    documents = [corpus.text_of(candidate.recipe_id) or candidate.name for candidate in candidates]
    try:
        hits = await reranker.rerank(query, documents, effective_top_k)
    except Exception as exc:  # noqa: BLE001 - 重排绝不能拖垮检索
        logger.warning("重排失败，降级回 RRF 顺序：%s", exc)
        return [candidate.model_copy(update={"degraded": True}) for candidate in candidates]

    reranked = [
        candidates[index].model_copy(update={"rank": new_rank, "rerank_score": score})
        for new_rank, (index, score) in enumerate(hits, start=1)
    ]
    # 走了本地兜底 = 降级路径（远程失败切本地时 degraded_count 也会 +1）
    degraded = getattr(reranker, "last_provider", None) == "local"
    if degraded:
        reranked = [candidate.model_copy(update={"degraded": True}) for candidate in reranked]
    return reranked
