"""检索真实冒烟（T1.8/T1.9）：真查询 → SiliconFlow embedding → 混合检索 → Top10。

用法::

    cd backend
    .venv\\Scripts\\python.exe -m scripts.smoke_retrieval            # 纯混合检索（RRF 顺序）
    .venv\\Scripts\\python.exe -m scripts.smoke_retrieval --rerank   # + bge-reranker 重排（带延迟）

默认不带 ``--rerank`` 时不连重排接口，避免每次冒烟多花一次远程调用。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infra.db import get_engine
from infra.embedding_client import build_embedding_client
from infra.rerank_client import build_rerank_client
from rag.corpus import CardCorpus, load_card_documents
from rag.retriever import HybridRetriever

QUERIES = ["酸甜开胃的家常菜", "怎么做勾芡", "适合冬天的暖胃汤"]


def _format(candidates: list, reranked: bool) -> None:
    for candidate in candidates:
        score_field = f"rerank={candidate.rerank_score:.4f}" if reranked else f"rrf={candidate.score:.4f}"
        degraded = " [degraded]" if candidate.degraded else ""
        print(f"  #{candidate.rank} {candidate.name}  {score_field}  channels={','.join(candidate.sources)}{degraded}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="检索冒烟")
    parser.add_argument("--rerank", action="store_true", help="接入 bge-reranker-v2-m3 重排并打印延迟")
    args = parser.parse_args()

    embedder = build_embedding_client()
    reranker = build_rerank_client() if args.rerank else None
    engine = get_engine()
    try:
        async with engine.connect() as conn:
            corpus = CardCorpus(await load_card_documents(conn))
        retriever = HybridRetriever(embedder=embedder, corpus=corpus, reranker=reranker, engine=engine)

        for query in QUERIES:
            started = time.perf_counter()
            candidates = await retriever.search(query, top_k=10)
            elapsed_ms = (time.perf_counter() - started) * 1000
            print(f"\n查询：{query}  （检索+重排 {elapsed_ms:.0f}ms）")
            _format(candidates, reranked=args.rerank)
            if reranker is not None:
                print(
                    f"  reranker provider={reranker.last_provider} remote={reranker.remote_count} "
                    f"degraded={reranker.degraded_count}"
                )
    finally:
        closer = getattr(embedder, "aclose", None)
        if closer is not None:
            await closer()
        if reranker is not None:
            rerank_closer = getattr(reranker, "aclose", None)
            if rerank_closer is not None:
                await rerank_closer()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
