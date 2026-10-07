"""跨层接口（Protocol）：所有抽象集中在这里，实现在 `infra/` 与 `rag/`。

分层规则：`domain` 不依赖任何层，所以这里的 Protocol 只引用标准库与 domain 自己的类型。
改这里的签名 = 改对外契约，必须同步 `docs/ARCHITECTURE.md` §5。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from domain.models.retrieval import HardFilters, RecipeCandidate


@runtime_checkable
class EmbeddingClient(Protocol):
    """文本 → 向量。

    实现（`infra/embedding_client.py`）：`RemoteEmbedding`（SiliconFlow，远程优先）、
    `LocalEmbedding`（sentence-transformers，本地兜底）、`FallbackEmbedding`（组合二者）。
    """

    model: str

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """返回与入参**顺序严格对应**的向量列表。"""
        ...


@runtime_checkable
class RerankClient(Protocol):
    """(query, documents) → ``[(原始下标, 相关性分数)]``，按分数降序。"""

    model: str

    async def rerank(
        self,
        query: str,
        documents: Sequence[str],
        top_k: int = 10,
    ) -> list[tuple[int, float]]:
        """下标是 ``documents`` 里的原始位置，方便调用方取回原文。"""
        ...


@runtime_checkable
class Retriever(Protocol):
    """菜谱检索：混合召回 + 融合 + 重排，返回带真实 ``recipe_id`` 的候选。

    实现（`rag/retriever.py`）：向量 Top50 + BM25 Top50 → RRF → 重排 → Top-k。
    硬约束（``filters``）**下推**到召回 SQL，不在召回后过滤（PRD F-B5）。
    """

    async def search(
        self,
        query: str,
        filters: HardFilters | None = None,
        top_k: int = 10,
    ) -> list[RecipeCandidate]:
        """返回按最终相关度降序的候选；每个候选都带真实 recipe_id。"""
        ...
